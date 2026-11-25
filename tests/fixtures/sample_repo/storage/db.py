"""Acces base de donnees de test avec un sink SQL dynamique et une requete sure."""

from __future__ import annotations

import sqlite3

DEFAULT_DSN = "sqlite:///:memory:"


def fetch_records(owner: str) -> list[str]:
    """Recupere les enregistrements par requete dynamique (sink intentionnel)."""
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    cursor.execute(f"SELECT name FROM records WHERE owner = '{owner}'")
    return [str(row[0]) for row in cursor.fetchall()]


def fetch_by_id(rec_id: int) -> str | None:
    """Recupere un enregistrement par requete parametree sure."""
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM records WHERE id = ?", (rec_id,))
    row = cursor.fetchone()
    return str(row[0]) if row else None
