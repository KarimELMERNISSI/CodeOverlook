"""CodeOverlook view renderers (Markdown for agents, Mermaid diagrams, standalone HTML)."""

from __future__ import annotations

from codeoverlook.views.html_renderer import render_atlas_html
from codeoverlook.views.markdown import (
    format_findings_lines,
    format_header,
    format_neighbor_line,
    format_source_block,
)
from codeoverlook.views.mermaid import render_block_mermaid, render_coverage_mermaid

__all__ = [
    "format_findings_lines",
    "format_header",
    "format_neighbor_line",
    "format_source_block",
    "render_atlas_html",
    "render_block_mermaid",
    "render_coverage_mermaid",
]
