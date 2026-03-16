from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from shutil import rmtree
from time import time
from typing import Dict, Optional
from uuid import uuid4

from flask import Flask, abort, redirect, render_template_string, request, send_file, url_for
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
    allow_insecure_ssl: bool
    stats: Dict[str, int]
    warnings: list[str]
    created_at: float


def create_app(*, storage_dir: Path) -> Flask:
    storage_root = storage_dir.expanduser().resolve()
    storage_root.mkdir(parents=True, exist_ok=True)
    renders: Dict[str, RenderResult] = {}

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024  # 64 MB upload limit

    def _default_state() -> dict[str, str | bool]:
        return {
            "max_depth": "2",
            "rdf_format": "",
            "label_mode": "human",
            "allow_insecure_ssl": False,
        }

    def _state_from_result(result: RenderResult) -> dict[str, str | bool]:
        return {
            "max_depth": str(result.max_depth),
            "rdf_format": result.rdf_format or "",
            "label_mode": result.label_mode,
            "allow_insecure_ssl": result.allow_insecure_ssl,
        }

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
        state: Optional[dict[str, str | bool]] = None,
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
        render_id = (request.args.get("render_id") or "").strip()
        result = renders.get(render_id) if render_id else None
        if render_id and result is None:
            return _render_home(
                error="The requested render is no longer available. Please upload the ontology again."
            )
        state = _state_from_result(result) if result else _default_state()
        return _render_home(result=result, state=state)

    @app.post("/render")
    def render():
        uploaded = request.files.get("ontology_file")
        if uploaded is None or not uploaded.filename:
            return _render_home(error="Please select an ontology file before rendering.")

        max_depth_raw = (request.form.get("max_depth") or "2").strip()
        rdf_format = (request.form.get("rdf_format") or "").strip() or None
        label_mode_raw = (request.form.get("label_mode") or "human").strip().lower()
        label_mode: LabelMode = "raw" if label_mode_raw == "raw" else "human"
        allow_insecure_ssl = (request.form.get("allow_insecure_ssl") or "").strip().lower() in {
            "1",
            "on",
            "true",
            "yes",
        }

        try:
            max_depth = int(max_depth_raw)
        except ValueError:
            state = {
                "max_depth": max_depth_raw,
                "rdf_format": rdf_format or "",
                "label_mode": label_mode,
                "allow_insecure_ssl": allow_insecure_ssl,
            }
            return _render_home(error="Max depth must be an integer >= 0.", state=state)
        if max_depth < 0:
            state = {
                "max_depth": str(max_depth),
                "rdf_format": rdf_format or "",
                "label_mode": label_mode,
                "allow_insecure_ssl": allow_insecure_ssl,
            }
            return _render_home(error="Max depth must be >= 0.", state=state)

        safe_name = secure_filename(uploaded.filename) or "ontology.owl"
        render_id = uuid4().hex
        run_dir = storage_root / render_id
        run_dir.mkdir(parents=True, exist_ok=True)
        input_path = run_dir / safe_name
        output_path = run_dir / f"{Path(safe_name).stem}_graph.html"

        uploaded.save(input_path)

        try:
            closure = load_ontology_closure(
                input_path,
                max_depth=max_depth,
                rdf_format=rdf_format,
                allow_insecure_ssl=allow_insecure_ssl,
            )
            stats = render_interactive_graph(closure, output_path, label_mode=label_mode)
        except Exception as exc:
            rmtree(run_dir, ignore_errors=True)
            state = {
                "max_depth": str(max_depth),
                "rdf_format": rdf_format or "",
                "label_mode": label_mode,
                "allow_insecure_ssl": allow_insecure_ssl,
            }
            return _render_home(error=f"Could not render ontology: {exc}", state=state)

        result = RenderResult(
            render_id=render_id,
            run_dir=run_dir,
            output_html=output_path,
            source_name=safe_name,
            label_mode=label_mode,
            max_depth=max_depth,
            rdf_format=rdf_format,
            allow_insecure_ssl=allow_insecure_ssl,
            stats=stats,
            warnings=closure.errors,
            created_at=time(),
        )
        renders[render_id] = result
        _prune_old_renders()

        return redirect(url_for("home", render_id=render_id))

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
      --info-bg: #e0f2fe;
      --info-text: #0c4a6e;
      --info-border: #7dd3fc;
      --surface: #fafafa;
      --shadow: rgba(15, 23, 42, 0.08);
      --bg-alt: #e9eef4;
    }
    html.ontoviewer-dark, body.ontoviewer-dark {
      color-scheme: dark;
      --bg: #020617;
      --card: #0f172a;
      --text: #e2e8f0;
      --muted: #cbd5e1;
      --border: #334155;
      --accent: #38bdf8;
      --danger-bg: #450a0a;
      --danger-text: #fecaca;
      --warn-bg: #451a03;
      --warn-text: #fcd34d;
      --info-bg: #082f49;
      --info-text: #bae6fd;
      --info-border: #0369a1;
      --surface: #111827;
      --shadow: rgba(2, 6, 23, 0.45);
      --bg-alt: #111827;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: linear-gradient(160deg, var(--bg) 0%, var(--bg-alt) 100%);
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
      box-shadow: 0 10px 30px var(--shadow);
    }
    .page-head {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 16px;
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
    .secondary-btn {
      width: auto;
      background: var(--card);
      color: var(--text);
      border-color: var(--border);
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
    .info {
      background: var(--info-bg);
      color: var(--info-text);
      border: 1px solid var(--info-border);
      border-radius: 8px;
      padding: 10px 12px;
      margin-top: 12px;
    }
    .hint {
      margin-top: 8px;
      font-size: 0.9rem;
      color: var(--muted);
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
      background: var(--surface);
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
      background: var(--card);
    }
    iframe {
      width: 100%;
      height: 72vh;
      border: 1px solid var(--border);
      border-radius: 10px;
      margin-top: 12px;
      background: var(--card);
    }
  </style>
</head>
<body>
  <div class="wrap">
    <section class="card">
      <div class="page-head">
        <div>
          <h1>OntoViewer Web UI</h1>
          <p>Upload a local ontology file, choose import depth and label mode, then render an interactive graph.</p>
        </div>
        <button id="ontoviewer-theme-toggle" type="button" class="secondary-btn">Dark mode</button>
      </div>

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
          <label for="allow_insecure_ssl">Remote import SSL handling</label>
          <label style="display:flex; gap:8px; align-items:center; margin:0; color:var(--text);">
            <input
              id="allow_insecure_ssl"
              type="checkbox"
              name="allow_insecure_ssl"
              value="1"
              style="width:auto; margin:0;"
              {% if state.allow_insecure_ssl %}checked{% endif %}
            />
            Allow insecure SSL fallback for trusted remote imports with broken certificates
          </label>
        </div>
        <div>
          <button type="submit">Render Graph</button>
        </div>
      </form>

      {% if error %}
        <div class="error">{{ error }}</div>
      {% endif %}
      {% if result %}
        <div class="info">
          <b>Current render:</b> {{ result.source_name }}.
          Choose a new file if you want to replace it.
        </div>
        <div class="actions">
          <a href="{{ url_for('home') }}">Clear current render</a>
        </div>
      {% else %}
        <div class="hint">No file stays selected after rendering. Pick a file again to create a new render.</div>
      {% endif %}
    </section>

    {% if result %}
      <section class="card">
        <p><b>Source:</b> {{ result.source_name }}</p>
        <p>
          <b>Label mode:</b> {{ result.label_mode }} |
          <b>Max depth:</b> {{ result.max_depth }} |
          <b>SSL:</b> {{ "insecure fallback enabled" if result.allow_insecure_ssl else "strict verification" }}
        </p>
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
        <iframe id="ontoviewer-graph-frame" src="{{ graph_url }}"></iframe>
      </section>
    {% endif %}
  </div>
  <script>
    (function () {
      const storageKey = "ontoviewer-theme";

      function getThemeMode() {
        try {
          const stored = window.localStorage.getItem(storageKey);
          if (stored === "light" || stored === "dark") {
            return stored;
          }
        } catch (error) {
          // Ignore storage access issues.
        }
        return "light";
      }

      function setThemeMode(mode, syncFrame) {
        document.documentElement.classList.toggle("ontoviewer-dark", mode === "dark");
        document.body.classList.toggle("ontoviewer-dark", mode === "dark");
        try {
          window.localStorage.setItem(storageKey, mode);
        } catch (error) {
          // Ignore storage access issues.
        }

        const btn = document.getElementById("ontoviewer-theme-toggle");
        if (btn) {
          btn.textContent = mode === "dark" ? "Light mode" : "Dark mode";
        }

        if (!syncFrame) {
          return;
        }

        const frame = document.getElementById("ontoviewer-graph-frame");
        if (!frame || !frame.contentWindow) {
          return;
        }
        if (typeof frame.contentWindow.ontoviewerApplyExternalTheme === "function") {
          frame.contentWindow.ontoviewerApplyExternalTheme(mode);
        }
      }

      window.addEventListener("message", function (event) {
        if (event.origin !== window.location.origin) {
          return;
        }
        if (!event.data || event.data.type !== "ontoviewer-theme") {
          return;
        }
        setThemeMode(event.data.mode === "dark" ? "dark" : "light", false);
      });

      const btn = document.getElementById("ontoviewer-theme-toggle");
      if (btn) {
        btn.addEventListener("click", function () {
          setThemeMode(getThemeMode() === "dark" ? "light" : "dark", true);
        });
      }

      const frame = document.getElementById("ontoviewer-graph-frame");
      if (frame) {
        frame.addEventListener("load", function () {
          setThemeMode(getThemeMode(), true);
        });
      }

      setThemeMode(getThemeMode(), false);
    })();
  </script>
</body>
</html>
"""
