# OntoViewer

OntoViewer is an open-source Python tool to visualize ontology classes and relationships in an interactive graph.

Current MVP includes:
- Load a local OWL/RDF ontology file.
- Resolve `owl:imports` recursively (configurable max depth).
- Extract classes and class-to-class relations.
- Optionally attach classes to ontology anchor nodes.
- Render an interactive HTML graph with zoom/pan controls.
- Switch live between force-directed graph view, family-tree view, and a 3D layered mandala view.
- Stack meta-ontology classes, ontology classes, and instantiated individuals on three discs, sliced into user-chosen sectors.
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
- Conda installed
  `Miniconda` is recommended, but `Anaconda`, `Mambaforge`, and similar Conda-compatible distributions also work.
- Git installed

### Recommended: Web UI install

This is the easiest way to use OntoViewer if you are not comfortable with the command line.

#### Linux / macOS

If `conda` is not recognized in your shell, run `conda init bash` or `conda init zsh` once, then reopen your terminal.

Do this once:

```bash
conda create -n ontoviewer python=3.12
conda activate ontoviewer
python -m pip install --upgrade pip
python -m pip install "ontoviewer[web] @ git+https://github.com/ylgrst/ontoviewer.git"
```

Then, whenever you want to use OntoViewer again:

```bash
conda activate ontoviewer
ontoviewer serve --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` in your browser.

#### Windows PowerShell

Open `Anaconda Prompt` or PowerShell with Conda initialized.

Quick checks:

```powershell
conda --version
python --version
```

If `conda` is not recognized in PowerShell but you do have Conda installed, run this once and then reopen PowerShell:

```powershell
conda init powershell
```

Do this once:

```powershell
conda create -n ontoviewer python=3.12
conda activate ontoviewer
python -m pip install --upgrade pip
python -m pip install "ontoviewer[web] @ git+https://github.com/ylgrst/ontoviewer.git"
```

Then, whenever you want to use OntoViewer again:

```powershell
conda activate ontoviewer
ontoviewer serve --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` in your browser.

### Command-line install

If you prefer generating an HTML graph from the terminal without the web UI:

#### Linux / macOS

If `conda` is not recognized in your shell, run `conda init bash` or `conda init zsh` once, then reopen your terminal.

```bash
conda create -n ontoviewer python=3.12
conda activate ontoviewer
python -m pip install --upgrade pip
python -m pip install "git+https://github.com/ylgrst/ontoviewer.git"
```

Then, whenever you want to use OntoViewer again:

```bash
conda activate ontoviewer
ontoviewer render /path/to/ontology.owl --output ontology_graph.html --max-depth 2
```

#### Windows PowerShell

Open `Anaconda Prompt` or PowerShell with Conda initialized.

Quick checks:

```powershell
conda --version
python --version
```

If `conda` is not recognized in PowerShell but you do have Conda installed, run this once and then reopen PowerShell:

```powershell
conda init powershell
```

```powershell
conda create -n ontoviewer python=3.12
conda activate ontoviewer
python -m pip install --upgrade pip
python -m pip install "git+https://github.com/ylgrst/ontoviewer.git"
```

Then, whenever you want to use OntoViewer again:

```powershell
conda activate ontoviewer
ontoviewer render C:\path\to\ontology.owl --output ontology_graph.html --max-depth 2
```

### Development install

If you want to work on the codebase itself:

#### Linux / macOS

```bash
git clone https://github.com/ylgrst/ontoviewer.git
cd ontoviewer
conda create -n ontoviewer python=3.12
conda activate ontoviewer
python -m pip install --upgrade pip
python -m pip install -e ".[dev,web]"
```

#### Windows PowerShell

```powershell
git clone https://github.com/ylgrst/ontoviewer.git
cd ontoviewer
conda create -n ontoviewer python=3.12
conda activate ontoviewer
python -m pip install --upgrade pip
python -m pip install -e ".[dev,web]"
```

### Updating an existing installation

If a new OntoViewer version is available, activate your Conda environment first:

```bash
conda activate ontoviewer
```

If you installed the Web UI version from GitHub:

```bash
python -m pip install --upgrade "ontoviewer[web] @ git+https://github.com/ylgrst/ontoviewer.git"
```

If you installed the CLI-only version from GitHub:

```bash
python -m pip install --upgrade "git+https://github.com/ylgrst/ontoviewer.git"
```

If you cloned the repository and installed it in editable mode:

```bash
git pull
python -m pip install -e ".[dev,web]"
```

If `pip` says everything is already installed but you still want to force a refresh:

```bash
python -m pip install --upgrade --force-reinstall "ontoviewer[web] @ git+https://github.com/ylgrst/ontoviewer.git"
```

OntoViewer also performs a lightweight GitHub release check on `ontoviewer serve` and `ontoviewer render`.
- It checks at most once per day thanks to a local cache.
- It prints a manual upgrade command when a newer tagged release is available.
- It does not update your environment automatically.
- Disable it per command with `--no-check-updates`.
- Disable it globally for a session with `ONTOVIEWER_DISABLE_UPDATE_CHECK=1`.

## Usage

### Local Web UI

Start the web UI:

```bash
ontoviewer serve --host 127.0.0.1 --port 8000
```

By default, `serve` also checks GitHub releases once per day and prints an upgrade notice if a newer tagged version is available.

OntoViewer now tries the requested port first and, if needed, automatically falls back to other common local ports such as `8080`, `18000`, `3000`, `5000`, and `8765`.

This automatic fallback is enabled by default through `--auto-port`.

If a fallback port is used:
- OntoViewer prints the final URL clearly in the terminal
- OntoViewer opens that exact URL in your default browser by default

If you prefer choosing a port yourself, common alternatives are:

```bash
ontoviewer serve --host 127.0.0.1 --port 8080
ontoviewer serve --host 127.0.0.1 --port 18000
```

If you want OntoViewer to fail instead of choosing another port automatically:

```bash
ontoviewer serve --host 127.0.0.1 --port 8000 --strict-port
```

If you do not want the browser to open automatically:

```bash
ontoviewer serve --host 127.0.0.1 --port 8000 --no-open-browser
```

If you do not want the release check for this command:

```bash
ontoviewer serve --host 127.0.0.1 --port 8000 --no-check-updates
```

In the graph UI:
- Use mouse wheel / trackpad to zoom.
- Drag background to pan.
- Use **Graph view / Family tree view / Mandala view** to switch layouts in the same rendered page.
- In Graph or Family tree view, Ctrl/⌘-click a meta-ontology class to add or drop it as a mandala sector.
- Use **Show relation edges / Hide relation edges** in either view. Graph view shows them by default; family-tree view starts with them hidden for readability.
- Use **Dark mode / Light mode** to switch the full rendered page theme, including the sidebar and background.
- Use the search bar to find node labels, then jump between matches with the left/right arrows.
- Use **Attach ontology nodes / Detach ontology nodes** to switch between ontology-anchored and free class layouts.
- Use **Collapse by ontology / Expand all** as a single toggle for switching between ontology-level overview and fully expanded view.
- Use **Show raw labels / Show human labels** to switch between ontology codes and human-readable labels.
- Click a class node to fold/unfold its whole descendant subclass tree into that class.
- Click an ontology entry in the legend to collapse or expand just that ontology in both graph view and family-tree view.
- Use the built-in legend to understand node and edge types.

In the Mandala view:
- Height encodes the layer: imported meta-ontology classes on top, the ontology's own classes in the middle, instantiated individuals at the bottom.
- Each pizza slice is a meta class you selected as a sector; a class sits in the slice of the nearest sector it descends from.
- Distance from the central axis is taxonomic depth below the sector's meta class, normalized per slice so the most specialised classes reach the rim.
- The central axis holds what every slice shares: the most general classes and anything not under a selected sector.
- An individual inherits the angle and radius of its type, so `rdf:type` reads as a near-vertical drop to the bottom disc.
- Drag to orbit, scroll to zoom, and click a node for its details. Move an ontology between the meta and ontology discs (or hide it) from the Layers panel.

Web UI features:
- Upload a local ontology file.
- Configure import recursion depth.
- Set optional RDF format.
- Choose default label mode (`human` or `raw`).
- Toggle the 3D mandala view on or off (leave it off for a smaller HTML file).
- Optionally enable an insecure SSL fallback for trusted remote import hosts with expired or broken certificates.
- Share the same dark/light theme between the web UI page and the embedded graph preview.
- Reload-safe result pages with a visible current-render status.
- Preview the generated graph inline.
- Download the generated HTML graph.

### CLI

Render a graph:

```bash
ontoviewer render /path/to/ontology.owl --output ontology_graph.html --max-depth 2
```

Options:
- `--max-depth`, `-d`: recursive import depth (`0` loads only the root ontology).
- `--output`, `-o`: output HTML file path.
- `--format`: force parser format (example: `xml`, `turtle`, `n3`, `nt`).
- `--label-mode`: initial display mode for class/property labels (`human` or `raw`).
- `--mandala/--no-mandala`: include the 3D mandala view (on by default). It inlines the vendored three.js runtime (~640 KB); use `--no-mandala` for a smaller file.
- `--allow-insecure-ssl`: retry remote imports without certificate verification when a remote host presents a broken or expired certificate.
- `--check-updates/--no-check-updates`: enable or disable the lightweight GitHub release check for that command.

After the command runs, open the generated HTML file in a browser.
The CLI summary includes loaded ontologies, total ontology references, and unresolved imports.

Edge conventions:
- `subClassOf`: solid blue arrow, no text label (reduced clutter).
- `property relation`: solid dark arrow, labeled with property name.
- `imports`: dashed orange arrow between ontology nodes.
- `ontology membership`: dashed gray arrow from ontology node to class node (visible when ontology nodes are attached).

Layout behavior:
- Root classes are attracted toward their ontology anchor.
- Subclasses are arranged around their direct parent class rather than the ontology center.
- In family-tree view, classes are arranged by hierarchy level so daughter classes descend from their mother class.
- In family-tree view, imported ontologies sit above the ontologies that import them, so dependency chains flow downward.
- In family-tree view, nodes are rendered as labeled boxes and edges use orthogonal routing for a more tree-like structure.
- Property relation edge visibility can be toggled independently in graph view and family-tree view.

## Project layout

```text
ontoviewer/
  cli.py         # command-line entrypoint
  loader.py      # ontology loading + recursive import resolution
  labels.py      # human-readable annotation label resolution
  visualize.py   # class/relation extraction + interactive graph rendering
  mandala.py     # individual extraction + mandala payload/geometry reference
  webapp.py      # Flask local web UI
  model.py       # shared dataclasses
  vendor/three/  # vendored three.js r134 runtime, inlined for the mandala view
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
- Some ontology hosts publish expired TLS certificates. OntoViewer keeps strict verification by default, but the CLI flag `--allow-insecure-ssl` and the matching Web UI checkbox let you opt into a fallback retry for trusted hosts only.
- Class/property node labels use annotation metadata (`rdfs:label`, `skos:prefLabel`, `IAO_0000111`, etc.) when present, then fall back to IRI-derived codes.
- The mandala view inlines the vendored three.js runtime, adding ~640 KB to each generated HTML file; disable it with `--no-mandala` (CLI) or the Web UI checkbox when size matters.
- The mandala's sector and radius geometry runs in the browser; `ontoviewer/mandala.py` holds a unit-tested Python reference of the same algorithm, and the two are kept in step.
- Mandala search covers classes only, not individuals. A class descending from two unrelated sectors is placed in its nearest slice, with the others listed in its info panel.
- This baseline focuses on class-level graph exploration. More advanced filtering/layout controls will be added in next commits.

## License

MIT (see `LICENSE`).
