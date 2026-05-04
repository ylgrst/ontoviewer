from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("pyvis")

from ontoviewer.loader import load_ontology_closure
from ontoviewer.visualize import Network
from ontoviewer.visualize import _compute_tree_layout
from ontoviewer.visualize import render_interactive_graph
from ontoviewer.visualize import _stable_ontology_colors


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
    assert "wrapGraphLabel" in html
    assert "isEmbeddedPreview()" in html
    assert '"dragNodes": false' in html or "dragNodes: false" in html
    assert "const savedGraphPositions = new Map();" in html
    assert "let savedGraphViewport = null;" in html
    assert "saveCurrentGraphPositions()" in html
    assert "function saveCurrentGraphViewport()" in html
    assert "function savedGraphPositionForNode(node)" in html
    assert "function openOntologyCluster(clusterId)" in html
    assert 'const previousViewMode = viewMode;' in html
    assert 'const switchingGraphToTree = previousViewMode === "graph" && mode === "tree";' in html
    assert 'const switchingTreeToGraph = previousViewMode === "tree" && mode === "graph";' in html
    assert "treeX" in html
    assert "treeY" in html
    assert "treeOnly" in html
    assert "treeSemanticType" in html
    assert "treeOntologyGroup" in html
    assert "treeChildren" in html
    assert "function treeChildrenMap()" in html
    assert "function activeChildrenMap()" in html
    assert "hidden: Boolean(node.hidden)" in html
    assert "ontology imports ontology edge" in html
    assert "ontology defines root class edge" in html
    assert "Gray dashed links connect an ontology node to the root classes defined in that ontology." in html
    assert "Use Show/Hide relation edges to toggle all non-subclass ontology relations such as has part, referenced by, references, and applies to." in html
    assert "property/restriction relation edge (hidden by default in family-tree view)" in html
    assert "setTreeHoverState" in html
    assert 'hierarchical: false' in html
    assert 'smooth: false' in html
    assert "treeFrom" in html
    assert "wrapTreeLabel" in html
    assert "hideLoadingBar" in html
    assert "refreshAfterClassToggle" in html
    assert 'network.on("selectNode"' in html
    assert 'network.on("hoverNode"' in html
    assert 'network.on("blurNode"' in html
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
    assert "let treeMembershipEdgesVisible = true;" in html
    assert "return viewMode === \"graph\" ? graphPropertyEdgesVisible : treePropertyEdgesVisible;" in html
    assert 'propertyBtn.style.display = "inline-block";' in html
    assert "collapsedOntologyGroups.has(edge.treeOntologyGroup)" in html
    assert "if (viewMode !== \"tree\" && nodeOptions.isTreeHelperNode)" in html
    assert "openOntologyClusters(false);" in html
    assert "if (viewMode === \"graph\")" in html
    assert "saveCurrentGraphViewport();" in html
    assert "saveCurrentGraphPositions();" in html
    assert '"enabled": false' in html or "enabled: false" in html
    assert "network.stopSimulation();" in html
    assert "network.redraw();" in html
    assert "if (savedGraphViewport)" in html
    assert "releaseFunction: function(clusterPosition, containedNodesPositions)" in html
    assert "targets.every((targetId) => hiddenIds.has(targetId))" in html
    assert "function refreshAfterOntologyToggle()" in html
    assert html.count("const currentScale = network.getScale();") >= 3
    assert html.count("const currentPosition = network.getViewPosition();") >= 3
    assert html.count("network.moveTo({") >= 3
    assert "clusterEdgeProperties: viewMode === \"tree\"" in html
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


def test_stable_ontology_colors_are_deterministic_and_distinct() -> None:
    ontology_ids = [
        "http://example.org/ontology/a",
        "http://example.org/ontology/b",
        "http://example.org/ontology/c",
    ]
    first_mapping = _stable_ontology_colors(ontology_ids)
    second_mapping = _stable_ontology_colors(list(reversed(ontology_ids)))

    assert first_mapping == second_mapping
    assert len(set(first_mapping.values())) == len(ontology_ids)
    assert all(color.startswith("#") and len(color) == 7 for color in first_mapping.values())


def test_render_includes_restriction_based_property_edges(tmp_path: Path) -> None:
    root_file = tmp_path / "restriction.ttl"
    output_file = tmp_path / "graph.html"

    root_file.write_text(
        """
@prefix ex: <http://example.org/root#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

<http://example.org/root> a owl:Ontology .
ex:Carrier a owl:Class ;
    rdfs:subClassOf [
        a owl:Restriction ;
        owl:onProperty ex:hasPart ;
        owl:someValuesFrom ex:ReferencedOnly
    ] .
ex:hasPart a owl:ObjectProperty ;
    rdfs:label "has part"@en .
""",
        encoding="utf-8",
    )

    closure = load_ontology_closure(root_file, max_depth=0, rdf_format="turtle")
    stats = render_interactive_graph(closure, output_file, label_mode="human")
    html = output_file.read_text(encoding="utf-8")

    assert stats["classes"] == 2
    assert stats["relations"] == 1
    assert "has part" in html
    assert "ReferencedOnly" in html


def test_render_wraps_long_graph_node_labels(tmp_path: Path) -> None:
    root_file = tmp_path / "long-label.ttl"
    output_file = tmp_path / "graph.html"

    root_file.write_text(
        """
@prefix ex: <http://example.org/root#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

<http://example.org/root> a owl:Ontology .
ex:LongNameClass a owl:Class ;
    rdfs:label "Nominal Length Specification"@en .
""",
        encoding="utf-8",
    )

    closure = load_ontology_closure(root_file, max_depth=0, rdf_format="turtle")
    render_interactive_graph(closure, output_file, label_mode="human")
    html = output_file.read_text(encoding="utf-8")

    assert "Nominal Length\\nSpecification" in html


def test_tree_layout_keeps_siblings_on_one_line() -> None:
    ontology_ids = ["http://example.org/root"]
    class_nodes = {
        "http://example.org/root#A",
        "http://example.org/root#B",
        "http://example.org/root#C",
        "http://example.org/root#D",
    }
    tree_positions, _ = _compute_tree_layout(
        ontology_ids=ontology_ids,
        ontology_level={"http://example.org/root": 0},
        class_nodes=class_nodes,
        subclass_pairs=set(),
        class_owner={cls: "http://example.org/root" for cls in class_nodes},
        class_display_labels={cls: cls.rsplit("#", 1)[-1] for cls in class_nodes},
    )

    sibling_levels = {tree_positions[node_id][1] for node_id in class_nodes}
    assert len(sibling_levels) == 1
