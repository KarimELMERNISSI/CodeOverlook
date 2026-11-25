"""Script de migration devant etre exclu par **/migrations/**."""

from __future__ import annotations

import os


def migrate() -> None:
    """Contient un sink volontaire qui ne doit pas etre indexe."""
    os.system("echo migration")
