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
from codeoverlook.core.slicer import ContextSlicer, SliceResult
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
    "ContextSlicer",
    "DEFAULT_TEST_PATTERNS",
    "EdgeRecord",
    "FactStore",
    "FileParseResult",
    "FindingRecord",
    "RepoCoverageReport",
    "SliceResult",
    "SymbolRecord",
    "TestCoverageAnalyzer",
    "TestFileAssociation",
    "UntestedTarget",
    "is_default_test_path",
    "matches_glob",
]
