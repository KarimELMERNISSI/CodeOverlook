"""Unified target resolution and persistent offline caching for local and GitHub repositories."""

from __future__ import annotations

import base64
import io
import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

_GITHUB_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_GITHUB_HTTPS_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/([^/]+)/([^/]+?)(?:\.git)?(?:/tree/(.+))?/?$"
)
_GITHUB_SSH_RE = re.compile(r"^git@github\.com:([^/]+)/([^/]+?)(?:\.git)?/?$")
_GITHUB_PREFIX_RE = re.compile(r"^(?:github|gh):([^/]+)/([^/]+?)(?:\.git)?/?$")
_SOURCE_META_FILENAME = ".codeoverlook-source.json"
_MAX_ZIP_BYTES = 250 * 1024 * 1024  # 250 MiB safety cap for archive downloads


class SourceResolutionError(Exception):
    """Raised when a local or GitHub inspection target cannot be resolved safely."""


@dataclass(frozen=True, slots=True)
class GitHubSpec:
    """Parsed components of a GitHub repository reference."""

    owner: str
    repo: str
    ref: str | None = None
    subpath: str | None = None

    @property
    def clone_url(self) -> str:
        """Canonical HTTPS Git clone URL for this repository."""
        return f"https://github.com/{self.owner}/{self.repo}.git"

    @property
    def full_name(self) -> str:
        """Repository identifier in `owner/repo` form."""
        return f"{self.owner}/{self.repo}"


@dataclass(frozen=True, slots=True)
class ResolvedTarget:
    """Resolved repository checkout ready for static analysis and slicing."""

    source_kind: Literal["local", "github"]
    display_name: str
    root_path: Path
    checkout_root: Path
    original_target: str
    from_cache: bool = False
    ref: str | None = None
    subpath: str | None = None
    clone_url: str | None = None
    fetch_method: str | None = None


@dataclass(frozen=True, slots=True)
class CachedRepoEntry:
    """Metadata describing one locally cached GitHub repository checkout."""

    owner: str
    repo: str
    ref: str
    checkout_path: Path
    fetched_at: str | None
    indexed: bool
    clone_url: str | None


def _validate_owner_repo(owner: str, repo: str) -> tuple[str, str]:
    clean_owner = owner.strip()
    clean_repo = repo.strip()
    if clean_repo.endswith(".git"):
        clean_repo = clean_repo[:-4]
    if (
        clean_owner in {"", ".", ".."}
        or clean_repo in {"", ".", ".."}
        or not _GITHUB_NAME_RE.match(clean_owner)
        or not _GITHUB_NAME_RE.match(clean_repo)
    ):
        raise SourceResolutionError(
            f"Invalid GitHub repository identifier: '{owner}/{repo}'."
        )
    return clean_owner, clean_repo


def _validate_ref(ref: str | None) -> str | None:
    if ref is None:
        return None
    cleaned = ref.strip()
    if not cleaned:
        return None
    if (
        cleaned.startswith("-")
        or ".." in cleaned
        or "\\" in cleaned
        or any(ch.isspace() or ord(ch) < 32 for ch in cleaned)
    ):
        raise SourceResolutionError(f"Invalid Git ref '{ref}'.")
    return cleaned


def _validate_subpath(subpath: str | None) -> str | None:
    if subpath is None:
        return None
    normalized = subpath.replace("\\", "/").strip().strip("/")
    if not normalized:
        return None
    if ":" in normalized or subpath.startswith(("/", "\\")):
        raise SourceResolutionError(
            f"Subpath must be relative to the repository root: '{subpath}'."
        )
    parts = [part for part in normalized.split("/") if part]
    if any(part in {".", ".."} for part in parts):
        raise SourceResolutionError(
            f"Subpath cannot contain '.' or '..' traversal segments: '{subpath}'."
        )
    return "/".join(parts)


def _ref_slug(ref: str | None) -> str:
    if not ref:
        return "default"
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", ref.replace("/", "__")).strip("._")
    if not slug or slug in {".", ".."}:
        return "ref"
    return slug


def _looks_like_local_path(raw: str) -> bool:
    if "\\" in raw or raw.startswith((".", "/", "~")):
        return True
    if len(raw) >= 2 and raw[1] == ":" and raw[0].isalpha():
        return True
    return Path(raw).expanduser().exists()


def parse_github_spec(target: str) -> GitHubSpec | None:
    """Parse a GitHub URL, SSH remote, or `owner/repo` shorthand.

    Returns `None` when `target` represents a local filesystem path. Raises
    `SourceResolutionError` if `target` explicitly targets GitHub with an
    unsupported or unsafe syntax.
    """
    raw = target.strip()
    if not raw:
        return None

    match = _GITHUB_HTTPS_RE.match(raw)
    if match:
        owner, repo = _validate_owner_repo(match.group(1), match.group(2))
        tree_tail = match.group(3)
        ref: str | None = None
        subpath: str | None = None
        if tree_tail:
            tail_parts = [p for p in tree_tail.split("/") if p]
            if tail_parts:
                ref = _validate_ref(tail_parts[0])
                if len(tail_parts) > 1:
                    subpath = _validate_subpath("/".join(tail_parts[1:]))
        return GitHubSpec(owner=owner, repo=repo, ref=ref, subpath=subpath)

    if raw.lower().startswith(("http://github.com", "https://github.com")):
        raise SourceResolutionError(
            f"Unsupported GitHub URL '{target}'. Use 'https://github.com/<owner>/<repo>' "
            "or 'https://github.com/<owner>/<repo>/tree/<ref>'."
        )

    match = _GITHUB_SSH_RE.match(raw)
    if match:
        owner, repo = _validate_owner_repo(match.group(1), match.group(2))
        return GitHubSpec(owner=owner, repo=repo)

    if raw.lower().startswith("git@github.com:"):
        raise SourceResolutionError(f"Unsupported GitHub SSH remote '{target}'.")

    match = _GITHUB_PREFIX_RE.match(raw)
    if match:
        owner, repo = _validate_owner_repo(match.group(1), match.group(2))
        return GitHubSpec(owner=owner, repo=repo)

    if raw.lower().startswith(("github:", "gh:")):
        raise SourceResolutionError(
            f"Invalid GitHub shorthand '{target}'. Expected 'github:<owner>/<repo>'."
        )

    if "://" in raw:
        raise SourceResolutionError(
            f"Unsupported remote URL '{target}'. Only GitHub repositories and local folders "
            "are currently supported."
        )

    if not _looks_like_local_path(raw) and "/" in raw:
        parts = [p for p in raw.strip("/").split("/") if p]
        if len(parts) == 2:
            owner, repo = _validate_owner_repo(parts[0], parts[1])
            return GitHubSpec(owner=owner, repo=repo)

    return None


def _scrub_secret(text: str, secret: str | None) -> str:
    if not secret:
        return text
    b64 = base64.b64encode(f"x-access-token:{secret}".encode()).decode("ascii")
    return text.replace(secret, "***").replace(b64, "***")


def _safe_extract_zipball(archive_bytes: bytes, dest_dir: Path) -> None:
    """Safely extract a GitHub zipball archive, stripping its single top-level directory."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_resolved = dest_dir.resolve()

    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zf:
            infos = zf.infolist()
            if not infos:
                raise SourceResolutionError("Downloaded GitHub archive is empty.")

            # Validate every archive path before writing anything to disk.
            raw_parts_list: list[tuple[zipfile.ZipInfo, list[str]]] = []
            for info in infos:
                member_name = info.filename.replace("\\", "/")
                if member_name.startswith("/") or ":" in member_name.split("/")[0]:
                    raise SourceResolutionError(
                        f"Unsafe absolute path in archive: '{info.filename}'."
                    )
                parts = [p for p in member_name.split("/") if p and p != "."]
                if any(part == ".." for part in parts):
                    raise SourceResolutionError(
                        f"Unsafe path traversal entry in archive: '{info.filename}'."
                    )
                if not parts:
                    continue
                # Skip symlinks (mode 0o120000 in upper 16 bits of external_attr).
                if ((info.external_attr >> 16) & 0o170000) == 0o120000:
                    continue
                raw_parts_list.append((info, parts))

            if not raw_parts_list:
                raise SourceResolutionError("Downloaded GitHub archive contains no files.")

            first_segments = {parts[0] for _, parts in raw_parts_list}
            strip_prefix = len(first_segments) == 1 and any(
                len(parts) > 1 for _, parts in raw_parts_list
            )

            for info, parts in raw_parts_list:
                rel_parts = parts[1:] if strip_prefix else parts
                if not rel_parts:
                    continue
                target_path = (dest_resolved / Path(*rel_parts)).resolve()
                if not target_path.is_relative_to(dest_resolved):
                    raise SourceResolutionError(
                        f"Unsafe destination outside checkout directory: '{info.filename}'."
                    )
                if info.is_dir():
                    target_path.mkdir(parents=True, exist_ok=True)
                    continue
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info, "r") as src_stream, target_path.open("wb") as dst_stream:
                    shutil.copyfileobj(src_stream, dst_stream)
    except zipfile.BadZipFile as exc:
        raise SourceResolutionError(f"Downloaded GitHub archive is corrupted: {exc}") from exc


class TargetResolver:
    """Resolves local folders and GitHub repositories with persistent offline caching."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        """Initialize the resolver with a persistent cache directory.

        Args:
            cache_dir: Optional override for cached GitHub repositories. Defaults to
                `$CODEOVERLOOK_CACHE_DIR` or `~/.codeoverlook/cache`.
        """
        if cache_dir is not None:
            self.cache_dir = cache_dir.expanduser().resolve()
        else:
            env_dir = os.environ.get("CODEOVERLOOK_CACHE_DIR")
            default_dir = Path(env_dir) if env_dir else (Path.home() / ".codeoverlook" / "cache")
            self.cache_dir = default_dir.expanduser().resolve()

    def _apply_subpath(self, checkout_root: Path, subpath: str | None) -> Path:
        validated = _validate_subpath(subpath)
        if not validated:
            return checkout_root
        checkout_resolved = checkout_root.resolve()
        sub_root = (checkout_resolved / validated).resolve()
        if not sub_root.is_relative_to(checkout_resolved):
            raise SourceResolutionError(
                f"Subpath '{subpath}' escapes repository root '{checkout_resolved}'."
            )
        if not sub_root.exists() or not sub_root.is_dir():
            raise SourceResolutionError(
                f"Subpath '{validated}' does not exist inside '{checkout_resolved}'."
            )
        return sub_root

    def _checkout_dir_for(self, spec: GitHubSpec, ref: str | None) -> Path:
        return self.cache_dir / "github" / spec.owner / spec.repo / _ref_slug(ref)

    @staticmethod
    def _is_populated_checkout(checkout_dir: Path) -> bool:
        if not checkout_dir.is_dir():
            return False
        if (checkout_dir / _SOURCE_META_FILENAME).is_file():
            return True
        return any(checkout_dir.iterdir())

    @staticmethod
    def _read_source_meta(checkout_dir: Path) -> dict[str, Any]:
        meta_path = checkout_dir / _SOURCE_META_FILENAME
        if not meta_path.is_file():
            return {}
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _write_source_meta(
        checkout_dir: Path,
        spec: GitHubSpec,
        ref: str | None,
        fetch_method: str,
    ) -> None:
        payload = {
            "owner": spec.owner,
            "repo": spec.repo,
            "ref": ref or "default",
            "requested_ref": ref,
            "clone_url": spec.clone_url,
            "fetch_method": fetch_method,
            "fetched_at": datetime.now(UTC).isoformat(),
        }
        meta_path = checkout_dir / _SOURCE_META_FILENAME
        meta_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @staticmethod
    def _clone_via_git(
        clone_url: str,
        staging_dir: Path,
        ref: str | None,
        token: str | None,
    ) -> tuple[bool, str]:
        git_bin = shutil.which("git")
        if not git_bin:
            return False, "git binary not found"

        cmd: list[str] = [git_bin]
        if token:
            b64 = base64.b64encode(f"x-access-token:{token}".encode()).decode("ascii")
            cmd.extend(
                [
                    "-c",
                    f"http.https://github.com/.extraheader=AUTHORIZATION: basic {b64}",
                ]
            )
        cmd.extend(["clone", "--depth", "1", "--single-branch"])
        if ref:
            cmd.extend(["--branch", ref])
        cmd.extend([clone_url, str(staging_dir)])

        env = dict(os.environ)
        env["GIT_TERMINAL_PROMPT"] = "0"
        try:
            proc = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return False, _scrub_secret(str(exc), token)

        if proc.returncode == 0:
            return True, ""
        err = (proc.stderr or proc.stdout or f"exit code {proc.returncode}").strip()
        return False, _scrub_secret(err, token)

    @staticmethod
    def _download_zipball(
        spec: GitHubSpec,
        staging_dir: Path,
        ref: str | None,
        token: str | None,
    ) -> None:
        url = f"https://api.github.com/repos/{spec.owner}/{spec.repo}/zipball"
        if ref:
            url = f"{url}/{urllib.parse.quote(ref, safe='')}"

        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "CodeOverlook",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"

        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                chunks: list[bytes] = []
                total = 0
                while True:
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > _MAX_ZIP_BYTES:
                        raise SourceResolutionError(
                            f"GitHub archive for '{spec.full_name}' exceeds 250 MiB safety limit."
                        )
                    chunks.append(chunk)
                archive_bytes = b"".join(chunks)
        except urllib.error.HTTPError as exc:
            raise SourceResolutionError(
                f"GitHub archive download failed for '{spec.full_name}' (HTTP {exc.code})."
            ) from exc
        except urllib.error.URLError as exc:
            raise SourceResolutionError(
                f"Network error fetching '{spec.full_name}' from GitHub: {exc.reason}"
            ) from exc
        except OSError as exc:
            raise SourceResolutionError(
                f"Error reading GitHub archive response for '{spec.full_name}': {exc}"
            ) from exc

        _safe_extract_zipball(archive_bytes, staging_dir)

    def _fetch_to_cache(
        self,
        spec: GitHubSpec,
        checkout_dir: Path,
        ref: str | None,
        token: str | None,
    ) -> str:
        parent = checkout_dir.parent
        parent.mkdir(parents=True, exist_ok=True)
        staging_dir = parent / f".staging-{uuid.uuid4().hex}"
        backup_dir = parent / f".backup-{uuid.uuid4().hex}"

        try:
            cloned, clone_err = self._clone_via_git(spec.clone_url, staging_dir, ref, token)
            if cloned:
                fetch_method = "git_clone"
            else:
                if staging_dir.exists():
                    shutil.rmtree(staging_dir, ignore_errors=True)
                try:
                    self._download_zipball(spec, staging_dir, ref, token)
                    fetch_method = "zipball"
                except SourceResolutionError as zip_exc:
                    raise SourceResolutionError(
                        f"Unable to fetch GitHub repository '{spec.full_name}'. "
                        f"git clone error: {clone_err}; zipball fallback error: {zip_exc}"
                    ) from zip_exc

            self._write_source_meta(staging_dir, spec, ref, fetch_method)

            if checkout_dir.exists():
                checkout_dir.replace(backup_dir)
            staging_dir.replace(checkout_dir)
            return fetch_method
        finally:
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)
            if backup_dir.exists():
                shutil.rmtree(backup_dir, ignore_errors=True)

    def resolve(
        self,
        target: str,
        *,
        ref: str | None = None,
        subpath: str | None = None,
        offline: bool = False,
        refresh: bool = False,
        token: str | None = None,
    ) -> ResolvedTarget:
        """Resolve a local folder or GitHub repository into a ready-to-scan directory.

        Args:
            target: Local directory path or GitHub URL / `owner/repo` shorthand.
            ref: Optional Git branch, tag, or commit SHA for GitHub targets.
            subpath: Optional relative subdirectory inside the repository.
            offline: When `True`, never make network calls; fail if a GitHub target is
                not yet present in the local cache.
            refresh: When `True`, re-fetch a GitHub target even if already cached.
            token: Optional GitHub personal access token (falls back to `GITHUB_TOKEN`).

        Returns:
            `ResolvedTarget` pointing to the resolved local or cached directory.

        Raises:
            SourceResolutionError: If the target is missing, malformed, or unreachable.
        """
        raw = target.strip()
        if not raw:
            raise SourceResolutionError("Target path or GitHub repository cannot be empty.")

        explicit_ref = _validate_ref(ref)
        explicit_subpath = _validate_subpath(subpath)
        spec = parse_github_spec(raw)

        if spec is None:
            local_checkout = Path(raw).expanduser().resolve()
            if not local_checkout.exists() or not local_checkout.is_dir():
                raise SourceResolutionError(
                    f"Repository path '{local_checkout}' does not exist or is not a directory."
                )
            root_path = self._apply_subpath(local_checkout, explicit_subpath)
            display = local_checkout.name
            if explicit_subpath:
                display = f"{display}/{explicit_subpath}"
            return ResolvedTarget(
                source_kind="local",
                display_name=display,
                root_path=root_path,
                checkout_root=local_checkout,
                original_target=raw,
                from_cache=False,
                ref=None,
                subpath=explicit_subpath,
                clone_url=None,
                fetch_method="local",
            )

        effective_ref = explicit_ref or spec.ref
        effective_subpath = explicit_subpath or spec.subpath
        checkout_dir = self._checkout_dir_for(spec, effective_ref)
        cached = self._is_populated_checkout(checkout_dir)

        if offline and refresh:
            raise SourceResolutionError(
                "Cannot refresh a GitHub repository while offline mode is enabled."
            )

        if cached and (offline or not refresh):
            meta = self._read_source_meta(checkout_dir)
            root_path = self._apply_subpath(checkout_dir, effective_subpath)
            display = spec.full_name
            if effective_ref:
                display = f"{display}@{effective_ref}"
            if effective_subpath:
                display = f"{display}/{effective_subpath}"
            return ResolvedTarget(
                source_kind="github",
                display_name=display,
                root_path=root_path,
                checkout_root=checkout_dir,
                original_target=raw,
                from_cache=True,
                ref=effective_ref,
                subpath=effective_subpath,
                clone_url=spec.clone_url,
                fetch_method=str(meta.get("fetch_method", "cache")),
            )

        if offline:
            ref_hint = f" --ref {effective_ref}" if effective_ref else ""
            raise SourceResolutionError(
                f"GitHub repository '{spec.full_name}' is not in the offline cache "
                f"('{checkout_dir}'). Run once online without `--offline` "
                f"(e.g. `codeoverlook scan {spec.full_name}{ref_hint}`) or provide a local folder."
            )

        effective_token = token if token is not None else os.environ.get("GITHUB_TOKEN")
        fetch_method = self._fetch_to_cache(spec, checkout_dir, effective_ref, effective_token)
        root_path = self._apply_subpath(checkout_dir, effective_subpath)
        display = spec.full_name
        if effective_ref:
            display = f"{display}@{effective_ref}"
        if effective_subpath:
            display = f"{display}/{effective_subpath}"
        return ResolvedTarget(
            source_kind="github",
            display_name=display,
            root_path=root_path,
            checkout_root=checkout_dir,
            original_target=raw,
            from_cache=False,
            ref=effective_ref,
            subpath=effective_subpath,
            clone_url=spec.clone_url,
            fetch_method=fetch_method,
        )

    def list_cached_repos(self) -> list[CachedRepoEntry]:
        """List all GitHub repositories currently stored in the local offline cache."""
        github_root = self.cache_dir / "github"
        if not github_root.is_dir():
            return []

        entries: list[CachedRepoEntry] = []
        for owner_dir in sorted(github_root.iterdir()):
            if not owner_dir.is_dir() or owner_dir.name.startswith("."):
                continue
            for repo_dir in sorted(owner_dir.iterdir()):
                if not repo_dir.is_dir() or repo_dir.name.startswith("."):
                    continue
                for ref_dir in sorted(repo_dir.iterdir()):
                    if not ref_dir.is_dir() or ref_dir.name.startswith("."):
                        continue
                    if not self._is_populated_checkout(ref_dir):
                        continue
                    meta = self._read_source_meta(ref_dir)
                    entries.append(
                        CachedRepoEntry(
                            owner=str(meta.get("owner") or owner_dir.name),
                            repo=str(meta.get("repo") or repo_dir.name),
                            ref=str(meta.get("ref") or ref_dir.name),
                            checkout_path=ref_dir,
                            fetched_at=(
                                str(meta["fetched_at"]) if meta.get("fetched_at") else None
                            ),
                            indexed=(ref_dir / ".codeoverlook" / "index.db").is_file(),
                            clone_url=(
                                str(meta["clone_url"])
                                if meta.get("clone_url")
                                else f"https://github.com/{owner_dir.name}/{repo_dir.name}.git"
                            ),
                        )
                    )
        entries.sort(key=lambda item: (item.owner.lower(), item.repo.lower(), item.ref.lower()))
        return entries
