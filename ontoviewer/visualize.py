from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, List, Set, Tuple

from pyvis.network import Network
from rdflib import URIRef
from rdflib.namespace import OWL, RDF, RDFS

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


def render_interactive_graph(closure: OntologyClosure, output_path: Path) -> Dict[str, int]:
    """Render an interactive HTML graph with ontology-aware colors and clustering controls."""
    ontology_ids = list(closure.documents.keys())
    ontology_color = {iri: PALETTE[idx % len(PALETTE)] for idx, iri in enumerate(ontology_ids)}
    ontology_group = {iri: _group_id(iri) for iri in ontology_ids}
    group_label = {
        ontology_group[iri]: _short_label(iri) for iri in ontology_ids
    }

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
        net.add_node(
            f"ont:{iri}",
            label=_short_label(iri),
            title=iri,
            shape="box",
            color=ontology_color[iri],
            group="ontology-meta",
        )

    class_nodes: Set[str] = set()
    class_owner: Dict[str, str] = {}
    relation_edges: List[Tuple[str, str, str, str]] = []

    for ont_iri, document in closure.documents.items():
        graph = document.graph

        for cls_iri in _extract_classes(graph):
            class_nodes.add(cls_iri)
            class_owner.setdefault(cls_iri, ont_iri)

        for s, _, o in graph.triples((None, RDFS.subClassOf, None)):
            if isinstance(s, URIRef) and isinstance(o, URIRef):
                relation_edges.append((str(s), str(o), "subClassOf", "subclass"))

        for prop in _extract_object_properties(graph):
            domains = [d for d in graph.objects(prop, RDFS.domain) if isinstance(d, URIRef)]
            ranges = [r for r in graph.objects(prop, RDFS.range) if isinstance(r, URIRef)]
            for domain in domains:
                for rng in ranges:
                    relation_edges.append((str(domain), str(rng), _short_label(str(prop)), "property"))

    for cls in class_nodes:
        owner = class_owner.get(cls, closure.root_iri)
        color = ontology_color.get(owner, "#9ca3af")
        group = ontology_group.get(owner, "unknown")
        net.add_node(
            cls,
            label=_short_label(cls),
            title=cls,
            color=color,
            shape="dot",
            size=16,
            group=group,
        )

    for src, dst, label, edge_type in relation_edges:
        if src in class_nodes and dst in class_nodes:
            color = "#6b7280" if edge_type == "subclass" else "#111827"
            net.add_edge(src, dst, label=label, title=edge_type, color=color)

    for edge in closure.import_edges:
        net.add_edge(
            f"ont:{edge.source_iri}",
            f"ont:{edge.target_iri}",
            label="imports",
            color="#9ca3af",
            dashes=True,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    net.write_html(str(output_path))
    _inject_cluster_controls(output_path, group_label)

    return {
        "ontologies": len(closure.documents),
        "classes": len(class_nodes),
        "relations": len(relation_edges),
        "imports": len(closure.import_edges),
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


def _inject_cluster_controls(output_path: Path, group_labels: Dict[str, str]) -> None:
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
</div>
<script>
(function() {{
  const groupLabels = {json.dumps(group_labels)};
  const clusterIds = [];

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
}})();
</script>
"""

    if "</body>" in html:
        html = html.replace("</body>", f"{controls}\n</body>")
    else:
        html += controls

    output_path.write_text(html, encoding="utf-8")
