from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Deque, Optional, Set, Tuple

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF

from ontoviewer.model import ImportEdge, OntologyClosure, OntologyDocument


def load_ontology_closure(
    ontology_file: Path,
    *,
    max_depth: int = 2,
    rdf_format: Optional[str] = None,
) -> OntologyClosure:
    """Load a local ontology and recursively load owl:imports up to max_depth."""
    if max_depth < 0:
        raise ValueError("max_depth must be >= 0")

    root_source = ontology_file.expanduser().resolve().as_uri()
    queue: Deque[Tuple[str, int, Optional[str]]] = deque([(root_source, 0, None)])
    visited_sources: Set[str] = set()

    closure = OntologyClosure(root_iri="")

    while queue:
        source, depth, importer_iri = queue.popleft()
        if source in visited_sources or depth > max_depth:
            continue
        visited_sources.add(source)

        graph = Graph()
        try:
            if source.startswith("file://"):
                graph.parse(_file_uri_to_path(source), format=rdf_format)
            else:
                graph.parse(source, format=rdf_format)
        except Exception as exc:  # pragma: no cover - defensive for unknown RDF parser errors
            closure.errors.append(f"Could not load {source}: {exc}")
            continue

        ontology_iri = _discover_ontology_iri(graph) or source

        if ontology_iri not in closure.documents:
            closure.documents[ontology_iri] = OntologyDocument(
                iri=ontology_iri,
                source=source,
                depth=depth,
                graph=graph,
            )

        if depth == 0:
            closure.root_iri = ontology_iri

        if importer_iri:
            closure.import_edges.append(ImportEdge(source_iri=importer_iri, target_iri=ontology_iri))

        if depth == max_depth:
            continue

        for imported_iri in _discover_imports(graph):
            queue.append((imported_iri, depth + 1, ontology_iri))

    if not closure.root_iri and closure.documents:
        closure.root_iri = next(iter(closure.documents))

    return closure


def _discover_ontology_iri(graph: Graph) -> Optional[str]:
    for subject in graph.subjects(RDF.type, OWL.Ontology):
        if isinstance(subject, URIRef):
            return str(subject)
    return None


def _discover_imports(graph: Graph) -> Set[str]:
    imports: Set[str] = set()
    for imported in graph.objects(None, OWL.imports):
        if isinstance(imported, URIRef):
            imports.add(str(imported))
    return imports


def _file_uri_to_path(file_uri: str) -> str:
    if not file_uri.startswith("file://"):
        return file_uri
    return file_uri.removeprefix("file://")
