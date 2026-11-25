"""User and agent interface subpackage (CLI, future MCP server)."""

from __future__ import annotations

from codeoverlook.interfaces.cli import build_parser, main
from codeoverlook.interfaces.web_server import (
    InspectionSessionRegistry,
    WorkbenchApp,
    create_workbench_server,
    serve_workbench,
)

__all__ = [
    "InspectionSessionRegistry",
    "WorkbenchApp",
    "build_parser",
    "create_workbench_server",
    "main",
    "serve_workbench",
]
