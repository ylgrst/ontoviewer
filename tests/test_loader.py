from __future__ import annotations

from pathlib import Path

import pytest

from ontoviewer.loader import load_ontology_closure


def test_recursive_imports_honor_depth_limit(tmp_path: Path) -> None:
    root_file = tmp_path / "root.ttl"
    child_file = tmp_path / "child.ttl"
    grandchild_file = tmp_path / "grandchild.ttl"

    root_file.write_text(
        f"""
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix ex: <http://example.org/root#> .
<http://example.org/root> a owl:Ontology ;
    owl:imports <{child_file.as_uri()}> .
ex:RootClass a owl:Class .
""",
        encoding="utf-8",
    )
    child_file.write_text(
        f"""
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix ex: <http://example.org/child#> .
<http://example.org/child> a owl:Ontology ;
    owl:imports <{grandchild_file.as_uri()}> .
ex:ChildClass a owl:Class .
""",
        encoding="utf-8",
    )
    grandchild_file.write_text(
        """
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix ex: <http://example.org/grandchild#> .
<http://example.org/grandchild> a owl:Ontology .
ex:GrandchildClass a owl:Class .
""",
        encoding="utf-8",
    )

    depth1 = load_ontology_closure(root_file, max_depth=1, rdf_format="turtle")
    assert set(depth1.documents) == {"http://example.org/root", "http://example.org/child"}
    assert {
        (edge.source_iri, edge.target_iri) for edge in depth1.import_edges
    } == {
        ("http://example.org/root", child_file.as_uri()),
        ("http://example.org/child", grandchild_file.as_uri()),
    }

    depth2 = load_ontology_closure(root_file, max_depth=2, rdf_format="turtle")
    assert set(depth2.documents) == {
        "http://example.org/root",
        "http://example.org/child",
        "http://example.org/grandchild",
    }
    assert len(depth2.errors) == 0


def test_unresolved_import_keeps_edge_and_warning(tmp_path: Path) -> None:
    root_file = tmp_path / "root.ttl"
    missing_file_uri = (tmp_path / "missing.ttl").as_uri()

    root_file.write_text(
        f"""
@prefix owl: <http://www.w3.org/2002/07/owl#> .
<http://example.org/root> a owl:Ontology ;
    owl:imports <{missing_file_uri}> .
""",
        encoding="utf-8",
    )

    closure = load_ontology_closure(root_file, max_depth=2, rdf_format="turtle")

    assert set(closure.documents) == {"http://example.org/root"}
    assert [(edge.source_iri, edge.target_iri) for edge in closure.import_edges] == [
        ("http://example.org/root", missing_file_uri)
    ]
    assert closure.errors


def test_missing_input_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_ontology_closure(tmp_path / "not_there.owl")
