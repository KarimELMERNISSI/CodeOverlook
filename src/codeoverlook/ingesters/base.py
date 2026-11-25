"""Protocoles d'extension pour les producteurs de faits (Extractors, Tracers, Auditors)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from codeoverlook.core.store import FileParseResult, FindingRecord


@runtime_checkable
class StaticExtractor(Protocol):
    """Contrat d'un extracteur statique de symboles, dependances et sinks par fichier."""

    def iter_python_files(self) -> list[Path]:
        """Liste les fichiers sources eligibles a l'indexation dans le depot."""
        ...

    def parse_file(self, file_path: Path) -> FileParseResult | None:
        """Analyse un fichier source et retourne ses faits ou `None` en cas d'echec E/S."""
        ...


@runtime_checkable
class RuntimeTracer(Protocol):
    """Contrat d'un traceur d'execution (MVP 2) enregistrant les flux reels."""

    def start(self, usecase_id: str) -> None:
        """Demarre la capture filtree pour un cas d'usage donne."""
        ...

    def stop(self) -> list[str]:
        """Arrete la capture et retourne la sequence compressee d'identifiants de symboles."""
        ...


@runtime_checkable
class SecurityAuditor(Protocol):
    """Contrat d'un adaptateur d'audit de securite externe (MVP 3, ex. SARIF)."""

    def ingest_report(self, report_path: Path) -> Sequence[FindingRecord]:
        """Convertit un rapport externe en enregistrements `FindingRecord` normalises."""
        ...
