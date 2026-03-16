from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("flask")

from ontoviewer.webapp import create_app


def test_render_uses_redirect_and_current_render_state(tmp_path: Path, monkeypatch) -> None:
    recorded_kwargs = {}

    def fake_load_ontology_closure(*args, **kwargs):
        recorded_kwargs.update(kwargs)
        return SimpleNamespace(errors=[])

    def fake_render_interactive_graph(_closure, output_path: Path, *, label_mode: str):
        output_path.write_text("<html><body>graph</body></html>", encoding="utf-8")
        return {
            "ontologies": 1,
            "ontology_refs": 1,
            "classes": 2,
            "relations": 1,
            "imports": 0,
            "unresolved_imports": 0,
        }

    monkeypatch.setattr("ontoviewer.webapp.load_ontology_closure", fake_load_ontology_closure)
    monkeypatch.setattr("ontoviewer.webapp.render_interactive_graph", fake_render_interactive_graph)

    app = create_app(storage_dir=tmp_path / "storage")
    client = app.test_client()

    response = client.post(
        "/render",
        data={
            "ontology_file": (BytesIO(b"@prefix owl: <http://www.w3.org/2002/07/owl#> ."), "demo.ttl"),
            "max_depth": "2",
            "rdf_format": "turtle",
            "label_mode": "human",
            "allow_insecure_ssl": "1",
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert response.status_code == 302
    location = response.headers["Location"]
    assert location.startswith("/?render_id=")

    home = client.get(location)
    page = home.get_data(as_text=True)
    assert "Current render:" in page
    assert "demo.ttl" in page
    assert "Choose a new file if you want to replace it." in page
    assert "insecure fallback enabled" in page
    assert recorded_kwargs["allow_insecure_ssl"] is True


def test_missing_render_id_shows_error(tmp_path: Path) -> None:
    app = create_app(storage_dir=tmp_path / "storage")
    client = app.test_client()

    response = client.get("/?render_id=does-not-exist")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "The requested render is no longer available." in page
