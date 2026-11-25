"""Tests de resolution des blocs fonctionnels, exclusions et violations d'architecture."""

from __future__ import annotations

from pathlib import Path

from codeoverlook.core.blocks import BlockResolver, matches_glob
from codeoverlook.core.store import FactStore
from codeoverlook.interfaces.cli import main


def test_block_resolution_exclusions_and_arch_violation(sample_repo: Path) -> None:
    """Verify `.codeoverlook.toml`, exclude globs, and `ui -> storage` violation."""
    assert main(["scan", str(sample_repo)]) == 0

    resolver = BlockResolver(sample_repo)
    assert resolver.is_excluded("ignored_pkg/secret.py") is True
    assert resolver.is_excluded("storage/migrations/001_init.py") is True
    assert resolver.is_excluded("ui/view.py") is False

    assert resolver.resolve("ui/view.py") == "ui"
    assert resolver.resolve("engine/service.py") == "engine"
    assert resolver.resolve("storage/db.py") == "storage"

    with FactStore(sample_repo / ".codeoverlook" / "index.db") as store:
        hashes = store.get_file_hashes()
        assert "ignored_pkg/secret.py" not in hashes
        assert "storage/migrations/001_init.py" not in hashes

        deps = store.get_block_dependencies()
        violations = resolver.check_violations(deps)

    assert any(
        v["src_block"] == "ui" and v["dst_block"] == "storage"
        for v in violations
    )


def test_fallback_block_resolver_and_glob_matching(tmp_path: Path) -> None:
    """Verifie le fallback heuristique (`root` et `src/<pkg>/<bloc>`) et les globs `**`."""
    resolver = BlockResolver(tmp_path)
    assert resolver.resolve("setup.py") == "root"
    assert resolver.resolve("src/codeoverlook/__init__.py") == "codeoverlook"
    assert resolver.resolve("src/codeoverlook/core/store.py") == "core"
    assert resolver.resolve("analytics/metrics.py") == "analytics"

    assert matches_glob("migrations/001.py", "**/migrations/**") is True
    assert matches_glob("storage/migrations/001.py", "**/migrations/**") is True
    assert matches_glob("storage/my_migrations/001.py", "**/migrations/**") is False
    assert matches_glob("src/migrations/001.py", "src/**/migrations/**") is True


def test_block_risk_summary_does_not_multiply_loc_with_multiple_findings(
    sample_repo: Path,
) -> None:
    """Plusieurs findings dans un meme fichier ne doivent pas multiplier `total_loc`."""
    db_file = sample_repo / "storage" / "db.py"
    db_file.write_text(
        db_file.read_text(encoding="utf-8")
        + "\n\ndef second_unsafe(q: str) -> None:\n    eval(q)\n",
        encoding="utf-8",
    )

    assert main(["scan", str(sample_repo)]) == 0

    with FactStore(sample_repo / ".codeoverlook" / "index.db") as store:
        summary = {b["block_id"]: b for b in store.get_block_risk_summary()}
        expected_loc = store.conn.execute(
            "SELECT SUM(loc) FROM files WHERE block_id = 'storage';"
        ).fetchone()[0]

    storage = summary["storage"]
    assert storage["total_loc"] == expected_loc
    assert storage["total_findings"] == 3  # SQL + eval dans db.py, ZipFile dans archive.py
    assert storage["high_risk_findings"] == 2  # SQL + eval


def test_invalid_toml_is_handled_gracefully(tmp_path: Path) -> None:
    """An invalid `.codeoverlook.toml` does not crash the resolver."""
    (tmp_path / ".codeoverlook.toml").write_text("blocks = [unclosed", encoding="utf-8")
    resolver = BlockResolver(tmp_path)
    assert len(resolver.config.warnings) == 1
    assert resolver.resolve("pkg/mod.py") == "pkg"
