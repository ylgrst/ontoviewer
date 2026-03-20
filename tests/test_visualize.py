from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("pyvis")

from ontoviewer.loader import load_ontology_closure
from ontoviewer.visualize import Network
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
    assert "Dark mode" in html
    assert "ontoviewerSetViewMode('tree')" in html
    assert "ontoviewerToggleCollapseAll()" in html
    assert "ontoviewerToggleTheme()" in html
    assert "ontoviewerToggleOntologyGroup(" in html
    assert "Search nodes" in html
    assert "ontoviewerUpdateSearch(this.value)" in html
    assert "ontoviewerStepSearch(-1)" in html
    assert "ontoviewerStepSearch(1)" in html
    assert "searchMatches" in html
    assert "scheduleCurrentSearchFocus" in html
    assert "revealNodeForSearch" in html
    assert "collapsedOntologyGroups" in html
    assert "reapplyCollapsedOntologyGroups()" in html
    assert "isEmbeddedPreview()" in html
    assert '"dragNodes": false' in html or "dragNodes: false" in html
    assert "levelSeparation: 140" in html
    assert 'direction: "UD"' in html
    assert 'type: "vertical"' in html
    assert "roundness: 0" in html
    assert "treeFrom" in html
    assert "wrapTreeLabel" in html
    assert "hideLoadingBar" in html
    assert "refreshAfterClassToggle" in html
    assert 'network.on("selectNode"' in html
    assert 'network.on("stabilized"' in html
    assert 'network.on("animationFinished"' in html
    assert "network.stopSimulation()" in html
    assert "ontoviewer-dark" in html
    assert "--ov-legend-edge: #111827;" in html
    assert "--ov-legend-edge: #cbd5e1;" in html
    assert "ontoviewerApplyExternalTheme" in html
    assert 'postMessage({ type: "ontoviewer-theme"' in html
    assert "openOntologyClusters(false)" in html
    assert "ontoviewerToggleTreeRelations()" in html
    assert "let graphPropertyEdgesVisible = true;" in html
    assert "let treePropertyEdgesVisible = false;" in html
    assert "return viewMode === \"graph\" ? graphPropertyEdgesVisible : treePropertyEdgesVisible;" in html
    assert 'propertyBtn.style.display = "inline-block";' in html
    assert "imports" in html


def test_render_avoids_pyvis_default_file_encoding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root_file = tmp_path / "unicode.ttl"
    output_file = tmp_path / "graph.html"

    root_file.write_text(
        """
@prefix ex: <http://example.org/root#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

<http://example.org/root> a owl:Ontology .
ex:Classe a owl:Class ;
    rdfs:label "Température µm"@fr .
""",
        encoding="utf-8",
    )

    def fail_write_html(self, name, local=True, notebook=False, open_browser=False):
        raise AssertionError("render_interactive_graph should write UTF-8 HTML itself")

    monkeypatch.setattr(Network, "write_html", fail_write_html)

    closure = load_ontology_closure(root_file, max_depth=0, rdf_format="turtle")
    render_interactive_graph(closure, output_file, label_mode="human")

    html = output_file.read_text(encoding="utf-8")
    assert json.dumps("Température µm")[1:-1] in html
