"""Tests de l'indexation incrementale (hash SHA-256, mise a jour partielle, pruning)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from codeoverlook.core.blocks import BlockResolver
from codeoverlook.core.store import FactStore
from codeoverlook.ingesters.python_ast import PythonASTIngester
from codeoverlook.interfaces.cli import main


def _run_incremental_scan(repo_root: Path, force: bool = False) -> tuple[int, int, int]:
    db_path = repo_root / ".codeoverlook" / "index.db"
    resolver = BlockResolver(repo_root)
    ingester = PythonASTIngester(
        repo_root,
        block_resolver=resolver.resolve,
        exclude_checker=resolver.is_excluded,
    )
    reindexed = 0
    skipped = 0
    active_paths: list[str] = []

    with FactStore(db_path) as store:
        store.init_schema()
        for py_file in ingester.iter_python_files():
            rel = py_file.relative_to(repo_root).as_posix()
            active_paths.append(rel)
            sha = hashlib.sha256(py_file.read_bytes()).hexdigest()
            if force or store.needs_reindex(rel, sha):
                parsed = ingester.parse_file(py_file)
                if parsed is not None:
                    store.replace_file_facts(parsed)
                    reindexed += 1
            else:
                skipped += 1
        pruned = store.prune_deleted_files(active_paths)

    return reindexed, skipped, pruned


def test_incremental_scan_skip_modify_and_prune(sample_repo: Path) -> None:
    """Verify hash-based skip, targeted re-indexing, and deleted-file pruning."""
    # 1. Initial scan: all eligible production + test files are indexed.
    reindexed, skipped, pruned = _run_incremental_scan(sample_repo)
    total_files = reindexed
    assert total_files == 9  # ui(2) + engine(3) + storage(3) + tests(1); excluded ignored
    assert skipped == 0
    assert pruned == 0

    # 2. Second scan sans modification : aucun fichier ne doit etre re-parse.
    reindexed_2, skipped_2, pruned_2 = _run_incremental_scan(sample_repo)
    assert reindexed_2 == 0
    assert skipped_2 == total_files
    assert pruned_2 == 0

    # 3. Modification d'un seul fichier : seul ce fichier est re-indexe.
    helper_path = sample_repo / "engine" / "helper.py"
    helper_path.write_text(
        helper_path.read_text(encoding="utf-8") + "\n\ndef extra_fn() -> int:\n    return 42\n",
        encoding="utf-8",
    )
    reindexed_3, skipped_3, pruned_3 = _run_incremental_scan(sample_repo)
    assert reindexed_3 == 1
    assert skipped_3 == total_files - 1
    assert pruned_3 == 0

    # 4. Suppression d'un fichier : purge atomique du fichier, de ses symboles et findings.
    db_target = sample_repo / "storage" / "archive.py"
    db_target.unlink()
    reindexed_4, skipped_4, pruned_4 = _run_incremental_scan(sample_repo)
    assert reindexed_4 == 0
    assert skipped_4 == total_files - 1
    assert pruned_4 == 1

    with FactStore(sample_repo / ".codeoverlook" / "index.db") as store:
        hashes = store.get_file_hashes()
        assert "storage/archive.py" not in hashes
        sym_count = store.conn.execute(
            "SELECT COUNT(*) FROM symbols WHERE file_path = 'storage/archive.py';"
        ).fetchone()[0]
        finding_count = store.conn.execute(
            "SELECT COUNT(*) FROM findings WHERE file_path = 'storage/archive.py';"
        ).fetchone()[0]
        edge_count = store.conn.execute(
            "SELECT COUNT(*) FROM edges WHERE src_id LIKE 'storage/archive.py%';"
        ).fetchone()[0]
        assert sym_count == 0
        assert finding_count == 0
        assert edge_count == 0


def test_force_scan_reindexes_all_files(sample_repo: Path, capsys: object) -> None:
    """Verify `--force` CLI flag re-indexes all files."""
    assert main(["scan", str(sample_repo)]) == 0
    assert main(["scan", str(sample_repo), "--force"]) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "9 indexed, 0 unchanged, 0 pruned." in captured.out
