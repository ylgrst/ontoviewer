from __future__ import annotations

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
            "smooth": {
              "enabled": true,
              "type": "dynamic"
            },
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
            isClassNode=True,
            humanLabel=human_display,
            rawLabel=raw_display,
            ontologyGroup=ontology_group_id,
            ontologyIri=owner,
        )
        if owner:
            net.add_edge(
                f"ont:{owner}",
                cls,
                color="#94a3b8",
                dashes=True,
                width=1,
                title="defined in ontology",
                edgeType="ontology-membership",
                hidden=True,
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
            hidden=True,
        )

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
          <span class="ontoviewer-swatch" style="background:{escape(color)}"></span>
          <span title="{escape(iri)}">{escape(_short_label(iri))}</span>
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
html, body {{
  margin: 0;
  padding: 0;
  width: 100%;
  height: 100%;
  overflow: hidden;
}}
#mynetwork {{
  width: calc(100vw - 360px) !important;
  height: 100vh !important;
}}
.ontoviewer-controls {{
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 999;
  width: 360px;
  background: rgba(255, 255, 255, 0.97);
  border-left: 1px solid #d1d5db;
  border-radius: 0;
  padding: 10px;
  box-shadow: -8px 0 24px rgba(0, 0, 0, 0.08);
  font-family: sans-serif;
  overflow: auto;
}}
.ontoviewer-controls button {{
  margin-right: 6px;
  margin-bottom: 6px;
  padding: 6px 10px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  cursor: pointer;
  background: #f8fafc;
}}
.ontoviewer-controls hr {{
  border: 0;
  border-top: 1px solid #e5e7eb;
  margin: 10px 0;
}}
.ontoviewer-legend-title {{
  font-size: 12px;
  font-weight: 700;
  color: #374151;
  margin-bottom: 4px;
}}
.ontoviewer-legend-row {{
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #4b5563;
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
  border: 2px solid #374151;
  border-radius: 4px;
  background: #ffffff;
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
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #374151;
}}
.ontoviewer-swatch {{
  width: 12px;
  height: 12px;
  border-radius: 3px;
  border: 1px solid #9ca3af;
  display: inline-block;
}}
.ontoviewer-legend-hint {{
  margin-top: 6px;
  font-size: 12px;
  color: #6b7280;
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
    border-top: 1px solid #d1d5db;
    box-shadow: 0 -8px 24px rgba(0, 0, 0, 0.08);
  }}
}}
</style>
<div class="ontoviewer-controls">
  <button id="ontoviewer-attach-toggle" onclick="window.ontoviewerToggleAttachment()">Attach ontology nodes</button>
  <button onclick="window.ontoviewerCollapseByOntology()">Collapse by ontology</button>
  <button onclick="window.ontoviewerExpandAll()">Expand all</button>
  <button id="ontoviewer-label-toggle" onclick="window.ontoviewerToggleLabels()">Show raw labels</button>
  <hr />
  <div class="ontoviewer-legend-title">Legend</div>
  <div class="ontoviewer-legend-row"><span class="ontoviewer-node-box"></span> Ontology node</div>
  <div class="ontoviewer-legend-row"><span class="ontoviewer-node-dot"></span> Class node (colored by ontology)</div>
  <div class="ontoviewer-legend-row"><span class="ontoviewer-line ontoviewer-line-subclass"></span> subclass edge</div>
  <div class="ontoviewer-legend-row"><span class="ontoviewer-line"></span> property relation edge</div>
  <div class="ontoviewer-legend-row"><span class="ontoviewer-line ontoviewer-line-imports"></span> imports edge</div>
  <div class="ontoviewer-legend-row"><span class="ontoviewer-line" style="border-top-color:#94a3b8;border-top-style:dashed;"></span> ontology membership edge</div>
  <div class="ontoviewer-legend-hint">Click a class node to collapse only its direct subclasses.</div>
  <div class="ontoviewer-legend-hint">Click a cluster node to expand it back.</div>
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
  let labelMode = {json.dumps(initial_label_mode)};
  let ontologyAttached = false;

  function labelModeText(mode) {{
    return mode === "human" ? "Show raw labels" : "Show human labels";
  }}

  function attachmentModeText(attached) {{
    return attached ? "Detach ontology nodes" : "Attach ontology nodes";
  }}

  function clusterIdFromGroup(groupId) {{
    return "cluster:" + groupId;
  }}

  function subclassClusterId(parentNodeId) {{
    return "subclasses:" + parentNodeId;
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
          color: "#111827"
        }}
      }}
    }});
    clusterIds.add(clusterId);
  }}

  function directSubclassIds(parentNodeId) {{
    const subclassIds = [];
    network.body.data.edges.forEach((edge) => {{
      if (edge.edgeType === "subclass" && edge.to === parentNodeId) {{
        subclassIds.push(edge.from);
      }}
    }});
    return subclassIds.filter((nodeId) => {{
      const node = network.body.data.nodes.get(nodeId);
      return node && node.isClassNode;
    }});
  }}

  function collapseDirectSubclasses(parentNodeId) {{
    const clusterId = subclassClusterId(parentNodeId);
    if (network.isCluster(clusterId)) {{
      return;
    }}

    const parentNode = network.body.data.nodes.get(parentNodeId);
    if (!parentNode) {{
      return;
    }}

    const subclassIds = directSubclassIds(parentNodeId);
    if (subclassIds.length === 0) {{
      return;
    }}

    const subclassIdSet = new Set(subclassIds);
    let clusterColor = parentNode.color || "#f3f4f6";

    network.cluster({{
      joinCondition: function(nodeOptions) {{
        return subclassIdSet.has(nodeOptions.id);
      }},
      clusterNodeProperties: {{
        id: clusterId,
        subclassCluster: true,
        parentNodeId: parentNodeId,
        label: parentNode.label + " subclasses",
        borderWidth: 2,
        shape: "dot",
        size: 20,
        color: clusterColor,
        font: {{
          color: "#111827"
        }}
      }}
    }});
    clusterIds.add(clusterId);
  }}

  function applyLabelMode(mode) {{
    labelMode = mode;
    const nodesDs = network.body.data.nodes;
    const edgesDs = network.body.data.edges;

    const nodeUpdates = [];
    nodesDs.forEach((node) => {{
      if (!node.isClassNode) {{
        return;
      }}
      const nextLabel = mode === "human"
        ? (node.humanLabel || node.rawLabel || node.label)
        : (node.rawLabel || node.humanLabel || node.label);
      if (nextLabel !== node.label) {{
        nodeUpdates.push({{ id: node.id, label: nextLabel }});
      }}
    }});
    if (nodeUpdates.length > 0) {{
      nodesDs.update(nodeUpdates);
    }}

    const edgeUpdates = [];
    edgesDs.forEach((edge) => {{
      if (edge.edgeType !== "property") {{
        return;
      }}
      const nextLabel = mode === "human"
        ? (edge.humanLabel || edge.rawLabel || edge.label)
        : (edge.rawLabel || edge.humanLabel || edge.label);
      if (nextLabel !== edge.label) {{
        edgeUpdates.push({{ id: edge.id, label: nextLabel }});
      }}
    }});
    if (edgeUpdates.length > 0) {{
      edgesDs.update(edgeUpdates);
    }}

    const toggleBtn = document.getElementById("ontoviewer-label-toggle");
    if (toggleBtn) {{
      toggleBtn.textContent = labelModeText(mode);
    }}
  }}

  function applyOntologyAttachment(attached) {{
    ontologyAttached = attached;
    const nodesDs = network.body.data.nodes;
    const edgesDs = network.body.data.edges;

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

    const edgeUpdates = [];
    edgesDs.forEach((edge) => {{
      if (edge.edgeType !== "imports" && edge.edgeType !== "ontology-membership") {{
        return;
      }}
      const nextHidden = !attached;
      if (edge.hidden !== nextHidden) {{
        edgeUpdates.push({{ id: edge.id, hidden: nextHidden }});
      }}
    }});
    if (edgeUpdates.length > 0) {{
      edgesDs.update(edgeUpdates);
    }}

    const attachBtn = document.getElementById("ontoviewer-attach-toggle");
    if (attachBtn) {{
      attachBtn.textContent = attachmentModeText(attached);
    }}
  }}

  window.ontoviewerCollapseByOntology = function() {{
    Object.entries(groupLabels).forEach(([groupId, label]) => {{
      collapseGroup(groupId, label);
    }});
  }};

  window.ontoviewerExpandAll = function() {{
    Array.from(clusterIds).forEach((clusterId) => {{
      if (network.isCluster(clusterId)) {{
        network.openCluster(clusterId);
      }}
    }});
    clusterIds.clear();
  }};

  window.ontoviewerToggleLabels = function() {{
    applyLabelMode(labelMode === "human" ? "raw" : "human");
  }};

  window.ontoviewerToggleAttachment = function() {{
    applyOntologyAttachment(!ontologyAttached);
  }};

  network.on("click", function(params) {{
    if (!params.nodes || params.nodes.length === 0) {{
      return;
    }}
    const nodeId = params.nodes[0];

    if (network.isCluster(nodeId)) {{
      network.openCluster(nodeId);
      clusterIds.delete(nodeId);
      return;
    }}

    const node = network.body.data.nodes.get(nodeId);
    if (!node || !node.isClassNode) {{
      return;
    }}
    const clusterId = subclassClusterId(nodeId);
    if (network.isCluster(clusterId)) {{
      network.openCluster(clusterId);
      clusterIds.delete(clusterId);
    }} else {{
      collapseDirectSubclasses(nodeId);
    }}
  }});

  applyOntologyAttachment(false);
  applyLabelMode(labelMode);
}})();
</script>
"""

    if "</body>" in html:
        html = html.replace("</body>", f"{controls}\n</body>")
    else:
        html += controls

    output_path.write_text(html, encoding="utf-8")
