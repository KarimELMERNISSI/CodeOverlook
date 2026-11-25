"""Core package of CodeOverlook: SQLite fact store, blocks, coverage and context slicing."""

from __future__ import annotations

from codeoverlook.core.blocks import (
    DEFAULT_TEST_PATTERNS,
    ArchConstraint,
    BlockConfig,
    BlockResolver,
    BlockRule,
    is_default_test_path,
    matches_glob,
)
from codeoverlook.core.coverage import (
    BlockCoverageSummary,
    RepoCoverageReport,
    TestCoverageAnalyzer,
    TestFileAssociation,
    UntestedTarget,
)
from codeoverlook.core.inspector import (
    InspectionSnapshot,
    ScanSummary,
    get_db_path,
    inspect_target,
    load_inspection_snapshot,
    scan_repository,
    slice_repository_target,
)
from codeoverlook.core.slicer import ContextSlicer, SliceResult
from codeoverlook.core.sources import (
    CachedRepoEntry,
    GitHubSpec,
    ResolvedTarget,
    SourceResolutionError,
    TargetResolver,
    parse_github_spec,
)
from codeoverlook.core.store import (
    EdgeRecord,
    FactStore,
    FileParseResult,
    FindingRecord,
    SymbolRecord,
)

__all__ = [
    "ArchConstraint",
    "BlockConfig",
    "BlockCoverageSummary",
    "BlockResolver",
    "BlockRule",
    "CachedRepoEntry",
    "ContextSlicer",
    "DEFAULT_TEST_PATTERNS",
    "EdgeRecord",
    "FactStore",
    "FileParseResult",
    "FindingRecord",
    "GitHubSpec",
    "InspectionSnapshot",
    "RepoCoverageReport",
    "ResolvedTarget",
    "ScanSummary",
    "SliceResult",
    "SourceResolutionError",
    "SymbolRecord",
    "TargetResolver",
    "TestCoverageAnalyzer",
    "TestFileAssociation",
    "UntestedTarget",
    "get_db_path",
    "inspect_target",
    "is_default_test_path",
    "load_inspection_snapshot",
    "matches_glob",
    "parse_github_spec",
    "scan_repository",
    "slice_repository_target",
]
