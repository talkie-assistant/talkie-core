"""Tests for /api/modules and /api/modules/{id}/help (module list and help endpoints)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient


def _make_modules_app(modules_root: Path) -> FastAPI:
    """Minimal app with only GET /api/modules and GET /api/modules/{module_id}/help."""
    app = FastAPI()

    @app.get("/api/modules")
    async def api_modules_list():
        try:
            from modules.discovery import get_modules_info

            infos = get_modules_info(modules_root)
            return {
                "modules": [
                    {
                        "id": m["id"],
                        "name": m["name"],
                        "version": m["version"],
                        "description": m["description"],
                        "ui_id": m.get("ui_id"),
                    }
                    for m in infos
                ]
            }
        except Exception:
            return {"modules": []}

    @app.get("/api/modules/{module_id}/help")
    async def api_module_help(module_id: str):
        try:
            from modules.discovery import resolve_module_help_path

            help_path = resolve_module_help_path(module_id, modules_root)
            if help_path is None or not help_path.is_file():
                return JSONResponse(
                    status_code=404, content={"error": "Module or help entry not found"}
                )
            raw = help_path.read_text(encoding="utf-8", errors="replace")
            try:
                import markdown

                html = markdown.markdown(
                    raw,
                    extensions=["tables", "fenced_code", "nl2br"],
                )
            except Exception:
                import html as html_module

                html = "<pre>" + html_module.escape(raw) + "</pre>"
            return {"content": html, "format": "html"}
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})

    return app


@pytest.fixture
def modules_root(tmp_path: Path) -> Path:
    """Temporary modules tree with speech and rag (one with docs)."""
    (tmp_path / "speech").mkdir()
    (tmp_path / "speech" / "config.yaml").write_text("audio: {}\n")
    (tmp_path / "speech" / "MODULE.yaml").write_text(
        "name: speech\nversion: '1.0.0'\ndescription: Audio\n"
    )
    (tmp_path / "speech" / "docs").mkdir()
    (tmp_path / "speech" / "docs" / "README.md").write_text(
        "# Speech module\n\nHelp text."
    )
    (tmp_path / "rag").mkdir()
    (tmp_path / "rag" / "config.yaml").write_text("rag: {}\n")
    (tmp_path / "rag" / "MODULE.yaml").write_text(
        "name: rag\nversion: '1.0.0'\nui_id: documents\n"
    )
    (tmp_path / "rag" / "docs").mkdir()
    (tmp_path / "rag" / "docs" / "README.md").write_text(
        "# RAG\n\n| A | B |\n|-|-|\n|1|2|"
    )
    return tmp_path


def test_api_modules_list_returns_modules(modules_root: Path) -> None:
    app = _make_modules_app(modules_root)
    client = TestClient(app)
    resp = client.get("/api/modules")
    assert resp.status_code == 200
    data = resp.json()
    assert "modules" in data
    mods = data["modules"]
    assert len(mods) == 2
    ids = {m["id"] for m in mods}
    assert "speech" in ids
    assert "rag" in ids
    for m in mods:
        assert "name" in m
        assert "version" in m
        assert "description" in m
        assert "ui_id" in m


def test_api_modules_help_returns_html(modules_root: Path) -> None:
    app = _make_modules_app(modules_root)
    client = TestClient(app)
    resp = client.get("/api/modules/speech/help")
    assert resp.status_code == 200
    data = resp.json()
    assert data["format"] == "html"
    assert "content" in data
    assert "Speech" in data["content"] or "speech" in data["content"].lower()
    assert "<" in data["content"]


def test_api_modules_help_by_ui_id(modules_root: Path) -> None:
    app = _make_modules_app(modules_root)
    client = TestClient(app)
    resp = client.get("/api/modules/documents/help")
    assert resp.status_code == 200
    data = resp.json()
    assert data["format"] == "html"
    assert "RAG" in data["content"] or "rag" in data["content"].lower()


def test_api_modules_help_404_unknown_id(modules_root: Path) -> None:
    app = _make_modules_app(modules_root)
    client = TestClient(app)
    resp = client.get("/api/modules/unknown_module/help")
    assert resp.status_code == 404
    assert resp.json().get("error")


def test_api_modules_help_404_missing_docs(modules_root: Path) -> None:
    """Module with no docs/README.md returns 404."""
    (modules_root / "nodocs").mkdir()
    (modules_root / "nodocs" / "config.yaml").write_text("x: 1\n")
    (modules_root / "nodocs" / "MODULE.yaml").write_text(
        "name: nodocs\nversion: '1.0'\n"
    )
    app = _make_modules_app(modules_root)
    client = TestClient(app)
    resp = client.get("/api/modules/nodocs/help")
    assert resp.status_code == 404
