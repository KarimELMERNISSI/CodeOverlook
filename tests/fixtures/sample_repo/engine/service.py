"""Service analytique avec cycle d'imports et appels inter-blocs."""

from __future__ import annotations

from dataclasses import dataclass

from storage.archive import extract_bundle
from storage.db import fetch_records

from engine.helper import normalize


@dataclass(frozen=True)
class ServiceConfig:
    """Configuration du service de rapport."""

    environment: str = "local"


class ReportBuilder:
    """Construit les syntheses analytiques a partir des enregistrements."""

    def build_summary(self, owner: str, limit: int = 10) -> list[str]:
        """Normalise le nom du proprietaire et retourne les entrees filtrees."""
        clean_owner = normalize(owner)
        rows = fetch_records(clean_owner)
        return rows[:limit]


def run_report(owner: str, bundle_path: str | None = None) -> list[str]:
    """Point d'entree metier orchestrant stockage et decompression."""
    if bundle_path:
        extract_bundle(bundle_path, "/tmp/out")
    builder = ReportBuilder()
    return builder.build_summary(owner)
