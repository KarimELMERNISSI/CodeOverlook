"""Utilitaires de normalisation formant un cycle d'imports avec engine.service."""

from __future__ import annotations

from engine.service import ServiceConfig


def normalize(value: str) -> str:
    """Nettoie une chaine utilisateur selon la configuration courante."""
    _cfg = ServiceConfig()
    return value.strip().lower()
