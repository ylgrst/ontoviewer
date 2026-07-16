"""Data extraction and geometry for the 3D layered mandala view.

The mandala stacks an ontology closure on three horizontal discs -- imported
meta-ontology classes on top, the root ontology's own classes in the middle,
and instantiated individuals at the bottom -- and slices each disc into angular
sectors rooted at meta-classes the user picks interactively.

Two coordinates carry meaning:

``theta`` (which slice)
    A class belongs to the sector of the selected meta-class it descends from.
    An individual inherits the sector of its type. Nodes that descend from no
    selected sector have no defined angle and collapse onto the central axis --
    those are the taxonomic roots and the classes the slices have in common.

``r`` (distance from the axis)
    Taxonomic depth below the sector's meta-class, normalized per sector so the
    deepest leaf of every slice lands on the rim. Depth is counted downward from
    the meta-class *through* the domain layer, never restarted per layer, so
    radius grows monotonically as you descend and ``rdf:type`` edges read as
    near-vertical drops beneath their class.

``assign_sectors`` and ``normalize`` are the reference implementation of that
geometry. Sector selection has to respond to a click without re-running Python,
so the live implementation is the ``assignSectors``/``normalize`` pair in the
mandala IIFE of :mod:`ontoviewer.visualize`. These two are kept structurally
parallel on purpose: this one is what the test suite pins down.
"""

from __future__ import annotations

from collections import deque
from typing import Dict, Iterable, List, Mapping, Sequence, Set, Tuple

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS

LAYER_META = "meta"
LAYER_ONTO = "onto"
LAYER_OBJECTS = "objects"

# Matches the reference mandala's toCylinder(): the innermost ring sits off-axis
# so that r_norm == 0 (a sector's own root class) stays distinguishable from the
# true axis, which is reserved for nodes belonging to no sector at all.
RADIUS_INNER = 0.18
RADIUS_SPAN = 0.92

# rdf:type objects that describe an entity's *schema role* rather than
# classifying an object. A subject typed only by these is not an individual.
NON_INDIVIDUAL_TYPES: frozenset[str] = frozenset(
    str(iri)
    for iri in (
        OWL.AllDifferent,
        OWL.AllDisjointClasses,
        OWL.AllDisjointProperties,
        OWL.AnnotationProperty,
        OWL.AsymmetricProperty,
        OWL.Axiom,
        OWL.Class,
        OWL.DatatypeProperty,
        OWL.DeprecatedClass,
        OWL.DeprecatedProperty,
        OWL.FunctionalProperty,
        OWL.InverseFunctionalProperty,
        OWL.IrreflexiveProperty,
        OWL.NamedIndividual,
        OWL.Ontology,
        OWL.ObjectProperty,
        OWL.ReflexiveProperty,
        OWL.Restriction,
        OWL.SymmetricProperty,
        OWL.TransitiveProperty,
        RDF.Property,
        RDFS.Class,
        RDFS.Datatype,
    )
)


def extract_individuals(graph: Graph, class_nodes: Set[str]) -> Dict[str, Set[str]]:
    """Map each individual to the known classes it is an instance of.

    A subject counts as an individual when it is declared an ``owl:NamedIndividual``
    or carries an ``rdf:type`` naming a class we render. Types that resolve to no
    rendered class are dropped -- an individual can legitimately end up with an
    empty type set, which places it on the bottom layer's axis.

    A subject that is also a rendered class is skipped entirely: under OWL punning
    the same IRI may be asserted as both, and the class identity is the one the
    rest of the pipeline already knows about.
    """
    declared: Set[str] = {
        str(subject)
        for subject in graph.subjects(RDF.type, OWL.NamedIndividual)
        if isinstance(subject, URIRef)
    }

    asserted_types: Dict[str, Set[str]] = {}
    for subject, _, type_iri in graph.triples((None, RDF.type, None)):
        if not isinstance(subject, URIRef) or not isinstance(type_iri, URIRef):
            continue
        type_str = str(type_iri)
        if type_str in NON_INDIVIDUAL_TYPES:
            continue
        asserted_types.setdefault(str(subject), set()).add(type_str)

    individuals: Dict[str, Set[str]] = {}
    for candidate in declared | set(asserted_types):
        if candidate in class_nodes:
            continue
        types = {t for t in asserted_types.get(candidate, set()) if t in class_nodes}
        if candidate in declared or types:
            individuals[candidate] = types
    return individuals


def build_super_classes(
    subclass_pairs: Iterable[Tuple[str, str]],
    class_nodes: Set[str],
) -> Dict[str, List[str]]:
    """Invert subclass pairs into child -> sorted parents, dropping self-loops.

    ``rdfs:subClassOf`` is asserted freely in the wild: ``A subClassOf A`` and
    longer cycles both occur. Self-loops are stripped here so no consumer has to
    think about them; genuine cycles survive and are handled by the visited-set
    guards in :func:`sector_distances` and the JS mirror.
    """
    super_classes: Dict[str, List[str]] = {cls: [] for cls in class_nodes}
    seen: Set[Tuple[str, str]] = set()
    for child, parent in subclass_pairs:
        if child == parent:
            continue
        if child not in class_nodes or parent not in class_nodes:
            continue
        if (child, parent) in seen:
            continue
        seen.add((child, parent))
        super_classes[child].append(parent)
    for parents in super_classes.values():
        parents.sort()
    return super_classes


def _sub_classes(super_classes: Mapping[str, Sequence[str]]) -> Dict[str, List[str]]:
    children: Dict[str, List[str]] = {cls: [] for cls in super_classes}
    for child, parents in super_classes.items():
        for parent in parents:
            children.setdefault(parent, []).append(child)
    for kids in children.values():
        kids.sort()
    return children


def sector_distances(
    super_classes: Mapping[str, Sequence[str]],
    sectors: Sequence[str],
) -> Dict[str, Dict[str, int]]:
    """For each class, the hop count down from every sector that reaches it.

    A class absent from the result descends from no selected sector.
    """
    children = _sub_classes(super_classes)
    distances: Dict[str, Dict[str, int]] = {}

    for sector in sectors:
        if sector not in super_classes:
            continue
        visited: Set[str] = {sector}
        queue: deque[Tuple[str, int]] = deque([(sector, 0)])
        while queue:
            current, depth = queue.popleft()
            distances.setdefault(current, {})[sector] = depth
            for child in children.get(current, []):
                if child not in visited:
                    visited.add(child)
                    queue.append((child, depth + 1))
    return distances


def assign_sectors(
    super_classes: Mapping[str, Sequence[str]],
    sectors: Sequence[str],
) -> Dict[str, Tuple[str, int]]:
    """Give each reachable class its primary sector and depth below that sector.

    The primary sector is the nearest one. Nesting therefore resolves itself: if
    a general sector and a more specific one below it are both selected, classes
    under the specific one are closer to it and land in the tighter slice.

    Ties -- a class equidistant from two incomparable sectors, the usual shape of
    a multiple-inheritance diamond -- break on the lexicographically smaller
    sector IRI, so placement never depends on the order the user clicked.
    Secondary memberships stay visible via :func:`sector_distances`.

    Classes descending from no sector are omitted: they belong on the axis.
    """
    ordered = sorted(set(sectors))
    distances = sector_distances(super_classes, ordered)

    assignment: Dict[str, Tuple[str, int]] = {}
    for cls, per_sector in distances.items():
        best_sector = ""
        best_depth = -1
        for sector in ordered:
            depth = per_sector.get(sector)
            if depth is None:
                continue
            if best_depth < 0 or depth < best_depth:
                best_sector = sector
                best_depth = depth
        if best_depth >= 0:
            assignment[cls] = (best_sector, best_depth)
    return assignment


def normalize(assignment: Mapping[str, Tuple[str, int]]) -> Dict[str, float]:
    """Scale each class's depth to [0, 1] against the deepest node in its sector.

    Normalizing per sector -- rather than per (sector, layer) -- is what keeps
    radius comparable across the discs. Depth is already measured from the meta
    sector root downward through the domain layer, so a subclass can never sit at
    a smaller radius than its own meta parent, and each slice's deepest leaf
    lands exactly on the rim.
    """
    deepest: Dict[str, int] = {}
    for sector, depth in assignment.values():
        if depth > deepest.get(sector, 0):
            deepest[sector] = depth

    return {
        cls: depth / max(1, deepest.get(sector, 0))
        for cls, (sector, depth) in assignment.items()
    }


def radius_for(r_norm: float) -> float:
    """Map a normalized depth onto the disc's usable annulus."""
    return RADIUS_INNER + r_norm * RADIUS_SPAN


def mandala_payload(
    *,
    class_nodes: Set[str],
    class_owner: Mapping[str, str],
    class_human_labels: Mapping[str, str],
    class_raw_labels: Mapping[str, str],
    subclass_pairs: Iterable[Tuple[str, str]],
    individuals: Mapping[str, Set[str]],
    individual_labels: Mapping[str, str],
    ontology_ids: Sequence[str],
    ontology_color: Mapping[str, str],
    ontology_labels: Mapping[str, str],
    root_iri: str,
) -> Dict[str, object]:
    """Build the JSON blob the mandala renderer consumes.

    Deliberately separate from the vis-network DataSet: individuals never enter
    the 2D graph and family-tree views, which keeps a large ABox from swamping
    them, and keeps this feature off those views' code paths entirely.

    ``superClasses`` carries the *full* subclass graph. The nodes' ``treeChildren``
    cannot stand in for it -- the family-tree layout drops subclass edges that
    cross an ontology boundary, and those are precisely the edges tying a domain
    class to the meta parent that gives it its slice.
    """
    super_classes = build_super_classes(subclass_pairs, class_nodes)

    classes = [
        {
            "id": cls,
            "humanLabel": class_human_labels.get(cls, class_raw_labels.get(cls, cls)),
            "rawLabel": class_raw_labels.get(cls, cls),
            "color": ontology_color.get(class_owner.get(cls, ""), "#9ca3af"),
            "ontologyIri": class_owner.get(cls, root_iri),
            "layer": LAYER_ONTO if class_owner.get(cls) == root_iri else LAYER_META,
            "superClasses": super_classes.get(cls, []),
        }
        for cls in sorted(class_nodes)
    ]

    individual_entries = [
        {
            "id": iri,
            "label": individual_labels.get(iri, iri),
            "types": sorted(types),
        }
        for iri, types in sorted(individuals.items())
    ]

    ontologies = [
        {
            "iri": iri,
            "label": ontology_labels.get(iri, iri),
            "color": ontology_color.get(iri, "#e5e7eb"),
            "defaultLayer": LAYER_ONTO if iri == root_iri else LAYER_META,
        }
        for iri in ontology_ids
    ]

    return {
        "rootIri": root_iri,
        "classes": classes,
        "individuals": individual_entries,
        "ontologies": ontologies,
    }
