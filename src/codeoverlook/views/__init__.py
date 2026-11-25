"""CodeOverlook view renderers (Markdown for agents, Mermaid diagrams, standalone HTML)."""

from __future__ import annotations

from codeoverlook.views.explorer_layout import build_explorer_model
from codeoverlook.views.html_renderer import render_atlas_html
from codeoverlook.views.markdown import (
    format_findings_lines,
    format_header,
    format_neighbor_line,
    format_source_block,
)
from codeoverlook.views.mermaid import render_block_mermaid, render_coverage_mermaid
from codeoverlook.views.workbench import render_workbench_html

__all__ = [
    "build_explorer_model",
    "format_findings_lines",
    "format_header",
    "format_neighbor_line",
    "format_source_block",
    "render_atlas_html",
    "render_block_mermaid",
    "render_coverage_mermaid",
    "render_workbench_html",
]
