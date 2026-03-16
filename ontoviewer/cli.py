from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

import typer

from ontoviewer.loader import load_ontology_closure
from ontoviewer.visualize import render_interactive_graph

app = typer.Typer(help="Interactive ontology visualizer for OWL/RDF ontologies.")


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
    typer.echo(f"Starting OntoViewer web UI at http://{host}:{port}")
    flask_app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    app()
