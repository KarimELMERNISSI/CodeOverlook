"""Test-to-block association and static test coverage gap analysis."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codeoverlook.core.store import FactStore


@dataclass(frozen=True, slots=True)
class TestFileAssociation:
    """Maps a single test file to the production blocks and symbols it exercises."""

    __test__ = False

    test_file: str
    test_functions: int
    primary_block: str
    target_blocks: list[str]
    target_symbols_count: int
    link_mode: str  # "static_graph" | "naming_heuristic" | "unlinked"


@dataclass(frozen=True, slots=True)
class BlockCoverageSummary:
    """Coverage and test-gap priority metrics for one functional block."""

    block_id: str
    prod_files: int
    tested_files: int
    file_coverage_pct: float
    prod_loc: int
    prod_symbols: int
    tested_symbols: int
    symbol_coverage_pct: float
    test_files_count: int
    test_functions_count: int
    sensitive_sinks: int
    untested_sinks: int
    inbound_prod_edges: int
    coverage_status: str  # "WELL_COVERED" | "PARTIAL" | "LOW" | "UNTESTED"
    priority_score: float


@dataclass(frozen=True, slots=True)
class UntestedTarget:
    """Concrete untested or partially covered production file recommended for tests."""

    file_path: str
    block_id: str
    loc: int
    untested_symbols: int
    untested_sinks: int
    inbound_prod_refs: int
    priority_score: float
    sample_symbols: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RepoCoverageReport:
    """Repository-wide test-to-block mapping and prioritized gap report."""

    total_test_files: int
    linked_test_files: int
    total_test_functions: int
    overall_file_coverage_pct: float
    overall_symbol_coverage_pct: float
    blocks: list[BlockCoverageSummary] = field(default_factory=list)
    test_associations: list[TestFileAssociation] = field(default_factory=list)
    untested_targets: list[UntestedTarget] = field(default_factory=list)


def _split_file_id(node_id: str) -> str:
    idx = node_id.find("::")
    return node_id[:idx] if idx != -1 else node_id


def _strip_test_affixes(stem: str) -> str:
    cleaned = stem
    if cleaned.startswith("test_"):
        cleaned = cleaned[5:]
    if cleaned.endswith("_test"):
        cleaned = cleaned[:-5]
    return cleaned


def _classify_coverage_status(
    tested_files: int,
    file_cov_pct: float,
    symbol_cov_pct: float,
) -> str:
    if tested_files == 0:
        return "UNTESTED"
    if file_cov_pct < 35.0 and symbol_cov_pct < 25.0:
        return "LOW"
    if file_cov_pct < 70.0 and symbol_cov_pct < 55.0:
        return "PARTIAL"
    return "WELL_COVERED"


class TestCoverageAnalyzer:
    """Maps test suites onto functional blocks and ranks coverage gaps.

    Combines static graph edges (`IMPORTS`, `CALLS`, `INHERITS`) originating
    from `is_test = 1` files, bounded 1-hop intra-block call reachability, and
    deterministic filename fallback to identify well-covered vs untested blocks.
    """

    __test__ = False

    def __init__(self, store: FactStore) -> None:
        """Initialize the analyzer for an open `FactStore` instance.

        Args:
            store: Active `FactStore` connected to `.codeoverlook/index.db`.
        """
        self.store = store

    def analyze(self) -> RepoCoverageReport:
        """Compute repository test-to-block associations and coverage gaps.

        Returns:
            A `RepoCoverageReport` containing block summaries, per-test-file
            associations, and ranked `UntestedTarget` files.
        """
        file_rows = self.store.conn.execute(
            "SELECT path, block_id, loc, is_test FROM files ORDER BY path;"
        ).fetchall()

        prod_files: dict[str, dict[str, Any]] = {}
        test_files: dict[str, dict[str, Any]] = {}
        for row in file_rows:
            entry = {
                "path": str(row["path"]),
                "block_id": str(row["block_id"]),
                "loc": int(row["loc"]),
            }
            if int(row["is_test"]) == 1:
                test_files[entry["path"]] = entry
            else:
                prod_files[entry["path"]] = entry

        prod_symbols_by_file, sym_to_file = self._load_prod_symbols()
        test_fn_counts = self._load_test_function_counts()
        sink_rows = self._load_prod_sinks()

        # Index edges touching production files
        edge_rows = self.store.conn.execute(
            """
            SELECT src_id, dst_id, kind, weight
            FROM edges
            WHERE target_scope = 'INTERNAL'
              AND kind IN ('IMPORTS', 'CALLS', 'INHERITS');
            """
        ).fetchall()

        test_to_prod_files: dict[str, set[str]] = defaultdict(set)
        test_to_prod_syms: dict[str, set[str]] = defaultdict(set)
        directly_tested_syms: set[str] = set()
        tested_files_by_graph: set[str] = set()

        inbound_prod_refs_by_file: dict[str, int] = defaultdict(int)
        inbound_prod_edges_by_block: dict[str, int] = defaultdict(int)
        intra_block_calls: dict[str, set[str]] = defaultdict(set)

        for row in edge_rows:
            src_id = str(row["src_id"])
            dst_id = str(row["dst_id"])
            kind = str(row["kind"])
            weight = int(row["weight"])
            src_file = _split_file_id(src_id)
            dst_file = _split_file_id(dst_id)

            if dst_file not in prod_files:
                continue

            if src_file in test_files:
                test_to_prod_files[src_file].add(dst_file)
                tested_files_by_graph.add(dst_file)
                if dst_id in sym_to_file:
                    test_to_prod_syms[src_file].add(dst_id)
                    directly_tested_syms.add(dst_id)
            elif src_file in prod_files and src_file != dst_file:
                inbound_prod_refs_by_file[dst_file] += weight
                src_block = prod_files[src_file]["block_id"]
                dst_block = prod_files[dst_file]["block_id"]
                if src_block != dst_block:
                    inbound_prod_edges_by_block[dst_block] += weight

            if (
                kind == "CALLS"
                and src_file in prod_files
                and prod_files[src_file]["block_id"] == prod_files[dst_file]["block_id"]
                and src_id in sym_to_file
                and dst_id in sym_to_file
            ):
                intra_block_calls[src_id].add(dst_id)

        # 1-hop intra-block reachability so modular private helpers called by tested
        # public entry points are counted as covered.
        tested_syms: set[str] = set(directly_tested_syms)
        for sym_id in directly_tested_syms:
            tested_syms.update(intra_block_calls.get(sym_id, set()))

        # Naming heuristic fallback only for test files with zero static graph edges
        heuristic_targets = self._match_unlinked_tests_by_name(
            test_files=test_files,
            test_to_prod_files=test_to_prod_files,
            prod_files=prod_files,
        )

        tested_files_all = set(tested_files_by_graph)
        test_associations: list[TestFileAssociation] = []
        block_to_test_files: dict[str, set[str]] = defaultdict(set)

        for test_path in sorted(test_files):
            fn_count = test_fn_counts.get(test_path, 0)
            graph_targets = test_to_prod_files.get(test_path, set())
            if graph_targets:
                link_mode = "static_graph"
                target_files = graph_targets
            elif test_path in heuristic_targets:
                link_mode = "naming_heuristic"
                target_files = heuristic_targets[test_path]
                tested_files_all.update(target_files)
            else:
                link_mode = "unlinked"
                target_files = set()

            block_counts: dict[str, int] = defaultdict(int)
            for pf in target_files:
                blk = prod_files[pf]["block_id"]
                block_counts[blk] += 1
                block_to_test_files[blk].add(test_path)

            ordered_blocks = [
                blk for blk, _ in sorted(block_counts.items(), key=lambda item: (-item[1], item[0]))
            ]
            primary_block = ordered_blocks[0] if ordered_blocks else "unlinked"
            test_associations.append(
                TestFileAssociation(
                    test_file=test_path,
                    test_functions=fn_count,
                    primary_block=primary_block,
                    target_blocks=ordered_blocks,
                    target_symbols_count=len(test_to_prod_syms.get(test_path, set())),
                    link_mode=link_mode,
                )
            )

        # Group sinks by file and determine which sinks lack test coverage
        sinks_by_file: dict[str, list[str | None]] = defaultdict(list)
        for s_row in sink_rows:
            sinks_by_file[str(s_row["file_path"])].append(
                str(s_row["symbol_id"]) if s_row["symbol_id"] is not None else None
            )

        # Build per-block summaries and per-file UntestedTarget entries
        files_by_block: dict[str, list[str]] = defaultdict(list)
        for path, info in prod_files.items():
            files_by_block[info["block_id"]].append(path)

        block_summaries: list[BlockCoverageSummary] = []
        untested_targets: list[UntestedTarget] = []

        total_prod_files = len(prod_files)
        total_tested_files = 0
        total_prod_syms = 0
        total_tested_syms = 0

        for block_id, block_paths in sorted(files_by_block.items()):
            b_prod_files = len(block_paths)
            b_tested_files = sum(1 for p in block_paths if p in tested_files_all)
            b_loc = sum(prod_files[p]["loc"] for p in block_paths)
            b_syms = 0
            b_tested_syms = 0
            b_sinks = 0
            b_untested_sinks = 0

            for p in block_paths:
                file_syms = prod_symbols_by_file.get(p, [])
                file_tested_syms = [s for s in file_syms if s["id"] in tested_syms]
                file_untested_syms = [s for s in file_syms if s["id"] not in tested_syms]

                b_syms += len(file_syms)
                b_tested_syms += len(file_tested_syms)

                file_sinks = sinks_by_file.get(p, [])
                b_sinks += len(file_sinks)
                file_untested_sinks = 0
                for sink_sym in file_sinks:
                    is_sink_covered = (
                        sink_sym in tested_syms
                        if sink_sym and sink_sym in sym_to_file
                        else p in tested_files_all
                    )
                    if not is_sink_covered:
                        file_untested_sinks += 1
                b_untested_sinks += file_untested_sinks

                is_file_tested = p in tested_files_all
                if not is_file_tested or file_untested_syms:
                    in_refs = inbound_prod_refs_by_file.get(p, 0)
                    file_priority = round(
                        (0.0 if is_file_tested else 20.0)
                        + file_untested_sinks * 20.0
                        + in_refs * 3.0
                        + len(file_untested_syms) * 2.0
                        + prod_files[p]["loc"] * 0.05,
                        1,
                    )
                    untested_targets.append(
                        UntestedTarget(
                            file_path=p,
                            block_id=block_id,
                            loc=prod_files[p]["loc"],
                            untested_symbols=len(file_untested_syms),
                            untested_sinks=file_untested_sinks,
                            inbound_prod_refs=in_refs,
                            priority_score=file_priority,
                            sample_symbols=[s["qualname"] for s in file_untested_syms[:5]],
                        )
                    )

            total_tested_files += b_tested_files
            total_prod_syms += b_syms
            total_tested_syms += b_tested_syms

            file_cov = round((b_tested_files / b_prod_files) * 100.0, 1) if b_prod_files else 0.0
            sym_cov = round((b_tested_syms / b_syms) * 100.0, 1) if b_syms else 0.0
            status = _classify_coverage_status(b_tested_files, file_cov, sym_cov)

            linked_tests = block_to_test_files.get(block_id, set())
            b_test_fns = sum(test_fn_counts.get(tf, 0) for tf in linked_tests)
            inbound_edges = inbound_prod_edges_by_block.get(block_id, 0)

            untested_factor = 1.0 - ((0.5 * file_cov + 0.5 * sym_cov) / 100.0)
            priority = round(
                untested_factor
                * (
                    b_loc * 0.04
                    + (b_syms - b_tested_syms) * 1.5
                    + b_untested_sinks * 15.0
                    + inbound_edges * 1.2
                ),
                1,
            )

            block_summaries.append(
                BlockCoverageSummary(
                    block_id=block_id,
                    prod_files=b_prod_files,
                    tested_files=b_tested_files,
                    file_coverage_pct=file_cov,
                    prod_loc=b_loc,
                    prod_symbols=b_syms,
                    tested_symbols=b_tested_syms,
                    symbol_coverage_pct=sym_cov,
                    test_files_count=len(linked_tests),
                    test_functions_count=b_test_fns,
                    sensitive_sinks=b_sinks,
                    untested_sinks=b_untested_sinks,
                    inbound_prod_edges=inbound_edges,
                    coverage_status=status,
                    priority_score=priority,
                )
            )

        block_summaries.sort(key=lambda b: (-b.priority_score, -b.prod_loc, b.block_id))
        untested_targets.sort(key=lambda t: (-t.priority_score, -t.loc, t.file_path))

        linked_test_files = sum(1 for a in test_associations if a.link_mode != "unlinked")
        total_test_functions = sum(a.test_functions for a in test_associations)
        overall_file_cov = (
            round((total_tested_files / total_prod_files) * 100.0, 1)
            if total_prod_files
            else 0.0
        )
        overall_sym_cov = (
            round((total_tested_syms / total_prod_syms) * 100.0, 1)
            if total_prod_syms
            else 0.0
        )

        return RepoCoverageReport(
            total_test_files=len(test_files),
            linked_test_files=linked_test_files,
            total_test_functions=total_test_functions,
            overall_file_coverage_pct=overall_file_cov,
            overall_symbol_coverage_pct=overall_sym_cov,
            blocks=block_summaries,
            test_associations=test_associations,
            untested_targets=untested_targets,
        )

    def _load_prod_symbols(self) -> tuple[dict[str, list[dict[str, str]]], dict[str, str]]:
        rows = self.store.conn.execute(
            """
            SELECT s.id, s.file_path, s.qualname
            FROM symbols s
            JOIN files f ON f.path = s.file_path
            WHERE f.is_test = 0
              AND s.kind IN ('class', 'function', 'method')
              AND NOT (
                  substr(s.name, 1, 2) = '__'
                  AND substr(s.name, -2) = '__'
                  AND length(s.name) > 4
              )
            ORDER BY s.file_path, s.start_line;
            """
        ).fetchall()
        by_file: dict[str, list[dict[str, str]]] = defaultdict(list)
        sym_to_file: dict[str, str] = {}
        for row in rows:
            sid = str(row["id"])
            fpath = str(row["file_path"])
            by_file[fpath].append({"id": sid, "qualname": str(row["qualname"])})
            sym_to_file[sid] = fpath
        return by_file, sym_to_file

    def _load_test_function_counts(self) -> dict[str, int]:
        rows = self.store.conn.execute(
            """
            SELECT s.file_path, COUNT(*) AS fn_count
            FROM symbols s
            JOIN files f ON f.path = s.file_path
            WHERE f.is_test = 1
              AND s.kind IN ('function', 'method')
              AND substr(s.name, 1, 5) = 'test_'
            GROUP BY s.file_path;
            """
        ).fetchall()
        return {str(r["file_path"]): int(r["fn_count"]) for r in rows}

    def _load_prod_sinks(self) -> list[Any]:
        return self.store.conn.execute(
            """
            SELECT fd.file_path, fd.symbol_id
            FROM findings fd
            JOIN files f ON f.path = fd.file_path
            WHERE f.is_test = 0 AND fd.category = 'SINK';
            """
        ).fetchall()

    @staticmethod
    def _match_unlinked_tests_by_name(
        test_files: dict[str, dict[str, Any]],
        test_to_prod_files: dict[str, set[str]],
        prod_files: dict[str, dict[str, Any]],
    ) -> dict[str, set[str]]:
        prod_by_stem: dict[str, list[str]] = defaultdict(list)
        for p in prod_files:
            stem = Path(p).stem.lower()
            if stem != "__init__":
                prod_by_stem[stem].append(p)

        matched: dict[str, set[str]] = {}
        for test_path in test_files:
            if test_to_prod_files.get(test_path):
                continue
            cleaned = _strip_test_affixes(Path(test_path).stem.lower())
            if not cleaned:
                continue
            if cleaned in prod_by_stem:
                matched[test_path] = set(prod_by_stem[cleaned])
        return matched
