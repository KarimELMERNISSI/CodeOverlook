"""Tests de detection des cycles d'imports, surfaces sensibles (sinks) et resilience AST."""

from __future__ import annotations

from pathlib import Path

from codeoverlook.core.store import FactStore
from codeoverlook.interfaces.cli import main


def test_detect_import_cycle_between_internal_modules(sample_repo: Path) -> None:
    """Detecte le cycle mutuel `engine/helper.py <-> engine/service.py` via `from ... import`."""
    assert main(["scan", str(sample_repo)]) == 0

    with FactStore(sample_repo / ".codeoverlook" / "index.db") as store:
        cycles = store.detect_import_cycles()

    assert len(cycles) == 1
    cycle = cycles[0]
    assert cycle[0] == cycle[-1]
    assert set(cycle) == {"engine/helper.py", "engine/service.py"}


def test_detect_sinks_without_false_positives(sample_repo: Path) -> None:
    """Detecte SQL dynamique et zipfile.ZipFile sans faux positif sur requete sure."""
    assert main(["scan", str(sample_repo)]) == 0

    with FactStore(sample_repo / ".codeoverlook" / "index.db") as store:
        rows = [
            dict(r)
            for r in store.conn.execute(
                "SELECT file_path, symbol_id, rule_id, severity, category "
                "FROM findings ORDER BY file_path, line;"
            ).fetchall()
        ]

    rule_ids = {r["rule_id"] for r in rows}
    assert "SINK-SQL-01" in rule_ids
    assert "SINK-ARCHIVE-01" in rule_ids
    assert len(rows) == 2

    sql_finding = next(r for r in rows if r["rule_id"] == "SINK-SQL-01")
    assert sql_finding["file_path"] == "storage/db.py"
    assert sql_finding["symbol_id"] == "storage/db.py::fetch_records"
    assert sql_finding["severity"] == "HIGH"
    assert sql_finding["category"] == "SINK"

    zip_finding = next(r for r in rows if r["rule_id"] == "SINK-ARCHIVE-01")
    assert zip_finding["file_path"] == "storage/archive.py"
    assert zip_finding["symbol_id"] == "storage/archive.py::extract_bundle"
    assert zip_finding["severity"] == "MEDIUM"


def test_syntax_error_is_recorded_resiliently(sample_repo: Path) -> None:
    """Un fichier Python syntaxiquement invalide produit `PARSE-SYNTAX-ERR` sans crash."""
    broken = sample_repo / "engine" / "broken.py"
    broken.write_text("def incomplete(:\n    pass\n", encoding="utf-8")

    assert main(["scan", str(sample_repo)]) == 0

    with FactStore(sample_repo / ".codeoverlook" / "index.db") as store:
        row = store.conn.execute(
            "SELECT rule_id, severity, category FROM findings WHERE file_path = 'engine/broken.py';"
        ).fetchone()

    assert row is not None
    assert row["rule_id"] == "PARSE-SYNTAX-ERR"
    assert row["severity"] == "MEDIUM"
    assert row["category"] == "ARCH"
