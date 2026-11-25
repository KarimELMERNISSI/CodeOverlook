"""Pure Markdown formatting helpers for compact ContextSlicer output."""

from __future__ import annotations

from typing import Any


def format_header(symbol: dict[str, Any], block_id: str, test_count: int = 0) -> str:
    """Format the top metadata header for a context slice."""
    test_label = (
        f"{test_count} reference(s) de test"
        if test_count > 0
        else "AUCUN (cible non couverte)"
    )
    return (
        f"# Context Slice: `{symbol['id']}`\n"
        f"- **Bloc fonctionnel :** `{block_id}`\n"
        f"- **Fichier :** `{symbol['file_path']}:{symbol['start_line']}-{symbol['end_line']}`\n"
        f"- **Type :** `{symbol['kind']}` | **Signature :** `{symbol['signature']}`\n"
        f"- **Tests associes :** {test_label}"
    )


def format_findings_lines(findings: list[dict[str, Any]]) -> list[str]:
    """Format active findings and sensitive sinks ordered by severity."""
    lines = ["## Alertes & Surfaces sensibles actives"]
    for finding in findings:
        lines.append(
            f"- **[{finding['severity']}]** `{finding['rule_id']}` "
            f"(`{finding['category']}`, L{finding['line']}): {finding['message']}"
        )
    return lines


def format_source_block(source_code: str, truncated: bool = False) -> str:
    """Format the target Python source block in Markdown."""
    title = "## Code source cible (tronque)" if truncated else "## Code source cible"
    return f"{title}\n```python\n{source_code}\n```"


def format_neighbor_line(item: dict[str, Any]) -> str:
    """Format signature and location only for a k-hop neighbor."""
    sig = item.get("signature") or item["id"]
    file_path = item.get("file_path")
    loc = f" (`{file_path}`)" if file_path else " (externe/stdlib)"
    return f"- `{item['id']}` -- `{sig}`{loc}"
