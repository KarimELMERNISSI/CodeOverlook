"""Gestion d'archives et de YAML de test."""

from __future__ import annotations

import zipfile
from typing import Any


def extract_bundle(bundle_path: str, dest_dir: str) -> list[str]:
    """Ouvre une archive ZIP (sink ZipFile intentionnel)."""
    with zipfile.ZipFile(bundle_path, "r") as zf:
        zf.extractall(dest_dir)
        return zf.namelist()


def parse_safe_manifest(yaml_mod: Any, raw_text: str) -> Any:
    """Charge du YAML avec SafeLoader (ne doit pas declencher d'alerte)."""
    return yaml_mod.load(raw_text, Loader=yaml_mod.SafeLoader)
