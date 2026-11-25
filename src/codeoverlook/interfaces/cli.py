"""Command-line interface (CLI) for CodeOverlook."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import time
from dataclasses import asdict
from pathlib import Path

from codeoverlook.core.blocks import BlockResolver
from codeoverlook.core.coverage import TestCoverageAnalyzer
from codeoverlook.core.slicer import ContextSlicer
from codeoverlook.core.store import FactStore, FileParseResult
from codeoverlook.ingesters.python_ast import PythonASTIngester
from codeoverlook.views.html_renderer import render_atlas_html
from codeoverlook.views.mermaid import render_block_mermaid, render_coverage_mermaid


def _get_db_path(repo_root: Path) -> Path:
    return repo_root.resolve() / ".codeoverlook" / "index.db"


def _validate_repo_dir(repo_arg: str) -> Path | None:
    repo_root = Path(repo_arg).resolve()
    if not repo_root.exists() or not repo_root.is_dir():
        print(
            f"Error: repository path '{repo_root}' does not exist or is not a directory.",
            file=sys.stderr,
        )
        return None
    return repo_root


def _require_existing_db(repo_root: Path) -> Path | None:
    db_path = _get_db_path(repo_root)
    if not db_path.exists():
        print(
            f"Error: no index found at '{db_path}'. "
            f"Run `codeoverlook scan {repo_root}` first.",
            file=sys.stderr,
        )
        return None
    return db_path


def cmd_scan(args: argparse.Namespace) -> int:
    """Index (or incrementally update) a Python repository into `.codeoverlook/index.db`.

    Args:
        args: Parsed CLI arguments containing `repo` and `force`.

    Returns:
        Exit code (`0` on success, `1` on error).
    """
    repo_root = _validate_repo_dir(args.repo)
    if repo_root is None:
        return 1

    db_path = _get_db_path(repo_root)
    t0 = time.perf_counter()

    resolver = BlockResolver(repo_root)
    for warning in resolver.config.warnings:
        print(f"Warning: {warning}", file=sys.stderr)

    ingester = PythonASTIngester(
        repo_root,
        block_resolver=resolver.resolve,
        exclude_checker=resolver.is_excluded,
        test_detector=resolver.is_test_file,
    )

    skipped = 0
    active_paths: list[str] = []
    parsed_batch: list[FileParseResult] = []

    with FactStore(db_path) as store:
        store.init_schema()
        existing_hashes = store.get_file_hashes()
        for py_file in ingester.iter_python_files():
            rel = py_file.relative_to(repo_root).as_posix()
            active_paths.append(rel)
            try:
                sha = hashlib.sha256(py_file.read_bytes()).hexdigest()
            except OSError as exc:
                print(f"Warning: could not read {rel} ({exc})", file=sys.stderr)
                continue

            if args.force or existing_hashes.get(rel) != sha:
                parsed = ingester.parse_file(py_file)
                if parsed is not None:
                    parsed_batch.append(parsed)
            else:
                skipped += 1

        if parsed_batch:
            store.replace_many_file_facts(parsed_batch)

        pruned = store.prune_deleted_files(active_paths)
        blocks = store.get_block_risk_summary()
        deps = store.get_block_dependencies()
        cycles = store.detect_import_cycles()
        violations = resolver.check_violations(deps)
        coverage = TestCoverageAnalyzer(store).analyze()

    reindexed = len(parsed_batch)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    print(
        f"Scan completed in {elapsed_ms:.0f} ms -- "
        f"{reindexed} indexed, {skipped} unchanged, {pruned} pruned."
    )
    print(f"SQLite index: {db_path}")
    print(
        f"Production blocks: {len(blocks)} | "
        f"Linked tests: {coverage.linked_test_files}/{coverage.total_test_files} files "
        f"({coverage.overall_file_coverage_pct:.1f}% files | "
        f"{coverage.overall_symbol_coverage_pct:.1f}% symbols)"
    )
    print(
        f"Import cycles: {len(cycles)} | "
        f"Architecture violations: {len(violations)}"
    )

    if cycles:
        print("\nDetected import cycles:")
        for cycle in cycles[:10]:
            print("  - " + " -> ".join(cycle))

    if violations:
        print("\nArchitecture violations (.codeoverlook.toml):")
        for violation in violations:
            print(
                f"  - {violation['src_block']} -> {violation['dst_block']} "
                f"({violation['edge_count']}x {violation['kind']}) : {violation['reason']}"
            )

    return 0


def cmd_blocks(args: argparse.Namespace) -> int:
    """Display functional block summary including test coverage and risk status."""
    repo_root = _validate_repo_dir(args.repo)
    if repo_root is None:
        return 1

    db_path = _require_existing_db(repo_root)
    if db_path is None:
        return 1

    with FactStore(db_path) as store:
        summary = store.get_block_risk_summary()
        deps = store.get_block_dependencies()
        coverage = TestCoverageAnalyzer(store).analyze()

    if args.json:
        print(
            json.dumps(
                {
                    "blocks": summary,
                    "dependencies": deps,
                    "coverage": [asdict(b) for b in coverage.blocks],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    cov_by_block = {b.block_id: b for b in coverage.blocks}
    print(
        f"{'BLOC':<20} {'FILES':>6} {'LOC':>7} {'TESTS':>7} "
        f"{'SYM_COV':>8} {'SINKS':>6} {'STATUS':<13}"
    )
    print("-" * 74)
    for block in summary:
        bid = str(block["block_id"])
        cov = cov_by_block.get(bid)
        tests_cnt = cov.test_files_count if cov else 0
        sym_cov = f"{cov.symbol_coverage_pct:.1f}%" if cov else "0.0%"
        status = cov.coverage_status if cov else "UNTESTED"
        print(
            f"{bid:<20} {block['file_count']:>6} {block['total_loc']:>7} "
            f"{tests_cnt:>7} {sym_cov:>8} {block['sensitive_sinks']:>6} {status:<13}"
        )
    return 0


def cmd_tests(args: argparse.Namespace) -> int:
    """Show test-to-block mapping, coverage status, and prioritized test gaps."""
    repo_root = _validate_repo_dir(args.repo)
    if repo_root is None:
        return 1

    db_path = _require_existing_db(repo_root)
    if db_path is None:
        return 1

    with FactStore(db_path) as store:
        report = TestCoverageAnalyzer(store).analyze()

    target_block = args.block
    if target_block:
        blocks = [b for b in report.blocks if b.block_id == target_block]
        assocs = [a for a in report.test_associations if target_block in a.target_blocks]
        gaps = [g for g in report.untested_targets if g.block_id == target_block]
    else:
        blocks = report.blocks
        assocs = report.test_associations
        gaps = report.untested_targets

    if args.json:
        print(
            json.dumps(
                {
                    "summary": {
                        "total_test_files": report.total_test_files,
                        "linked_test_files": report.linked_test_files,
                        "total_test_functions": report.total_test_functions,
                        "overall_file_coverage_pct": report.overall_file_coverage_pct,
                        "overall_symbol_coverage_pct": report.overall_symbol_coverage_pct,
                    },
                    "blocks": [asdict(b) for b in blocks],
                    "test_associations": [asdict(a) for a in assocs],
                    "untested_targets": [asdict(g) for g in gaps[: args.limit]],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    print(
        f"Test suite: {report.linked_test_files}/{report.total_test_files} linked files | "
        f"{report.total_test_functions} test_* functions | "
        f"Overall: {report.overall_file_coverage_pct:.1f}% files, "
        f"{report.overall_symbol_coverage_pct:.1f}% symbols"
    )
    print()
    print(
        f"{'BLOCK':<18} {'PROD':>5} {'TESTED':>6} {'FILE%':>7} {'SYM%':>7} "
        f"{'TESTS':>6} {'UNT_SINKS':>9} {'PRIO':>7} {'STATUS':<12}"
    )
    print("-" * 86)
    for b in blocks:
        print(
            f"{b.block_id:<18} {b.prod_files:>5} {b.tested_files:>6} "
            f"{b.file_coverage_pct:>6.1f}% {b.symbol_coverage_pct:>6.1f}% "
            f"{b.test_files_count:>6} {b.untested_sinks:>9} {b.priority_score:>7.1f} "
            f"{b.coverage_status:<12}"
        )

    if target_block:
        print(f"\nAssociated test files for block '{target_block}' ({len(assocs)}):")
        for assoc in assocs[: args.limit]:
            print(
                f"  - {assoc.test_file} ({assoc.test_functions} tests, "
                f"{assoc.target_symbols_count} symbols, {assoc.link_mode})"
            )

    print(f"\nTop priority targets to add tests (limit {args.limit}):")
    for gap in gaps[: args.limit]:
        syms = ", ".join(gap.sample_symbols[:3]) if gap.sample_symbols else "module-level"
        print(
            f"  - [{gap.block_id}] {gap.file_path} (prio={gap.priority_score}, "
            f"untested_syms={gap.untested_symbols}, untested_sinks={gap.untested_sinks}, "
            f"refs={gap.inbound_prod_refs}) -> {syms}"
        )

    return 0


def cmd_slice(args: argparse.Namespace) -> int:
    """Extract a token-bounded Markdown context slice for a target symbol or file."""
    repo_root = _validate_repo_dir(args.repo)
    if repo_root is None:
        return 1

    db_path = _require_existing_db(repo_root)
    if db_path is None:
        return 1

    with FactStore(db_path) as store:
        slicer = ContextSlicer(store, repo_root)
        result = slicer.slice_target(args.target, token_budget=args.budget, depth=args.depth)
    print(result.markdown)
    return 0


def cmd_mermaid(args: argparse.Namespace) -> int:
    """Generate a Mermaid diagram for architecture blocks or test coverage."""
    repo_root = _validate_repo_dir(args.repo)
    if repo_root is None:
        return 1

    db_path = _require_existing_db(repo_root)
    if db_path is None:
        return 1

    with FactStore(db_path) as store:
        summary = store.get_block_risk_summary()
        deps = store.get_block_dependencies()
        coverage = TestCoverageAnalyzer(store).analyze() if args.mode == "coverage" else None

    if args.mode == "coverage" and coverage is not None:
        print(render_coverage_mermaid(coverage, deps))
    else:
        print(render_block_mermaid(summary, deps))
    return 0


def cmd_html(args: argparse.Namespace) -> int:
    """Generate a standalone interactive HTML coverage and architecture explorer."""
    repo_root = _validate_repo_dir(args.repo)
    if repo_root is None:
        return 1

    db_path = _require_existing_db(repo_root)
    if db_path is None:
        return 1

    resolver = BlockResolver(repo_root)
    with FactStore(db_path) as store:
        summary = store.get_block_risk_summary()
        deps = store.get_block_dependencies()
        cycles = store.detect_import_cycles()
        violations = resolver.check_violations(deps)
        coverage = TestCoverageAnalyzer(store).analyze()

    html_doc = render_atlas_html(
        repo_name=repo_root.name,
        coverage=coverage,
        block_summary=summary,
        dependencies=deps,
        cycles=cycles,
        violations=violations,
    )
    out_path = (
        Path(args.output).resolve()
        if args.output
        else (repo_root / ".codeoverlook" / "overlook.html")
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_doc, encoding="utf-8")
    print(f"HTML explorer generated: {out_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser for the `codeoverlook` CLI."""
    parser = argparse.ArgumentParser(
        prog="codeoverlook",
        description=(
            "Deterministic Python architecture mapping, test gap analysis, and Context Slicer"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="Index (or incrementally update) a Python repository")
    p_scan.add_argument("repo", nargs="?", default=".", help="Target repository path")
    p_scan.add_argument("--force", action="store_true", help="Force full re-indexing")
    p_scan.set_defaults(func=cmd_scan)

    p_blocks = sub.add_parser(
        "blocks",
        help="Display functional blocks, risk, and test coverage summary",
    )
    p_blocks.add_argument("repo", nargs="?", default=".", help="Target repository path")
    p_blocks.add_argument("--json", action="store_true", help="Emit structured JSON output")
    p_blocks.set_defaults(func=cmd_blocks)

    p_tests = sub.add_parser(
        "tests",
        help="Show test-to-block mapping and prioritized coverage gaps",
    )
    p_tests.add_argument("repo", nargs="?", default=".", help="Target repository path")
    p_tests.add_argument("--block", default=None, help="Filter report to one functional block")
    p_tests.add_argument("--limit", type=int, default=15, help="Max untested targets to display")
    p_tests.add_argument("--json", action="store_true", help="Emit structured JSON output")
    p_tests.set_defaults(func=cmd_tests)

    p_slice = sub.add_parser("slice", help="Extract a compact context slice for AI agents")
    p_slice.add_argument(
        "target",
        help="Symbol or file path (e.g. core/workspace.py or function name)",
    )
    p_slice.add_argument("--repo", default=".", help="Target repository path")
    p_slice.add_argument(
        "--budget",
        type=int,
        default=3000,
        help="Maximum estimated token budget",
    )
    p_slice.add_argument(
        "--depth",
        type=int,
        default=1,
        help="Neighborhood traversal depth (1 or 2)",
    )
    p_slice.set_defaults(func=cmd_slice)

    p_mermaid = sub.add_parser(
        "mermaid",
        help="Generate a Mermaid graph for architecture blocks or test coverage",
    )
    p_mermaid.add_argument("repo", nargs="?", default=".", help="Target repository path")
    p_mermaid.add_argument(
        "--mode",
        choices=("arch", "coverage"),
        default="arch",
        help="Diagram mode: architecture risks ('arch') or test coverage ('coverage')",
    )
    p_mermaid.set_defaults(func=cmd_mermaid)

    p_html = sub.add_parser(
        "html",
        help="Generate a standalone interactive HTML block & test coverage explorer",
    )
    p_html.add_argument("repo", nargs="?", default=".", help="Target repository path")
    p_html.add_argument("--output", default=None, help="Custom output HTML file path")
    p_html.set_defaults(func=cmd_html)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the `codeoverlook` CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (sqlite3.Error, OSError) as exc:
        print(f"CodeOverlook execution error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
