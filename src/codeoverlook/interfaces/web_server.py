"""Local stdlib HTTP workbench server for interactive online/offline inspection."""

from __future__ import annotations

import json
import sqlite3
import threading
import urllib.parse
import uuid
import webbrowser
from collections import OrderedDict
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from codeoverlook import __version__
from codeoverlook.core.inspector import (
    InspectionSnapshot,
    inspect_target,
    slice_repository_target,
)
from codeoverlook.core.sources import SourceResolutionError, TargetResolver
from codeoverlook.views.mermaid import render_block_mermaid, render_coverage_mermaid
from codeoverlook.views.workbench import render_workbench_html

_MAX_REQUEST_BYTES = 1_048_576  # 1 MiB


class _PayloadTooLargeError(Exception):
    """Raised when an HTTP JSON request exceeds `_MAX_REQUEST_BYTES`."""


class InspectionSessionRegistry:
    """Thread-safe bounded registry of active `InspectionSnapshot` sessions."""

    def __init__(self, max_sessions: int = 16) -> None:
        self._max_sessions = max(1, max_sessions)
        self._lock = threading.Lock()
        self._sessions: OrderedDict[str, InspectionSnapshot] = OrderedDict()

    def put(self, snapshot: InspectionSnapshot) -> str:
        """Store a snapshot under a fresh session ID and return the ID."""
        session_id = uuid.uuid4().hex[:16]
        with self._lock:
            self._sessions[session_id] = snapshot
            self._sessions.move_to_end(session_id)
            while len(self._sessions) > self._max_sessions:
                self._sessions.popitem(last=False)
        return session_id

    def get(self, session_id: str) -> InspectionSnapshot | None:
        """Retrieve a snapshot by session ID, or `None` if expired/unknown."""
        with self._lock:
            snapshot = self._sessions.get(session_id)
            if snapshot is not None:
                self._sessions.move_to_end(session_id)
            return snapshot


class WorkbenchApp:
    """Application state shared across HTTP workbench request handler threads."""

    def __init__(
        self,
        *,
        resolver: TargetResolver | None = None,
        initial_target: str | None = None,
        offline_default: bool = False,
        max_sessions: int = 16,
    ) -> None:
        self.resolver = resolver or TargetResolver()
        self.registry = InspectionSessionRegistry(max_sessions=max_sessions)
        self.initial_target = initial_target
        self.offline_default = offline_default

    def list_cache_payload(self) -> dict[str, Any]:
        """Serialize cached GitHub repositories for `GET /api/cache`."""
        entries = self.resolver.list_cached_repos()
        return {
            "cache_dir": str(self.resolver.cache_dir),
            "repositories": [
                {
                    "owner": entry.owner,
                    "repo": entry.repo,
                    "ref": entry.ref,
                    "checkout_path": str(entry.checkout_path),
                    "fetched_at": entry.fetched_at,
                    "indexed": entry.indexed,
                    "clone_url": entry.clone_url,
                }
                for entry in entries
            ],
        }

    def inspect_payload(self, body: dict[str, Any]) -> dict[str, Any]:
        """Execute repository resolution + scan and return workbench JSON payload."""
        raw_target = body.get("target")
        if not isinstance(raw_target, str) or not raw_target.strip():
            raise ValueError("Field 'target' must be a non-empty string.")

        ref = body.get("ref")
        if ref is not None and not isinstance(ref, str):
            raise ValueError("Field 'ref' must be a string or null.")
        subpath = body.get("subpath")
        if subpath is not None and not isinstance(subpath, str):
            raise ValueError("Field 'subpath' must be a string or null.")
        token = body.get("token")
        if token is not None and not isinstance(token, str):
            raise ValueError("Field 'token' must be a string or null.")

        offline = bool(body.get("offline", False))
        refresh = bool(body.get("refresh", False))
        force_scan = bool(body.get("force", False))

        resolved, scan_summary, snapshot = inspect_target(
            raw_target,
            ref=ref,
            subpath=subpath,
            offline=offline,
            refresh=refresh,
            force_scan=force_scan,
            token=token,
            resolver=self.resolver,
        )
        session_id = self.registry.put(snapshot)
        mermaid_arch = render_block_mermaid(snapshot.block_summary, snapshot.dependencies)
        mermaid_cov = render_coverage_mermaid(snapshot.coverage, snapshot.dependencies)

        return {
            "session_id": session_id,
            "report_url": f"/api/report/{session_id}/html",
            "target": {
                "source_kind": resolved.source_kind,
                "display_name": resolved.display_name,
                "root_path": str(resolved.root_path),
                "checkout_root": str(resolved.checkout_root),
                "from_cache": resolved.from_cache,
                "ref": resolved.ref,
                "subpath": resolved.subpath,
                "clone_url": resolved.clone_url,
                "fetch_method": resolved.fetch_method,
            },
            "scan": {
                "elapsed_ms": round(scan_summary.elapsed_ms, 2),
                "indexed_files": scan_summary.indexed_files,
                "skipped_files": scan_summary.skipped_files,
                "pruned_files": scan_summary.pruned_files,
                "warnings": scan_summary.warnings,
            },
            "coverage_summary": {
                "blocks_count": len(snapshot.coverage.blocks),
                "total_test_files": snapshot.coverage.total_test_files,
                "linked_test_files": snapshot.coverage.linked_test_files,
                "total_test_functions": snapshot.coverage.total_test_functions,
                "overall_file_coverage_pct": snapshot.coverage.overall_file_coverage_pct,
                "overall_symbol_coverage_pct": snapshot.coverage.overall_symbol_coverage_pct,
            },
            "blocks": [asdict(b) for b in snapshot.coverage.blocks],
            "dependencies": snapshot.dependencies,
            "cycles": snapshot.cycles,
            "violations": snapshot.violations,
            "mermaid_arch": mermaid_arch,
            "mermaid_coverage": mermaid_cov,
        }

    def slice_payload(self, body: dict[str, Any]) -> dict[str, Any]:
        """Run `ContextSlicer` for an active workbench session."""
        session_id = body.get("session_id")
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("Field 'session_id' must be a non-empty string.")
        snapshot = self.registry.get(session_id.strip())
        if snapshot is None:
            raise FileNotFoundError(f"Unknown or expired inspection session '{session_id}'.")

        target = body.get("target")
        if not isinstance(target, str) or not target.strip():
            raise ValueError("Field 'target' must be a non-empty string.")

        raw_budget = body.get("budget", 2500)
        raw_depth = body.get("depth", 1)
        if not isinstance(raw_budget, int) or raw_budget < 1:
            raise ValueError("Field 'budget' must be a positive integer.")
        if not isinstance(raw_depth, int) or raw_depth < 1:
            raise ValueError("Field 'depth' must be a positive integer.")

        result = slice_repository_target(
            snapshot.target,
            target.strip(),
            token_budget=raw_budget,
            depth=raw_depth,
        )
        return {
            "target": result.target,
            "markdown": result.markdown,
            "estimated_tokens": result.estimated_tokens,
            "truncated": result.truncated,
        }


def _make_handler(app: WorkbenchApp) -> type[BaseHTTPRequestHandler]:
    class _WorkbenchHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

        def _send_bytes(
            self,
            status: int,
            content_type: str,
            payload: bytes,
            extra_headers: dict[str, str] | None = None,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            if extra_headers:
                for key, val in extra_headers.items():
                    self.send_header(key, val)
            self.end_headers()
            self.wfile.write(payload)

        def _send_json(self, status: int, data: Any) -> None:
            raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self._send_bytes(status, "application/json; charset=utf-8", raw)

        def _send_html(
            self,
            status: int,
            html_text: str,
            extra_headers: dict[str, str] | None = None,
        ) -> None:
            self._send_bytes(
                status,
                "text/html; charset=utf-8",
                html_text.encode("utf-8"),
                extra_headers=extra_headers,
            )

        def _read_json_body(self) -> dict[str, Any]:
            raw_len = self.headers.get("Content-Length", "0")
            try:
                content_len = int(raw_len)
            except ValueError as exc:
                raise ValueError("Invalid Content-Length header.") from exc
            if content_len < 0:
                raise ValueError("Invalid negative Content-Length header.")
            if content_len > _MAX_REQUEST_BYTES:
                raise _PayloadTooLargeError("Request body exceeds 1 MiB limit.")
            raw_bytes = self.rfile.read(content_len) if content_len else b"{}"
            parsed = json.loads(raw_bytes.decode("utf-8"))
            if not isinstance(parsed, dict):
                raise ValueError("JSON request body must be an object.")
            return parsed

        def do_GET(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path

            if path == "/":
                html_doc = render_workbench_html(
                    initial_target=app.initial_target,
                    offline_default=app.offline_default,
                )
                self._send_html(HTTPStatus.OK, html_doc)
                return

            if path == "/api/health":
                self._send_json(HTTPStatus.OK, {"status": "ok", "version": __version__})
                return

            if path == "/api/cache":
                self._send_json(HTTPStatus.OK, app.list_cache_payload())
                return

            if path.startswith("/api/report/") and path.endswith("/html"):
                parts = [p for p in path.split("/") if p]
                if len(parts) == 4 and parts[0] == "api" and parts[1] == "report":
                    snapshot = app.registry.get(parts[2])
                    if snapshot is None:
                        self._send_json(
                            HTTPStatus.NOT_FOUND,
                            {"error": f"Unknown or expired inspection session '{parts[2]}'."},
                        )
                        return
                    query = urllib.parse.parse_qs(parsed.query)
                    extra: dict[str, str] | None = None
                    if query.get("download", ["0"])[0] == "1":
                        extra = {"Content-Disposition": 'attachment; filename="overlook.html"'}
                    self._send_html(HTTPStatus.OK, snapshot.html_doc, extra_headers=extra)
                    return

            self._send_json(HTTPStatus.NOT_FOUND, {"error": f"Route not found: {path}"})

        def do_POST(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path

            try:
                body = self._read_json_body()
                if path == "/api/inspect":
                    self._send_json(HTTPStatus.OK, app.inspect_payload(body))
                    return
                if path == "/api/slice":
                    self._send_json(HTTPStatus.OK, app.slice_payload(body))
                    return
                self._send_json(HTTPStatus.NOT_FOUND, {"error": f"Route not found: {path}"})
            except _PayloadTooLargeError as exc:
                self._send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": str(exc)})
            except (SourceResolutionError, ValueError, json.JSONDecodeError) as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            except FileNotFoundError as exc:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            except (sqlite3.Error, OSError) as exc:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    return _WorkbenchHandler


class _ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def create_workbench_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    *,
    cache_dir: Path | None = None,
    initial_target: str | None = None,
    offline_default: bool = False,
) -> ThreadingHTTPServer:
    """Create a configured `ThreadingHTTPServer` for the CodeOverlook Web Workbench.

    Args:
        host: Bind address (defaults to loopback `127.0.0.1`).
        port: TCP port (pass `0` for an ephemeral OS-assigned port in tests).
        cache_dir: Optional persistent cache directory override.
        initial_target: Optional local folder or GitHub target to auto-inspect on load.
        offline_default: Whether the workbench starts with `Offline mode` enabled.

    Returns:
        Ready-to-serve `ThreadingHTTPServer` instance.
    """
    app = WorkbenchApp(
        resolver=TargetResolver(cache_dir=cache_dir),
        initial_target=initial_target,
        offline_default=offline_default,
    )
    return _ReusableThreadingHTTPServer((host, port), _make_handler(app))


def serve_workbench(
    host: str = "127.0.0.1",
    port: int = 8765,
    *,
    cache_dir: Path | None = None,
    initial_target: str | None = None,
    offline_default: bool = False,
    open_browser: bool = True,
) -> int:
    """Start the local CodeOverlook Web Workbench and block until interrupted."""
    server = create_workbench_server(
        host=host,
        port=port,
        cache_dir=cache_dir,
        initial_target=initial_target,
        offline_default=offline_default,
    )
    bound_host, bound_port = server.server_address[:2]
    url = f"http://{bound_host}:{bound_port}/"
    print(f"CodeOverlook Workbench listening at {url}")
    print(f"Offline cache directory: {TargetResolver(cache_dir=cache_dir).cache_dir}")
    print("Press Ctrl+C to stop.")

    if open_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping CodeOverlook Workbench.")
    finally:
        server.server_close()
    return 0
