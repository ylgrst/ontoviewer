from __future__ import annotations

from types import SimpleNamespace
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


def test_print_update_notice_emits_message(monkeypatch: pytest.MonkeyPatch) -> None:
    emitted: dict[str, object] = {}

    monkeypatch.delenv(cli.DISABLE_UPDATE_CHECK_ENV, raising=False)
    monkeypatch.setattr(cli, "update_notice", lambda **kwargs: "Update available")
    monkeypatch.setattr(
        cli.typer,
        "secho",
        lambda message, **kwargs: emitted.update({"message": message, "kwargs": kwargs}),
    )

    cli._print_update_notice("web", enabled=True)

    assert emitted["message"] == "Update available"
    assert emitted["kwargs"]["err"] is True


def test_print_update_notice_respects_disable_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, bool] = {}

    monkeypatch.setenv(cli.DISABLE_UPDATE_CHECK_ENV, "1")
    monkeypatch.setattr(
        cli,
        "update_notice",
        lambda **kwargs: called.setdefault("called", True),
    )

    cli._print_update_notice("cli", enabled=True)

    assert "called" not in called


def test_should_reexec_with_utf8_on_windows_legacy_encoding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli.os, "name", "nt", raising=False)
    monkeypatch.setattr(cli, "sys", SimpleNamespace(flags=SimpleNamespace(utf8_mode=0)))
    monkeypatch.delenv(cli.UTF8_REEXEC_ENV, raising=False)
    monkeypatch.setattr(cli.locale, "getpreferredencoding", lambda do_setlocale=False: "cp1252")

    assert cli._should_reexec_with_utf8() is True


def test_ensure_utf8_mode_reexecs_once(monkeypatch: pytest.MonkeyPatch) -> None:
    invoked: dict[str, object] = {}

    monkeypatch.setattr(cli.os, "name", "nt", raising=False)
    monkeypatch.setattr(
        cli,
        "sys",
        SimpleNamespace(
            executable="C:/Python/python.exe",
            argv=["ontoviewer", "serve", "--port", "8000"],
            flags=SimpleNamespace(utf8_mode=0),
        ),
    )
    monkeypatch.delenv(cli.UTF8_REEXEC_ENV, raising=False)
    monkeypatch.setattr(cli.locale, "getpreferredencoding", lambda do_setlocale=False: "cp1252")
    monkeypatch.setattr(
        cli.os,
        "execvpe",
        lambda executable, argv, env: invoked.update(
            {"executable": executable, "argv": argv, "env": env}
        ),
    )

    cli._ensure_utf8_mode()

    assert invoked["executable"] == "C:/Python/python.exe"
    assert invoked["argv"] == [
        "C:/Python/python.exe",
        "-m",
        "ontoviewer.cli",
        "serve",
        "--port",
        "8000",
    ]
    assert invoked["env"]["PYTHONUTF8"] == "1"
    assert invoked["env"][cli.UTF8_REEXEC_ENV] == "1"


def test_launch_browser_uses_windows_cmd_start_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: dict[str, object] = {}

    monkeypatch.setattr(cli.os, "name", "nt", raising=False)
    monkeypatch.setattr(cli, "sys", type("FakeSys", (), {"platform": "win32"})())
    monkeypatch.setattr(cli.webbrowser, "open_new_tab", lambda url: False)
    monkeypatch.setattr(
        cli.subprocess,
        "Popen",
        lambda args, **kwargs: opened.setdefault("args", args),
    )
    monkeypatch.setattr(
        cli.os,
        "startfile",
        lambda url: opened.setdefault("url", url),
        raising=False,
    )

    assert cli._launch_browser("http://127.0.0.1:18000") is True
    assert opened["args"] == ["cmd.exe", "/c", "start", "", "http://127.0.0.1:18000"]


def test_launch_browser_falls_back_to_windows_explorer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempted: list[list[str]] = []

    monkeypatch.setattr(cli.os, "name", "nt", raising=False)
    monkeypatch.setattr(cli, "sys", type("FakeSys", (), {"platform": "win32"})())
    monkeypatch.setattr(cli.webbrowser, "open_new_tab", lambda url: False)

    def fake_popen(args, **kwargs):
        attempted.append(args)
        if args[0] == "cmd.exe":
            raise OSError("start failed")
        return object()

    monkeypatch.setattr(cli.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(cli.os, "startfile", lambda url: None, raising=False)

    assert cli._launch_browser("http://127.0.0.1:18000") is True
    assert attempted == [
        ["cmd.exe", "/c", "start", "", "http://127.0.0.1:18000"],
        ["explorer.exe", "http://127.0.0.1:18000"],
    ]


def test_serve_reports_actual_fallback_port(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pytest.importorskip("flask")
    import ontoviewer.webapp

    monkeypatch.setattr(ontoviewer.webapp, "create_app", lambda *, storage_dir: object())
    monkeypatch.setattr(cli, "_pick_serving_port", lambda host, port: 18000)
    monkeypatch.setattr(
        cli,
        "_run_server",
        lambda flask_app, host, port, browser_url=None: None,
    )

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

    launched: dict[str, object] = {}

    monkeypatch.setattr(ontoviewer.webapp, "create_app", lambda *, storage_dir: object())
    monkeypatch.setattr(cli, "_pick_serving_port", lambda host, port: 18000)
    monkeypatch.setattr(
        cli,
        "_run_server",
        lambda flask_app, host, port, browser_url=None: launched.update(
            {"host": host, "port": port, "browser_url": browser_url}
        ),
    )

    result = runner.invoke(cli.app, ["serve", "--storage-dir", str(tmp_path / "storage")])

    assert result.exit_code == 0
    assert launched["host"] == "127.0.0.1"
    assert launched["port"] == 18000
    assert launched["browser_url"] == "http://127.0.0.1:18000"
