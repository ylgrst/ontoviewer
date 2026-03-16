from __future__ import annotations

from collections import deque
import hashlib
import json
from html import escape
from pathlib import Path
from typing import Dict, Literal, Optional, Set, Tuple

from pyvis.network import Network
from rdflib import URIRef
from rdflib.namespace import OWL, RDF, RDFS

from ontoviewer.labels import preferred_annotation_label
from ontoviewer.model import OntologyClosure

PALETTE = [
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#17becf",
    "#bcbd22",
    "#8c564b",
    "#e377c2",
    "#9467bd",
    "#7f7f7f",
]


LabelMode = Literal["human", "raw"]


def render_interactive_graph(
    closure: OntologyClosure,
    output_path: Path,
    *,
    label_mode: LabelMode = "human",
) -> Dict[str, int]:
    """Render an interactive HTML graph with ontology-aware colors and clustering controls."""
    source_to_ontology_iri = {
        document.source: ontology_iri for ontology_iri, document in closure.documents.items()
    }
    canonical_import_edges = {
        (
            source_to_ontology_iri.get(edge.source_iri, edge.source_iri),
            source_to_ontology_iri.get(edge.target_iri, edge.target_iri),
        )
        for edge in closure.import_edges
    }

    loaded_ontology_ids = list(closure.documents.keys())
    ontology_color = {iri: PALETTE[idx % len(PALETTE)] for idx, iri in enumerate(loaded_ontology_ids)}
    ontology_legend = {iri: ontology_color[iri] for iri in loaded_ontology_ids}
    ontology_group = {iri: _group_id(iri) for iri in loaded_ontology_ids}
    group_label = {ontology_group[iri]: _short_label(iri) for iri in loaded_ontology_ids}

    ontology_refs: Set[str] = set(loaded_ontology_ids)
    if closure.root_iri:
        ontology_refs.add(closure.root_iri)
    for source_iri, target_iri in canonical_import_edges:
        ontology_refs.add(source_iri)
        ontology_refs.add(target_iri)
    ontology_ids = sorted(ontology_refs)

    net = Network(height="850px", width="100%", directed=True, notebook=False, cdn_resources="in_line")
    net.set_options(
        """
        {
          "interaction": {
            "hover": true,
            "navigationButtons": true,
            "keyboard": true,
            "hideEdgesOnDrag": true
          },
          "layout": {
            "improvedLayout": true
          },
          "nodes": {
            "font": {
              "size": 14,
              "strokeWidth": 4,
              "strokeColor": "#f3f4f6"
            }
          },
          "physics": {
            "enabled": true,
            "solver": "barnesHut",
            "barnesHut": {
              "gravitationalConstant": -8000,
              "springLength": 190,
              "springConstant": 0.02,
              "damping": 0.28
            },
            "stabilization": {
              "iterations": 300
            }
          },
          "edges": {
            "smooth": false,
            "arrows": {
              "to": {
                "enabled": true
              }
            }
          }
        }
        """
    )

    for iri in ontology_ids:
        is_loaded = iri in closure.documents
        net.add_node(
            f"ont:{iri}",
            label=_short_label(iri),
            title=f"{iri}\n{'loaded' if is_loaded else 'declared import (unresolved)'}",
            shape="box",
            color=ontology_color.get(iri, "#e5e7eb"),
            borderWidth=2 if is_loaded else 1,
            font={"color": "#111827" if is_loaded else "#6b7280"},
            hidden=True,
            physics=False,
            ontologyGroup=ontology_group.get(iri, "unknown"),
            ontologyIri=iri,
            isOntologyNode=True,
            ontologyLoaded=is_loaded,
            level=0,
        )

    class_nodes: Set[str] = set()
    class_owner: Dict[str, str] = {}
    class_display_labels: Dict[str, str] = {}
    property_display_labels: Dict[str, str] = {}
    relation_edges: Set[Tuple[str, str, str, str, str]] = set()

    for ont_iri, document in closure.documents.items():
        graph = document.graph

        for cls_iri in _extract_declared_classes(graph):
            class_nodes.add(cls_iri)
            class_owner.setdefault(cls_iri, ont_iri)
            if cls_iri not in class_display_labels:
                readable = preferred_annotation_label(graph, cls_iri)
                if readable:
                    class_display_labels[cls_iri] = readable
        class_nodes.update(_extract_referenced_classes(graph))

    for cls in class_nodes:
        if cls not in class_owner:
            inferred_owner = _infer_owner_from_iri(cls, loaded_ontology_ids)
            if inferred_owner:
                class_owner[cls] = inferred_owner

    for ont_iri, document in closure.documents.items():
        graph = document.graph

        for s, _, o in graph.triples((None, RDFS.subClassOf, None)):
            if isinstance(s, URIRef) and isinstance(o, URIRef):
                relation_edges.add((str(s), str(o), "subClassOf", "subClassOf", "subclass"))

        for prop in _extract_object_properties(graph):
            prop_iri = str(prop)
            human_property_label = property_display_labels.get(prop_iri)
            if human_property_label is None:
                human_property_label = preferred_annotation_label(graph, prop_iri) or _short_label(prop_iri)
                property_display_labels[prop_iri] = human_property_label
            raw_property_label = _short_label(prop_iri)

            domains = [d for d in graph.objects(prop, RDFS.domain) if isinstance(d, URIRef)]
            ranges = [r for r in graph.objects(prop, RDFS.range) if isinstance(r, URIRef)]
            for domain in domains:
                for rng in ranges:
                    relation_edges.add(
                        (
                            str(domain),
                            str(rng),
                            human_property_label,
                            raw_property_label,
                            "property",
                        )
                    )

    subclass_pairs = {
        (src, dst)
        for src, dst, _, _, edge_type in relation_edges
        if edge_type == "subclass" and src in class_nodes and dst in class_nodes
    }
    direct_subclasses = {src for src, _ in subclass_pairs}
    root_classes = class_nodes - direct_subclasses
    ontology_level = _compute_ontology_levels(
        ontology_ids=ontology_ids,
        root_iri=closure.root_iri,
        canonical_import_edges=canonical_import_edges,
        documents=closure.documents,
    )
    class_level = _compute_class_levels(
        class_nodes=class_nodes,
        subclass_pairs=subclass_pairs,
        class_owner=class_owner,
        ontology_level=ontology_level,
    )

    for cls in class_nodes:
        owner = class_owner.get(cls, closure.root_iri)
        color = ontology_color.get(owner, "#9ca3af")
        ontology_group_id = ontology_group.get(owner, "unknown")
        short = _short_label(cls)
        human_display = class_display_labels.get(cls, short)
        raw_display = short
        display = human_display if label_mode == "human" else raw_display
        title = cls if human_display == short else f"{human_display} ({short})\n{cls}"
        net.add_node(
            cls,
            label=display,
            title=title,
            color=color,
            shape="dot",
            size=16,
            borderWidth=1,
            isClassNode=True,
            humanLabel=human_display,
            rawLabel=raw_display,
            ontologyGroup=ontology_group_id,
            ontologyIri=owner,
            level=class_level.get(cls, 1),
        )
        if owner and cls in root_classes:
            net.add_edge(
                f"ont:{owner}",
                cls,
                color="#94a3b8",
                dashes=True,
                width=1,
                title="defined in ontology",
                edgeType="ontology-membership",
                semanticFrom=f"ont:{owner}",
                semanticTo=cls,
                treeFrom=f"ont:{owner}",
                treeTo=cls,
                physics=False,
                hidden=True,
            )
            net.add_edge(
                f"ont:{owner}",
                cls,
                edgeType="layout-root",
                hidden=True,
                physics=True,
                length=240,
            )

    rendered_relations = 0
    for src, dst, human_label, raw_label, edge_type in relation_edges:
        if src in class_nodes and dst in class_nodes:
            if edge_type == "subclass":
                net.add_edge(
                    src,
                    dst,
                    title="subClassOf",
                    color="#2563eb",
                    width=1.6,
                    edgeType=edge_type,
                    semanticFrom=src,
                    semanticTo=dst,
                    treeFrom=dst,
                    treeTo=src,
                    physics=False,
                )
                net.add_edge(
                    src,
                    dst,
                    edgeType="layout-subclass",
                    hidden=True,
                    physics=True,
                    length=120,
                )
            else:
                display_label = human_label if label_mode == "human" else raw_label
                net.add_edge(
                    src,
                    dst,
                    label=display_label,
                    title=edge_type,
                    color="#111827",
                    width=1.8,
                    edgeType=edge_type,
                    humanLabel=human_label,
                    rawLabel=raw_label,
                    semanticFrom=src,
                    semanticTo=dst,
                    treeFrom=src,
                    treeTo=dst,
                    physics=False,
                )
            rendered_relations += 1

    for source_iri, target_iri in canonical_import_edges:
        net.add_edge(
            f"ont:{source_iri}",
            f"ont:{target_iri}",
            label="imports",
            color="#f59e0b",
            dashes=True,
            width=2.4,
            edgeType="imports",
            semanticFrom=f"ont:{source_iri}",
            semanticTo=f"ont:{target_iri}",
            treeFrom=f"ont:{target_iri}",
            treeTo=f"ont:{source_iri}",
            physics=False,
            hidden=True,
        )

    for iri in ontology_ids:
        node = net.get_node(f"ont:{iri}")
        if node is not None:
            node["level"] = ontology_level.get(iri, 0)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    net.write_html(str(output_path))
    has_unresolved_ontology_nodes = any(iri not in closure.documents for iri in ontology_ids)
    _inject_cluster_controls(
        output_path,
        group_label,
        initial_label_mode=label_mode,
        ontology_legend=ontology_legend,
        has_unresolved_ontology_nodes=has_unresolved_ontology_nodes,
    )

    unresolved_import_targets = {
        target_iri for _, target_iri in canonical_import_edges if target_iri not in closure.documents
    }

    return {
        "ontologies": len(closure.documents),
        "ontology_refs": len(ontology_ids),
        "classes": len(class_nodes),
        "relations": rendered_relations,
        "imports": len(canonical_import_edges),
        "unresolved_imports": len(unresolved_import_targets),
    }


def _extract_declared_classes(graph) -> Set[str]:
    classes: Set[str] = set()
    for cls in graph.subjects(RDF.type, OWL.Class):
        if isinstance(cls, URIRef):
            classes.add(str(cls))
    for cls in graph.subjects(RDF.type, RDFS.Class):
        if isinstance(cls, URIRef):
            classes.add(str(cls))
    return classes


def _extract_referenced_classes(graph) -> Set[str]:
    classes: Set[str] = set()
    for obj in graph.objects(None, RDFS.domain):
        if isinstance(obj, URIRef):
            classes.add(str(obj))
    for obj in graph.objects(None, RDFS.range):
        if isinstance(obj, URIRef):
            classes.add(str(obj))
    return classes


def _extract_object_properties(graph) -> Set[URIRef]:
    properties: Set[URIRef] = set()
    for prop in graph.subjects(RDF.type, OWL.ObjectProperty):
        if isinstance(prop, URIRef):
            properties.add(prop)
    for prop in graph.subjects(RDF.type, RDF.Property):
        if isinstance(prop, URIRef):
            properties.add(prop)
    return properties


def _short_label(iri: str) -> str:
    if "#" in iri:
        return iri.rsplit("#", 1)[-1]
    stripped = iri.rstrip("/")
    if "/" in stripped:
        return stripped.rsplit("/", 1)[-1]
    return iri


def _group_id(iri: str) -> str:
    return f"g{hashlib.sha1(iri.encode('utf-8')).hexdigest()[:10]}"


def _infer_owner_from_iri(class_iri: str, ontology_ids: list[str]) -> Optional[str]:
    best_match: Optional[str] = None
    best_len = -1
    for ontology_iri in ontology_ids:
        if _iri_matches_ontology(class_iri, ontology_iri) and len(ontology_iri) > best_len:
            best_match = ontology_iri
            best_len = len(ontology_iri)
    return best_match


def _iri_matches_ontology(entity_iri: str, ontology_iri: str) -> bool:
    if entity_iri == ontology_iri:
        return True
    normalized = ontology_iri.rstrip("/#")
    for prefix in (ontology_iri, normalized):
        if entity_iri.startswith(prefix + "#") or entity_iri.startswith(prefix + "/"):
            return True
    return False


def _compute_ontology_levels(
    *,
    ontology_ids: list[str],
    root_iri: str,
    canonical_import_edges: Set[Tuple[str, str]],
    documents: Dict[str, object],
) -> Dict[str, int]:
    depths: Dict[str, int] = {}
    children: Dict[str, list[str]] = {}
    indegree: Dict[str, int] = {iri: 0 for iri in ontology_ids}

    # In family-tree mode, imported ontologies sit above the ontologies that import them.
    for importer_iri, imported_iri in canonical_import_edges:
        children.setdefault(imported_iri, []).append(importer_iri)
        indegree[importer_iri] = indegree.get(importer_iri, 0) + 1
        indegree.setdefault(imported_iri, 0)

    queue: deque[str] = deque()
    for iri in ontology_ids:
        if indegree.get(iri, 0) == 0:
            depths[iri] = 0
            queue.append(iri)

    if not queue and root_iri:
        depths[root_iri] = 0
        queue.append(root_iri)

    while queue:
        current = queue.popleft()
        current_depth = depths.get(current, 0)
        for child in children.get(current, []):
            next_depth = current_depth + 1
            if child not in depths or next_depth < depths[child]:
                depths[child] = next_depth
                queue.append(child)

    if len(depths) < len(ontology_ids):
        max_document_depth = max((getattr(doc, "depth", 0) for doc in documents.values()), default=0)
        max_known_depth = max(depths.values(), default=0)
        for iri in ontology_ids:
            if iri in depths:
                continue
            doc = documents.get(iri)
            guessed_depth = getattr(doc, "depth", 0) if doc is not None else 0
            depths[iri] = max_known_depth + max(max_document_depth - guessed_depth, 0)

    return {iri: depths.get(iri, 0) * 4 for iri in ontology_ids}


def _compute_class_levels(
    *,
    class_nodes: Set[str],
    subclass_pairs: Set[Tuple[str, str]],
    class_owner: Dict[str, str],
    ontology_level: Dict[str, int],
) -> Dict[str, int]:
    parents: Dict[str, Set[str]] = {cls: set() for cls in class_nodes}
    children: Dict[str, Set[str]] = {cls: set() for cls in class_nodes}
    levels: Dict[str, int] = {}

    for child, parent in subclass_pairs:
        parents.setdefault(child, set()).add(parent)
        children.setdefault(parent, set()).add(child)

    roots = [cls for cls in class_nodes if not parents.get(cls)]
    queue: deque[str] = deque()

    for cls in roots:
        owner = class_owner.get(cls)
        levels[cls] = ontology_level.get(owner, 0) + 1
        queue.append(cls)

    while queue:
        parent = queue.popleft()
        parent_level = levels.get(parent, 1)
        for child in children.get(parent, set()):
            next_level = parent_level + 1
            if child not in levels or next_level < levels[child]:
                levels[child] = next_level
                queue.append(child)

    for cls in class_nodes:
        if cls not in levels:
            owner = class_owner.get(cls)
            levels[cls] = ontology_level.get(owner, 0) + 1

    return levels


def _inject_cluster_controls(
    output_path: Path,
    group_labels: Dict[str, str],
    *,
    initial_label_mode: LabelMode,
    ontology_legend: Dict[str, str],
    has_unresolved_ontology_nodes: bool,
) -> None:
    html = output_path.read_text(encoding="utf-8")
    ontology_items = "".join(
        f"""
        <li class="ontoviewer-ontology-item">
          <button
            type="button"
            class="ontoviewer-ontology-entry"
            data-group-id="{escape(_group_id(iri))}"
            onclick="window.ontoviewerToggleOntologyGroup('{escape(_group_id(iri))}')"
            title="{escape(iri)}"
          >
            <span class="ontoviewer-ontology-entry-main">
              <span class="ontoviewer-swatch" style="background:{escape(color)}"></span>
              <span>{escape(_short_label(iri))}</span>
            </span>
            <span class="ontoviewer-ontology-state">Collapse</span>
          </button>
        </li>
        """
        for iri, color in ontology_legend.items()
    )
    if not ontology_items:
        ontology_items = "<li class='ontoviewer-ontology-item'><span>No loaded ontologies</span></li>"

    unresolved_item = ""
    if has_unresolved_ontology_nodes:
        unresolved_item = """
        <li class="ontoviewer-ontology-item">
          <span class="ontoviewer-swatch" style="background:#e5e7eb"></span>
          <span>Unresolved imported ontology</span>
        </li>
        """

    controls = f"""
<style>
:root {{
  color-scheme: light;
  --ov-page-bg: #eef2f7;
  --ov-network-bg: #f8fafc;
  --ov-panel-bg: rgba(255, 255, 255, 0.97);
  --ov-border: #d1d5db;
  --ov-border-strong: #cbd5e1;
  --ov-text: #111827;
  --ov-text-muted: #4b5563;
  --ov-text-soft: #6b7280;
  --ov-button-bg: #f8fafc;
  --ov-button-bg-active: #e2e8f0;
  --ov-button-text: #111827;
  --ov-shadow: rgba(0, 0, 0, 0.08);
}}
html.ontoviewer-dark,
body.ontoviewer-dark {{
  color-scheme: dark;
  --ov-page-bg: #020617;
  --ov-network-bg: #0f172a;
  --ov-panel-bg: rgba(15, 23, 42, 0.96);
  --ov-border: #334155;
  --ov-border-strong: #475569;
  --ov-text: #e2e8f0;
  --ov-text-muted: #cbd5e1;
  --ov-text-soft: #94a3b8;
  --ov-button-bg: #0f172a;
  --ov-button-bg-active: #1e293b;
  --ov-button-text: #f8fafc;
  --ov-shadow: rgba(2, 6, 23, 0.45);
}}
html, body {{
  margin: 0;
  padding: 0;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: var(--ov-page-bg);
  color: var(--ov-text);
}}
#mynetwork {{
  width: calc(100vw - 360px) !important;
  height: 100vh !important;
  background: var(--ov-network-bg);
}}
.ontoviewer-controls {{
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 999;
  width: 360px;
  background: var(--ov-panel-bg);
  border-left: 1px solid var(--ov-border);
  border-radius: 0;
  padding: 10px;
  box-shadow: -8px 0 24px var(--ov-shadow);
  font-family: sans-serif;
  overflow: auto;
}}
.ontoviewer-controls button {{
  margin-right: 6px;
  margin-bottom: 6px;
  padding: 6px 10px;
  border: 1px solid var(--ov-border-strong);
  border-radius: 6px;
  cursor: pointer;
  background: var(--ov-button-bg);
  color: var(--ov-button-text);
}}
.ontoviewer-controls button[disabled] {{
  opacity: 0.6;
  cursor: default;
}}
.ontoviewer-controls button:not([disabled]):hover {{
  background: var(--ov-button-bg-active);
}}
.ontoviewer-search {{
  display: grid;
  gap: 6px;
  margin-bottom: 4px;
}}
.ontoviewer-search-input {{
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--ov-border-strong);
  border-radius: 6px;
  background: var(--ov-button-bg);
  color: var(--ov-button-text);
  font: inherit;
}}
.ontoviewer-search-input::placeholder {{
  color: var(--ov-text-soft);
}}
.ontoviewer-search-row {{
  display: flex;
  align-items: center;
  gap: 6px;
}}
.ontoviewer-search-row button {{
  margin: 0;
  min-width: 34px;
  padding: 4px 8px;
}}
.ontoviewer-search-count {{
  font-size: 12px;
  color: var(--ov-text-soft);
}}
.ontoviewer-controls hr {{
  border: 0;
  border-top: 1px solid var(--ov-border);
  margin: 10px 0;
}}
.ontoviewer-legend-title {{
  font-size: 12px;
  font-weight: 700;
  color: var(--ov-text);
  margin-bottom: 4px;
}}
.ontoviewer-legend-row {{
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--ov-text-muted);
  margin-bottom: 4px;
}}
.ontoviewer-line {{
  display: inline-block;
  width: 28px;
  border-top: 2px solid #111827;
}}
.ontoviewer-line-subclass {{
  border-top-color: #2563eb;
}}
.ontoviewer-line-imports {{
  border-top-color: #f59e0b;
  border-top-style: dashed;
}}
.ontoviewer-node-box {{
  width: 22px;
  height: 14px;
  border: 2px solid var(--ov-text-muted);
  border-radius: 4px;
  background: var(--ov-button-bg);
  display: inline-block;
}}
.ontoviewer-node-dot {{
  width: 12px;
  height: 12px;
  border-radius: 999px;
  background: #9ca3af;
  display: inline-block;
}}
.ontoviewer-ontology-list {{
  list-style: none;
  margin: 6px 0 0;
  padding: 0;
  display: grid;
  gap: 4px;
}}
.ontoviewer-ontology-item {{
  list-style: none;
}}
.ontoviewer-ontology-entry {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 12px;
  color: var(--ov-text);
  width: 100%;
  margin: 0 !important;
  text-align: left;
}}
.ontoviewer-ontology-entry-main {{
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}}
.ontoviewer-ontology-entry-main span:last-child {{
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}}
.ontoviewer-ontology-entry.is-collapsed {{
  background: var(--ov-button-bg-active);
}}
.ontoviewer-ontology-state {{
  font-size: 11px;
  color: var(--ov-text-soft);
}}
.ontoviewer-swatch {{
  width: 12px;
  height: 12px;
  border-radius: 3px;
  border: 1px solid var(--ov-border-strong);
  display: inline-block;
  flex: 0 0 auto;
}}
.ontoviewer-legend-hint {{
  margin-top: 6px;
  font-size: 12px;
  color: var(--ov-text-soft);
}}
@media (max-width: 1100px) {{
  #mynetwork {{
    width: 100vw !important;
    height: calc(100vh - 260px) !important;
  }}
  .ontoviewer-controls {{
    top: auto;
    left: 0;
    right: 0;
    bottom: 0;
    width: 100%;
    height: 260px;
    border-left: none;
    border-top: 1px solid var(--ov-border);
    box-shadow: 0 -8px 24px var(--ov-shadow);
  }}
}}
</style>
<div class="ontoviewer-controls">
  <button id="ontoviewer-graph-view-btn" onclick="window.ontoviewerSetViewMode('graph')">Graph view</button>
  <button id="ontoviewer-tree-view-btn" onclick="window.ontoviewerSetViewMode('tree')">Family tree view</button>
  <button id="ontoviewer-theme-toggle" onclick="window.ontoviewerToggleTheme()">Dark mode</button>
  <hr />
  <div class="ontoviewer-search">
    <input
      id="ontoviewer-search-input"
      class="ontoviewer-search-input"
      type="search"
      placeholder="Search nodes"
      oninput="window.ontoviewerUpdateSearch(this.value)"
      onkeydown="window.ontoviewerHandleSearchKey(event)"
    />
    <div class="ontoviewer-search-row">
      <button id="ontoviewer-search-prev" type="button" onclick="window.ontoviewerStepSearch(-1)" aria-label="Previous search result">&larr;</button>
      <button id="ontoviewer-search-next" type="button" onclick="window.ontoviewerStepSearch(1)" aria-label="Next search result">&rarr;</button>
      <span id="ontoviewer-search-count" class="ontoviewer-search-count">No search</span>
    </div>
  </div>
  <hr />
  <button id="ontoviewer-attach-toggle" onclick="window.ontoviewerToggleAttachment()">Attach ontology nodes</button>
  <button id="ontoviewer-collapse-toggle" onclick="window.ontoviewerToggleCollapseAll()">Collapse by ontology</button>
  <button id="ontoviewer-property-toggle" onclick="window.ontoviewerToggleTreeRelations()">Show relation edges</button>
  <button id="ontoviewer-label-toggle" onclick="window.ontoviewerToggleLabels()">Show raw labels</button>
  <hr />
  <div class="ontoviewer-legend-title">Legend</div>
  <div class="ontoviewer-legend-row"><span class="ontoviewer-node-box"></span> Ontology node</div>
  <div class="ontoviewer-legend-row"><span class="ontoviewer-node-dot"></span> Class node (dot in graph view, box in family-tree view)</div>
  <div class="ontoviewer-legend-row"><span class="ontoviewer-line ontoviewer-line-subclass"></span> subclass edge</div>
  <div class="ontoviewer-legend-row"><span class="ontoviewer-line"></span> property relation edge (hidden by default in family-tree view)</div>
  <div class="ontoviewer-legend-row"><span class="ontoviewer-line ontoviewer-line-imports"></span> imports edge</div>
  <div class="ontoviewer-legend-row"><span class="ontoviewer-line" style="border-top-color:#94a3b8;border-top-style:dashed;"></span> ontology membership edge</div>
  <div class="ontoviewer-legend-hint">Click a class node to fold or unfold its descendant subclass tree.</div>
  <div class="ontoviewer-legend-hint">Click an ontology in the legend to collapse or expand only that ontology.</div>
  <div class="ontoviewer-legend-hint">Use ontology collapse only for high-level overview.</div>
  <div class="ontoviewer-legend-hint">Family-tree view hides relation edges by default so the hierarchy stays readable.</div>
  <hr />
  <div class="ontoviewer-legend-title">Ontology Colors</div>
  <ul class="ontoviewer-ontology-list">
    {ontology_items}
    {unresolved_item}
  </ul>
</div>
<script>
(function() {{
  const groupLabels = {json.dumps(group_labels)};
  const clusterIds = new Set();
  const collapsedOntologyGroups = new Set();
  const collapsedClassNodes = new Set();
  let searchQuery = "";
  let searchMatches = [];
  let searchMatchIndex = -1;
  let pendingSearchFocusNodeId = null;
  let labelMode = {json.dumps(initial_label_mode)};
  let viewMode = "graph";
  let graphOntologyAttached = false;
  let ontologyAttached = false;
  let treePropertyEdgesVisible = false;
  let themeMode = getInitialThemeMode();
  const graphViewOptions = {{
    interaction: {{
      dragNodes: true,
      dragView: true,
      zoomView: true
    }},
    layout: {{
      hierarchical: false,
      improvedLayout: true
    }},
    physics: {{
      enabled: true,
      solver: "barnesHut",
      barnesHut: {{
        gravitationalConstant: -8000,
        springLength: 190,
        springConstant: 0.02,
        damping: 0.28
      }},
      stabilization: {{
        iterations: 300
      }}
    }},
    edges: {{
      smooth: false
    }}
  }};
  const treeViewOptions = {{
    interaction: {{
      dragNodes: false,
      dragView: true,
      zoomView: true
    }},
    layout: {{
      hierarchical: {{
        enabled: true,
        direction: "UD",
        sortMethod: "directed",
        shakeTowards: "roots",
        levelSeparation: 140,
        nodeSpacing: 170,
        treeSpacing: 200,
        blockShifting: true,
        edgeMinimization: true,
        parentCentralization: true
      }}
    }},
    physics: {{
      enabled: false
    }},
    edges: {{
      smooth: {{
        enabled: true,
        type: "vertical",
        roundness: 0
      }}
    }}
  }};

  function labelModeText(mode) {{
    return mode === "human" ? "Show raw labels" : "Show human labels";
  }}

  function attachmentModeText(attached) {{
    return attached ? "Detach ontology nodes" : "Attach ontology nodes";
  }}

  function collapseToggleText() {{
    return collapsedOntologyGroups.size > 0 || collapsedClassNodes.size > 0
      ? "Expand all"
      : "Collapse by ontology";
  }}

  function propertyToggleText() {{
    return treePropertyEdgesVisible ? "Hide relation edges" : "Show relation edges";
  }}

  function themeToggleText(mode) {{
    return mode === "dark" ? "Light mode" : "Dark mode";
  }}

  function searchCountText() {{
    if (!searchQuery) {{
      return "No search";
    }}
    if (searchMatches.length === 0 || searchMatchIndex < 0) {{
      return "0 results";
    }}
    return (searchMatchIndex + 1) + " / " + searchMatches.length;
  }}

  function getInitialThemeMode() {{
    try {{
      const stored = window.localStorage.getItem("ontoviewer-theme");
      if (stored === "light" || stored === "dark") {{
        return stored;
      }}
    }} catch (error) {{
      // Ignore storage access errors and fall back to a safe default.
    }}
    return "light";
  }}

  function setStoredThemeMode(mode) {{
    try {{
      window.localStorage.setItem("ontoviewer-theme", mode);
    }} catch (error) {{
      // Ignore storage access errors.
    }}
  }}

  function themeFontColor() {{
    return themeMode === "dark" ? "#f8fafc" : "#111827";
  }}

  function themeStrokeColor() {{
    return themeMode === "dark" ? "#0f172a" : "#f3f4f6";
  }}

  function themeMutedFontColor() {{
    return themeMode === "dark" ? "#94a3b8" : "#6b7280";
  }}

  function themeEdgeColor(edgeType) {{
    if (edgeType === "subclass") {{
      return "#2563eb";
    }}
    if (edgeType === "imports") {{
      return "#f59e0b";
    }}
    if (edgeType === "ontology-membership") {{
      return themeMode === "dark" ? "#64748b" : "#94a3b8";
    }}
    if (edgeType === "property") {{
      return themeMode === "dark" ? "#cbd5e1" : "#111827";
    }}
    return themeMode === "dark" ? "#94a3b8" : "#111827";
  }}

  function themeEdgeFont(edgeType) {{
    if (edgeType === "property") {{
      return {{
        color: themeMode === "dark" ? "#e2e8f0" : "#111827",
        strokeWidth: 3,
        strokeColor: themeMode === "dark" ? "#0f172a" : "#ffffff"
      }};
    }}
    if (edgeType === "imports") {{
      return {{
        color: "#f59e0b",
        strokeWidth: 3,
        strokeColor: themeMode === "dark" ? "#0f172a" : "#ffffff"
      }};
    }}
    return undefined;
  }}

  function hideLoadingBar() {{
    const loadingBar = document.getElementById("loadingBar");
    if (!loadingBar) {{
      return;
    }}
    const text = document.getElementById("text");
    if (text) {{
      text.textContent = "100%";
    }}
    const bar = document.getElementById("bar");
    if (bar) {{
      bar.style.width = "496px";
    }}
    loadingBar.style.opacity = 0;
    loadingBar.style.display = "none";
    loadingBar.style.visibility = "hidden";
    loadingBar.setAttribute("aria-hidden", "true");
  }}

  function scheduleLoadingBarHide(delayMs) {{
    window.setTimeout(hideLoadingBar, delayMs || 0);
  }}

  function searchableNodeText(node) {{
    return [
      node.humanLabel || "",
      node.rawLabel || "",
      node.label || "",
      node.title || "",
      node.ontologyIri || ""
    ].join(" ").toLowerCase();
  }}

  function wrapTreeLabel(text, maxChars) {{
    if (!text || text.length <= maxChars) {{
      return text;
    }}
    const words = text.split(/\\s+/).filter(Boolean);
    if (words.length <= 1) {{
      const chunks = [];
      for (let i = 0; i < text.length; i += maxChars) {{
        chunks.push(text.slice(i, i + maxChars));
      }}
      return chunks.join("\\n");
    }}
    const lines = [];
    let currentLine = "";
    words.forEach((word) => {{
      const candidate = currentLine ? currentLine + " " + word : word;
      if (candidate.length > maxChars && currentLine) {{
        lines.push(currentLine);
        currentLine = word;
      }} else {{
        currentLine = candidate;
      }}
    }});
    if (currentLine) {{
      lines.push(currentLine);
    }}
    return lines.join("\\n");
  }}

  function viewModeButtonState(mode) {{
    const graphBtn = document.getElementById("ontoviewer-graph-view-btn");
    const treeBtn = document.getElementById("ontoviewer-tree-view-btn");
    if (graphBtn) {{
      graphBtn.disabled = mode === "graph";
    }}
    if (treeBtn) {{
      treeBtn.disabled = mode === "tree";
    }}
  }}

  function refreshCollapseToggle() {{
    const collapseBtn = document.getElementById("ontoviewer-collapse-toggle");
    if (!collapseBtn) {{
      return;
    }}
    if (viewMode === "tree") {{
      if (collapsedOntologyGroups.size > 0 || collapsedClassNodes.size > 0) {{
        collapseBtn.style.display = "inline-block";
        collapseBtn.textContent = "Expand all";
      }} else {{
        collapseBtn.style.display = "none";
      }}
      return;
    }}
    collapseBtn.style.display = "inline-block";
    collapseBtn.textContent = collapseToggleText();
  }}

  function refreshPropertyToggle() {{
    const propertyBtn = document.getElementById("ontoviewer-property-toggle");
    if (!propertyBtn) {{
      return;
    }}
    propertyBtn.textContent = propertyToggleText();
    propertyBtn.style.display = viewMode === "tree" ? "inline-block" : "none";
  }}

  function isEmbeddedPreview() {{
    return window.parent && window.parent !== window;
  }}

  function refreshThemeToggle() {{
    const themeBtn = document.getElementById("ontoviewer-theme-toggle");
    if (!themeBtn) {{
      return;
    }}
    themeBtn.textContent = themeToggleText(themeMode);
    themeBtn.style.display = isEmbeddedPreview() ? "none" : "inline-block";
  }}

  function refreshSearchControls() {{
    const countEl = document.getElementById("ontoviewer-search-count");
    if (countEl) {{
      countEl.textContent = searchCountText();
    }}
    const disabled = searchMatches.length === 0;
    const prevBtn = document.getElementById("ontoviewer-search-prev");
    const nextBtn = document.getElementById("ontoviewer-search-next");
    if (prevBtn) {{
      prevBtn.disabled = disabled;
    }}
    if (nextBtn) {{
      nextBtn.disabled = disabled;
    }}
  }}

  function refreshOntologyLegendControls() {{
    document.querySelectorAll(".ontoviewer-ontology-entry[data-group-id]").forEach((entry) => {{
      const groupId = entry.getAttribute("data-group-id");
      const collapsed = collapsedOntologyGroups.has(groupId);
      entry.classList.toggle("is-collapsed", collapsed);
      entry.disabled = false;
      entry.title = collapsed ? "Expand this ontology" : "Collapse this ontology";
      const state = entry.querySelector(".ontoviewer-ontology-state");
      if (state) {{
        state.textContent = collapsed ? "Expand" : "Collapse";
      }}
    }});
  }}

  function clusterIdFromGroup(groupId) {{
    return "cluster:" + groupId;
  }}

  function groupIdFromClusterId(clusterId) {{
    return clusterId.startsWith("cluster:") ? clusterId.slice("cluster:".length) : null;
  }}

  function openOntologyClusters(clearTrackedGroups) {{
    Array.from(clusterIds).forEach((clusterId) => {{
      if (network.isCluster(clusterId)) {{
        network.openCluster(clusterId);
      }}
    }});
    clusterIds.clear();
    if (clearTrackedGroups) {{
      collapsedOntologyGroups.clear();
    }}
    refreshOntologyLegendControls();
  }}

  function expandOntologyGroup(groupId) {{
    const clusterId = clusterIdFromGroup(groupId);
    if (network.isCluster(clusterId)) {{
      network.openCluster(clusterId);
    }}
    clusterIds.delete(clusterId);
    collapsedOntologyGroups.delete(groupId);
    refreshCollapseToggle();
    refreshOntologyLegendControls();
  }}

  function reapplyCollapsedOntologyGroups() {{
    Object.entries(groupLabels).forEach(([groupId, label]) => {{
      if (collapsedOntologyGroups.has(groupId)) {{
        collapseGroup(groupId, label);
      }}
    }});
    refreshCollapseToggle();
    refreshOntologyLegendControls();
  }}

  function currentSearchNodeId() {{
    if (searchMatchIndex < 0 || searchMatchIndex >= searchMatches.length) {{
      return null;
    }}
    return searchMatches[searchMatchIndex];
  }}

  function baseBorderWidth(node) {{
    if (node.ontologyCluster) {{
      return 3;
    }}
    if (node.isClassNode) {{
      return viewMode === "tree" ? 1.5 : 1;
    }}
    if (node.isOntologyNode) {{
      return node.ontologyLoaded ? 2 : 1;
    }}
    return node.borderWidth || 1;
  }}

  function refreshSearchHighlight() {{
    const activeNodeId = currentSearchNodeId();
    const nodesDs = network.body.data.nodes;
    const nodeUpdates = [];
    nodesDs.forEach((node) => {{
      if (!(node.isClassNode || node.isOntologyNode || node.ontologyCluster)) {{
        return;
      }}
      const isActive = activeNodeId !== null && node.id === activeNodeId;
      nodeUpdates.push({{
        id: node.id,
        borderWidth: isActive ? baseBorderWidth(node) + 2 : baseBorderWidth(node),
        shadow: isActive
          ? {{
              enabled: true,
              color: themeMode === "dark" ? "rgba(56, 189, 248, 0.55)" : "rgba(37, 99, 235, 0.35)",
              size: 18,
              x: 0,
              y: 0
            }}
          : {{ enabled: false }}
      }});
    }});
    if (nodeUpdates.length > 0) {{
      nodesDs.update(nodeUpdates);
    }}
    refreshSearchControls();
  }}

  function applyNodeStyle(mode) {{
    const nodesDs = network.body.data.nodes;
    const nodeUpdates = [];
    nodesDs.forEach((node) => {{
      if (node.isClassNode) {{
        if (mode === "tree") {{
          nodeUpdates.push({{
            id: node.id,
            shape: "box",
            size: 24,
            margin: 10,
            borderWidth: 1.5,
            widthConstraint: {{ maximum: 220 }},
            font: {{
              color: themeFontColor(),
              strokeWidth: 0
            }}
          }});
        }} else {{
          nodeUpdates.push({{
            id: node.id,
            shape: "dot",
            size: 16,
            margin: 0,
            borderWidth: 1,
            widthConstraint: false,
            font: {{
              size: 14,
              color: themeFontColor(),
              strokeWidth: 4,
              strokeColor: themeStrokeColor()
            }}
          }});
        }}
      }} else if (node.isOntologyNode) {{
        const ontologyFontColor = node.ontologyLoaded ? themeFontColor() : themeMutedFontColor();
        if (mode === "tree") {{
          nodeUpdates.push({{
            id: node.id,
            shape: "box",
            margin: 12,
            widthConstraint: {{ maximum: 240 }},
            font: {{
              size: 14,
              color: ontologyFontColor,
              strokeWidth: 0
            }}
          }});
        }} else {{
          nodeUpdates.push({{
            id: node.id,
            shape: "box",
            margin: 8,
            widthConstraint: false,
            font: {{
              color: ontologyFontColor,
              strokeWidth: 0
            }}
          }});
        }}
      }} else if (node.ontologyCluster) {{
        nodeUpdates.push({{
          id: node.id,
          font: {{
            color: themeFontColor(),
            strokeWidth: 0
          }}
        }});
      }}
    }});
    if (nodeUpdates.length > 0) {{
      nodesDs.update(nodeUpdates);
    }}
  }}

  function applyTheme(mode, notifyParent) {{
    themeMode = mode;
    document.documentElement.classList.toggle("ontoviewer-dark", mode === "dark");
    document.body.classList.toggle("ontoviewer-dark", mode === "dark");
    setStoredThemeMode(mode);
    applyNodeStyle(viewMode);
    refreshEdgeVisibility();
    refreshThemeToggle();
    refreshSearchHighlight();
    if (notifyParent && window.parent && window.parent !== window) {{
      try {{
        window.parent.postMessage({{ type: "ontoviewer-theme", mode: mode }}, "*");
      }} catch (error) {{
        // Ignore parent messaging failures.
      }}
    }}
  }}

  function applyEdgeOrientation(mode) {{
    const edgesDs = network.body.data.edges;
    const edgeUpdates = [];
    edgesDs.forEach((edge) => {{
      const nextFrom = mode === "tree"
        ? (edge.treeFrom || edge.semanticFrom || edge.from)
        : (edge.semanticFrom || edge.from);
      const nextTo = mode === "tree"
        ? (edge.treeTo || edge.semanticTo || edge.to)
        : (edge.semanticTo || edge.to);
      if (edge.from !== nextFrom || edge.to !== nextTo) {{
        edgeUpdates.push({{
          id: edge.id,
          from: nextFrom,
          to: nextTo
        }});
      }}
    }});
    if (edgeUpdates.length > 0) {{
      edgesDs.update(edgeUpdates);
    }}
  }}

  function collapseGroup(groupId, label) {{
    const clusterId = clusterIdFromGroup(groupId);
    if (network.isCluster(clusterId)) {{
      return;
    }}
    let clusterColor = "#f3f4f6";
    network.body.data.nodes.forEach((node) => {{
      if (node.ontologyGroup === groupId && node.isClassNode && node.color) {{
        clusterColor = node.color;
      }}
    }});
    network.cluster({{
      joinCondition: function(nodeOptions) {{
        return nodeOptions.ontologyGroup === groupId;
      }},
      clusterNodeProperties: {{
        id: clusterId,
        ontologyCluster: true,
        ontologyGroup: groupId,
        label: label,
        borderWidth: 3,
        shape: "database",
        color: clusterColor,
        font: {{
          color: themeFontColor()
        }}
      }}
    }});
    clusterIds.add(clusterId);
    collapsedOntologyGroups.add(groupId);
    refreshCollapseToggle();
    refreshOntologyLegendControls();
  }}

  function subclassChildrenMap() {{
    const childrenByParent = new Map();
    network.body.data.edges.forEach((edge) => {{
      if (edge.edgeType !== "subclass") {{
        return;
      }}
      const childId = edge.semanticFrom || edge.from;
      const parentId = edge.semanticTo || edge.to;
      if (!childrenByParent.has(parentId)) {{
        childrenByParent.set(parentId, []);
      }}
      childrenByParent.get(parentId).push(childId);
    }});
    return childrenByParent;
  }}

  function descendantClassIds(parentNodeId, childrenByParent, visited) {{
    const descendants = [];
    const directChildren = childrenByParent.get(parentNodeId) || [];
    directChildren.forEach((childId) => {{
      if (visited.has(childId)) {{
        return;
      }}
      visited.add(childId);
      descendants.push(childId);
      descendants.push(...descendantClassIds(childId, childrenByParent, visited));
    }});
    return descendants;
  }}

  function hiddenClassIds() {{
    const childrenByParent = subclassChildrenMap();
    const hiddenIds = new Set();
    collapsedClassNodes.forEach((parentNodeId) => {{
      descendantClassIds(parentNodeId, childrenByParent, new Set()).forEach((nodeId) => {{
        hiddenIds.add(nodeId);
      }});
    }});
    return hiddenIds;
  }}

  function collapsedDescendantCount(nodeId) {{
    if (!collapsedClassNodes.has(nodeId)) {{
      return 0;
    }}
    return descendantClassIds(nodeId, subclassChildrenMap(), new Set()).length;
  }}

  function nodeBaseLabel(node, mode) {{
    if (mode === "human") {{
      return node.humanLabel || node.rawLabel || node.label;
    }}
    return node.rawLabel || node.humanLabel || node.label;
  }}

  function applyLabelMode(mode) {{
    labelMode = mode;
    const nodesDs = network.body.data.nodes;
    const hiddenIds = hiddenClassIds();
    const nodeUpdates = [];
    nodesDs.forEach((node) => {{
      if (!node.isClassNode) {{
        return;
      }}
      const plainLabel = nodeBaseLabel(node, mode);
      const baseLabel = viewMode === "tree" ? wrapTreeLabel(plainLabel, 18) : plainLabel;
      const collapsedCount = collapsedClassNodes.has(node.id) ? collapsedDescendantCount(node.id) : 0;
      const suffix = collapsedCount > 0
        ? (viewMode === "tree" ? "\\n(+" + collapsedCount + ")" : " (+" + collapsedCount + ")")
        : "";
      const nextLabel = baseLabel + suffix;
      const nextHidden = hiddenIds.has(node.id);
      const nextPhysics = !nextHidden;
      if (
        nextLabel !== node.label ||
        nextHidden !== Boolean(node.hidden) ||
        nextPhysics !== Boolean(node.physics)
      ) {{
        nodeUpdates.push({{
          id: node.id,
          label: nextLabel,
          hidden: nextHidden,
          physics: nextPhysics
        }});
      }}
    }});
    if (nodeUpdates.length > 0) {{
      nodesDs.update(nodeUpdates);
    }}

    const toggleBtn = document.getElementById("ontoviewer-label-toggle");
    if (toggleBtn) {{
      toggleBtn.textContent = labelModeText(mode);
    }}

    refreshEdgeVisibility();
    refreshSearchHighlight();
  }}

  function applyOntologyAttachment(attached) {{
    ontologyAttached = attached;
    const nodesDs = network.body.data.nodes;
    const nodeUpdates = [];
    nodesDs.forEach((node) => {{
      if (!node.isOntologyNode) {{
        return;
      }}
      const nextHidden = !attached;
      if (node.hidden !== nextHidden) {{
        nodeUpdates.push({{ id: node.id, hidden: nextHidden }});
      }}
    }});
    if (nodeUpdates.length > 0) {{
      nodesDs.update(nodeUpdates);
    }}

    const attachBtn = document.getElementById("ontoviewer-attach-toggle");
    if (attachBtn) {{
      attachBtn.textContent = attachmentModeText(attached);
      attachBtn.disabled = viewMode === "tree";
    }}

    refreshEdgeVisibility();
  }}

  function applyViewMode(mode) {{
    viewMode = mode;
    openOntologyClusters(false);
    if (mode === "tree") {{
      network.stopSimulation();
      network.setOptions(treeViewOptions);
      applyEdgeOrientation("tree");
      applyNodeStyle("tree");
      applyOntologyAttachment(true);
      applyLabelMode(labelMode);
      reapplyCollapsedOntologyGroups();
      network.fit({{ animation: true }});
      scheduleLoadingBarHide(0);
    }} else {{
      network.setOptions(graphViewOptions);
      applyEdgeOrientation("graph");
      applyNodeStyle("graph");
      applyOntologyAttachment(graphOntologyAttached);
      applyLabelMode(labelMode);
      reapplyCollapsedOntologyGroups();
      network.stabilize(200);
    }}
    viewModeButtonState(mode);
    refreshPropertyToggle();
    refreshOntologyLegendControls();
    refreshSearchHighlight();
    scheduleCurrentSearchFocus(mode === "tree" ? 120 : 260);
  }}

  function refreshAfterClassToggle() {{
    if (viewMode === "tree") {{
      network.stopSimulation();
      network.setOptions(treeViewOptions);
      applyEdgeOrientation("tree");
      applyNodeStyle("tree");
      refreshSearchHighlight();
      network.redraw();
      network.fit({{ animation: true }});
      scheduleLoadingBarHide(0);
      return;
    }}
    refreshSearchHighlight();
    network.stabilize(80);
  }}

  function expandCollapsedAncestorsForNode(nodeId) {{
    const childrenByParent = subclassChildrenMap();
    let changed = false;
    Array.from(collapsedClassNodes).forEach((parentNodeId) => {{
      if (parentNodeId === nodeId) {{
        return;
      }}
      const descendants = descendantClassIds(parentNodeId, childrenByParent, new Set());
      if (descendants.includes(nodeId)) {{
        collapsedClassNodes.delete(parentNodeId);
        changed = true;
      }}
    }});
    return changed;
  }}

  function revealNodeForSearch(nodeId) {{
    const node = network.body.data.nodes.get(nodeId);
    if (!node) {{
      return false;
    }}

    let changed = false;
    if (node.isOntologyNode && viewMode === "graph" && !ontologyAttached) {{
      graphOntologyAttached = true;
      applyOntologyAttachment(true);
      changed = true;
    }}

    if (node.ontologyGroup && collapsedOntologyGroups.has(node.ontologyGroup)) {{
      expandOntologyGroup(node.ontologyGroup);
      changed = true;
    }}

    if (node.isClassNode && expandCollapsedAncestorsForNode(node.id)) {{
      changed = true;
    }}

    if (changed) {{
      applyLabelMode(labelMode);
      refreshCollapseToggle();
      if (viewMode === "tree") {{
        network.stopSimulation();
        network.setOptions(treeViewOptions);
        applyEdgeOrientation("tree");
        applyNodeStyle("tree");
        network.redraw();
      }} else {{
        network.stabilize(80);
      }}
      refreshSearchHighlight();
    }}

    return changed;
  }}

  function focusNodeNow(nodeId) {{
    const node = network.body.data.nodes.get(nodeId);
    if (!node || node.hidden) {{
      return false;
    }}
    pendingSearchFocusNodeId = null;
    network.focus(nodeId, {{
      scale: viewMode === "tree" ? 1.2 : 1.15,
      animation: {{
        duration: 450,
        easingFunction: "easeInOutQuad"
      }}
    }});
    return true;
  }}

  function maybeFocusPendingSearchNode() {{
    if (!pendingSearchFocusNodeId) {{
      return;
    }}
    focusNodeNow(pendingSearchFocusNodeId);
  }}

  function scheduleCurrentSearchFocus(delayMs) {{
    const nodeId = currentSearchNodeId();
    if (!nodeId) {{
      pendingSearchFocusNodeId = null;
      refreshSearchHighlight();
      return;
    }}
    revealNodeForSearch(nodeId);
    pendingSearchFocusNodeId = nodeId;
    refreshSearchHighlight();
    window.setTimeout(maybeFocusPendingSearchNode, delayMs || 0);
  }}

  function updateSearchMatches(query) {{
    searchQuery = (query || "").trim().toLowerCase();
    const previousNodeId = currentSearchNodeId();

    if (!searchQuery) {{
      searchMatches = [];
      searchMatchIndex = -1;
      pendingSearchFocusNodeId = null;
      refreshSearchHighlight();
      return;
    }}

    const matches = [];
    network.body.data.nodes.forEach((node) => {{
      if (node.ontologyCluster) {{
        return;
      }}
      if (!(node.isClassNode || node.isOntologyNode)) {{
        return;
      }}
      if (searchableNodeText(node).includes(searchQuery)) {{
        matches.push(node.id);
      }}
    }});
    searchMatches = matches;

    if (searchMatches.length === 0) {{
      searchMatchIndex = -1;
      pendingSearchFocusNodeId = null;
      refreshSearchHighlight();
      return;
    }}

    const preservedIndex = previousNodeId ? searchMatches.indexOf(previousNodeId) : -1;
    searchMatchIndex = preservedIndex >= 0 ? preservedIndex : 0;
    scheduleCurrentSearchFocus(0);
  }}

  function refreshEdgeVisibility() {{
    const edgesDs = network.body.data.edges;
    const hiddenIds = hiddenClassIds();
    const edgeUpdates = [];
    edgesDs.forEach((edge) => {{
      let nextHidden = false;
      if (edge.edgeType === "layout-root" || edge.edgeType === "layout-subclass") {{
        nextHidden = true;
      }} else if (edge.edgeType === "imports") {{
        nextHidden = !ontologyAttached;
      }} else if (edge.edgeType === "ontology-membership") {{
        nextHidden = !ontologyAttached || hiddenIds.has(edge.to);
      }} else if (edge.edgeType === "property") {{
        nextHidden = hiddenIds.has(edge.from) || hiddenIds.has(edge.to);
        if (viewMode === "tree" && !treePropertyEdgesVisible) {{
          nextHidden = true;
        }}
      }} else {{
        nextHidden = hiddenIds.has(edge.from) || hiddenIds.has(edge.to);
      }}

      let nextLabel = edge.label;
      if (edge.edgeType === "property") {{
        nextLabel = labelMode === "human"
          ? (edge.humanLabel || edge.rawLabel || edge.label)
          : (edge.rawLabel || edge.humanLabel || edge.label);
      }}

      const nextColor = themeEdgeColor(edge.edgeType);
      const nextFont = themeEdgeFont(edge.edgeType);

      if (
        nextHidden !== Boolean(edge.hidden) ||
        nextLabel !== edge.label ||
        nextColor !== edge.color ||
        JSON.stringify(nextFont || null) !== JSON.stringify(edge.font || null)
      ) {{
        edgeUpdates.push({{
          id: edge.id,
          hidden: nextHidden,
          label: nextLabel,
          color: nextColor,
          font: nextFont
        }});
      }}
    }});
    if (edgeUpdates.length > 0) {{
      edgesDs.update(edgeUpdates);
    }}
  }}

  function collapseAllByOntology() {{
    Object.keys(groupLabels).forEach((groupId) => {{
      collapsedOntologyGroups.add(groupId);
    }});
    Object.entries(groupLabels).forEach(([groupId, label]) => {{
      collapseGroup(groupId, label);
    }});
    refreshCollapseToggle();
    refreshOntologyLegendControls();
  }}

  function expandAll() {{
    openOntologyClusters(true);
    collapsedClassNodes.clear();
    applyLabelMode(labelMode);
    refreshCollapseToggle();
  }}

  window.ontoviewerToggleCollapseAll = function() {{
    if (viewMode === "tree") {{
      if (collapsedOntologyGroups.size > 0 || collapsedClassNodes.size > 0) {{
        expandAll();
      }}
      return;
    }}
    if (collapsedOntologyGroups.size > 0 || collapsedClassNodes.size > 0) {{
      expandAll();
    }} else {{
      collapseAllByOntology();
    }}
  }};

  window.ontoviewerToggleLabels = function() {{
    applyLabelMode(labelMode === "human" ? "raw" : "human");
  }};

  window.ontoviewerToggleTheme = function() {{
    applyTheme(themeMode === "dark" ? "light" : "dark", true);
  }};

  window.ontoviewerApplyExternalTheme = function(mode) {{
    if (mode !== "light" && mode !== "dark") {{
      return;
    }}
    applyTheme(mode, false);
  }};

  window.ontoviewerToggleTreeRelations = function() {{
    if (viewMode !== "tree") {{
      return;
    }}
    treePropertyEdgesVisible = !treePropertyEdgesVisible;
    refreshPropertyToggle();
    refreshEdgeVisibility();
  }};

  window.ontoviewerToggleAttachment = function() {{
    graphOntologyAttached = !graphOntologyAttached;
    if (viewMode === "graph") {{
      applyOntologyAttachment(graphOntologyAttached);
    }}
  }};

  window.ontoviewerSetViewMode = function(mode) {{
    applyViewMode(mode);
  }};

  window.ontoviewerUpdateSearch = function(query) {{
    updateSearchMatches(query);
  }};

  window.ontoviewerStepSearch = function(direction) {{
    if (searchMatches.length === 0) {{
      return;
    }}
    const step = direction < 0 ? -1 : 1;
    searchMatchIndex = (searchMatchIndex + step + searchMatches.length) % searchMatches.length;
    scheduleCurrentSearchFocus(0);
  }};

  window.ontoviewerHandleSearchKey = function(event) {{
    if (event.key !== "Enter") {{
      return;
    }}
    event.preventDefault();
    window.ontoviewerStepSearch(event.shiftKey ? -1 : 1);
  }};

  window.ontoviewerToggleOntologyGroup = function(groupId) {{
    if (collapsedOntologyGroups.has(groupId)) {{
      expandOntologyGroup(groupId);
    }} else {{
      collapseGroup(groupId, groupLabels[groupId] || "Ontology");
    }}
    applyLabelMode(labelMode);
    refreshCollapseToggle();
    refreshOntologyLegendControls();
    if (viewMode === "tree") {{
      network.fit({{ animation: true }});
    }} else {{
      network.stabilize(80);
    }}
  }};

  function handleActivatedNode(nodeId) {{
    if (network.isCluster(nodeId)) {{
      const groupId = groupIdFromClusterId(nodeId);
      if (groupId) {{
        expandOntologyGroup(groupId);
      }} else {{
        network.openCluster(nodeId);
        clusterIds.delete(nodeId);
        refreshCollapseToggle();
        refreshOntologyLegendControls();
      }}
      applyLabelMode(labelMode);
      if (viewMode === "tree") {{
        network.fit({{ animation: true }});
      }}
      return true;
    }}

    const node = network.body.data.nodes.get(nodeId);
    if (!node || !node.isClassNode) {{
      return false;
    }}
    const descendantCount = descendantClassIds(nodeId, subclassChildrenMap(), new Set()).length;
    if (descendantCount === 0) {{
      return false;
    }}
    if (collapsedClassNodes.has(nodeId)) {{
      collapsedClassNodes.delete(nodeId);
    }} else {{
      collapsedClassNodes.add(nodeId);
    }}
    applyLabelMode(labelMode);
    refreshCollapseToggle();
    refreshAfterClassToggle();
    return true;
  }}

  network.on("selectNode", function(params) {{
    if (!params.nodes || params.nodes.length === 0) {{
      return;
    }}
    const handled = handleActivatedNode(params.nodes[0]);
    if (handled) {{
      network.unselectAll();
    }}
  }});

  network.on("stabilized", function() {{
    scheduleLoadingBarHide(0);
    maybeFocusPendingSearchNode();
  }});

  network.on("animationFinished", function() {{
    scheduleLoadingBarHide(0);
    maybeFocusPendingSearchNode();
  }});

  network.once("afterDrawing", function() {{
    scheduleLoadingBarHide(0);
    maybeFocusPendingSearchNode();
  }});

  applyViewMode("graph");
  applyTheme(themeMode, false);
  applyLabelMode(labelMode);
  refreshCollapseToggle();
  refreshPropertyToggle();
  refreshSearchControls();
  refreshOntologyLegendControls();
}})();
</script>
"""

    if "</body>" in html:
        html = html.replace("</body>", f"{controls}\n</body>")
    else:
        html += controls

    output_path.write_text(html, encoding="utf-8")
