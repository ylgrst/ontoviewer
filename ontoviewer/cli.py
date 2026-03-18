from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import sys
from typing import Literal, Optional
import webbrowser

import typer

from ontoviewer.loader import load_ontology_closure
from ontoviewer.visualize import render_interactive_graph

app = typer.Typer(help="Interactive ontology visualizer for OWL/RDF ontologies.")
COMMON_WEB_PORTS = (8080, 18000, 3000, 5000, 8765)


@app.command("render")
def render(
    ontology_file: Path = typer.Argument(..., help="Path to a local ontology file."),
    output: Path = typer.Option(
        Path("ontology_graph.html"),
        "--output",
        "-o",
        help="Output HTML graph file.",
    ),
    max_depth: int = typer.Option(
        2,
        "--max-depth",
        "-d",
        min=0,
        help="Maximum owl:imports recursion depth.",
    ),
    rdf_format: Optional[str] = typer.Option(
        None,
        "--format",
        help="Optional RDF format (e.g. xml, turtle, n3, nt).",
    ),
    label_mode: Literal["human", "raw"] = typer.Option(
        "human",
        "--label-mode",
        help="Default graph label mode: human-readable annotation labels or raw ontology codes.",
    ),
    allow_insecure_ssl: bool = typer.Option(
        False,
        "--allow-insecure-ssl/--strict-ssl",
        help=(
            "Retry remote imports without certificate verification if HTTPS validation fails. "
            "Use only for trusted ontology hosts."
        ),
    ),
) -> None:
    """Render an interactive graph from a local ontology file."""
    closure = load_ontology_closure(
        ontology_file,
        max_depth=max_depth,
        rdf_format=rdf_format,
        allow_insecure_ssl=allow_insecure_ssl,
    )
    stats = render_interactive_graph(closure, output, label_mode=label_mode)

    typer.echo(f"Graph written to: {output.resolve()}")
    typer.echo(
        "Loaded "
        f"{stats['ontologies']} ontologies, "
        f"{stats['ontology_refs']} ontology references, "
        f"{stats['classes']} classes, "
        f"{stats['relations']} relations, "
        f"{stats['imports']} imports, "
        f"{stats['unresolved_imports']} unresolved imports."
    )
    if closure.errors:
        typer.echo("Warnings:")
        for err in closure.errors:
            typer.echo(f"  - {err}")


@app.command("serve")
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Host interface to bind."),
    port: int = typer.Option(
        8000,
        "--port",
        min=1,
        max=65535,
        help="TCP port for the web UI server.",
    ),
    storage_dir: Path = typer.Option(
        Path(".ontoviewer-web"),
        "--storage-dir",
        help="Directory used to store uploaded ontologies and generated HTML files.",
    ),
    auto_port: bool = typer.Option(
        True,
        "--auto-port/--strict-port",
        help="If the requested port is unavailable, automatically try fallback ports such as 8080 and 18000.",
    ),
    open_browser: bool = typer.Option(
        True,
        "--open-browser/--no-open-browser",
        help="Open the web UI in the default browser after the server starts. Disable on remote or headless machines.",
    ),
) -> None:
    """Run a local web UI for uploading and visualizing ontologies."""
    try:
        from ontoviewer.webapp import create_app
    except ModuleNotFoundError as exc:
        if exc.name in {"flask", "werkzeug"}:
            typer.echo(
                "Web UI dependencies are missing. Install with: pip install -e '.[web]'",
                err=True,
            )
            raise typer.Exit(code=1)
        raise

    flask_app = create_app(storage_dir=storage_dir)
    actual_port = port
    if auto_port:
        selected_port = _pick_serving_port(host, port)
        if selected_port is None:
            typer.echo(
                "Could not find an available local port. Try a manual one such as 8080 or 18000.",
                err=True,
            )
            raise typer.Exit(code=1)
        actual_port = selected_port
        if actual_port != port:
            typer.echo(f"Port {port} is unavailable on {host}. Using {actual_port} instead.")
    elif not _port_is_available(host, port):
        typer.echo(
            f"Port {port} is unavailable on {host}. "
            "Try another port such as 8080 or 18000, or rerun with --auto-port.",
            err=True,
        )
        raise typer.Exit(code=1)

    url = _browser_url(host, actual_port)
    typer.echo(f"Starting OntoViewer web UI at {url}")

    try:
        _run_server(flask_app, host, actual_port, browser_url=url if open_browser else None)
    except OSError as exc:
        typer.echo(f"Could not start the web UI on {host}:{actual_port}: {exc}", err=True)
        raise typer.Exit(code=1)


def _candidate_ports(preferred_port: int) -> list[int]:
    candidates = [preferred_port, *COMMON_WEB_PORTS]
    candidates.extend(range(preferred_port + 1, min(preferred_port + 21, 65536)))

    deduped: list[int] = []
    seen: set[int] = set()
    for candidate in candidates:
        if 1 <= candidate <= 65535 and candidate not in seen:
            deduped.append(candidate)
            seen.add(candidate)
    return deduped


def _pick_serving_port(host: str, preferred_port: int) -> Optional[int]:
    for candidate in _candidate_ports(preferred_port):
        if _port_is_available(host, candidate):
            return candidate
    return None


def _port_is_available(host: str, port: int) -> bool:
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        return False

    for family, socktype, proto, _, sockaddr in addresses:
        try:
            with socket.socket(family, socktype, proto) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                    try:
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                    except OSError:
                        pass
                sock.bind(sockaddr)
                return True
        except OSError:
            continue
    return False


def _browser_url(host: str, port: int) -> str:
    browser_host = host
    if host in {"0.0.0.0", ""}:
        browser_host = "127.0.0.1"
    elif host in {"::", "[::]", "::1"}:
        browser_host = "localhost"
    elif ":" in host and not host.startswith("["):
        browser_host = f"[{host}]"
    return f"http://{browser_host}:{port}"


def _launch_browser(url: str) -> bool:
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        for command in (
            ["cmd.exe", "/c", "start", "", url],
            ["explorer.exe", url],
            ["rundll32.exe", "url.dll,FileProtocolHandler", url],
        ):
            try:
                subprocess.Popen(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=creationflags,
                )
                return True
            except OSError:
                pass

        startfile = getattr(os, "startfile", None)
        if startfile is not None:
            try:
                startfile(url)
                return True
            except OSError:
                pass

    try:
        if webbrowser.open_new_tab(url):
            return True
    except Exception:
        pass

    if sys.platform == "darwin":
        try:
            subprocess.Popen(
                ["open", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except OSError:
            pass
    else:
        try:
            subprocess.Popen(
                ["xdg-open", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except OSError:
            pass
    return False


def _run_server(flask_app, host: str, port: int, browser_url: Optional[str] = None) -> None:
    from werkzeug.serving import make_server

    server = make_server(host, port, flask_app, threaded=True)
    try:
        if browser_url and not _launch_browser(browser_url):
            typer.echo(
                f"Could not open the browser automatically. Open {browser_url} manually.",
                err=True,
            )
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    app()
