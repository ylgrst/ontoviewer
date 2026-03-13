from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("pyvis")

from ontoviewer.loader import load_ontology_closure
from ontoviewer.visualize import render_interactive_graph


def test_rendered_html_includes_family_tree_controls(tmp_path: Path) -> None:
    root_file = tmp_path / "root.ttl"
    child_file = tmp_path / "child.ttl"
    output_file = tmp_path / "graph.html"

    child_file.write_text(
        """
@prefix ex: <http://example.org/child#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .

<http://example.org/child> a owl:Ontology .
ex:ImportedRoot a owl:Class .
""",
        encoding="utf-8",
    )
    root_file.write_text(
        f"""
@prefix ex: <http://example.org/root#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

<http://example.org/root> a owl:Ontology ;
    owl:imports <{child_file.as_uri()}> .
ex:RootClass a owl:Class .
ex:ChildClass a owl:Class ;
    rdfs:subClassOf ex:RootClass .
""",
        encoding="utf-8",
    )

    closure = load_ontology_closure(root_file, max_depth=1, rdf_format="turtle")
    stats = render_interactive_graph(closure, output_file, label_mode="human")
    html = output_file.read_text(encoding="utf-8")

    assert stats["ontologies"] == 2
    assert stats["imports"] == 1
    assert "Graph view" in html
    assert "Family tree view" in html
    assert "ontoviewerSetViewMode('tree')" in html
    assert "ontoviewerToggleCollapseAll()" in html
    assert "levelSeparation: 130" in html
    assert 'direction: "UD"' in html
    assert 'type: "vertical"' in html
    assert "treeFrom" in html
    assert "imports" in html
