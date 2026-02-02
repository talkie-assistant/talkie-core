"""Tests for /api/marketplace/git-available, /api/marketplace/modules, /api/marketplace/install."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient


def _make_marketplace_app(root: Path, org: str = "talkie-assistant") -> FastAPI:
    """Minimal app with marketplace routes only (same logic as run_web)."""
    app = FastAPI()
    _install_attempts: list[tuple[float, str]] = []

    @app.get("/api/marketplace/git-available")
    async def api_marketplace_git_available():
        try:
            from marketplace import git_available

            return {"git_available": git_available(root)}
        except Exception:
            return {"git_available": False}

    @app.get("/api/marketplace/modules")
    async def api_marketplace_modules():
        try:
            from marketplace import list_marketplace_modules

            modules = list_marketplace_modules(root, org)
            return {"modules": modules}
        except Exception:
            return {"modules": [], "error": "Could not load marketplace"}

    @app.post("/api/marketplace/install")
    async def api_marketplace_install(request: Request):
        import time as time_module

        client_host = request.client.host if request.client else "unknown"
        now = time_module.monotonic()
        _install_attempts[:] = [(t, h) for t, h in _install_attempts if now - t < 60]
        if sum(1 for _, h in _install_attempts if h == client_host) >= 5:
            return JSONResponse(
                status_code=429,
                content={"error": "Too many installs; try again in a minute"},
            )
        _install_attempts.append((now, client_host))

        try:
            body = await request.json()
        except Exception:
            return JSONResponse(status_code=400, content={"error": "Invalid JSON body"})
        if not isinstance(body, dict):
            return JSONResponse(
                status_code=400, content={"error": "repo_name required"}
            )

        repo_name = body.get("repo_name")
        if not repo_name or not isinstance(repo_name, str):
            return JSONResponse(
                status_code=400, content={"error": "repo_name required"}
            )
        repo_name = repo_name.strip()
        if not repo_name:
            return JSONResponse(
                status_code=400, content={"error": "repo_name required"}
            )
        try:
            from marketplace import install_module

            loop = asyncio.get_event_loop()
            ok, message, status_code = await loop.run_in_executor(
                None,
                lambda: install_module(root, org, repo_name),
            )
            if ok:
                return {
                    "ok": True,
                    "path": message,
                    "message": "Module added. Restart the app (or reload the page and reconnect) to load it.",
                }
            if status_code == 409:
                return JSONResponse(
                    status_code=409, content={"error": "already installed"}
                )
            return JSONResponse(status_code=status_code, content={"error": message})
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})

    return app


@pytest.fixture
def app_root(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "modules").mkdir()
    return root


def test_api_marketplace_git_available_returns_bool(app_root: Path) -> None:
    app = _make_marketplace_app(app_root)
    client = TestClient(app)
    resp = client.get("/api/marketplace/git-available")
    assert resp.status_code == 200
    data = resp.json()
    assert "git_available" in data
    assert isinstance(data["git_available"], bool)
    assert data["git_available"] is False


def test_api_marketplace_git_available_true_when_in_repo(talkie_root: Path) -> None:
    app = _make_marketplace_app(talkie_root)
    client = TestClient(app)
    resp = client.get("/api/marketplace/git-available")
    assert resp.status_code == 200
    assert resp.json()["git_available"] is True


def test_api_marketplace_git_available_exception_returns_false(app_root: Path) -> None:
    """When git_available raises, handler returns 200 with git_available: false."""
    with patch("marketplace.git_available", side_effect=RuntimeError("git not found")):
        app = _make_marketplace_app(app_root)
        client = TestClient(app)
        resp = client.get("/api/marketplace/git-available")
    assert resp.status_code == 200
    data = resp.json()
    assert "git_available" in data
    assert data["git_available"] is False


def test_api_marketplace_modules_returns_list(app_root: Path) -> None:
    with patch(
        "marketplace._list_org_repos",
        return_value=[
            {
                "name": "talkie-module-foo",
                "description": "Foo",
                "clone_url": "",
                "html_url": "",
            }
        ],
    ):
        app = _make_marketplace_app(app_root)
        client = TestClient(app)
        resp = client.get("/api/marketplace/modules")
    assert resp.status_code == 200
    data = resp.json()
    assert "modules" in data
    assert isinstance(data["modules"], list)
    mods = data["modules"]
    assert len(mods) >= 1
    m = mods[0]
    assert m["repo_name"] == "talkie-module-foo"
    assert m["shortname"] == "foo"
    assert "installed" in m
    assert "clone_url" in m
    assert "html_url" in m


def test_api_marketplace_modules_handles_error(app_root: Path) -> None:
    with patch(
        "marketplace.list_marketplace_modules", side_effect=RuntimeError("API down")
    ):
        app = _make_marketplace_app(app_root)
        client = TestClient(app)
        resp = client.get("/api/marketplace/modules")
    assert resp.status_code == 200
    data = resp.json()
    assert data["modules"] == []
    assert "error" in data
    assert "Could not load" in data["error"]


def test_api_marketplace_install_missing_repo_name_returns_400(app_root: Path) -> None:
    app = _make_marketplace_app(app_root)
    client = TestClient(app)
    resp = client.post("/api/marketplace/install", json={})
    assert resp.status_code == 400
    assert resp.json().get("error") == "repo_name required"


def test_api_marketplace_install_empty_repo_name_returns_400(app_root: Path) -> None:
    app = _make_marketplace_app(app_root)
    client = TestClient(app)
    resp = client.post("/api/marketplace/install", json={"repo_name": ""})
    assert resp.status_code == 400
    assert "repo_name" in resp.json().get(
        "error", ""
    ).lower() or "required" in resp.json().get("error", "")


def test_api_marketplace_install_invalid_json_body_returns_400(app_root: Path) -> None:
    app = _make_marketplace_app(app_root)
    client = TestClient(app)
    resp = client.post(
        "/api/marketplace/install",
        content=b"not valid json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400
    assert "error" in resp.json()
    assert "JSON" in resp.json()["error"] or "json" in resp.json()["error"].lower()


def test_api_marketplace_install_body_not_object_returns_400(app_root: Path) -> None:
    app = _make_marketplace_app(app_root)
    client = TestClient(app)
    resp = client.post("/api/marketplace/install", json=["array"])
    assert resp.status_code == 400
    assert resp.json().get("error") == "repo_name required"


def test_api_marketplace_install_repo_name_not_string_returns_400(
    app_root: Path,
) -> None:
    app = _make_marketplace_app(app_root)
    client = TestClient(app)
    resp = client.post("/api/marketplace/install", json={"repo_name": 123})
    assert resp.status_code == 400
    assert resp.json().get("error") == "repo_name required"


def test_api_marketplace_install_repo_name_whitespace_only_returns_400(
    app_root: Path,
) -> None:
    app = _make_marketplace_app(app_root)
    client = TestClient(app)
    resp = client.post("/api/marketplace/install", json={"repo_name": "   "})
    assert resp.status_code == 400
    assert resp.json().get("error") == "repo_name required"


def test_api_marketplace_install_invalid_name_returns_400(app_root: Path) -> None:
    app = _make_marketplace_app(app_root)
    client = TestClient(app)
    resp = client.post("/api/marketplace/install", json={"repo_name": "not-valid"})
    assert resp.status_code == 400
    assert (
        "Invalid" in resp.json().get("error", "")
        or "invalid" in resp.json().get("error", "").lower()
    )


def test_api_marketplace_install_success_returns_200(app_root: Path) -> None:
    with patch("marketplace.git_available", return_value=True):
        with patch("marketplace._repo_exists_in_org", return_value=True):
            with patch("marketplace.subprocess.run") as mock_run:
                mock_run.return_value = type(
                    "R", (), {"returncode": 0, "stdout": "", "stderr": ""}
                )()
                app = _make_marketplace_app(app_root)
                client = TestClient(app)
                resp = client.post(
                    "/api/marketplace/install",
                    json={"repo_name": "talkie-module-newmod"},
                )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True
    assert data.get("path") == "modules/newmod"
    assert "message" in data
    assert "Restart" in data["message"] or "reload" in data["message"].lower()


def test_api_marketplace_install_already_installed_returns_409(
    talkie_root: Path,
) -> None:
    if not (talkie_root / "modules" / "speech").exists():
        pytest.skip("modules/speech not present")
    with patch("marketplace.git_available", return_value=True):
        with patch("marketplace._repo_exists_in_org", return_value=True):
            app = _make_marketplace_app(talkie_root)
            client = TestClient(app)
            resp = client.post(
                "/api/marketplace/install", json={"repo_name": "talkie-module-speech"}
            )
    assert resp.status_code == 409
    assert "already" in resp.json().get("error", "").lower()


def test_api_marketplace_install_rate_limit_returns_429(app_root: Path) -> None:
    with patch("marketplace.git_available", return_value=True):
        with patch("marketplace._repo_exists_in_org", return_value=True):
            with patch("marketplace.subprocess.run") as mock_run:
                mock_run.return_value = type(
                    "R", (), {"returncode": 0, "stdout": "", "stderr": ""}
                )()
                app = _make_marketplace_app(app_root)
                client = TestClient(app)
                for i in range(5):
                    resp = client.post(
                        "/api/marketplace/install",
                        json={"repo_name": "talkie-module-foo"},
                    )
                    assert resp.status_code in (200, 500), (
                        f"Request {i + 1}: {resp.status_code}"
                    )
                resp6 = client.post(
                    "/api/marketplace/install", json={"repo_name": "talkie-module-bar"}
                )
    assert resp6.status_code == 429
    assert (
        "Too many" in resp6.json().get("error", "")
        or "minute" in resp6.json().get("error", "").lower()
    )


def test_api_marketplace_install_repo_not_in_org_returns_400(app_root: Path) -> None:
    with patch("marketplace.git_available", return_value=True):
        with patch("marketplace._repo_exists_in_org", return_value=False):
            app = _make_marketplace_app(app_root)
            client = TestClient(app)
            resp = client.post(
                "/api/marketplace/install", json={"repo_name": "talkie-module-fake"}
            )
    assert resp.status_code == 400
    assert "not found" in resp.json().get(
        "error", ""
    ).lower() or "Repository" in resp.json().get("error", "")


def test_api_marketplace_modules_response_shape_ui_expects(app_root: Path) -> None:
    """Each module has shortname, repo_name, description, installed (bool); optional clone_url, html_url."""
    with patch(
        "marketplace._list_org_repos",
        return_value=[
            {
                "name": "talkie-module-foo",
                "description": "Foo desc",
                "clone_url": "https://x/foo.git",
                "html_url": "https://x/foo",
            },
            {
                "name": "talkie-module-bar",
                "description": "",
                "clone_url": "",
                "html_url": "",
            },
        ],
    ):
        app = _make_marketplace_app(app_root)
        client = TestClient(app)
        resp = client.get("/api/marketplace/modules")
    assert resp.status_code == 200
    data = resp.json()
    mods = data["modules"]
    assert len(mods) >= 2
    for m in mods:
        assert "shortname" in m
        assert "repo_name" in m
        assert "description" in m
        assert "installed" in m
        assert isinstance(m["installed"], bool)
    assert mods[0]["shortname"] == "foo"
    assert mods[0]["repo_name"] == "talkie-module-foo"
    assert mods[0]["description"] == "Foo desc"
    assert "clone_url" in mods[0]
    assert "html_url" in mods[0]


def test_api_marketplace_modules_null_description_becomes_empty_string(
    app_root: Path,
) -> None:
    """Repo with description: null still yields module with description key as string (e.g. "")."""
    from marketplace import _cache

    _cache.clear()
    with patch(
        "marketplace._list_org_repos",
        return_value=[
            {
                "name": "talkie-module-baz",
                "description": None,
                "clone_url": "",
                "html_url": "",
            },
        ],
    ):
        app = _make_marketplace_app(app_root)
        client = TestClient(app)
        resp = client.get("/api/marketplace/modules")
    assert resp.status_code == 200
    mods = resp.json()["modules"]
    assert len(mods) >= 1
    m = next((x for x in mods if x["shortname"] == "baz"), None)
    assert m is not None
    assert "description" in m
    assert isinstance(m["description"], str)
    assert m["description"] == ""


def test_api_marketplace_install_success_response_shape_ui_expects(
    app_root: Path,
) -> None:
    """Install 200 response has ok === True, path, message for UI."""
    with patch("marketplace.git_available", return_value=True):
        with patch("marketplace._repo_exists_in_org", return_value=True):
            with patch("marketplace.subprocess.run") as mock_run:
                mock_run.return_value = type(
                    "R", (), {"returncode": 0, "stdout": "", "stderr": ""}
                )()
                app = _make_marketplace_app(app_root)
                client = TestClient(app)
                resp = client.post(
                    "/api/marketplace/install",
                    json={"repo_name": "talkie-module-newmod"},
                )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True
    assert "path" in data
    assert data["path"] == "modules/newmod"
    assert "message" in data
    assert isinstance(data["message"], str)


def test_api_marketplace_install_exception_returns_500(app_root: Path) -> None:
    """When install_module raises, handler returns 500 with error."""
    with patch("marketplace.git_available", return_value=True):
        with patch("marketplace._repo_exists_in_org", return_value=True):
            with patch(
                "marketplace.install_module", side_effect=RuntimeError("git failed")
            ):
                app = _make_marketplace_app(app_root)
                client = TestClient(app)
                resp = client.post(
                    "/api/marketplace/install", json={"repo_name": "talkie-module-foo"}
                )
    assert resp.status_code == 500
    data = resp.json()
    assert "error" in data
    assert "git failed" in data["error"] or "failed" in data["error"].lower()


def test_api_marketplace_install_returns_500_when_install_module_fails(
    app_root: Path,
) -> None:
    """When install_module returns (False, msg, 500), handler returns 500 with error."""
    with patch("marketplace.git_available", return_value=True):
        with patch("marketplace._repo_exists_in_org", return_value=True):
            with patch(
                "marketplace.install_module",
                return_value=(False, "submodule add failed", 500),
            ):
                app = _make_marketplace_app(app_root)
                client = TestClient(app)
                resp = client.post(
                    "/api/marketplace/install", json={"repo_name": "talkie-module-foo"}
                )
    assert resp.status_code == 500
    data = resp.json()
    assert "error" in data
    assert "submodule add failed" in data["error"] or "failed" in data["error"].lower()


def test_api_marketplace_install_returns_504_on_timeout(app_root: Path) -> None:
    """When install_module returns (False, 'Install timed out', 504), handler returns 504 with error."""
    with patch("marketplace.git_available", return_value=True):
        with patch("marketplace._repo_exists_in_org", return_value=True):
            with patch(
                "marketplace.install_module",
                return_value=(False, "Install timed out", 504),
            ):
                app = _make_marketplace_app(app_root)
                client = TestClient(app)
                resp = client.post(
                    "/api/marketplace/install", json={"repo_name": "talkie-module-foo"}
                )
    assert resp.status_code == 504
    data = resp.json()
    assert "error" in data
    assert "timed out" in data["error"].lower() or "timeout" in data["error"].lower()


def test_api_marketplace_web_ui_flow(app_root: Path) -> None:
    """Exact sequence the frontend uses: git-available, modules, then install; assert response shapes."""
    fake_repos = [
        {
            "name": "talkie-module-widget",
            "description": "A widget module",
            "clone_url": "",
            "html_url": "",
        },
    ]
    with patch("marketplace._list_org_repos", return_value=fake_repos):
        with patch("marketplace.git_available", return_value=True):
            with patch("marketplace._repo_exists_in_org", return_value=True):
                with patch("marketplace.subprocess.run") as mock_run:
                    mock_run.return_value = type(
                        "R", (), {"returncode": 0, "stdout": "", "stderr": ""}
                    )()
                    app = _make_marketplace_app(app_root)
                    client = TestClient(app)

                    # 1. GET git-available
                    r1 = client.get("/api/marketplace/git-available")
                    assert r1.status_code == 200
                    assert "git_available" in r1.json()
                    assert isinstance(r1.json()["git_available"], bool)

                    # 2. GET modules
                    r2 = client.get("/api/marketplace/modules")
                    assert r2.status_code == 200
                    data2 = r2.json()
                    assert "modules" in data2
                    mods = data2["modules"]
                    assert len(mods) >= 1
                    for m in mods:
                        assert "shortname" in m
                        assert "installed" in m
                        assert "repo_name" in m
                        assert "description" in m

                    # 3. POST install
                    r3 = client.post(
                        "/api/marketplace/install",
                        json={"repo_name": "talkie-module-widget"},
                    )
                    assert r3.status_code == 200
                    data3 = r3.json()
                    assert data3.get("ok") is True
                    assert "path" in data3
                    assert "message" in data3


@pytest.fixture
def talkie_root() -> Path:
    return Path(__file__).resolve().parent.parent
