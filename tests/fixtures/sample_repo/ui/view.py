"""Vue UI de test violant intentionnellement la frontiere vers storage."""

from __future__ import annotations

from engine.service import run_report
from storage.db import DEFAULT_DSN


def render_dashboard(owner: str) -> dict[str, object]:
    """Genere les donnees affichees dans le tableau de bord."""
    payload = run_report(owner)
    return {"dsn": DEFAULT_DSN, "payload": payload}
