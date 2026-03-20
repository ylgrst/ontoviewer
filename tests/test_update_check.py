from __future__ import annotations

from pathlib import Path

from ontoviewer import update_check


def test_latest_release_uses_fresh_cache(tmp_path: Path, monkeypatch) -> None:
    cache_path = tmp_path / "update_check.json"
    cached = update_check.ReleaseInfo(
        version="0.9.2",
        tag_name="v0.9.2",
        html_url="https://example.invalid/release",
        checked_at=1_000.0,
    )
    update_check._store_cached_release(cached, cache_path=cache_path)
    monkeypatch.setattr(
        update_check,
        "_fetch_latest_release",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("cache should be used first")),
    )

    latest = update_check.latest_release(now=1_100.0, cache_path=cache_path)

    assert latest == cached


def test_latest_release_refreshes_expired_cache(tmp_path: Path, monkeypatch) -> None:
    cache_path = tmp_path / "update_check.json"
    update_check._store_cached_release(
        update_check.ReleaseInfo(
            version="0.9.1",
            tag_name="v0.9.1",
            html_url="https://example.invalid/old",
            checked_at=1_000.0,
        ),
        cache_path=cache_path,
    )
    fresh = update_check.ReleaseInfo(
        version="0.9.2",
        tag_name="v0.9.2",
        html_url="https://example.invalid/new",
        checked_at=update_check.CACHE_TTL_SECONDS + 1_100.0,
    )
    monkeypatch.setattr(update_check, "_fetch_latest_release", lambda **kwargs: fresh)

    latest = update_check.latest_release(
        now=1_000.0 + update_check.CACHE_TTL_SECONDS + 10.0,
        cache_path=cache_path,
    )

    assert latest == fresh
    assert update_check._load_cached_release(now=fresh.checked_at, cache_path=cache_path) == fresh


def test_update_notice_for_web_install(monkeypatch) -> None:
    monkeypatch.setattr(
        update_check,
        "latest_release",
        lambda **kwargs: update_check.ReleaseInfo(
            version="0.9.2",
            tag_name="v0.9.2",
            html_url="https://github.com/ylgrst/ontoviewer/releases/tag/v0.9.2",
            checked_at=1_000.0,
        ),
    )

    notice = update_check.update_notice(current_version="0.9.1", usage="web")

    assert notice is not None
    assert "OntoViewer 0.9.2 (installed: 0.9.1)" in notice
    assert '"ontoviewer[web] @ git+https://github.com/ylgrst/ontoviewer.git@v0.9.2"' in notice


def test_update_notice_omits_when_current_is_latest(monkeypatch) -> None:
    monkeypatch.setattr(
        update_check,
        "latest_release",
        lambda **kwargs: update_check.ReleaseInfo(
            version="0.9.1",
            tag_name="v0.9.1",
            html_url="https://github.com/ylgrst/ontoviewer/releases/tag/v0.9.1",
            checked_at=1_000.0,
        ),
    )

    assert update_check.update_notice(current_version="0.9.1", usage="cli") is None
