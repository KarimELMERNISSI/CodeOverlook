"""Compact subgraph extraction under strict token budgets for AI agents."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codeoverlook.core.store import FactStore
from codeoverlook.views.markdown import (
    format_findings_lines,
    format_header,
    format_neighbor_line,
    format_source_block,
)

TRUNCATION_CODE_MARKER = "# ... [tronque par budget tokens]"
TRUNCATION_REL_LINE = "- *... [autres relations omises par budget tokens]*"


@dataclass(slots=True)
class SliceResult:
    """Formatted output from `ContextSlicer.slice_target`."""

    target: str
    markdown: str
    estimated_tokens: int
    truncated: bool = False


class ContextSlicer:
    """Extract a compact, verifiable Markdown context bounded by token budget.

    Strict priority order under budget constraints:
    1. Functional block header, signature, and test association count.
    2. Active security findings and sensitive sinks (`findings`).
    3. Exact target symbol source code (cleanly truncated if needed).
    4. Signatures only (no bodies) for k-hop production callers, associated
       test callers, and callees.
    """

    def __init__(self, store: FactStore, repo_root: Path) -> None:
        """Initialize the slicer with an active `FactStore` and repository root.

        Args:
            store: Open `FactStore` instance.
            repo_root: Target repository root directory.
        """
        self.store = store
        self.repo_root = repo_root.resolve()

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return max(1, len(text) // 4)

    def _resolve_symbol(self, target: str) -> dict[str, Any] | None:
        row = self.store.conn.execute(
            "SELECT * FROM symbols WHERE id = ?;", (target,)
        ).fetchone()
        if row:
            return dict(row)

        row = self.store.conn.execute(
            """
            SELECT * FROM symbols
            WHERE id LIKE ? OR qualname = ? OR name = ?
            ORDER BY length(id) ASC
            LIMIT 1;
            """,
            (f"%{target}", target, target),
        ).fetchone()
        return dict(row) if row else None

    def _read_source_span(self, rel_path: str, start_line: int, end_line: int) -> str:
        full_path = self.repo_root / rel_path
        try:
            raw_text = full_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return f"# [Fichier inaccessible sur disque : {exc}]"

        lines = raw_text.splitlines()
        if start_line == 1 and end_line == 1:
            snippet = lines[:120]
        else:
            snippet = lines[max(0, start_line - 1) : end_line]
        return "\n".join(snippet)

    def _fetch_findings(self, file_path: str, sym_id: str) -> list[dict[str, Any]]:
        rows = self.store.conn.execute(
            """
            SELECT severity, category, rule_id, line, message
            FROM findings
            WHERE file_path = ? AND (symbol_id = ? OR symbol_id IS NULL)
            ORDER BY
                CASE severity
                    WHEN 'CRITICAL' THEN 1
                    WHEN 'HIGH' THEN 2
                    WHEN 'MEDIUM' THEN 3
                    WHEN 'LOW' THEN 4
                    ELSE 5
                END,
                line ASC;
            """,
            (file_path, sym_id),
        ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _join_sections(sections: list[str]) -> str:
        return "\n\n".join(s.strip("\n") for s in sections if s.strip()) + "\n"

    def _append_findings_section(
        self,
        sections: list[str],
        findings: list[dict[str, Any]],
        char_budget: int,
    ) -> bool:
        if not findings:
            return False
        lines = format_findings_lines(findings)
        title = lines[0]
        accepted: list[str] = [title]
        truncated = False

        for line in lines[1:]:
            candidate = self._join_sections(sections + ["\n".join(accepted + [line])])
            if len(candidate) <= char_budget:
                accepted.append(line)
            else:
                truncated = True
                break

        if len(accepted) > 1:
            sections.append("\n".join(accepted))
        return truncated

    def _append_source_section(
        self,
        sections: list[str],
        source_code: str,
        char_budget: int,
    ) -> bool:
        full_block = format_source_block(source_code, truncated=False)
        if len(self._join_sections(sections + [full_block])) <= char_budget:
            sections.append(full_block)
            return False

        empty_truncated_block = format_source_block(TRUNCATION_CODE_MARKER, truncated=True)
        overhead = len(self._join_sections(sections + [empty_truncated_block]))
        available_for_code = char_budget - overhead - 1

        if available_for_code > 0:
            clipped = source_code[:available_for_code].rstrip()
            payload = f"{clipped}\n{TRUNCATION_CODE_MARKER}" if clipped else TRUNCATION_CODE_MARKER
            sections.append(format_source_block(payload, truncated=True))
            return True

        return True

    def _append_neighborhood_section(
        self,
        sections: list[str],
        label: str,
        items: list[dict[str, Any]],
        char_budget: int,
    ) -> bool:
        if not items:
            return False

        accepted: list[str] = [f"## {label}"]
        truncated = False

        for item in items:
            line = format_neighbor_line(item)
            candidate_with_line = self._join_sections(sections + ["\n".join(accepted + [line])])

            if len(candidate_with_line) <= char_budget:
                accepted.append(line)
            else:
                candidate_with_marker = self._join_sections(
                    sections + ["\n".join(accepted + [TRUNCATION_REL_LINE])]
                )
                if len(candidate_with_marker) <= char_budget:
                    accepted.append(TRUNCATION_REL_LINE)
                truncated = True
                break

        if len(accepted) > 1:
            sections.append("\n".join(accepted))
        return truncated

    def slice_target(self, target: str, token_budget: int = 3000, depth: int = 1) -> SliceResult:
        """Extract a Markdown context bounded by `token_budget` for a symbol or file.

        Args:
            target: Exact symbol ID, `qualname`, `name`, or path suffix.
            token_budget: Maximum estimated token budget (>= 1).
            depth: Neighborhood traversal depth (>= 1).

        Returns:
            `SliceResult` strictly satisfying `estimated_tokens <= token_budget`.
        """
        safe_budget = max(1, token_budget)
        char_budget = safe_budget * 4

        try:
            symbol = self._resolve_symbol(target)
        except sqlite3.Error as exc:
            msg = (
                "# Context Slice -- Erreur d'index\n\n"
                f"Impossible de lire l'index SQLite : {exc}\n"
            )
            return self._finalize_result(target, msg, safe_budget, truncated=False)

        if not symbol:
            msg = (
                "# Context Slice -- Introuvable\n\n"
                f"Aucun symbole ou fichier correspondant a `{target}`.\n"
            )
            return self._finalize_result(target, msg, safe_budget, truncated=False)

        sym_id = str(symbol["id"])
        file_path = str(symbol["file_path"])

        try:
            file_row = self.store.conn.execute(
                "SELECT block_id, loc FROM files WHERE path = ?;", (file_path,)
            ).fetchone()
            block_id = str(file_row["block_id"]) if file_row else "unassigned"
            neighborhood = self.store.get_symbol_neighborhood(sym_id, depth=depth)
            findings = self._fetch_findings(file_path, sym_id)
        except sqlite3.Error as exc:
            msg = f"# Context Slice -- Erreur de requete\n\nErreur SQLite sur `{sym_id}` : {exc}\n"
            return self._finalize_result(sym_id, msg, safe_budget, truncated=False)

        prod_callers = [c for c in neighborhood["callers"] if int(c.get("is_test", 0)) == 0]
        test_callers = [c for c in neighborhood["callers"] if int(c.get("is_test", 0)) == 1]

        sections: list[str] = []
        truncated = False

        # 1. Header (Priority 1)
        header = format_header(symbol, block_id, test_count=len(test_callers))
        if len(header) + 1 <= char_budget:
            sections.append(header)
        else:
            sections.append(header[: max(1, char_budget - 1)])
            truncated = True

        # 2. Active findings and sensitive sinks (Priority 2)
        if self._append_findings_section(sections, findings, char_budget):
            truncated = True

        # 3. Target source code (Priority 3)
        source_code = self._read_source_span(
            file_path, int(symbol["start_line"]), int(symbol["end_line"])
        )
        if self._append_source_section(sections, source_code, char_budget):
            truncated = True

        # 4. k-hop neighborhood signatures only (Priority 4)
        for label, items in (
            ("Appelants directs (Callers)", prod_callers),
            ("Tests associes (Test Callers)", test_callers),
            ("Dependances / Appeles (Callees)", neighborhood["callees"]),
        ):
            if self._append_neighborhood_section(sections, label, items, char_budget):
                truncated = True

        markdown = self._join_sections(sections)
        return self._finalize_result(sym_id, markdown, safe_budget, truncated=truncated)

    def _finalize_result(
        self,
        target: str,
        markdown: str,
        token_budget: int,
        truncated: bool,
    ) -> SliceResult:
        char_budget = max(1, token_budget) * 4
        if len(markdown) > char_budget:
            markdown = markdown[: max(1, char_budget - 1)].rstrip() + "\n"
            truncated = True
        return SliceResult(
            target=target,
            markdown=markdown,
            estimated_tokens=self._estimate_tokens(markdown),
            truncated=truncated,
        )
