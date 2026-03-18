from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("pyvis")
pytest.importorskip("typer")

from typer.testing import CliRunner

from ontoviewer import cli

runner = CliRunner()


def test_pick_serving_port_uses_first_available_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli,
        "_port_is_available",
        lambda host, port: port == 18000,
    )

    assert cli._pick_serving_port("127.0.0.1", 8000) == 18000


def test_browser_url_uses_loopback_for_wildcard_host() -> None:
    assert cli._browser_url("0.0.0.0", 8080) == "http://127.0.0.1:8080"
    assert cli._browser_url("::", 8080) == "http://localhost:8080"


def test_launch_browser_uses_windows_startfile_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: dict[str, str] = {}

    monkeypatch.setattr(cli.webbrowser, "open_new_tab", lambda url: False)
    monkeypatch.setattr(cli.os, "name", "nt", raising=False)
    monkeypatch.setattr(cli, "sys", type("FakeSys", (), {"platform": "win32"})())
    monkeypatch.setattr(
        cli.os,
        "startfile",
        lambda url: opened.setdefault("url", url),
        raising=False,
    )

    assert cli._launch_browser("http://127.0.0.1:18000") is True
    assert opened["url"] == "http://127.0.0.1:18000"


def test_serve_reports_actual_fallback_port(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pytest.importorskip("flask")
    import ontoviewer.webapp

    monkeypatch.setattr(ontoviewer.webapp, "create_app", lambda *, storage_dir: object())
    monkeypatch.setattr(cli, "_pick_serving_port", lambda host, port: 18000)
    monkeypatch.setattr(cli, "_run_server", lambda flask_app, host, port: None)

    result = runner.invoke(
        cli.app,
        ["serve", "--no-open-browser", "--storage-dir", str(tmp_path / "storage")],
    )

    assert result.exit_code == 0
    assert "Port 8000 is unavailable on 127.0.0.1. Using 18000 instead." in result.output
    assert "Starting OntoViewer web UI at http://127.0.0.1:18000" in result.output


def test_serve_opens_browser_on_resolved_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pytest.importorskip("flask")
    import ontoviewer.webapp

    opened: dict[str, str] = {}

    class ImmediateTimer:
        def __init__(self, interval: float, function, args=None, kwargs=None):
            self.function = function
            self.args = tuple(args or ())
            self.kwargs = dict(kwargs or {})
            self.daemon = False

        def start(self) -> None:
            self.function(*self.args, **self.kwargs)

    monkeypatch.setattr(ontoviewer.webapp, "create_app", lambda *, storage_dir: object())
    monkeypatch.setattr(cli, "_pick_serving_port", lambda host, port: 18000)
    monkeypatch.setattr(cli, "_run_server", lambda flask_app, host, port: None)
    monkeypatch.setattr(cli.threading, "Timer", ImmediateTimer)
    monkeypatch.setattr(cli, "_launch_browser", lambda url: opened.setdefault("url", url))

    result = runner.invoke(cli.app, ["serve", "--storage-dir", str(tmp_path / "storage")])

    assert result.exit_code == 0
    assert opened["url"] == "http://127.0.0.1:18000"
