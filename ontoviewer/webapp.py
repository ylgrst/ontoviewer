from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from shutil import rmtree
from time import time
from typing import Dict, Optional
from uuid import uuid4

from flask import Flask, abort, render_template_string, request, send_file, url_for
from werkzeug.utils import secure_filename

from ontoviewer.loader import load_ontology_closure
from ontoviewer.visualize import LabelMode, render_interactive_graph

MAX_STORED_RENDERS = 20


@dataclass(slots=True)
class RenderResult:
    render_id: str
    run_dir: Path
    output_html: Path
    source_name: str
    label_mode: LabelMode
    max_depth: int
    rdf_format: Optional[str]
    stats: Dict[str, int]
    warnings: list[str]
    created_at: float


def create_app(*, storage_dir: Path) -> Flask:
    storage_root = storage_dir.expanduser().resolve()
    storage_root.mkdir(parents=True, exist_ok=True)
    renders: Dict[str, RenderResult] = {}

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024  # 64 MB upload limit

    def _default_state() -> dict[str, str]:
        return {"max_depth": "2", "rdf_format": "", "label_mode": "human"}

    def _prune_old_renders() -> None:
        if len(renders) <= MAX_STORED_RENDERS:
            return

        ordered = sorted(renders.values(), key=lambda item: item.created_at)
        for item in ordered[: len(renders) - MAX_STORED_RENDERS]:
            renders.pop(item.render_id, None)
            rmtree(item.run_dir, ignore_errors=True)

    def _render_home(
        *,
        error: Optional[str] = None,
        result: Optional[RenderResult] = None,
        state: Optional[dict[str, str]] = None,
    ) -> str:
        state = state or _default_state()
        return render_template_string(
            HOME_TEMPLATE,
            error=error,
            result=result,
            state=state,
            graph_url=url_for("graph", render_id=result.render_id) if result else None,
            download_url=url_for("download", render_id=result.render_id) if result else None,
        )

    @app.get("/")
    def home() -> str:
        return _render_home()

    @app.post("/render")
    def render() -> str:
        uploaded = request.files.get("ontology_file")
        if uploaded is None or not uploaded.filename:
            return _render_home(error="Please select an ontology file before rendering.")

        max_depth_raw = (request.form.get("max_depth") or "2").strip()
        rdf_format = (request.form.get("rdf_format") or "").strip() or None
        label_mode_raw = (request.form.get("label_mode") or "human").strip().lower()
        label_mode: LabelMode = "raw" if label_mode_raw == "raw" else "human"

        try:
            max_depth = int(max_depth_raw)
        except ValueError:
            state = {"max_depth": max_depth_raw, "rdf_format": rdf_format or "", "label_mode": label_mode}
            return _render_home(error="Max depth must be an integer >= 0.", state=state)
        if max_depth < 0:
            state = {"max_depth": str(max_depth), "rdf_format": rdf_format or "", "label_mode": label_mode}
            return _render_home(error="Max depth must be >= 0.", state=state)

        safe_name = secure_filename(uploaded.filename) or "ontology.owl"
        render_id = uuid4().hex
        run_dir = storage_root / render_id
        run_dir.mkdir(parents=True, exist_ok=True)
        input_path = run_dir / safe_name
        output_path = run_dir / f"{Path(safe_name).stem}_graph.html"

        uploaded.save(input_path)

        try:
            closure = load_ontology_closure(input_path, max_depth=max_depth, rdf_format=rdf_format)
            stats = render_interactive_graph(closure, output_path, label_mode=label_mode)
        except Exception as exc:
            rmtree(run_dir, ignore_errors=True)
            state = {"max_depth": str(max_depth), "rdf_format": rdf_format or "", "label_mode": label_mode}
            return _render_home(error=f"Could not render ontology: {exc}", state=state)

        result = RenderResult(
            render_id=render_id,
            run_dir=run_dir,
            output_html=output_path,
            source_name=safe_name,
            label_mode=label_mode,
            max_depth=max_depth,
            rdf_format=rdf_format,
            stats=stats,
            warnings=closure.errors,
            created_at=time(),
        )
        renders[render_id] = result
        _prune_old_renders()

        state = {"max_depth": str(max_depth), "rdf_format": rdf_format or "", "label_mode": label_mode}
        return _render_home(result=result, state=state)

    @app.get("/graph/<render_id>")
    def graph(render_id: str):
        result = renders.get(render_id)
        if result is None or not result.output_html.exists():
            abort(404)
        return send_file(result.output_html, mimetype="text/html")

    @app.get("/download/<render_id>")
    def download(render_id: str):
        result = renders.get(render_id)
        if result is None or not result.output_html.exists():
            abort(404)
        return send_file(
            result.output_html,
            as_attachment=True,
            download_name=result.output_html.name,
            mimetype="text/html",
        )

    return app


HOME_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>OntoViewer</title>
  <style>
    :root {
      --bg: #f4f6f8;
      --card: #ffffff;
      --text: #111827;
      --muted: #4b5563;
      --border: #d1d5db;
      --accent: #0ea5e9;
      --danger-bg: #fee2e2;
      --danger-text: #991b1b;
      --warn-bg: #fef3c7;
      --warn-text: #92400e;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: linear-gradient(160deg, #f4f6f8 0%, #e9eef4 100%);
      color: var(--text);
      font-family: "Source Sans 3", "Segoe UI", sans-serif;
      padding: 24px;
    }
    .wrap {
      max-width: 1200px;
      margin: 0 auto;
      display: grid;
      gap: 16px;
    }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px;
      box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08);
    }
    h1 {
      margin: 0 0 8px;
      font-size: 1.8rem;
    }
    p {
      margin: 0;
      color: var(--muted);
    }
    form {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 12px;
      align-items: end;
      margin-top: 16px;
    }
    label {
      display: block;
      font-size: 0.9rem;
      color: var(--muted);
      margin-bottom: 6px;
    }
    input, select, button {
      width: 100%;
      border-radius: 8px;
      border: 1px solid var(--border);
      padding: 10px 12px;
      font: inherit;
    }
    button {
      cursor: pointer;
      background: var(--accent);
      color: white;
      border-color: transparent;
      font-weight: 600;
    }
    .error {
      background: var(--danger-bg);
      color: var(--danger-text);
      border: 1px solid #fca5a5;
      border-radius: 8px;
      padding: 10px 12px;
      margin-top: 12px;
    }
    .warn {
      background: var(--warn-bg);
      color: var(--warn-text);
      border: 1px solid #fcd34d;
      border-radius: 8px;
      padding: 10px 12px;
      margin-top: 10px;
    }
    .stats {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
      gap: 8px;
      margin-top: 12px;
    }
    .stat {
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px;
      background: #fafafa;
    }
    .stat b { display: block; font-size: 1.2rem; }
    .actions {
      margin-top: 12px;
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
    .actions a {
      text-decoration: none;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 8px 12px;
      color: var(--text);
      background: #fff;
    }
    iframe {
      width: 100%;
      height: 72vh;
      border: 1px solid var(--border);
      border-radius: 10px;
      margin-top: 12px;
      background: white;
    }
  </style>
</head>
<body>
  <div class="wrap">
    <section class="card">
      <h1>OntoViewer Web UI</h1>
      <p>Upload a local ontology file, choose import depth and label mode, then render an interactive graph.</p>

      <form action="/render" method="post" enctype="multipart/form-data">
        <div>
          <label for="ontology_file">Ontology file</label>
          <input id="ontology_file" type="file" name="ontology_file" required />
        </div>
        <div>
          <label for="max_depth">Import recursion depth</label>
          <input id="max_depth" type="number" min="0" name="max_depth" value="{{ state.max_depth }}" />
        </div>
        <div>
          <label for="rdf_format">RDF format (optional)</label>
          <input id="rdf_format" type="text" name="rdf_format" value="{{ state.rdf_format }}" placeholder="auto / turtle / xml / nt" />
        </div>
        <div>
          <label for="label_mode">Default label mode</label>
          <select id="label_mode" name="label_mode">
            <option value="human" {% if state.label_mode == "human" %}selected{% endif %}>human</option>
            <option value="raw" {% if state.label_mode == "raw" %}selected{% endif %}>raw</option>
          </select>
        </div>
        <div>
          <button type="submit">Render Graph</button>
        </div>
      </form>

      {% if error %}
        <div class="error">{{ error }}</div>
      {% endif %}
    </section>

    {% if result %}
      <section class="card">
        <p><b>Source:</b> {{ result.source_name }}</p>
        <p><b>Label mode:</b> {{ result.label_mode }} | <b>Max depth:</b> {{ result.max_depth }}</p>
        <div class="stats">
          <div class="stat"><span>Ontologies</span><b>{{ result.stats.ontologies }}</b></div>
          <div class="stat"><span>Ontology refs</span><b>{{ result.stats.ontology_refs }}</b></div>
          <div class="stat"><span>Classes</span><b>{{ result.stats.classes }}</b></div>
          <div class="stat"><span>Relations</span><b>{{ result.stats.relations }}</b></div>
          <div class="stat"><span>Imports</span><b>{{ result.stats.imports }}</b></div>
          <div class="stat"><span>Unresolved imports</span><b>{{ result.stats.unresolved_imports }}</b></div>
        </div>
        <div class="actions">
          <a href="{{ graph_url }}" target="_blank" rel="noreferrer">Open graph in new tab</a>
          <a href="{{ download_url }}">Download HTML</a>
        </div>
        {% if result.warnings %}
          <div class="warn">
            <b>Warnings:</b>
            <ul>
              {% for warning in result.warnings %}
                <li>{{ warning }}</li>
              {% endfor %}
            </ul>
          </div>
        {% endif %}
        <iframe src="{{ graph_url }}"></iframe>
      </section>
    {% endif %}
  </div>
</body>
</html>
"""
