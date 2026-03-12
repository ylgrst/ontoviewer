from __future__ import annotations

from typing import Iterable, Optional

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DC, DCTERMS, RDFS, SKOS

# Common annotation properties used to store human-readable entity names.
LABEL_PREDICATES = (
    RDFS.label,
    SKOS.prefLabel,
    DCTERMS.title,
    DC.title,
    URIRef("http://purl.obolibrary.org/obo/IAO_0000111"),
    SKOS.altLabel,
    URIRef("http://www.geneontology.org/formats/oboInOwl#hasExactSynonym"),
)


def preferred_annotation_label(
    graph: Graph,
    resource_iri: str | URIRef,
    *,
    preferred_lang: str = "en",
) -> Optional[str]:
    """Return the best human-readable label from common annotation properties."""
    resource = resource_iri if isinstance(resource_iri, URIRef) else URIRef(resource_iri)

    for predicate in LABEL_PREDICATES:
        best = _pick_literal(graph.objects(resource, predicate), preferred_lang=preferred_lang)
        if best:
            return best
    return None


def _pick_literal(values: Iterable[object], *, preferred_lang: str) -> Optional[str]:
    preferred: list[str] = []
    neutral: list[str] = []
    other: list[str] = []

    preferred_lang = preferred_lang.lower()

    for value in values:
        if not isinstance(value, Literal):
            continue
        text = str(value).strip()
        if not text:
            continue

        lang = (value.language or "").lower()
        if lang and (lang == preferred_lang or lang.startswith(f"{preferred_lang}-")):
            preferred.append(text)
        elif not lang:
            neutral.append(text)
        else:
            other.append(text)

    for bucket in (preferred, neutral, other):
        if bucket:
            return bucket[0]
    return None
