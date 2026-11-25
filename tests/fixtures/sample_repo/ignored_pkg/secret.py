"""Module exclu par ignored_pkg/**."""

from __future__ import annotations


def ignored_eval(expr: str) -> object:
    """Ne doit pas apparaitre dans l'index."""
    return eval(expr)
