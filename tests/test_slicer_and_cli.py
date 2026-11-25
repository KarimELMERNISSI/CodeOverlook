"""Tests du ContextSlicer sous contrainte de budget tokens et de la CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codeoverlook.core.slicer import ContextSlicer
from codeoverlook.core.store import FactStore
from codeoverlook.interfaces.cli import main


def test_slicer_priority_order_and_one_hop_signatures(sample_repo: Path) -> None:
    """Verifie l'ordre de priorite et l'absence du corps des voisins 1-hop."""
    assert main(["scan", str(sample_repo)]) == 0

    with FactStore(sample_repo / ".codeoverlook" / "index.db") as store:
        slicer = ContextSlicer(store, sample_repo)
        result = slicer.slice_target("ReportBuilder.build_summary", token_budget=3000, depth=1)

    md = result.markdown
    assert "# Context Slice: `engine/service.py::ReportBuilder.build_summary`" in md
    assert "- **Bloc fonctionnel :** `engine`" in md
    assert "## Code source cible" in md
    assert "def build_summary(self, owner: str, limit: int = 10) -> list[str]:" in md
    assert "## Appelants directs (Callers)" in md
    assert "engine/service.py::run_report" in md
    assert "## Dependances / Appeles (Callees)" in md
    assert "storage/db.py::fetch_records" in md
    # Le corps du voisin (ex. sqlite3.connect) ne doit jamais etre injecte.
    assert 'sqlite3.connect(":memory:")' not in md
    assert result.estimated_tokens <= 3000


def test_slicer_includes_findings_before_source(sample_repo: Path) -> None:
    """Les alertes et sinks actifs apparaissent avant le code source cible."""
    assert main(["scan", str(sample_repo)]) == 0

    with FactStore(sample_repo / ".codeoverlook" / "index.db") as store:
        slicer = ContextSlicer(store, sample_repo)
        result = slicer.slice_target("fetch_records", token_budget=2000, depth=1)

    md = result.markdown
    idx_alerts = md.index("## Alertes & Surfaces sensibles actives")
    idx_source = md.index("## Code source cible")
    assert idx_alerts < idx_source
    assert "SINK-SQL-01" in md
    assert result.estimated_tokens <= 2000


@pytest.mark.parametrize("budget", [40, 80, 140, 220, 400, 3000])
def test_slicer_strictly_respects_token_budget(sample_repo: Path, budget: int) -> None:
    """Invariant strict : `estimated_tokens <= budget` meme sous forte contrainte."""
    assert main(["scan", str(sample_repo)]) == 0

    with FactStore(sample_repo / ".codeoverlook" / "index.db") as store:
        slicer = ContextSlicer(store, sample_repo)
        result = slicer.slice_target("ReportBuilder.build_summary", token_budget=budget, depth=1)

    assert result.estimated_tokens <= budget
    if budget <= 140:
        assert result.truncated is True


def test_slicer_missing_symbol_returns_explicit_message(sample_repo: Path) -> None:
    """Un symbole inconnu retourne une reponse explicite sans lever d'exception."""
    assert main(["scan", str(sample_repo)]) == 0

    with FactStore(sample_repo / ".codeoverlook" / "index.db") as store:
        slicer = ContextSlicer(store, sample_repo)
        result = slicer.slice_target("symbole_inexistant", token_budget=500)

    assert "Introuvable" in result.markdown
    assert result.estimated_tokens <= 500


def test_cli_blocks_slice_mermaid_and_missing_index(
    sample_repo: Path,
    tmp_path: Path,
    capsys: object,
) -> None:
    """Teste les sous-commandes CLI de bout en bout et la gestion d'un depot non indexe."""
    # Depot non indexe -> code retour 1 et message d'erreur explicite.
    empty_repo = tmp_path / "empty_repo"
    empty_repo.mkdir()
    assert main(["blocks", str(empty_repo)]) == 1
    assert main(["slice", "x", "--repo", str(empty_repo)]) == 1
    assert main(["mermaid", str(empty_repo)]) == 1
    _ = capsys.readouterr()  # type: ignore[attr-defined]

    assert main(["scan", str(sample_repo)]) == 0
    _ = capsys.readouterr()  # type: ignore[attr-defined]

    # blocks --json
    assert main(["blocks", str(sample_repo), "--json"]) == 0
    blocks_out = capsys.readouterr().out  # type: ignore[attr-defined]
    payload = json.loads(blocks_out)
    block_ids = {b["block_id"] for b in payload["blocks"]}
    assert block_ids == {"ui", "engine", "storage"}

    # blocks tableau texte
    assert main(["blocks", str(sample_repo)]) == 0
    table_out = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "BLOC" in table_out
    assert "storage" in table_out

    # slice
    assert main(["slice", "run_report", "--repo", str(sample_repo), "--budget", "1500"]) == 0
    slice_out = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "engine/service.py::run_report" in slice_out

    # mermaid
    assert main(["mermaid", str(sample_repo)]) == 0
    mermaid_out = capsys.readouterr().out  # type: ignore[attr-defined]
    assert mermaid_out.startswith("graph LR")
    assert "ui -->|1| storage" in mermaid_out
    assert "style storage fill:#fde2e2" in mermaid_out
