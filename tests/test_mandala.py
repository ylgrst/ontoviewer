from __future__ import annotations

from rdflib import Graph

from ontoviewer.mandala import (
    LAYER_META,
    LAYER_ONTO,
    RADIUS_INNER,
    RADIUS_SPAN,
    assign_sectors,
    build_super_classes,
    extract_individuals,
    mandala_payload,
    normalize,
    radius_for,
    sector_distances,
)

EX = "http://example.org/onto#"


def _graph(turtle: str) -> Graph:
    graph = Graph()
    graph.parse(data=turtle, format="turtle")
    return graph


def test_extract_individuals_collects_declared_and_typed_instances():
    graph = _graph(
        f"""
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix ex: <{EX}> .

        ex:Bolt a owl:Class .
        ex:bolt1 a owl:NamedIndividual, ex:Bolt .
        ex:bolt2 a ex:Bolt .
        """
    )

    individuals = extract_individuals(graph, {f"{EX}Bolt"})

    assert individuals == {
        f"{EX}bolt1": {f"{EX}Bolt"},
        f"{EX}bolt2": {f"{EX}Bolt"},
    }


def test_extract_individuals_keeps_declared_individual_without_resolvable_type():
    graph = _graph(
        f"""
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix ex: <{EX}> .

        ex:loose a owl:NamedIndividual, <http://elsewhere.example/Unknown> .
        """
    )

    # The unresolvable type is dropped, but the individual survives and will be
    # parked on the bottom layer's axis.
    assert extract_individuals(graph, set()) == {f"{EX}loose": set()}


def test_extract_individuals_ignores_schema_entities():
    graph = _graph(
        f"""
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        @prefix ex: <{EX}> .

        <{EX}> a owl:Ontology .
        ex:Bolt a owl:Class .
        ex:hasPart a owl:ObjectProperty, owl:TransitiveProperty .
        ex:Size a rdfs:Datatype .
        """
    )

    assert extract_individuals(graph, {f"{EX}Bolt"}) == {}


def test_extract_individuals_skips_punned_class():
    graph = _graph(
        f"""
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix ex: <{EX}> .

        ex:Bolt a owl:Class .
        ex:Species a owl:Class .
        # Punning: Bolt is asserted as both a class and an instance of Species.
        ex:Bolt a ex:Species .
        """
    )

    assert extract_individuals(graph, {f"{EX}Bolt", f"{EX}Species"}) == {}


def test_build_super_classes_drops_self_loops_and_foreign_endpoints():
    classes = {"A", "B"}
    pairs = {("A", "A"), ("A", "B"), ("B", "Outside")}

    assert build_super_classes(pairs, classes) == {"A": ["B"], "B": []}


def test_assign_sectors_measures_depth_downward_from_the_sector():
    # Continuant -> Object -> Bolt, so depth grows with specialization.
    super_classes = {
        "Continuant": [],
        "Object": ["Continuant"],
        "Bolt": ["Object"],
    }

    assert assign_sectors(super_classes, ["Continuant"]) == {
        "Continuant": ("Continuant", 0),
        "Object": ("Continuant", 1),
        "Bolt": ("Continuant", 2),
    }


def test_assign_sectors_leaves_ancestors_and_strangers_unassigned():
    super_classes = {
        "Entity": [],
        "Continuant": ["Entity"],
        "Bolt": ["Continuant"],
        "Process": ["Entity"],
    }

    assignment = assign_sectors(super_classes, ["Continuant"])

    # Entity sits above the sector and Process beside it: both belong on the axis.
    assert "Entity" not in assignment
    assert "Process" not in assignment
    assert assignment["Bolt"] == ("Continuant", 1)


def test_assign_sectors_prefers_the_nearest_of_two_nested_sectors():
    super_classes = {
        "Continuant": [],
        "MaterialEntity": ["Continuant"],
        "Bolt": ["MaterialEntity"],
    }

    assignment = assign_sectors(super_classes, ["Continuant", "MaterialEntity"])

    # The general sector keeps its own slice; everything below the specific one
    # lands in the tighter slice rather than being swallowed by the ancestor.
    assert assignment["Continuant"] == ("Continuant", 0)
    assert assignment["MaterialEntity"] == ("MaterialEntity", 0)
    assert assignment["Bolt"] == ("MaterialEntity", 1)


def test_assign_sectors_breaks_diamond_ties_on_sector_iri_not_click_order():
    # Classic OWL diamond: Hybrid descends from two incomparable sectors, both
    # exactly one hop away.
    super_classes = {
        "Physical": [],
        "Abstract": [],
        "Hybrid": ["Physical", "Abstract"],
    }

    forward = assign_sectors(super_classes, ["Physical", "Abstract"])
    reversed_order = assign_sectors(super_classes, ["Abstract", "Physical"])

    assert forward["Hybrid"] == ("Abstract", 1)
    assert forward == reversed_order

    # The discarded membership stays recoverable for the info panel.
    assert sector_distances(super_classes, ["Physical", "Abstract"])["Hybrid"] == {
        "Physical": 1,
        "Abstract": 1,
    }


def test_assign_sectors_prefers_the_closer_sector_over_the_lexical_one():
    super_classes = {
        "Zeta": [],
        "Alpha": [],
        "Mid": ["Alpha"],
        "Leaf": ["Zeta", "Mid"],
    }

    # Leaf is 1 hop below Zeta and 2 below Alpha; distance wins over the tiebreak.
    assert assign_sectors(super_classes, ["Alpha", "Zeta"])["Leaf"] == ("Zeta", 1)


def test_assign_sectors_terminates_on_a_subclass_cycle():
    super_classes = {"A": ["B"], "B": ["A"]}

    assert assign_sectors(super_classes, ["A"]) == {"A": ("A", 0), "B": ("A", 1)}


def test_assign_sectors_with_no_selection_puts_everything_on_the_axis():
    super_classes = {"A": [], "B": ["A"]}

    assert assign_sectors(super_classes, []) == {}


def test_assign_sectors_ignores_a_sector_that_is_not_a_known_class():
    super_classes = {"A": []}

    assert assign_sectors(super_classes, ["Ghost"]) == {}


def test_normalize_puts_each_sectors_deepest_leaf_on_the_rim():
    assignment = {
        "Continuant": ("Continuant", 0),
        "Object": ("Continuant", 1),
        "Bolt": ("Continuant", 2),
        # A shallower sector still fills its slice out to the rim.
        "Process": ("Process", 0),
        "Assembling": ("Process", 1),
    }

    r_norm = normalize(assignment)

    assert r_norm["Continuant"] == 0.0
    assert r_norm["Object"] == 0.5
    assert r_norm["Bolt"] == 1.0
    assert r_norm["Assembling"] == 1.0


def test_normalize_handles_a_sector_with_no_descendants():
    assert normalize({"Solo": ("Solo", 0)}) == {"Solo": 0.0}


def test_radius_keeps_a_sector_root_off_the_axis():
    # The axis itself is reserved for nodes belonging to no sector.
    assert radius_for(0.0) == RADIUS_INNER
    assert radius_for(1.0) == RADIUS_INNER + RADIUS_SPAN


def test_radius_grows_monotonically_from_meta_parent_to_domain_child():
    # The property that makes rdf:type edges read as near-vertical drops: a
    # domain subclass never sits closer to the axis than its meta parent.
    super_classes = {
        "Continuant": [],
        "Object": ["Continuant"],
        "Bolt": ["Object"],
        "M6Bolt": ["Bolt"],
    }
    r_norm = normalize(assign_sectors(super_classes, ["Continuant"]))
    radii = [radius_for(r_norm[cls]) for cls in ("Continuant", "Object", "Bolt", "M6Bolt")]

    assert radii == sorted(radii)
    assert radii[0] < radii[-1]


def test_mandala_payload_layers_root_classes_apart_from_imported_ones():
    root = "http://example.org/domain"
    meta = "http://example.org/upper"

    payload = mandala_payload(
        class_nodes={"http://example.org/upper#Entity", "http://example.org/domain#Bolt"},
        class_owner={
            "http://example.org/upper#Entity": meta,
            "http://example.org/domain#Bolt": root,
        },
        class_human_labels={"http://example.org/domain#Bolt": "Bolt"},
        class_raw_labels={
            "http://example.org/upper#Entity": "Entity",
            "http://example.org/domain#Bolt": "Bolt",
        },
        subclass_pairs={("http://example.org/domain#Bolt", "http://example.org/upper#Entity")},
        individuals={"http://example.org/domain#bolt1": {"http://example.org/domain#Bolt"}},
        individual_labels={"http://example.org/domain#bolt1": "bolt 1"},
        ontology_ids=[meta, root],
        ontology_color={meta: "#111111", root: "#222222"},
        ontology_labels={meta: "upper", root: "domain"},
        root_iri=root,
    )

    by_id = {entry["id"]: entry for entry in payload["classes"]}
    assert by_id["http://example.org/upper#Entity"]["layer"] == LAYER_META
    assert by_id["http://example.org/domain#Bolt"]["layer"] == LAYER_ONTO

    # The cross-ontology subclass edge survives: it is what hands the domain
    # class its slice.
    assert by_id["http://example.org/domain#Bolt"]["superClasses"] == [
        "http://example.org/upper#Entity"
    ]
    assert by_id["http://example.org/domain#Bolt"]["color"] == "#222222"

    assert payload["individuals"] == [
        {
            "id": "http://example.org/domain#bolt1",
            "label": "bolt 1",
            "types": ["http://example.org/domain#Bolt"],
        }
    ]
    assert {o["iri"]: o["defaultLayer"] for o in payload["ontologies"]} == {
        meta: LAYER_META,
        root: LAYER_ONTO,
    }
