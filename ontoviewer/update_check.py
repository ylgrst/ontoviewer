from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import time
from typing import Literal, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from ontoviewer import __version__

REPO_URL = "https://github.com/ylgrst/ontoviewer"
LATEST_RELEASE_API_URL = f"{REPO_URL}/releases/latest"
LATEST_RELEASE_JSON_URL = "https://api.github.com/repos/ylgrst/ontoviewer/releases/latest"
CACHE_TTL_SECONDS = 24 * 60 * 60


@dataclass(slots=True)
class ReleaseInfo:
    version: str
    tag_name: str
    html_url: str
    checked_at: float


def _cache_path() -> Path:
    if os.name == "nt":
        base_dir = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base_dir = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base_dir / "ontoviewer" / "update_check.json"


def _normalize_version(version: str) -> str:
    return version.strip().lstrip("vV")


def _version_key(version: str) -> tuple[int, ...]:
    normalized = _normalize_version(version)
    parts: list[int] = []
    for chunk in normalized.split("."):
        digits = "".join(character for character in chunk if character.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def _load_cached_release(*, now: Optional[float] = None, cache_path: Optional[Path] = None) -> Optional[ReleaseInfo]:
    cache_file = cache_path or _cache_path()
    if not cache_file.exists():
        return None

    try:
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    checked_at = float(payload.get("checked_at", 0.0))
    if checked_at <= 0:
        return None

    current_time = now if now is not None else time.time()
    if current_time - checked_at > CACHE_TTL_SECONDS:
        return None

    version = _normalize_version(str(payload.get("version", "")))
    tag_name = str(payload.get("tag_name", "")).strip()
    html_url = str(payload.get("html_url", "")).strip() or LATEST_RELEASE_API_URL
    if not version or not tag_name:
        return None

    return ReleaseInfo(version=version, tag_name=tag_name, html_url=html_url, checked_at=checked_at)


def _store_cached_release(release: ReleaseInfo, *, cache_path: Optional[Path] = None) -> None:
    cache_file = cache_path or _cache_path()
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": release.version,
        "tag_name": release.tag_name,
        "html_url": release.html_url,
        "checked_at": release.checked_at,
    }
    cache_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _fetch_latest_release(*, now: Optional[float] = None, timeout: float = 2.5) -> Optional[ReleaseInfo]:
    request = Request(
        LATEST_RELEASE_JSON_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"OntoViewer/{__version__}",
        },
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except (URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None

    tag_name = str(payload.get("tag_name", "")).strip()
    version = _normalize_version(tag_name)
    if not version:
        return None

    html_url = str(payload.get("html_url", "")).strip() or f"{REPO_URL}/releases/tag/{tag_name}"
    checked_at = now if now is not None else time.time()
    return ReleaseInfo(version=version, tag_name=tag_name, html_url=html_url, checked_at=checked_at)


def latest_release(*, now: Optional[float] = None, cache_path: Optional[Path] = None) -> Optional[ReleaseInfo]:
    cached = _load_cached_release(now=now, cache_path=cache_path)
    if cached is not None:
        return cached

    fetched = _fetch_latest_release(now=now)
    if fetched is None:
        return None

    try:
        _store_cached_release(fetched, cache_path=cache_path)
    except OSError:
        pass
    return fetched


def update_notice(
    *,
    current_version: str,
    usage: Literal["web", "cli"],
    now: Optional[float] = None,
    cache_path: Optional[Path] = None,
) -> Optional[str]:
    release = latest_release(now=now, cache_path=cache_path)
    if release is None:
        return None

    current_key = _version_key(current_version)
    latest_key = _version_key(release.version)
    if not current_key or not latest_key or latest_key <= current_key:
        return None

    if usage == "web":
        update_command = (
            'python -m pip install --upgrade '
            f'"ontoviewer[web] @ git+https://github.com/ylgrst/ontoviewer.git@{release.tag_name}"'
        )
    else:
        update_command = (
            'python -m pip install --upgrade '
            f'"git+https://github.com/ylgrst/ontoviewer.git@{release.tag_name}"'
        )

    return "\n".join(
        [
            f"Update available: OntoViewer {release.version} (installed: {current_version})",
            f"Release: {release.html_url}",
            "Update with:",
            f"  {update_command}",
        ]
    )
