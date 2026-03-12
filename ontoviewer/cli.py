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
) -> None:
    """Render an interactive graph from a local ontology file."""
    closure = load_ontology_closure(ontology_file, max_depth=max_depth, rdf_format=rdf_format)
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


if __name__ == "__main__":
    app()
