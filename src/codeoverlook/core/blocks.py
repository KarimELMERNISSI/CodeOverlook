"""Functional block resolution, test file classification, and architecture rules."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

DEFAULT_TEST_PATTERNS: tuple[str, ...] = (
    "tests/**",
    "test/**",
    "**/tests/**",
    "**/test/**",
    "test_*.py",
    "**/test_*.py",
    "*_test.py",
    "**/*_test.py",
    "conftest.py",
    "**/conftest.py",
)


@dataclass(frozen=True, slots=True)
class BlockRule:
    """Rule mapping file path glob patterns to a functional block."""

    name: str
    patterns: tuple[str, ...]
    description: str = ""


@dataclass(frozen=True, slots=True)
class ArchConstraint:
    """Architectural boundary rule forbidding direct dependencies between blocks."""

    src_block: str
    forbid_target: str
    reason: str = ""


@dataclass(slots=True)
class BlockConfig:
    """Configuration parsed from `.codeoverlook.toml`."""

    blocks: list[BlockRule] = field(default_factory=list)
    constraints: list[ArchConstraint] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)
    test_patterns: list[str] = field(default_factory=lambda: list(DEFAULT_TEST_PATTERNS))
    has_custom_test_patterns: bool = False
    warnings: list[str] = field(default_factory=list)


@lru_cache(maxsize=256)
def _compile_glob_regex(pattern: str) -> re.Pattern[str]:
    """Convert a POSIX glob pattern (`**`, `*`, `?`) into a compiled regex."""
    normalized = pattern.replace("\\", "/").lstrip("./")
    parts: list[str] = ["^"]
    idx = 0
    length = len(normalized)

    while idx < length:
        if normalized.startswith("**/", idx):
            parts.append("(?:.+/)?")
            idx += 3
        elif normalized.startswith("/**", idx) and idx + 3 == length:
            parts.append("(?:/.*)?")
            idx += 3
        elif normalized.startswith("**", idx):
            parts.append(".*")
            idx += 2
        elif normalized[idx] == "*":
            parts.append("[^/]*")
            idx += 1
        elif normalized[idx] == "?":
            parts.append("[^/]")
            idx += 1
        else:
            parts.append(re.escape(normalized[idx]))
            idx += 1

    parts.append("$")
    return re.compile("".join(parts))


def matches_glob(rel_posix: str, pattern: str) -> bool:
    """Evaluate a relative POSIX path against a glob pattern supporting `**`.

    Args:
        rel_posix: Relative POSIX file path (without leading `./`).
        pattern: Glob pattern from `.codeoverlook.toml` or defaults.

    Returns:
        `True` if the path matches the pattern, `False` otherwise.
    """
    cleaned_path = rel_posix.replace("\\", "/").lstrip("./")
    return bool(_compile_glob_regex(pattern).match(cleaned_path))


def is_default_test_path(rel_posix: str) -> bool:
    """Determine if a relative POSIX path is a test file using default heuristics.

    Files nested under synthetic `fixtures/` directories are not marked as tests
    unless the filename itself follows pytest `test_*.py` / `*_test.py` naming.
    """
    cleaned = rel_posix.replace("\\", "/").lstrip("./")
    filename = Path(cleaned).name
    in_fixtures = matches_glob(cleaned, "fixtures/**") or matches_glob(cleaned, "**/fixtures/**")
    if in_fixtures and not (filename.startswith("test_") or filename.endswith("_test.py")):
        return False
    return any(matches_glob(cleaned, pat) for pat in DEFAULT_TEST_PATTERNS)


class BlockResolver:
    """Resolve functional blocks, test files, and architectural constraints."""

    def __init__(self, repo_root: Path, config_path: Path | None = None) -> None:
        """Initialize the resolver for a target repository.

        Args:
            repo_root: Repository root directory.
            config_path: Optional override path to `.codeoverlook.toml`.
        """
        self.repo_root = repo_root.resolve()
        self.config_path = config_path or (self.repo_root / ".codeoverlook.toml")
        self.config = self._load_config()

    def _load_config(self) -> BlockConfig:
        if not self.config_path.exists():
            return BlockConfig()

        try:
            raw_text = self.config_path.read_text(encoding="utf-8")
            raw = tomllib.loads(raw_text)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            return BlockConfig(
                warnings=[
                    f"Configuration ignored ({self.config_path}): {exc}"
                ]
            )

        blocks: list[BlockRule] = []
        raw_blocks = raw.get("blocks", {})
        if isinstance(raw_blocks, dict):
            for name, spec in raw_blocks.items():
                if isinstance(spec, list):
                    patterns = tuple(str(p) for p in spec)
                    desc = ""
                elif isinstance(spec, dict):
                    raw_patterns = spec.get("patterns", [])
                    patterns = (
                        tuple(str(p) for p in raw_patterns)
                        if isinstance(raw_patterns, list)
                        else ()
                    )
                    desc = str(spec.get("description", ""))
                else:
                    continue
                blocks.append(BlockRule(name=str(name), patterns=patterns, description=desc))

        constraints: list[ArchConstraint] = []
        raw_arch = raw.get("architecture", {})
        if isinstance(raw_arch, dict):
            for rule in raw_arch.get("forbid", []):
                if not isinstance(rule, dict):
                    continue
                src = rule.get("from")
                dst = rule.get("to")
                if src and dst:
                    constraints.append(
                        ArchConstraint(
                            src_block=str(src),
                            forbid_target=str(dst),
                            reason=str(rule.get("reason", "")),
                        )
                    )

        raw_scan = raw.get("scan", {})
        raw_exclude = raw_scan.get("exclude", []) if isinstance(raw_scan, dict) else []
        exclude = [str(p) for p in raw_exclude] if isinstance(raw_exclude, list) else []

        raw_tests = raw.get("tests", {})
        custom_test_patterns = (
            [str(p) for p in raw_tests.get("patterns", [])]
            if isinstance(raw_tests, dict) and isinstance(raw_tests.get("patterns"), list)
            else None
        )

        return BlockConfig(
            blocks=blocks,
            constraints=constraints,
            exclude_patterns=exclude,
            test_patterns=(
                custom_test_patterns
                if custom_test_patterns is not None
                else list(DEFAULT_TEST_PATTERNS)
            ),
            has_custom_test_patterns=custom_test_patterns is not None,
        )

    def resolve(self, rel_posix: str) -> str:
        """Return the functional block identifier for a relative POSIX path."""
        for block in self.config.blocks:
            for pattern in block.patterns:
                if matches_glob(rel_posix, pattern):
                    return block.name
        return self._fallback_block(rel_posix)

    def is_excluded(self, rel_posix: str) -> bool:
        """Return `True` if the path matches `[scan].exclude` in `.codeoverlook.toml`."""
        return any(matches_glob(rel_posix, pat) for pat in self.config.exclude_patterns)

    def is_test_file(self, rel_posix: str) -> bool:
        """Return `True` if the file belongs to the repository test suite."""
        if not self.config.has_custom_test_patterns:
            return is_default_test_path(rel_posix)
        return any(matches_glob(rel_posix, pat) for pat in self.config.test_patterns)

    @staticmethod
    def _fallback_block(rel_posix: str) -> str:
        parts = Path(rel_posix).parts
        if len(parts) <= 1:
            return "root"
        if parts[0] == "src":
            if len(parts) >= 4:
                return parts[2]
            if len(parts) == 3:
                return parts[1]
        return parts[0]

    def check_violations(self, block_deps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Check inter-block dependencies against `architecture.forbid` rules.

        Args:
            block_deps: Aggregated block dependency edges from `FactStore`.

        Returns:
            List of violation records with explicit reasons.
        """
        violations: list[dict[str, Any]] = []
        for dep in block_deps:
            for rule in self.config.constraints:
                if (
                    dep["src_block"] == rule.src_block
                    and dep["dst_block"] == rule.forbid_target
                ):
                    violations.append(
                        {
                            "src_block": dep["src_block"],
                            "dst_block": dep["dst_block"],
                            "kind": dep["kind"],
                            "edge_count": dep["edge_count"],
                            "reason": rule.reason or "Forbidden dependency in .codeoverlook.toml",
                        }
                    )
        return violations
