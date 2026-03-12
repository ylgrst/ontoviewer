# OntoViewer

OntoViewer is an open-source Python tool to visualize ontology classes and relationships in an interactive graph.

Current MVP includes:
- Load a local OWL/RDF ontology file.
- Resolve `owl:imports` recursively (configurable max depth).
- Extract classes and class-to-class relations.
- Render an interactive HTML graph with zoom/pan controls.
- Color nodes by originating ontology.
- Collapse/expand class nodes by ontology group.
- Show ontology import links as dashed edges labeled `imports`.
- Keep declared import nodes visible even when they cannot be loaded.

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
git clone https://github.com/<your-username>/ontoviewer.git
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

## Usage

Render a graph:

```bash
ontoviewer render /path/to/ontology.owl --output ontology_graph.html --max-depth 2
```

Options:
- `--max-depth`, `-d`: recursive import depth (`0` loads only the root ontology).
- `--output`, `-o`: output HTML file path.
- `--format`: force parser format (example: `xml`, `turtle`, `n3`, `nt`).

After the command runs, open the generated HTML file in a browser.
The CLI summary includes loaded ontologies, total ontology references, and unresolved imports.

In the graph UI:
- Use mouse wheel / trackpad to zoom.
- Drag background to pan.
- Use **Collapse by ontology** to reduce visual complexity.
- Use **Expand all** to restore full detail.

## Project layout

```text
ontoviewer/
  cli.py         # command-line entrypoint
  loader.py      # ontology loading + recursive import resolution
  visualize.py   # class/relation extraction + interactive graph rendering
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
- This baseline focuses on class-level graph exploration. More advanced filtering/layout controls will be added in next commits.

## License

MIT (see `LICENSE`).
