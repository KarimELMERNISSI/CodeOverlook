"""Shared fixtures for the CodeOverlook pytest suite."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "sample_repo"


@pytest.fixture()
def sample_repo(tmp_path: Path) -> Path:
    """Copie le mini-depot synthetique dans `tmp_path/repo` pour garantir l'isolation."""
    target = tmp_path / "repo"
    shutil.copytree(FIXTURES_DIR, target)
    return target
