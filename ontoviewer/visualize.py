from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, Literal, Set, Tuple

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
            "keyboard": true
          },
          "physics": {
            "enabled": true,
            "stabilization": {
              "iterations": 200
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
            group="ontology-meta",
        )

    class_nodes: Set[str] = set()
    class_owner: Dict[str, str] = {}
    class_display_labels: Dict[str, str] = {}
    property_display_labels: Dict[str, str] = {}
    relation_edges: Set[Tuple[str, str, str, str, str]] = set()

    for ont_iri, document in closure.documents.items():
        graph = document.graph

        for cls_iri in _extract_classes(graph):
            class_nodes.add(cls_iri)
            class_owner.setdefault(cls_iri, ont_iri)
            if cls_iri not in class_display_labels:
                readable = preferred_annotation_label(graph, cls_iri)
                if readable:
                    class_display_labels[cls_iri] = readable

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
        group = ontology_group.get(owner, "unknown")
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
            group=group,
            isClassNode=True,
            humanLabel=human_display,
            rawLabel=raw_display,
        )
        if owner:
            net.add_edge(
                f"ont:{owner}",
                cls,
                color="#cbd5e1",
                dashes=True,
                width=1,
                title="defined in ontology",
                edgeType="ontology-membership",
            )

    rendered_relations = 0
    for src, dst, human_label, raw_label, edge_type in relation_edges:
        if src in class_nodes and dst in class_nodes:
            color = "#6b7280" if edge_type == "subclass" else "#111827"
            display_label = human_label if label_mode == "human" else raw_label
            net.add_edge(
                src,
                dst,
                label=display_label,
                title=edge_type,
                color=color,
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
            color="#9ca3af",
            dashes=True,
            width=2,
            edgeType="imports",
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    net.write_html(str(output_path))
    _inject_cluster_controls(output_path, group_label, initial_label_mode=label_mode)

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


def _extract_classes(graph) -> Set[str]:
    classes: Set[str] = set()
    for cls in graph.subjects(RDF.type, OWL.Class):
        if isinstance(cls, URIRef):
            classes.add(str(cls))
    for cls in graph.subjects(RDF.type, RDFS.Class):
        if isinstance(cls, URIRef):
            classes.add(str(cls))
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


def _inject_cluster_controls(
    output_path: Path,
    group_labels: Dict[str, str],
    *,
    initial_label_mode: LabelMode,
) -> None:
    html = output_path.read_text(encoding="utf-8")

    controls = f"""
<style>
.ontoviewer-controls {{
  position: fixed;
  top: 12px;
  left: 12px;
  z-index: 999;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid #d1d5db;
  border-radius: 8px;
  padding: 8px;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.1);
  font-family: sans-serif;
}}
.ontoviewer-controls button {{
  margin-right: 6px;
  padding: 6px 10px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  cursor: pointer;
  background: #f8fafc;
}}
</style>
<div class="ontoviewer-controls">
  <button onclick="window.ontoviewerCollapseByOntology()">Collapse by ontology</button>
  <button onclick="window.ontoviewerExpandAll()">Expand all</button>
  <button id="ontoviewer-label-toggle" onclick="window.ontoviewerToggleLabels()">Show raw labels</button>
</div>
<script>
(function() {{
  const groupLabels = {json.dumps(group_labels)};
  const clusterIds = [];
  let labelMode = {json.dumps(initial_label_mode)};

  function labelModeText(mode) {{
    return mode === "human" ? "Show raw labels" : "Show human labels";
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

  window.ontoviewerCollapseByOntology = function() {{
    Object.entries(groupLabels).forEach(([groupId, label]) => {{
      const clusterId = "cluster:" + groupId;
      if (network.isCluster(clusterId)) {{
        return;
      }}
      network.cluster({{
        joinCondition: function(nodeOptions) {{
          const nodeId = String(nodeOptions.id || "");
          return nodeOptions.group === groupId && !nodeId.startsWith("ont:");
        }},
        clusterNodeProperties: {{
          id: clusterId,
          label: "Cluster: " + label,
          borderWidth: 3,
          shape: "database",
          color: "#f3f4f6",
          font: {{
            color: "#111827"
          }}
        }}
      }});
      clusterIds.push(clusterId);
    }});
  }};

  window.ontoviewerExpandAll = function() {{
    clusterIds.forEach((clusterId) => {{
      if (network.isCluster(clusterId)) {{
        network.openCluster(clusterId);
      }}
    }});
  }};

  window.ontoviewerToggleLabels = function() {{
    applyLabelMode(labelMode === "human" ? "raw" : "human");
  }};

  applyLabelMode(labelMode);
}})();
</script>
"""

    if "</body>" in html:
        html = html.replace("</body>", f"{controls}\n</body>")
    else:
        html += controls

    output_path.write_text(html, encoding="utf-8")
