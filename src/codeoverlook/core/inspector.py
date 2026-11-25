"""Shared repository scanning, snapshot loading, and slicing orchestration."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codeoverlook.core.blocks import BlockResolver
from codeoverlook.core.coverage import RepoCoverageReport, TestCoverageAnalyzer
from codeoverlook.core.slicer import ContextSlicer, SliceResult
from codeoverlook.core.sources import ResolvedTarget, TargetResolver
from codeoverlook.core.store import FactStore, FileParseResult
from codeoverlook.ingesters.python_ast import PythonASTIngester
from codeoverlook.views.html_renderer import render_atlas_html


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    """Progress snapshot emitted during target resolution, scanning, and rendering."""

    stage: str
    percent: int
    message: str
    current: int = 0
    total: int = 0


ProgressCallback = Callable[[ProgressEvent], None]


def _emit(callback: ProgressCallback | None, event: ProgressEvent) -> None:
    if callback is not None:
        callback(event)


@dataclass(slots=True)
class ScanSummary:
    """Result metrics produced by indexing a resolved repository."""

    target: ResolvedTarget
    db_path: Path
    elapsed_ms: float
    indexed_files: int
    skipped_files: int
    pruned_files: int
    blocks: list[dict[str, Any]] = field(default_factory=list)
    dependencies: list[dict[str, Any]] = field(default_factory=list)
    cycles: list[list[str]] = field(default_factory=list)
    violations: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    coverage: RepoCoverageReport | None = None


@dataclass(slots=True)
class InspectionSnapshot:
    """Complete architectural, coverage, and HTML explorer snapshot for a repository."""

    target: ResolvedTarget
    db_path: Path
    block_summary: list[dict[str, Any]]
    dependencies: list[dict[str, Any]]
    cycles: list[list[str]]
    violations: list[dict[str, Any]]
    coverage: RepoCoverageReport
    html_doc: str


def get_db_path(repo_root: Path) -> Path:
    """Return the canonical `.codeoverlook/index.db` path for a repository root."""
    return repo_root.resolve() / ".codeoverlook" / "index.db"


def _require_db_path(target: ResolvedTarget) -> Path:
    db_path = get_db_path(target.root_path)
    if not db_path.exists():
        raise FileNotFoundError(
            f"No index found at '{db_path}'. "
            f"Run `codeoverlook scan {target.original_target}` first."
        )
    return db_path


def scan_repository(
    target: ResolvedTarget,
    *,
    force: bool = False,
    warning_handler: Callable[[str], None] | None = None,
    progress_callback: ProgressCallback | None = None,
) -> ScanSummary:
    """Index or incrementally update `target` into its SQLite Fact Store.

    Args:
        target: Resolved local or cached GitHub target.
        force: When `True`, re-parse every file regardless of matching `sha256`.
        warning_handler: Optional callback invoked for non-fatal config/read warnings.
        progress_callback: Optional callback receiving `ProgressEvent` updates.

    Returns:
        `ScanSummary` containing scan timings, counts, cycles, violations, and coverage.
    """
    repo_root = target.root_path.resolve()
    db_path = get_db_path(repo_root)
    t0 = time.perf_counter()

    resolver = BlockResolver(repo_root)
    warnings = list(resolver.config.warnings)
    if warning_handler:
        for warning in warnings:
            warning_handler(warning)

    _emit(progress_callback, ProgressEvent("discovering", 18, "Discovering Python files..."))
    ingester = PythonASTIngester(
        repo_root,
        block_resolver=resolver.resolve,
        exclude_checker=resolver.is_excluded,
        test_detector=resolver.is_test_file,
    )
    py_files = ingester.iter_python_files()
    total_files = len(py_files)
    _emit(
        progress_callback,
        ProgressEvent("discovering", 22, f"Found {total_files} Python files", 0, total_files),
    )

    skipped = 0
    active_paths: list[str] = []
    parsed_batch: list[FileParseResult] = []
    emit_step = max(1, total_files // 40)

    with FactStore(db_path) as store:
        store.init_schema()
        existing_hashes = store.get_file_hashes()
        for idx, py_file in enumerate(py_files, start=1):
            rel = py_file.relative_to(repo_root).as_posix()
            active_paths.append(rel)
            try:
                sha = hashlib.sha256(py_file.read_bytes()).hexdigest()
            except OSError as exc:
                msg = f"could not read {rel} ({exc})"
                warnings.append(msg)
                if warning_handler:
                    warning_handler(msg)
                continue

            if force or existing_hashes.get(rel) != sha:
                parsed = ingester.parse_file(py_file)
                if parsed is not None:
                    parsed_batch.append(parsed)
            else:
                skipped += 1

            if idx == 1 or idx == total_files or idx % emit_step == 0:
                pct = 22 + int((idx / max(1, total_files)) * 56)
                _emit(
                    progress_callback,
                    ProgressEvent(
                        "scanning",
                        pct,
                        f"Scanning Python files ({idx}/{total_files})...",
                        idx,
                        total_files,
                    ),
                )

        _emit(
            progress_callback,
            ProgressEvent(
                "storing",
                80,
                f"Writing {len(parsed_batch)} parsed files to SQLite...",
                len(parsed_batch),
                total_files,
            ),
        )
        if parsed_batch:
            store.replace_many_file_facts(parsed_batch)

        _emit(
            progress_callback,
            ProgressEvent(
                "analyzing",
                88,
                "Computing dependencies, cycles, and test coverage...",
                total_files,
                total_files,
            ),
        )
        pruned = store.prune_deleted_files(active_paths)
        blocks = store.get_block_risk_summary()
        deps = store.get_block_dependencies()
        cycles = store.detect_import_cycles()
        violations = resolver.check_violations(deps)
        coverage = TestCoverageAnalyzer(store).analyze()

    elapsed_ms = (time.perf_counter() - t0) * 1000
    return ScanSummary(
        target=target,
        db_path=db_path,
        elapsed_ms=elapsed_ms,
        indexed_files=len(parsed_batch),
        skipped_files=skipped,
        pruned_files=pruned,
        blocks=blocks,
        dependencies=deps,
        cycles=cycles,
        violations=violations,
        warnings=warnings,
        coverage=coverage,
    )


def load_inspection_snapshot(
    target: ResolvedTarget,
    *,
    progress_callback: ProgressCallback | None = None,
) -> InspectionSnapshot:
    """Load an `InspectionSnapshot` and standalone HTML report from an existing index.

    Args:
        target: Resolved repository target whose `.codeoverlook/index.db` already exists.
        progress_callback: Optional callback receiving `ProgressEvent` updates.

    Returns:
        Populated `InspectionSnapshot` ready for CLI output or web workbench rendering.

    Raises:
        FileNotFoundError: If `.codeoverlook/index.db` does not exist yet.
    """
    repo_root = target.root_path.resolve()
    db_path = _require_db_path(target)

    resolver = BlockResolver(repo_root)
    with FactStore(db_path) as store:
        summary = store.get_block_risk_summary()
        deps = store.get_block_dependencies()
        cycles = store.detect_import_cycles()
        violations = resolver.check_violations(deps)
        coverage = TestCoverageAnalyzer(store).analyze()
        catalog = store.get_explorer_catalog()

    _emit(
        progress_callback,
        ProgressEvent("rendering", 94, "Rendering interactive HTML explorer..."),
    )
    html_doc = render_atlas_html(
        repo_name=target.display_name,
        coverage=coverage,
        block_summary=summary,
        dependencies=deps,
        cycles=cycles,
        violations=violations,
        catalog=catalog,
    )
    return InspectionSnapshot(
        target=target,
        db_path=db_path,
        block_summary=summary,
        dependencies=deps,
        cycles=cycles,
        violations=violations,
        coverage=coverage,
        html_doc=html_doc,
    )


def inspect_target(
    raw_target: str,
    *,
    ref: str | None = None,
    subpath: str | None = None,
    offline: bool = False,
    refresh: bool = False,
    force_scan: bool = False,
    token: str | None = None,
    cache_dir: Path | None = None,
    resolver: TargetResolver | None = None,
    progress_callback: ProgressCallback | None = None,
) -> tuple[ResolvedTarget, ScanSummary, InspectionSnapshot]:
    """Resolve a local or GitHub target, scan it, and return a full inspection snapshot.

    Args:
        raw_target: Local directory path or GitHub repository URL/shorthand.
        ref: Optional Git branch, tag, or commit SHA.
        subpath: Optional relative subdirectory inside the repository.
        offline: Restrict resolution to local folders and cached GitHub checkouts.
        refresh: Re-fetch a GitHub checkout from upstream even if cached.
        force_scan: Re-index all Python files even when `sha256` hashes match.
        token: Optional GitHub access token.
        cache_dir: Optional custom cache directory when `resolver` is not supplied.
        resolver: Optional preconfigured `TargetResolver` instance.
        progress_callback: Optional callback receiving `ProgressEvent` updates.

    Returns:
        Tuple of `(ResolvedTarget, ScanSummary, InspectionSnapshot)`.
    """
    _emit(progress_callback, ProgressEvent("resolving", 5, f"Resolving target '{raw_target}'..."))
    active_resolver = resolver or TargetResolver(cache_dir=cache_dir)
    resolved = active_resolver.resolve(
        raw_target,
        ref=ref,
        subpath=subpath,
        offline=offline,
        refresh=refresh,
        token=token,
    )
    mode = (
        "local"
        if resolved.source_kind == "local"
        else ("cached offline" if resolved.from_cache else (resolved.fetch_method or "online"))
    )
    _emit(
        progress_callback,
        ProgressEvent("resolving", 15, f"Resolved {resolved.display_name} ({mode})"),
    )
    scan_summary = scan_repository(resolved, force=force_scan, progress_callback=progress_callback)
    snapshot = load_inspection_snapshot(resolved, progress_callback=progress_callback)
    _emit(progress_callback, ProgressEvent("done", 100, "Inspection complete."))
    return resolved, scan_summary, snapshot


def slice_repository_target(
    target: ResolvedTarget,
    symbol_or_file: str,
    *,
    token_budget: int = 3000,
    depth: int = 1,
) -> SliceResult:
    """Extract a token-budgeted `SliceResult` from an already-indexed target.

    Args:
        target: Resolved repository target.
        symbol_or_file: Symbol name, qualified name, or relative file path.
        token_budget: Maximum estimated token budget.
        depth: K-hop neighborhood traversal depth.

    Returns:
        `SliceResult` containing bounded Markdown and token estimate.

    Raises:
        FileNotFoundError: If `.codeoverlook/index.db` has not been created yet.
    """
    repo_root = target.root_path.resolve()
    db_path = _require_db_path(target)
    with FactStore(db_path) as store:
        slicer = ContextSlicer(store, repo_root)
        return slicer.slice_target(symbol_or_file, token_budget=token_budget, depth=depth)
