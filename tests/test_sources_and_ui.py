"""Offline tests for local/GitHub target resolution, persistent caching, CLI, and web UI."""

from __future__ import annotations

import io
import json
import os
import shutil
import stat
import subprocess
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

import pytest

from codeoverlook.core.inspector import ProgressEvent, inspect_target
from codeoverlook.core.sources import (
    GitHubSpec,
    SourceResolutionError,
    TargetResolver,
    _safe_replace_dir,
    _safe_rmtree,
    parse_github_spec,
)
from codeoverlook.interfaces.cli import main
from codeoverlook.interfaces.web_server import create_workbench_server
from codeoverlook.views.workbench import render_workbench_html


def _zip_from_directory(src_dir: Path, *, root_folder: str = "acme-demo-abc123") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(src_dir.rglob("*")):
            if file_path.is_dir() or "__pycache__" in file_path.parts:
                continue
            rel = file_path.relative_to(src_dir).as_posix()
            zf.writestr(f"{root_folder}/{rel}", file_path.read_bytes())
    return buf.getvalue()


def _http_request(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, dict(resp.headers.items()), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers.items()), exc.read()


def test_parse_github_spec_variants_and_safety(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify supported GitHub URLs/shorthands and rejection of unsafe refs/subpaths."""
    assert parse_github_spec("https://github.com/acme/demo") == GitHubSpec("acme", "demo")
    assert parse_github_spec("https://github.com/acme/demo.git") == GitHubSpec("acme", "demo")
    assert parse_github_spec("https://github.com/acme/demo/tree/main") == GitHubSpec(
        "acme", "demo", ref="main"
    )
    assert parse_github_spec("https://github.com/acme/demo/tree/v1.2/pkg/sub") == GitHubSpec(
        "acme", "demo", ref="v1.2", subpath="pkg/sub"
    )
    assert parse_github_spec("git@github.com:acme/demo.git") == GitHubSpec("acme", "demo")
    assert parse_github_spec("github:acme/demo") == GitHubSpec("acme", "demo")
    assert parse_github_spec("gh:acme/demo") == GitHubSpec("acme", "demo")

    monkeypatch.chdir(tmp_path)
    assert parse_github_spec("acme/demo") == GitHubSpec("acme", "demo")

    # Existing local directory with a slash must resolve locally, not as GitHub shorthand.
    local_dir = tmp_path / "acme" / "demo"
    local_dir.mkdir(parents=True)
    assert parse_github_spec("acme/demo") is None

    with pytest.raises(SourceResolutionError):
        parse_github_spec("https://github.com/acme/demo/tree/-badref")

    with pytest.raises(SourceResolutionError):
        parse_github_spec("https://github.com/acme/demo/tree/main/../escape")


def test_target_resolver_local_and_subpath(sample_repo: Path) -> None:
    """Resolve local directories and validate relative subpaths safely."""
    resolver = TargetResolver(cache_dir=sample_repo.parent / "cache")

    direct = resolver.resolve(str(sample_repo))
    assert direct.source_kind == "local"
    assert direct.root_path == sample_repo.resolve()
    assert direct.from_cache is False

    sub = resolver.resolve(str(sample_repo), subpath="engine")
    assert sub.source_kind == "local"
    assert sub.root_path == (sample_repo / "engine").resolve()
    assert sub.subpath == "engine"

    with pytest.raises(SourceResolutionError):
        resolver.resolve(str(sample_repo), subpath="../outside")

    with pytest.raises(SourceResolutionError):
        resolver.resolve(str(sample_repo / "missing_dir"))


def test_target_resolver_github_clone_and_offline_cache_reuse(
    sample_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mock shallow git clone once, then verify strict offline cache reuse."""
    cache_dir = tmp_path / "cache"
    resolver = TargetResolver(cache_dir=cache_dir)

    with pytest.raises(SourceResolutionError):
        resolver.resolve("acme/demo", offline=True)

    clone_calls: list[list[str]] = []

    def fake_which(name: str) -> str | None:
        return "git" if name == "git" else None

    def fake_run(cmd: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        clone_calls.append(cmd)
        dest = Path(cmd[-1])
        shutil.copytree(sample_repo, dest)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("codeoverlook.core.sources.shutil.which", fake_which)
    monkeypatch.setattr("codeoverlook.core.sources.subprocess.run", fake_run)

    online = resolver.resolve("https://github.com/acme/demo", ref="main")
    assert online.source_kind == "github"
    assert online.from_cache is False
    assert online.fetch_method == "git_clone"
    assert (online.checkout_root / ".codeoverlook-source.json").is_file()
    assert len(clone_calls) == 1

    # Second resolution in strict offline mode must not invoke git or network.
    def fail_if_called(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("Network or git clone must not run in offline cache hit")

    monkeypatch.setattr("codeoverlook.core.sources.subprocess.run", fail_if_called)
    offline = resolver.resolve("acme/demo", ref="main", offline=True)
    assert offline.source_kind == "github"
    assert offline.from_cache is True
    assert offline.root_path == online.root_path

    cached = resolver.list_cached_repos()
    assert len(cached) == 1
    assert cached[0].owner == "acme"
    assert cached[0].repo == "demo"
    assert cached[0].ref == "main"
    assert cached[0].indexed is False


def test_target_resolver_zipball_fallback_and_zip_slip_guard(
    sample_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fallback to GitHub zipball when git is absent, and block Zip Slip payloads."""
    cache_dir = tmp_path / "cache"
    resolver = TargetResolver(cache_dir=cache_dir)

    monkeypatch.setattr("codeoverlook.core.sources.shutil.which", lambda _name: None)
    good_zip = _zip_from_directory(sample_repo)

    class _FakeResp:
        def __init__(self, payload: bytes) -> None:
            self._stream = io.BytesIO(payload)

        def read(self, size: int = -1) -> bytes:
            return self._stream.read(size)

        def __enter__(self) -> _FakeResp:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(
        "codeoverlook.core.sources.urllib.request.urlopen",
        lambda *_args, **_kwargs: _FakeResp(good_zip),
    )

    resolved = resolver.resolve("github:acme/zipdemo")
    assert resolved.fetch_method == "zipball"
    assert (resolved.root_path / "engine" / "service.py").is_file()

    # Malicious archive containing path traversal must be rejected cleanly.
    bad_buf = io.BytesIO()
    with zipfile.ZipFile(bad_buf, "w") as zf:
        zf.writestr("../evil.py", "print('bad')\n")
    bad_zip = bad_buf.getvalue()

    monkeypatch.setattr(
        "codeoverlook.core.sources.urllib.request.urlopen",
        lambda *_args, **_kwargs: _FakeResp(bad_zip),
    )
    with pytest.raises(SourceResolutionError):
        resolver.resolve("github:acme/badzip")


def test_cli_offline_cached_github_and_cache_listing(
    sample_repo: Path,
    tmp_path: Path,
    capsys: object,
) -> None:
    """Run CLI subcommands against a cached GitHub checkout strictly offline."""
    cache_dir = tmp_path / "cache"
    cached_checkout = cache_dir / "github" / "acme" / "demo" / "default"
    cached_checkout.parent.mkdir(parents=True)
    shutil.copytree(sample_repo, cached_checkout)
    (cached_checkout / ".codeoverlook-source.json").write_text(
        json.dumps(
            {
                "owner": "acme",
                "repo": "demo",
                "ref": "default",
                "clone_url": "https://github.com/acme/demo.git",
                "fetch_method": "git_clone",
                "fetched_at": "2026-11-25T10:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    cache_flag = ["--cache-dir", str(cache_dir)]

    assert main(["scan", "acme/demo", "--offline", *cache_flag]) == 0
    scan_out = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "GitHub acme/demo (cached offline)" in scan_out

    assert main(["blocks", "acme/demo", "--offline", "--json", *cache_flag]) == 0
    blocks_payload = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    assert {b["block_id"] for b in blocks_payload["blocks"]} == {"ui", "engine", "storage"}

    assert main(["tests", "acme/demo", "--offline", "--json", *cache_flag]) == 0
    tests_payload = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    assert tests_payload["summary"]["linked_test_files"] == 1

    assert (
        main(
            [
                "slice",
                "ReportBuilder.build_summary",
                "--repo",
                "acme/demo",
                "--offline",
                "--budget",
                "1800",
                *cache_flag,
            ]
        )
        == 0
    )
    slice_out = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "engine/service.py::ReportBuilder.build_summary" in slice_out

    assert main(["mermaid", "acme/demo", "--offline", *cache_flag]) == 0
    assert capsys.readouterr().out.startswith("graph LR")  # type: ignore[attr-defined]

    assert main(["html", "acme/demo", "--offline", *cache_flag]) == 0
    _ = capsys.readouterr()  # type: ignore[attr-defined]
    assert (cached_checkout / ".codeoverlook" / "overlook.html").is_file()

    assert main(["cache", "--json", *cache_flag]) == 0
    cache_payload = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    assert len(cache_payload["repositories"]) == 1
    assert cache_payload["repositories"][0]["indexed"] is True


def test_web_workbench_server_local_and_cached_github(
    sample_repo: Path,
    tmp_path: Path,
) -> None:
    """Exercise HTTP endpoints on the local web workbench end-to-end."""
    cache_dir = tmp_path / "cache"
    cached_checkout = cache_dir / "github" / "acme" / "demo" / "main"
    cached_checkout.parent.mkdir(parents=True)
    shutil.copytree(sample_repo, cached_checkout)
    (cached_checkout / ".codeoverlook-source.json").write_text(
        json.dumps(
            {
                "owner": "acme",
                "repo": "demo",
                "ref": "main",
                "clone_url": "https://github.com/acme/demo.git",
                "fetch_method": "zipball",
                "fetched_at": "2026-11-25T10:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    server = create_workbench_server("127.0.0.1", 0, cache_dir=cache_dir)
    port = server.server_address[1]
    base_url = f"http://127.0.0.1:{port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        status, _hdrs, root_body = _http_request(f"{base_url}/")
        assert status == 200
        assert "CodeOverlook Inspection Workbench" in root_body.decode("utf-8")

        status, _hdrs, health_body = _http_request(f"{base_url}/api/health")
        assert status == 200
        assert json.loads(health_body)["status"] == "ok"

        status, _hdrs, cache_body = _http_request(f"{base_url}/api/cache")
        assert status == 200
        cache_json = json.loads(cache_body)
        assert len(cache_json["repositories"]) == 1

        # Inspect local folder
        status, _hdrs, local_res = _http_request(
            f"{base_url}/api/inspect",
            method="POST",
            payload={"target": str(sample_repo), "offline": True},
        )
        assert status == 200
        local_data = json.loads(local_res)
        assert local_data["target"]["source_kind"] == "local"
        assert local_data["coverage_summary"]["blocks_count"] == 3
        assert local_data["mermaid_arch"].startswith("graph LR")

        # Inspect cached GitHub repository strictly offline
        status, _hdrs, gh_res = _http_request(
            f"{base_url}/api/inspect",
            method="POST",
            payload={"target": "acme/demo", "ref": "main", "offline": True},
        )
        assert status == 200
        gh_data = json.loads(gh_res)
        assert gh_data["target"]["source_kind"] == "github"
        assert gh_data["target"]["from_cache"] is True
        session_id = gh_data["session_id"]

        # Retrieve rendered standalone HTML report and download variant
        status, _hdrs, html_body = _http_request(f"{base_url}/api/report/{session_id}/html")
        assert status == 200
        assert "CodeOverlook Coverage &amp; Architecture Inspector" in html_body.decode("utf-8")

        status, dl_hdrs, _ = _http_request(
            f"{base_url}/api/report/{session_id}/html?download=1"
        )
        assert status == 200
        assert "attachment" in dl_hdrs.get("Content-Disposition", "")

        # Slice a symbol via the workbench API
        status, _hdrs, slice_res = _http_request(
            f"{base_url}/api/slice",
            method="POST",
            payload={
                "session_id": session_id,
                "target": "ReportBuilder.build_summary",
                "budget": 1800,
                "depth": 1,
            },
        )
        assert status == 200
        slice_data = json.loads(slice_res)
        assert slice_data["estimated_tokens"] <= 1800
        assert "engine/service.py::ReportBuilder.build_summary" in slice_data["markdown"]

        # Uncached GitHub target in offline mode returns 400 JSON
        status, _hdrs, err_res = _http_request(
            f"{base_url}/api/inspect",
            method="POST",
            payload={"target": "acme/not-cached", "offline": True},
        )
        assert status == 400
        assert "not in the offline cache" in json.loads(err_res)["error"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_windows_cache_cleanup_and_replace_resilience(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify read-only `.git` cleanup, rename retries, and copy fallback on PermissionError."""
    ro_dir = tmp_path / "readonly_tree"
    pack_dir = ro_dir / ".git" / "objects" / "pack"
    pack_dir.mkdir(parents=True)
    ro_file = pack_dir / "pack-test.idx"
    ro_file.write_text("pack", encoding="utf-8")
    os.chmod(ro_file, stat.S_IREAD)

    _safe_rmtree(ro_dir)
    assert not ro_dir.exists()

    # Transient PermissionError recovers via retry.
    src_retry = tmp_path / "staging_retry"
    dst_retry = tmp_path / "dst_retry"
    src_retry.mkdir()
    (src_retry / "app.py").write_text("x = 1\n", encoding="utf-8")

    monkeypatch.setattr("codeoverlook.core.sources.time.sleep", lambda _s: None)
    real_rename = os.rename
    attempts = {"count": 0}

    def flaky_rename(s: Path, d: Path) -> None:
        attempts["count"] += 1
        if attempts["count"] <= 2:
            raise PermissionError(5, "Access is denied")
        real_rename(s, d)

    monkeypatch.setattr("codeoverlook.core.sources.os.rename", flaky_rename)
    _safe_replace_dir(src_retry, dst_retry)
    assert attempts["count"] == 3
    assert (dst_retry / "app.py").is_file()

    # Persistent PermissionError falls back to copying without `.git`.
    src_fallback = tmp_path / "staging_fallback"
    dst_fallback = tmp_path / "dst_fallback"
    (src_fallback / ".git").mkdir(parents=True)
    (src_fallback / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (src_fallback / "main.py").write_text("print('ok')\n", encoding="utf-8")

    def always_denied(_s: Path, _d: Path) -> None:
        raise PermissionError(5, "Access is denied")

    monkeypatch.setattr("codeoverlook.core.sources.os.rename", always_denied)
    _safe_replace_dir(src_fallback, dst_fallback)
    assert (dst_fallback / "main.py").is_file()
    assert not (dst_fallback / ".git").exists()

    # `_clone_via_git` disables fsmonitor to avoid background file locks on Windows.
    captured_cmds: list[list[str]] = []
    monkeypatch.setattr("codeoverlook.core.sources.shutil.which", lambda _n: "git")

    def fake_clone(cmd: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured_cmds.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("codeoverlook.core.sources.subprocess.run", fake_clone)
    ok, _err = TargetResolver._clone_via_git(
        "https://github.com/acme/demo.git",
        tmp_path / "clone_target",
        None,
        None,
    )
    assert ok is True
    assert "core.fsmonitor=false" in captured_cmds[0]


def test_inspect_progress_events_and_async_workbench_jobs(
    sample_repo: Path,
    tmp_path: Path,
) -> None:
    """Verify monotonic progress callbacks and async workbench job polling."""
    events: list[ProgressEvent] = []
    inspect_target(str(sample_repo), progress_callback=events.append)

    stages = [e.stage for e in events]
    percents = [e.percent for e in events]
    assert stages[0] == "resolving"
    assert "scanning" in stages
    assert stages[-1] == "done"
    assert percents[-1] == 100
    assert percents == sorted(percents)

    wb_html = render_workbench_html()
    assert 'id="progress-wrap"' in wb_html
    assert 'role="progressbar"' in wb_html
    assert "/api/inspect/start" in wb_html

    server = create_workbench_server("127.0.0.1", 0, cache_dir=tmp_path / "cache")
    port = server.server_address[1]
    base_url = f"http://127.0.0.1:{port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        # Successful async inspection job reaches `done` with full session result.
        status, _hdrs, start_body = _http_request(
            f"{base_url}/api/inspect/start",
            method="POST",
            payload={"target": str(sample_repo), "offline": True},
        )
        assert status == 202
        start_data = json.loads(start_body)
        status_url = f"{base_url}{start_data['status_url']}"

        job_data: dict[str, Any] = {}
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            j_status, _hdrs, j_body = _http_request(status_url)
            assert j_status == 200
            job_data = json.loads(j_body)
            if job_data["status"] in {"done", "error"}:
                break
            time.sleep(0.03)

        assert job_data["status"] == "done"
        assert job_data["percent"] == 100
        assert job_data["result"]["session_id"]
        assert job_data["result"]["report_url"].startswith("/api/report/")

        # Failing async inspection job (uncached offline GitHub repo) reports `error`.
        status, _hdrs, err_start = _http_request(
            f"{base_url}/api/inspect/start",
            method="POST",
            payload={"target": "acme/missing-offline", "offline": True},
        )
        assert status == 202
        err_url = f"{base_url}{json.loads(err_start)['status_url']}"

        err_job: dict[str, Any] = {}
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            j_status, _hdrs, j_body = _http_request(err_url)
            assert j_status == 200
            err_job = json.loads(j_body)
            if err_job["status"] in {"done", "error"}:
                break
            time.sleep(0.03)

        assert err_job["status"] == "error"
        assert err_job["http_status"] == 400
        assert "not in the offline cache" in err_job["error"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
