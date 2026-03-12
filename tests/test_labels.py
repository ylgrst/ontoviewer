from __future__ import annotations

from rdflib import Graph

from ontoviewer.labels import preferred_annotation_label


def test_prefers_english_rdfs_label() -> None:
    graph = Graph()
    graph.parse(
        data="""
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix ex: <http://example.org/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

ex:C001 a owl:Class ;
  rdfs:label "Personne"@fr ;
  rdfs:label "Person"@en .
""",
        format="turtle",
    )

    assert preferred_annotation_label(graph, "http://example.org/C001") == "Person"


def test_falls_back_to_iao_preferred_term() -> None:
    graph = Graph()
    graph.parse(
        data="""
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix ex: <http://example.org/> .

ex:C002 a owl:Class ;
  <http://purl.obolibrary.org/obo/IAO_0000111> "Human readable name" .
""",
        format="turtle",
    )

    assert preferred_annotation_label(graph, "http://example.org/C002") == "Human readable name"


def test_returns_none_when_no_label_annotations() -> None:
    graph = Graph()
    graph.parse(
        data="""
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix ex: <http://example.org/> .

ex:C003 a owl:Class .
""",
        format="turtle",
    )

    assert preferred_annotation_label(graph, "http://example.org/C003") is None
