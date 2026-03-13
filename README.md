# OntoViewer

OntoViewer is an open-source Python tool to visualize ontology classes and relationships in an interactive graph.

Current MVP includes:
- Load a local OWL/RDF ontology file.
- Resolve `owl:imports` recursively (configurable max depth).
- Extract classes and class-to-class relations.
- Optionally attach classes to ontology anchor nodes.
- Render an interactive HTML graph with zoom/pan controls.
- Color nodes by originating ontology.
- Collapse/expand ontology groups interactively.
- Show ontology import links as dashed edges labeled `imports`.
- Keep declared import nodes visible even when they cannot be loaded.
- Prefer human-readable labels from class/property annotations when available.
- Run a local web UI with file upload and in-browser graph preview.

## Why this project?

Many ontology graph tools are hard to use or no longer maintained. OntoViewer aims to be:
- simple to install,
- easy to run on local ontology files,
- interactive enough to explore large imported ontology sets.

## Install

### Prerequisites
- Python 3.10+

### Local development install

```bash
git clone https://github.com/ylgrst/ontoviewer.git
cd ontoviewer
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .
```

For development (tests):

```bash
pip install -e ".[dev]"
```

For local web UI:

```bash
pip install -e ".[web]"
```

## Usage

Render a graph:

```bash
ontoviewer render /path/to/ontology.owl --output ontology_graph.html --max-depth 2
```

Options:
- `--max-depth`, `-d`: recursive import depth (`0` loads only the root ontology).
- `--output`, `-o`: output HTML file path.
- `--format`: force parser format (example: `xml`, `turtle`, `n3`, `nt`).
- `--label-mode`: initial display mode for class/property labels (`human` or `raw`).

After the command runs, open the generated HTML file in a browser.
The CLI summary includes loaded ontologies, total ontology references, and unresolved imports.

In the graph UI:
- Use mouse wheel / trackpad to zoom.
- Drag background to pan.
- Use **Attach ontology nodes / Detach ontology nodes** to switch between ontology-anchored and free class layouts.
- Use **Collapse by ontology** to reduce visual complexity.
- Use **Expand all** to restore both ontology clusters and folded subclass trees.
- Use **Show raw labels / Show human labels** to switch between ontology codes and human-readable labels.
- Click a class node to collapse/expand only its direct subclasses.
- Use the built-in legend to understand node and edge types.

Edge conventions:
- `subClassOf`: solid blue arrow, no text label (reduced clutter).
- `property relation`: solid dark arrow, labeled with property name.
- `imports`: dashed orange arrow between ontology nodes.
- `ontology membership`: dashed gray arrow from ontology node to class node (visible when ontology nodes are attached).

### Local Web UI

Start the web UI:

```bash
ontoviewer serve --host 127.0.0.1 --port 8000
```

Then open `http://127.0.0.1:8000` in your browser.

Web UI features:
- Upload a local ontology file.
- Configure import recursion depth.
- Set optional RDF format.
- Choose default label mode (`human` or `raw`).
- Reload-safe result pages with a visible current-render status.
- Preview the generated graph inline.
- Download the generated HTML graph.

## Project layout

```text
ontoviewer/
  cli.py         # command-line entrypoint
  loader.py      # ontology loading + recursive import resolution
  labels.py      # human-readable annotation label resolution
  visualize.py   # class/relation extraction + interactive graph rendering
  webapp.py      # Flask local web UI
  model.py       # shared dataclasses
tests/
  test_loader.py # recursive import traversal tests
```

## Tests

```bash
pytest
```

## Notes and current limits

- Import loading relies on import IRIs being resolvable from your environment.
- Remote import retrieval failures are reported as warnings; graph generation still completes with available ontologies.
- Class/property node labels use annotation metadata (`rdfs:label`, `skos:prefLabel`, `IAO_0000111`, etc.) when present, then fall back to IRI-derived codes.
- This baseline focuses on class-level graph exploration. More advanced filtering/layout controls will be added in next commits.

## License

MIT (see `LICENSE`).
