"""Tests for test-to-block detection, coverage gap ranking, Mermaid and HTML views."""

from __future__ import annotations

import json
from pathlib import Path

from codeoverlook.core.coverage import TestCoverageAnalyzer
from codeoverlook.core.slicer import ContextSlicer
from codeoverlook.core.store import FactStore
from codeoverlook.interfaces.cli import main


def test_is_test_classification_and_codeoverlook_gitignore(sample_repo: Path) -> None:
    """Verify `is_test` persistence and automatic `.codeoverlook/.gitignore` creation."""
    assert main(["scan", str(sample_repo)]) == 0

    gitignore = sample_repo / ".codeoverlook" / ".gitignore"
    assert gitignore.exists()
    assert "*" in gitignore.read_text(encoding="utf-8")

    with FactStore(sample_repo / ".codeoverlook" / "index.db") as store:
        rows = {
            row["path"]: row["is_test"]
            for row in store.conn.execute("SELECT path, is_test FROM files;").fetchall()
        }

    assert rows["tests/test_engine.py"] == 1
    assert rows["engine/service.py"] == 0
    assert rows["storage/db.py"] == 0


def test_fixture_type_inference_links_test_to_engine_block(sample_repo: Path) -> None:
    """Pytest fixture return type resolves `report_builder.build_summary` to engine block."""
    assert main(["scan", str(sample_repo)]) == 0

    with FactStore(sample_repo / ".codeoverlook" / "index.db") as store:
        edges = store.conn.execute(
            """
            SELECT src_id, dst_id, kind
            FROM edges
            WHERE src_id = 'tests/test_engine.py::test_build_summary'
              AND target_scope = 'INTERNAL';
            """
        ).fetchall()
        report = TestCoverageAnalyzer(store).analyze()

    dst_ids = {row["dst_id"] for row in edges}
    assert "engine/service.py::ReportBuilder.build_summary" in dst_ids

    by_block = {b.block_id: b for b in report.blocks}
    assert by_block["engine"].test_files_count == 1
    assert by_block["engine"].test_functions_count == 1
    assert by_block["engine"].tested_files >= 1
    assert by_block["engine"].tested_symbols >= 2

    # ui and storage have zero test files covering them
    assert by_block["storage"].coverage_status == "UNTESTED"
    assert by_block["storage"].untested_sinks == 2
    assert by_block["ui"].coverage_status == "UNTESTED"

    # Untested storage with sinks ranks above already-covered engine
    assert report.blocks[0].block_id == "storage"
    assert report.untested_targets[0].block_id == "storage"


def test_context_slicer_separates_prod_and_test_callers(sample_repo: Path) -> None:
    """ContextSlicer renders test references in header and separate Test Callers section."""
    assert main(["scan", str(sample_repo)]) == 0

    with FactStore(sample_repo / ".codeoverlook" / "index.db") as store:
        slicer = ContextSlicer(store, sample_repo)
        covered = slicer.slice_target("ReportBuilder.build_summary", token_budget=2500)
        uncovered = slicer.slice_target("fetch_records", token_budget=2500)

    assert "- **Tests associes :** 1 reference(s) de test" in covered.markdown
    assert "## Appelants directs (Callers)" in covered.markdown
    assert "engine/service.py::run_report" in covered.markdown
    assert "## Tests associes (Test Callers)" in covered.markdown
    assert "tests/test_engine.py::test_build_summary" in covered.markdown
    assert covered.estimated_tokens <= 2500

    assert "- **Tests associes :** AUCUN (cible non couverte)" in uncovered.markdown
    assert uncovered.estimated_tokens <= 2500


def test_cli_tests_mermaid_coverage_and_html(sample_repo: Path, capsys: object) -> None:
    """Verify `tests`, `mermaid --mode coverage`, and `html` CLI subcommands."""
    assert main(["scan", str(sample_repo)]) == 0
    _ = capsys.readouterr()  # type: ignore[attr-defined]

    assert main(["tests", str(sample_repo), "--json"]) == 0
    tests_payload = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    assert tests_payload["summary"]["total_test_files"] == 1
    assert tests_payload["summary"]["linked_test_files"] == 1
    assert any(b["block_id"] == "storage" for b in tests_payload["blocks"])

    assert main(["tests", str(sample_repo), "--block", "engine"]) == 0
    block_out = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "tests/test_engine.py" in block_out

    assert main(["mermaid", str(sample_repo), "--mode", "coverage"]) == 0
    mermaid_out = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "test_suite" in mermaid_out
    assert "test_suite -.->|1 files| engine" in mermaid_out
    assert "fill:#fde2e2" in mermaid_out

    assert main(["html", str(sample_repo)]) == 0
    _ = capsys.readouterr()  # type: ignore[attr-defined]
    html_file = sample_repo / ".codeoverlook" / "overlook.html"
    assert html_file.exists()
    html_text = html_file.read_text(encoding="utf-8")
    assert "CodeOverlook Coverage &amp; Architecture Inspector" in html_text
    assert "tests/test_engine.py" in html_text
