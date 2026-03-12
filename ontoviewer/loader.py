from __future__ import annotations

from collections import deque
from os import name as os_name
from pathlib import Path
from typing import Deque, Optional, Set, Tuple
from urllib.parse import unquote, urljoin, urlparse

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
    if not ontology_file.exists():
        raise FileNotFoundError(f"Ontology file does not exist: {ontology_file}")

    root_source = ontology_file.expanduser().resolve().as_uri()
    queue: Deque[Tuple[str, int]] = deque([(root_source, 0)])
    visited_sources: Set[str] = set()
    seen_import_edges: Set[Tuple[str, str]] = set()

    closure = OntologyClosure(root_iri="")

    while queue:
        source, depth = queue.popleft()
        if source in visited_sources or depth > max_depth:
            continue
        visited_sources.add(source)

        try:
            graph = _load_graph(source, rdf_format=rdf_format)
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

        for imported_iri in _discover_imports(graph):
            edge_key = (ontology_iri, imported_iri)
            if edge_key not in seen_import_edges:
                seen_import_edges.add(edge_key)
                closure.import_edges.append(ImportEdge(source_iri=ontology_iri, target_iri=imported_iri))

            if depth < max_depth:
                next_source = _resolve_import_source(imported_iri, source)
                queue.append((next_source, depth + 1))

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


def _load_graph(source: str, *, rdf_format: Optional[str]) -> Graph:
    graph = Graph()
    if source.startswith("file://"):
        graph.parse(_file_uri_to_path(source), format=rdf_format)
    else:
        graph.parse(source, format=rdf_format)
    return graph


def _resolve_import_source(import_iri: str, parent_source: str) -> str:
    """Resolve an import IRI to a source rdflib can parse."""
    parsed = urlparse(import_iri)

    if parsed.scheme in {"http", "https", "file"}:
        return import_iri
    if parsed.scheme:
        return import_iri

    if parent_source.startswith("file://"):
        parent_path = Path(_file_uri_to_path(parent_source))
        base_dir = parent_path if parent_path.exists() and parent_path.is_dir() else parent_path.parent
        return (base_dir / import_iri).resolve().as_uri()

    if parent_source.startswith("http://") or parent_source.startswith("https://"):
        return urljoin(parent_source, import_iri)

    return import_iri


def _file_uri_to_path(file_uri: str) -> str:
    parsed = urlparse(file_uri)
    if parsed.scheme != "file":
        return file_uri

    path = unquote(parsed.path)
    if parsed.netloc:
        path = f"//{parsed.netloc}{path}"
    if os_name == "nt" and path.startswith("/") and len(path) >= 3 and path[2] == ":":
        path = path[1:]
    return path
