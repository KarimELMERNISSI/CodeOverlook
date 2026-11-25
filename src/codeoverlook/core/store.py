"""Incremental SQLite access layer for the code graph, coverage and audits."""

from __future__ import annotations

import sqlite3
from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class SymbolRecord:
    """Represents an indexed Python symbol (module, class, function, or method)."""

    id: str  # e.g. "core/workspace.py::WorkspaceManager.create"
    file_path: str
    kind: str  # "module" | "class" | "function" | "method"
    name: str
    qualname: str
    signature: str
    start_line: int
    end_line: int
    docstring: str | None = None


@dataclass(frozen=True, slots=True)
class EdgeRecord:
    """Represents a directed relationship between two entities in the code graph."""

    src_id: str
    dst_id: str
    kind: str  # "IMPORTS" | "CALLS" | "INHERITS" | "RUNTIME_CALL"
    target_scope: str = "INTERNAL"  # "INTERNAL" | "STDLIB" | "EXTERNAL"
    weight: int = 1


@dataclass(frozen=True, slots=True)
class FindingRecord:
    """Represents a static finding, sensitive sink, or architectural violation."""

    file_path: str
    symbol_id: str | None
    tool: str
    rule_id: str
    severity: str  # "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO"
    category: str  # "SINK" | "SAST" | "CVE" | "ARCH"
    line: int
    message: str


@dataclass(slots=True)
class FileParseResult:
    """Complete static analysis result for a single Python source file."""

    file_path: str
    sha256: str
    loc: int
    block_id: str = "unassigned"
    is_test: bool = False
    symbols: list[SymbolRecord] = field(default_factory=list)
    edges: list[EdgeRecord] = field(default_factory=list)
    findings: list[FindingRecord] = field(default_factory=list)


class FactStore:
    """Incremental SQLite persistence layer for CodeOverlook graphs and audits.

    Stores all artifacts inside `.codeoverlook/index.db` (WAL mode, foreign keys
    enabled) and exposes native SQL graph traversals (`WITH RECURSIVE`).
    """

    def __init__(self, db_path: Path) -> None:
        """Open (or create) the SQLite fact store database.

        When initialized inside a `.codeoverlook` directory, automatically writes
        a local `.gitignore` file so Git ignores all CodeOverlook artifacts.

        Args:
            db_path: Path to `.codeoverlook/index.db`.
        """
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_store_gitignore()
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self._configure_connection()

    def _ensure_store_gitignore(self) -> None:
        if self.db_path.parent.name != ".codeoverlook":
            return
        gitignore_path = self.db_path.parent / ".gitignore"
        if not gitignore_path.exists():
            gitignore_path.write_text(
                "# Automatically created by CodeOverlook.\n*\n",
                encoding="utf-8",
            )

    def _configure_connection(self) -> None:
        self.conn.execute("PRAGMA journal_mode = WAL;")
        self.conn.execute("PRAGMA synchronous = NORMAL;")
        self.conn.execute("PRAGMA foreign_keys = ON;")

    def _migrate_existing_schema(self) -> None:
        cols = self.conn.execute("PRAGMA table_info(files);").fetchall()
        if not cols:
            return
        col_names = {row["name"] for row in cols}
        if "is_test" not in col_names:
            self.conn.execute(
                "ALTER TABLE files ADD COLUMN is_test INTEGER NOT NULL DEFAULT 0;"
            )
            self.conn.execute("DROP VIEW IF EXISTS v_block_risk_summary;")
            self.conn.commit()

    def init_schema(self, schema_path: Path | None = None) -> None:
        """Initialize or migrate the SQLite schema, indexes, and analytical views.

        Args:
            schema_path: Optional path to a custom SQL schema script.
        """
        self._migrate_existing_schema()
        path = schema_path or Path(__file__).with_name("schema.sql")
        if path.exists():
            self.conn.executescript(path.read_text(encoding="utf-8"))
        else:
            self.conn.executescript(_DEFAULT_SCHEMA_SQL)
        self.conn.commit()

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self.conn.close()

    def __enter__(self) -> FactStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Incremental indexing
    # ------------------------------------------------------------------

    def get_file_hashes(self) -> dict[str, str]:
        """Return `{relative_posix_path: sha256}` for all currently indexed files."""
        rows = self.conn.execute("SELECT path, sha256 FROM files;").fetchall()
        return {row["path"]: row["sha256"] for row in rows}

    def needs_reindex(self, file_path: str, sha256: str) -> bool:
        """Return whether a file must be re-parsed based on its SHA-256 digest."""
        row = self.conn.execute(
            "SELECT sha256 FROM files WHERE path = ?;", (file_path,)
        ).fetchone()
        return row is None or row["sha256"] != sha256

    def replace_file_facts(self, result: FileParseResult) -> None:
        """Atomically replace all indexed facts for a single parsed file."""
        self.replace_many_file_facts([result])

    def replace_many_file_facts(self, results: Iterable[FileParseResult]) -> None:
        """Atomically replace indexed facts for a batch of files in one transaction.

        Batching all file updates inside a single SQLite transaction avoids
        hundreds of individual disk syncs on large repositories.

        Args:
            results: Iterable of `FileParseResult` entries to upsert.
        """
        batch = list(results)
        if not batch:
            return

        file_rows: list[tuple[str, str, str, int, int]] = []
        symbol_rows: list[tuple[str, str, str, str, str, str, int, int, str | None]] = []
        edge_rows: list[tuple[str, str, str, str, int]] = []
        finding_rows: list[tuple[str, str | None, str, str, str, str, int, str]] = []

        with self.conn:
            for res in batch:
                self.conn.execute(
                    """
                    DELETE FROM edges
                    WHERE src_id = ?
                       OR src_id LIKE ?
                       OR src_id IN (SELECT id FROM symbols WHERE file_path = ?);
                    """,
                    (res.file_path, f"{res.file_path}::%", res.file_path),
                )
                self.conn.execute(
                    "DELETE FROM findings WHERE file_path = ? AND tool = 'codeoverlook-ast';",
                    (res.file_path,),
                )
                self.conn.execute(
                    "DELETE FROM symbols WHERE file_path = ?;",
                    (res.file_path,),
                )
                file_rows.append(
                    (
                        res.file_path,
                        res.sha256,
                        res.block_id,
                        res.loc,
                        1 if res.is_test else 0,
                    )
                )
                for sym in res.symbols:
                    symbol_rows.append(
                        (
                            sym.id,
                            sym.file_path,
                            sym.kind,
                            sym.name,
                            sym.qualname,
                            sym.signature,
                            sym.start_line,
                            sym.end_line,
                            sym.docstring,
                        )
                    )
                for edge in res.edges:
                    edge_rows.append(
                        (edge.src_id, edge.dst_id, edge.kind, edge.target_scope, edge.weight)
                    )
                for finding in res.findings:
                    finding_rows.append(
                        (
                            finding.file_path,
                            finding.symbol_id,
                            finding.tool,
                            finding.rule_id,
                            finding.severity,
                            finding.category,
                            finding.line,
                            finding.message,
                        )
                    )

            self.conn.executemany(
                """
                INSERT INTO files (path, sha256, block_id, loc, is_test)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    sha256 = excluded.sha256,
                    block_id = excluded.block_id,
                    loc = excluded.loc,
                    is_test = excluded.is_test,
                    indexed_at = CURRENT_TIMESTAMP;
                """,
                file_rows,
            )

            if symbol_rows:
                self.conn.executemany(
                    """
                    INSERT OR REPLACE INTO symbols
                        (id, file_path, kind, name, qualname, signature,
                         start_line, end_line, docstring)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    symbol_rows,
                )

            if edge_rows:
                self.conn.executemany(
                    """
                    INSERT INTO edges (src_id, dst_id, kind, target_scope, weight)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(src_id, dst_id, kind) DO UPDATE SET
                        weight = edges.weight + excluded.weight;
                    """,
                    edge_rows,
                )

            if finding_rows:
                self.conn.executemany(
                    """
                    INSERT INTO findings
                        (file_path, symbol_id, tool, rule_id, severity, category, line, message)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    finding_rows,
                )

    def prune_deleted_files(self, active_paths: Iterable[str]) -> int:
        """Remove indexed files that no longer exist on disk.

        Args:
            active_paths: Currently active relative POSIX file paths.

        Returns:
            Number of pruned file entries.
        """
        active = set(active_paths)
        existing = set(self.get_file_hashes().keys())
        stale = existing - active
        if not stale:
            return 0
        with self.conn:
            for path in sorted(stale):
                self.conn.execute(
                    """
                    DELETE FROM edges
                    WHERE src_id = ?
                       OR src_id LIKE ?
                       OR src_id IN (SELECT id FROM symbols WHERE file_path = ?);
                    """,
                    (path, f"{path}::%", path),
                )
                self.conn.execute("DELETE FROM findings WHERE file_path = ?;", (path,))
                self.conn.execute("DELETE FROM symbols WHERE file_path = ?;", (path,))
                self.conn.execute("DELETE FROM files WHERE path = ?;", (path,))
        return len(stale)

    # ------------------------------------------------------------------
    # Graph & audit queries (human + AI agents)
    # ------------------------------------------------------------------

    def get_symbol_neighborhood(self, symbol_id: str, depth: int = 1) -> dict[str, Any]:
        """Return direct callers and callees up to `depth` hops.

        Each returned neighbor includes `is_test` (`0` or `1`) so consumers can
        distinguish production dependencies from associated tests.

        Args:
            symbol_id: Canonical symbol ID.
            depth: Maximum traversal depth (>= 1).

        Returns:
            Dictionary with keys `target`, `callers`, and `callees`.
        """
        bounded_depth = max(1, depth)
        callees = self.conn.execute(
            """
            WITH RECURSIVE walk(id, level) AS (
                SELECT dst_id, 1 FROM edges
                WHERE src_id = ? AND kind IN ('CALLS', 'IMPORTS', 'INHERITS')
                UNION
                SELECT e.dst_id, w.level + 1
                FROM edges e
                JOIN walk w ON e.src_id = w.id
                WHERE w.level < ? AND e.kind IN ('CALLS', 'IMPORTS', 'INHERITS')
            )
            SELECT DISTINCT
                w.id,
                w.level,
                s.file_path,
                s.kind,
                s.signature,
                COALESCE(f.is_test, 0) AS is_test
            FROM walk w
            LEFT JOIN symbols s ON s.id = w.id
            LEFT JOIN files f ON f.path = s.file_path
            ORDER BY w.level, w.id;
            """,
            (symbol_id, bounded_depth),
        ).fetchall()

        callers = self.conn.execute(
            """
            WITH RECURSIVE walk(id, level) AS (
                SELECT src_id, 1 FROM edges
                WHERE dst_id = ? AND kind IN ('CALLS', 'IMPORTS', 'INHERITS')
                UNION
                SELECT e.src_id, w.level + 1
                FROM edges e
                JOIN walk w ON e.dst_id = w.id
                WHERE w.level < ? AND e.kind IN ('CALLS', 'IMPORTS', 'INHERITS')
            )
            SELECT DISTINCT
                w.id,
                w.level,
                s.file_path,
                s.kind,
                s.signature,
                COALESCE(f.is_test, 0) AS is_test
            FROM walk w
            LEFT JOIN symbols s ON s.id = w.id
            LEFT JOIN files f ON f.path = s.file_path
            ORDER BY w.level, w.id;
            """,
            (symbol_id, bounded_depth),
        ).fetchall()

        return {
            "target": symbol_id,
            "callers": [dict(r) for r in callers],
            "callees": [dict(r) for r in callees],
        }

    def detect_import_cycles(self, max_depth: int = 6) -> list[list[str]]:
        """Detect internal module import cycles across production files.

        Uses a polynomial `WITH RECURSIVE ... UNION` reachability CTE in SQLite
        to isolate cyclic production import edges, then reconstructs canonical
        shortest cycles up to `max_depth` via BFS.

        Args:
            max_depth: Maximum cycle ring length returned.

        Returns:
            List of canonical import cycles as `[a.py, ..., a.py]`.
        """
        bounded_depth = max(2, max_depth)
        rows = self.conn.execute(
            """
            WITH RECURSIVE
            module_imports(src_file, dst_file) AS MATERIALIZED (
                SELECT DISTINCT
                    CASE
                        WHEN instr(e.src_id, '::') > 0
                        THEN substr(e.src_id, 1, instr(e.src_id, '::') - 1)
                        ELSE e.src_id
                    END AS src_file,
                    CASE
                        WHEN instr(e.dst_id, '::') > 0
                        THEN substr(e.dst_id, 1, instr(e.dst_id, '::') - 1)
                        ELSE e.dst_id
                    END AS dst_file
                FROM edges e
                WHERE e.kind = 'IMPORTS' AND e.target_scope = 'INTERNAL'
            ),
            prod_imports(src_file, dst_file) AS MATERIALIZED (
                SELECT mi.src_file, mi.dst_file
                FROM module_imports mi
                JOIN files f_src ON f_src.path = mi.src_file
                JOIN files f_dst ON f_dst.path = mi.dst_file
                WHERE mi.src_file != mi.dst_file
                  AND f_src.is_test = 0
                  AND f_dst.is_test = 0
            ),
            reach(start_node, current_node) AS (
                SELECT src_file, dst_file FROM prod_imports
                UNION
                SELECT r.start_node, p.dst_file
                FROM reach r
                JOIN prod_imports p ON r.current_node = p.src_file
            )
            SELECT p.src_file, p.dst_file
            FROM prod_imports p
            JOIN reach r ON r.start_node = p.dst_file AND r.current_node = p.src_file
            ORDER BY p.src_file, p.dst_file;
            """
        ).fetchall()

        if not rows:
            return []

        adj: dict[str, list[str]] = defaultdict(list)
        cyclic_edges: list[tuple[str, str]] = []
        for row in rows:
            u = str(row["src_file"])
            v = str(row["dst_file"])
            adj[u].append(v)
            cyclic_edges.append((u, v))

        seen: set[tuple[str, ...]] = set()
        for u, v in cyclic_edges:
            path = self._shortest_path_bfs(adj, start=v, goal=u, max_nodes=bounded_depth)
            if path is None:
                continue
            ring = [u, *path[:-1]]
            if len(ring) > bounded_depth:
                continue
            min_idx = min(range(len(ring)), key=ring.__getitem__)
            rotated = [*ring[min_idx:], *ring[:min_idx]]
            seen.add(tuple([*rotated, rotated[0]]))

        return [list(cycle) for cycle in sorted(seen)]

    @staticmethod
    def _shortest_path_bfs(
        adj: dict[str, list[str]],
        start: str,
        goal: str,
        max_nodes: int,
    ) -> list[str] | None:
        queue: deque[list[str]] = deque([[start]])
        visited: set[str] = {start}
        while queue:
            path = queue.popleft()
            curr = path[-1]
            if curr == goal:
                return path
            if len(path) >= max_nodes:
                continue
            for nxt in adj.get(curr, ()):
                if nxt == goal:
                    return [*path, nxt]
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append([*path, nxt])
        return None

    def get_block_dependencies(self, include_tests: bool = False) -> list[dict[str, Any]]:
        """Aggregate internal edges between distinct functional blocks.

        Args:
            include_tests: When `False` (default), excludes edges originating
                from or targeting test files (`is_test = 1`).

        Returns:
            List of `{src_block, dst_block, kind, edge_count}` records.
        """
        test_filter = "" if include_tests else "AND f_src.is_test = 0 AND f_dst.is_test = 0"
        rows = self.conn.execute(
            f"""
            WITH projected_edges AS (
                SELECT
                    CASE
                        WHEN instr(src_id, '::') > 0
                        THEN substr(src_id, 1, instr(src_id, '::') - 1)
                        ELSE src_id
                    END AS src_file,
                    CASE
                        WHEN instr(dst_id, '::') > 0
                        THEN substr(dst_id, 1, instr(dst_id, '::') - 1)
                        ELSE dst_id
                    END AS dst_file,
                    kind,
                    weight
                FROM edges
                WHERE target_scope = 'INTERNAL'
            )
            SELECT
                f_src.block_id AS src_block,
                f_dst.block_id AS dst_block,
                pe.kind,
                SUM(pe.weight) AS edge_count
            FROM projected_edges pe
            JOIN files f_src ON pe.src_file = f_src.path
            JOIN files f_dst ON pe.dst_file = f_dst.path
            WHERE f_src.block_id != f_dst.block_id
              {test_filter}
            GROUP BY f_src.block_id, f_dst.block_id, pe.kind
            ORDER BY edge_count DESC, src_block ASC, dst_block ASC;
            """
        ).fetchall()
        return [dict(r) for r in rows]

    def get_block_risk_summary(self, include_tests: bool = False) -> list[dict[str, Any]]:
        """Return per-block summary: file count, LOC, findings, and sensitive sinks.

        Pre-aggregates findings per file before joining to prevent LOC duplication
        when a file has multiple findings.

        Args:
            include_tests: When `False` (default), summarizes production blocks only.

        Returns:
            List of block summary dictionaries ordered by risk descending.
        """
        test_filter = "" if include_tests else "WHERE f.is_test = 0"
        rows = self.conn.execute(
            f"""
            WITH file_findings AS (
                SELECT
                    file_path,
                    COUNT(*) AS total_findings,
                    SUM(CASE WHEN severity IN ('CRITICAL', 'HIGH') THEN 1 ELSE 0 END)
                        AS high_risk_findings,
                    SUM(CASE WHEN category = 'SINK' THEN 1 ELSE 0 END) AS sensitive_sinks
                FROM findings
                GROUP BY file_path
            )
            SELECT
                f.block_id,
                COUNT(f.path) AS file_count,
                COALESCE(SUM(f.loc), 0) AS total_loc,
                COALESCE(SUM(ff.total_findings), 0) AS total_findings,
                COALESCE(SUM(ff.high_risk_findings), 0) AS high_risk_findings,
                COALESCE(SUM(ff.sensitive_sinks), 0) AS sensitive_sinks
            FROM files f
            LEFT JOIN file_findings ff ON ff.file_path = f.path
            {test_filter}
            GROUP BY f.block_id
            ORDER BY high_risk_findings DESC, sensitive_sinks DESC, file_count DESC, f.block_id ASC;
            """
        ).fetchall()
        return [dict(r) for r in rows]


_DEFAULT_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL,
    block_id TEXT NOT NULL DEFAULT 'unassigned',
    loc INTEGER NOT NULL DEFAULT 0,
    is_test INTEGER NOT NULL DEFAULT 0,
    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS symbols (
    id TEXT PRIMARY KEY,
    file_path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    qualname TEXT NOT NULL,
    signature TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    docstring TEXT
);

CREATE TABLE IF NOT EXISTS edges (
    src_id TEXT NOT NULL,
    dst_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    target_scope TEXT NOT NULL DEFAULT 'INTERNAL',
    weight INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (src_id, dst_id, kind)
);

CREATE TABLE IF NOT EXISTS traces (
    usecase_id TEXT PRIMARY KEY,
    entry_symbol_id TEXT,
    sequence_json TEXT NOT NULL,
    coverage_ratio REAL DEFAULT 0.0,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
    symbol_id TEXT,
    tool TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    category TEXT NOT NULL,
    line INTEGER NOT NULL,
    message TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_files_block ON files(block_id);
CREATE INDEX IF NOT EXISTS idx_files_test ON files(is_test, block_id);
CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_path);
CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src_id, kind);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst_id, kind);
CREATE INDEX IF NOT EXISTS idx_edges_kind_scope ON edges(kind, target_scope);
CREATE INDEX IF NOT EXISTS idx_findings_file ON findings(file_path, severity);
CREATE INDEX IF NOT EXISTS idx_findings_symbol ON findings(symbol_id);

CREATE VIEW IF NOT EXISTS v_internal_module_edges AS
SELECT DISTINCT
    CASE
        WHEN instr(src_id, '::') > 0
        THEN substr(src_id, 1, instr(src_id, '::') - 1)
        ELSE src_id
    END AS src_file,
    CASE
        WHEN instr(dst_id, '::') > 0
        THEN substr(dst_id, 1, instr(dst_id, '::') - 1)
        ELSE dst_id
    END AS dst_file,
    kind,
    weight
FROM edges
WHERE target_scope = 'INTERNAL';

CREATE VIEW IF NOT EXISTS v_block_risk_summary AS
WITH file_findings AS (
    SELECT
        file_path,
        COUNT(*) AS total_findings,
        SUM(CASE WHEN severity IN ('CRITICAL', 'HIGH') THEN 1 ELSE 0 END) AS high_risk_findings,
        SUM(CASE WHEN category = 'SINK' THEN 1 ELSE 0 END) AS sensitive_sinks
    FROM findings
    GROUP BY file_path
)
SELECT
    f.block_id,
    COUNT(f.path) AS file_count,
    COALESCE(SUM(f.loc), 0) AS total_loc,
    COALESCE(SUM(ff.total_findings), 0) AS total_findings,
    COALESCE(SUM(ff.high_risk_findings), 0) AS high_risk_findings,
    COALESCE(SUM(ff.sensitive_sinks), 0) AS sensitive_sinks
FROM files f
LEFT JOIN file_findings ff ON ff.file_path = f.path
WHERE f.is_test = 0
GROUP BY f.block_id;
"""
