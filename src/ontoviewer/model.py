from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from rdflib import Graph


@dataclass(slots=True)
class OntologyDocument:
    iri: str
    source: str
    depth: int
    graph: Graph


@dataclass(slots=True)
class ImportEdge:
    source_iri: str
    target_iri: str


@dataclass(slots=True)
class OntologyClosure:
    root_iri: str
    documents: Dict[str, OntologyDocument] = field(default_factory=dict)
    import_edges: List[ImportEdge] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
