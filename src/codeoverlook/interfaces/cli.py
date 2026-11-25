"""Command-line interface (CLI) for CodeOverlook."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict
from pathlib import Path

from codeoverlook.core.blocks import BlockResolver
from codeoverlook.core.coverage import TestCoverageAnalyzer
from codeoverlook.core.inspector import (
    get_db_path,
    scan_repository,
    slice_repository_target,
)
from codeoverlook.core.sources import ResolvedTarget, SourceResolutionError, TargetResolver
from codeoverlook.core.store import FactStore
from codeoverlook.interfaces.web_server import serve_workbench
from codeoverlook.views.html_renderer import render_atlas_html
from codeoverlook.views.mermaid import render_block_mermaid, render_coverage_mermaid


def _resolve_target_from_args(args: argparse.Namespace) -> ResolvedTarget | None:
    cache_dir = Path(args.cache_dir) if getattr(args, "cache_dir", None) else None
    resolver = TargetResolver(cache_dir=cache_dir)
    try:
        return resolver.resolve(
            args.repo,
            ref=getattr(args, "ref", None),
            subpath=getattr(args, "subpath", None),
            offline=bool(getattr(args, "offline", False)),
            refresh=bool(getattr(args, "refresh", False)),
        )
    except SourceResolutionError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return None


def _require_existing_db(target: ResolvedTarget) -> Path | None:
    db_path = get_db_path(target.root_path)
    if not db_path.exists():
        print(
            f"Error: no index found at '{db_path}'. "
            f"Run `codeoverlook scan {target.original_target}` first.",
            file=sys.stderr,
        )
        return None
    return db_path


def _add_source_args(parser: argparse.ArgumentParser, *, include_refresh: bool = False) -> None:
    parser.add_argument(
        "--ref",
        default=None,
        help="Git branch, tag, or commit SHA when inspecting a GitHub target",
    )
    parser.add_argument(
        "--subpath",
        default=None,
        help="Optional subdirectory relative to the repository root",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Offline mode: inspect local folders or previously cached GitHub repos only",
    )
    parser.add_argument(
        "--cache-dir",
        default=None,
        help="Override persistent cache directory (defaults to ~/.codeoverlook/cache)",
    )
    if include_refresh:
        parser.add_argument(
            "--refresh",
            action="store_true",
            help="Re-fetch a cached GitHub repository from upstream before running",
        )


def cmd_scan(args: argparse.Namespace) -> int:
    """Index (or incrementally update) a local or GitHub Python repository."""
    target = _resolve_target_from_args(args)
    if target is None:
        return 1

    summary = scan_repository(
        target,
        force=bool(args.force),
        warning_handler=lambda msg: print(f"Warning: {msg}", file=sys.stderr),
    )
    coverage = summary.coverage
    assert coverage is not None

    if target.source_kind == "github":
        mode = "cached offline" if target.from_cache else (target.fetch_method or "online")
        print(f"Source: GitHub {target.display_name} ({mode}) -> {target.root_path}")

    print(
        f"Scan completed in {summary.elapsed_ms:.0f} ms -- "
        f"{summary.indexed_files} indexed, {summary.skipped_files} unchanged, "
        f"{summary.pruned_files} pruned."
    )
    print(f"SQLite index: {summary.db_path}")
    print(
        f"Production blocks: {len(summary.blocks)} | "
        f"Linked tests: {coverage.linked_test_files}/{coverage.total_test_files} files "
        f"({coverage.overall_file_coverage_pct:.1f}% files | "
        f"{coverage.overall_symbol_coverage_pct:.1f}% symbols)"
    )
    print(
        f"Import cycles: {len(summary.cycles)} | "
        f"Architecture violations: {len(summary.violations)}"
    )

    if summary.cycles:
        print("\nDetected import cycles:")
        for cycle in summary.cycles[:10]:
            print("  - " + " -> ".join(cycle))

    if summary.violations:
        print("\nArchitecture violations (.codeoverlook.toml):")
        for violation in summary.violations:
            print(
                f"  - {violation['src_block']} -> {violation['dst_block']} "
                f"({violation['edge_count']}x {violation['kind']}) : {violation['reason']}"
            )

    return 0


def cmd_blocks(args: argparse.Namespace) -> int:
    """Display functional block summary including test coverage and risk status."""
    target = _resolve_target_from_args(args)
    if target is None:
        return 1

    db_path = _require_existing_db(target)
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
    target = _resolve_target_from_args(args)
    if target is None:
        return 1

    db_path = _require_existing_db(target)
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
    target = _resolve_target_from_args(args)
    if target is None:
        return 1

    db_path = _require_existing_db(target)
    if db_path is None:
        return 1

    result = slice_repository_target(
        target,
        args.target,
        token_budget=args.budget,
        depth=args.depth,
    )
    print(result.markdown)
    return 0


def cmd_mermaid(args: argparse.Namespace) -> int:
    """Generate a Mermaid diagram for architecture blocks or test coverage."""
    target = _resolve_target_from_args(args)
    if target is None:
        return 1

    db_path = _require_existing_db(target)
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
    target = _resolve_target_from_args(args)
    if target is None:
        return 1

    db_path = _require_existing_db(target)
    if db_path is None:
        return 1

    repo_root = target.root_path
    resolver = BlockResolver(repo_root)
    with FactStore(db_path) as store:
        summary = store.get_block_risk_summary()
        deps = store.get_block_dependencies()
        cycles = store.detect_import_cycles()
        violations = resolver.check_violations(deps)
        coverage = TestCoverageAnalyzer(store).analyze()

    html_doc = render_atlas_html(
        repo_name=target.display_name,
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


def cmd_cache(args: argparse.Namespace) -> int:
    """List locally cached GitHub repositories available for offline inspection."""
    cache_dir = Path(args.cache_dir) if args.cache_dir else None
    resolver = TargetResolver(cache_dir=cache_dir)
    entries = resolver.list_cached_repos()

    if args.json:
        print(
            json.dumps(
                {
                    "cache_dir": str(resolver.cache_dir),
                    "repositories": [
                        {
                            "owner": e.owner,
                            "repo": e.repo,
                            "ref": e.ref,
                            "checkout_path": str(e.checkout_path),
                            "fetched_at": e.fetched_at,
                            "indexed": e.indexed,
                            "clone_url": e.clone_url,
                        }
                        for e in entries
                    ],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    print(f"Offline cache directory: {resolver.cache_dir}")
    if not entries:
        print("No cached GitHub repositories found.")
        return 0

    print(f"{'REPOSITORY':<34} {'REF':<16} {'INDEXED':<9} {'FETCHED_AT'}")
    print("-" * 82)
    for entry in entries:
        full_name = f"{entry.owner}/{entry.repo}"
        indexed_str = "yes" if entry.indexed else "no"
        fetched = entry.fetched_at[:19].replace("T", " ") if entry.fetched_at else "unknown"
        print(f"{full_name:<34} {entry.ref:<16} {indexed_str:<9} {fetched}")
    return 0


def cmd_ui(args: argparse.Namespace) -> int:
    """Launch the local interactive web workbench for local folders or GitHub repos."""
    cache_dir = Path(args.cache_dir) if args.cache_dir else None
    return serve_workbench(
        host=args.host,
        port=args.port,
        cache_dir=cache_dir,
        initial_target=args.target,
        offline_default=bool(args.offline),
        open_browser=not bool(args.no_browser),
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser for the `codeoverlook` CLI."""
    parser = argparse.ArgumentParser(
        prog="codeoverlook",
        description=(
            "Deterministic Python architecture mapping, test gap analysis, and Context Slicer"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser(
        "scan",
        help="Index (or incrementally update) a local folder or GitHub repository",
    )
    p_scan.add_argument(
        "repo",
        nargs="?",
        default=".",
        help="Local repository path or GitHub URL / owner/repo",
    )
    p_scan.add_argument("--force", action="store_true", help="Force full re-indexing")
    _add_source_args(p_scan, include_refresh=True)
    p_scan.set_defaults(func=cmd_scan)

    p_blocks = sub.add_parser(
        "blocks",
        help="Display functional blocks, risk, and test coverage summary",
    )
    p_blocks.add_argument(
        "repo",
        nargs="?",
        default=".",
        help="Local repository path or GitHub URL / owner/repo",
    )
    p_blocks.add_argument("--json", action="store_true", help="Emit structured JSON output")
    _add_source_args(p_blocks)
    p_blocks.set_defaults(func=cmd_blocks)

    p_tests = sub.add_parser(
        "tests",
        help="Show test-to-block mapping and prioritized coverage gaps",
    )
    p_tests.add_argument(
        "repo",
        nargs="?",
        default=".",
        help="Local repository path or GitHub URL / owner/repo",
    )
    p_tests.add_argument("--block", default=None, help="Filter report to one functional block")
    p_tests.add_argument("--limit", type=int, default=15, help="Max untested targets to display")
    p_tests.add_argument("--json", action="store_true", help="Emit structured JSON output")
    _add_source_args(p_tests)
    p_tests.set_defaults(func=cmd_tests)

    p_slice = sub.add_parser("slice", help="Extract a compact context slice for AI agents")
    p_slice.add_argument(
        "target",
        help="Symbol or file path (e.g. core/workspace.py or function name)",
    )
    p_slice.add_argument(
        "--repo",
        default=".",
        help="Local repository path or GitHub URL / owner/repo",
    )
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
    _add_source_args(p_slice)
    p_slice.set_defaults(func=cmd_slice)

    p_mermaid = sub.add_parser(
        "mermaid",
        help="Generate a Mermaid graph for architecture blocks or test coverage",
    )
    p_mermaid.add_argument(
        "repo",
        nargs="?",
        default=".",
        help="Local repository path or GitHub URL / owner/repo",
    )
    p_mermaid.add_argument(
        "--mode",
        choices=("arch", "coverage"),
        default="arch",
        help="Diagram mode: architecture risks ('arch') or test coverage ('coverage')",
    )
    _add_source_args(p_mermaid)
    p_mermaid.set_defaults(func=cmd_mermaid)

    p_html = sub.add_parser(
        "html",
        help="Generate a standalone interactive HTML block & test coverage explorer",
    )
    p_html.add_argument(
        "repo",
        nargs="?",
        default=".",
        help="Local repository path or GitHub URL / owner/repo",
    )
    p_html.add_argument("--output", default=None, help="Custom output HTML file path")
    _add_source_args(p_html, include_refresh=True)
    p_html.set_defaults(func=cmd_html)

    p_cache = sub.add_parser(
        "cache",
        help="List GitHub repositories cached locally for offline inspection",
    )
    p_cache.add_argument("--json", action="store_true", help="Emit structured JSON output")
    p_cache.add_argument(
        "--cache-dir",
        default=None,
        help="Override persistent cache directory (defaults to ~/.codeoverlook/cache)",
    )
    p_cache.set_defaults(func=cmd_cache)

    p_ui = sub.add_parser(
        "ui",
        help="Start the local interactive web workbench for local folders or GitHub repos",
    )
    p_ui.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    p_ui.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765)")
    p_ui.add_argument(
        "--target",
        default=None,
        help="Optional local folder or GitHub repo to inspect automatically on load",
    )
    p_ui.add_argument(
        "--offline",
        action="store_true",
        help="Start with offline mode enabled",
    )
    p_ui.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not automatically open the browser",
    )
    p_ui.add_argument(
        "--cache-dir",
        default=None,
        help="Override persistent cache directory (defaults to ~/.codeoverlook/cache)",
    )
    p_ui.set_defaults(func=cmd_ui)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the `codeoverlook` CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (SourceResolutionError, FileNotFoundError, sqlite3.Error, OSError) as exc:
        print(f"CodeOverlook execution error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
