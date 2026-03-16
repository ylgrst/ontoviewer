from __future__ import annotations

from collections import deque
from contextlib import contextmanager
from os import name as os_name
from pathlib import Path
import ssl
from typing import Deque, Optional, Set, Tuple
from urllib.error import URLError
from urllib.parse import unquote, urljoin, urlparse

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF

from ontoviewer.model import ImportEdge, OntologyClosure, OntologyDocument


def load_ontology_closure(
    ontology_file: Path,
    *,
    max_depth: int = 2,
    rdf_format: Optional[str] = None,
    allow_insecure_ssl: bool = False,
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
            graph, used_insecure_ssl = _load_graph(
                source,
                rdf_format=rdf_format,
                allow_insecure_ssl=allow_insecure_ssl,
            )
        except Exception as exc:  # pragma: no cover - defensive for unknown RDF parser errors
            closure.errors.append(f"Could not load {source}: {exc}")
            continue

        if used_insecure_ssl:
            closure.errors.append(
                "Loaded "
                f"{source} with SSL verification disabled after certificate validation failed. "
                "Use this fallback only for hosts you trust."
            )

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
            next_source = _resolve_import_source(imported_iri, source)
            edge_key = (ontology_iri, next_source)
            if edge_key not in seen_import_edges:
                seen_import_edges.add(edge_key)
                closure.import_edges.append(ImportEdge(source_iri=ontology_iri, target_iri=next_source))

            if depth < max_depth:
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


def _load_graph(
    source: str,
    *,
    rdf_format: Optional[str],
    allow_insecure_ssl: bool = False,
) -> tuple[Graph, bool]:
    graph = Graph()
    if source.startswith("file://"):
        graph.parse(_file_uri_to_path(source), format=rdf_format)
        return graph, False

    try:
        graph.parse(source, format=rdf_format)
        return graph, False
    except Exception as exc:
        if not allow_insecure_ssl or not _is_ssl_certificate_verification_error(exc):
            raise

    # rdflib ultimately relies on urllib for remote fetches, so a temporary
    # context swap lets us retry only this one parse with certificate checks off.
    retry_graph = Graph()
    with _temporary_unverified_ssl_context():
        retry_graph.parse(source, format=rdf_format)
    return retry_graph, True


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


def _is_ssl_certificate_verification_error(exc: Exception) -> bool:
    seen: Set[int] = set()
    stack: list[BaseException] = [exc]

    while stack:
        current = stack.pop()
        marker = id(current)
        if marker in seen:
            continue
        seen.add(marker)

        if isinstance(current, ssl.SSLCertVerificationError):
            return True
        if isinstance(current, ssl.SSLError) and "CERTIFICATE_VERIFY_FAILED" in str(current):
            return True
        if isinstance(current, URLError):
            reason = current.reason
            if isinstance(reason, BaseException):
                stack.append(reason)
            elif isinstance(reason, str) and "certificate verify failed" in reason.lower():
                return True

        text = str(current)
        if "CERTIFICATE_VERIFY_FAILED" in text or "certificate verify failed" in text.lower():
            return True

        linked = getattr(current, "__cause__", None)
        if isinstance(linked, BaseException):
            stack.append(linked)
        linked = getattr(current, "__context__", None)
        if isinstance(linked, BaseException):
            stack.append(linked)

    return False


@contextmanager
def _temporary_unverified_ssl_context():
    original_context_factory = ssl._create_default_https_context
    ssl._create_default_https_context = ssl._create_unverified_context
    try:
        yield
    finally:
        ssl._create_default_https_context = original_context_factory
