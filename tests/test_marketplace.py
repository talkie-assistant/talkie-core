"""Tests for marketplace: validate_repo_name, shortname_from_repo, git_available, list_marketplace_modules, install_module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from marketplace import (
    REPO_NAME_RE,
    _invalidate_cache,
    git_available,
    install_module,
    list_marketplace_modules,
    shortname_from_repo,
    validate_repo_name,
)


# ---- validate_repo_name ----
def test_validate_repo_name_valid() -> None:
    assert validate_repo_name("talkie-module-speech") is True
    assert validate_repo_name("talkie-module-rag") is True
    assert validate_repo_name("talkie-module-browser") is True
    assert validate_repo_name("talkie-module-foo") is True
    assert validate_repo_name("talkie-module-foo_bar") is True
    assert validate_repo_name("talkie-module-foo-bar") is True
    assert validate_repo_name("talkie-module-123") is True


def test_validate_repo_name_invalid() -> None:
    assert validate_repo_name("") is False
    assert validate_repo_name("speech") is False
    assert validate_repo_name("talkie-speech") is False
    assert validate_repo_name("talkie-module-") is False
    assert validate_repo_name("talkie-module-foo/bar") is False
    assert validate_repo_name("talkie-module-..") is False
    assert validate_repo_name("../talkie-module-foo") is False
    assert validate_repo_name("talkie-module-foo ") is False
    assert validate_repo_name(" talkie-module-foo") is False


# ---- shortname_from_repo ----
def test_shortname_from_repo_valid() -> None:
    assert shortname_from_repo("talkie-module-speech") == "speech"
    assert shortname_from_repo("talkie-module-rag") == "rag"
    assert shortname_from_repo("talkie-module-browser") == "browser"
    assert shortname_from_repo("talkie-module-foo") == "foo"
    assert shortname_from_repo("talkie-module-foo_bar") == "foo_bar"


def test_shortname_from_repo_no_prefix() -> None:
    assert shortname_from_repo("speech") == ""
    assert shortname_from_repo("talkie-speech") == ""


def test_shortname_from_repo_empty_after_prefix() -> None:
    assert shortname_from_repo("talkie-module-") == ""


# ---- REPO_NAME_RE constant ----
def test_repo_name_re_matches_valid() -> None:
    assert REPO_NAME_RE.match("talkie-module-speech")
    assert REPO_NAME_RE.match("talkie-module-foo_bar-baz")


def test_repo_name_re_rejects_invalid() -> None:
    assert REPO_NAME_RE.match("talkie-module-") is None
    assert REPO_NAME_RE.match("talkie-module-foo/bar") is None
    assert REPO_NAME_RE.match("other-prefix") is None


# ---- git_available ----
def test_git_available_in_repo_root(talkie_root: Path) -> None:
    """When run from talkie-core (a git repo), root should be detected as git repo."""
    assert talkie_root.is_dir()
    result = git_available(talkie_root)
    assert result is True


def test_git_available_nonexistent_dir() -> None:
    result = git_available(Path("/nonexistent/path/for/talkie"))
    assert result is False


def test_git_available_non_git_dir(tmp_path: Path) -> None:
    """A plain directory that is not a git repo returns False."""
    (tmp_path / "sub").mkdir()
    result = git_available(tmp_path / "sub")
    assert result is False


@pytest.fixture
def talkie_root() -> Path:
    """Path to talkie-core project root (parent of tests/)."""
    return Path(__file__).resolve().parent.parent


# ---- list_marketplace_modules (mocked GitHub) ----
def test_list_marketplace_modules_filters_and_merges_installed(
    tmp_path: Path, modules_root: Path
) -> None:
    """list_marketplace_modules filters talkie-module-* and merges installed from get_modules_info."""
    fake_repos = [
        {
            "name": "talkie-module-speech",
            "description": "Speech",
            "clone_url": "https://github.com/org/talkie-module-speech.git",
            "html_url": "https://github.com/org/talkie-module-speech",
        },
        {
            "name": "talkie-module-rag",
            "description": "RAG",
            "clone_url": "https://github.com/org/talkie-module-rag.git",
            "html_url": "https://github.com/org/talkie-module-rag",
        },
        {"name": "other-repo", "description": "Not a module"},
    ]
    root = tmp_path / "proj"
    root.mkdir()
    (root / "modules").mkdir()
    # Copy modules_root layout so get_modules_info finds speech and rag
    for name in ["speech", "rag"]:
        src = modules_root / name
        if src.exists():
            dst = root / "modules" / name
            dst.mkdir(parents=True)
            for f in ["config.yaml", "MODULE.yaml"]:
                if (src / f).exists():
                    (dst / f).write_text((src / f).read_text())
            (dst / "docs").mkdir(exist_ok=True)
            (dst / "docs" / "README.md").write_text("# Doc\n")

    with patch("marketplace._list_org_repos", return_value=fake_repos):
        result = list_marketplace_modules(root, "talkie-assistant", use_cache=False)
    assert len(result) == 2
    names = {m["repo_name"] for m in result}
    assert "talkie-module-speech" in names
    assert "talkie-module-rag" in names
    for m in result:
        assert m["shortname"] in ("speech", "rag")
        assert m["installed"] is True
        assert "clone_url" in m
        assert "html_url" in m
        assert "description" in m


def test_list_marketplace_modules_skips_non_module_repos(tmp_path: Path) -> None:
    fake_repos = [
        {"name": "talkie-module-foo", "description": "Foo"},
        {"name": "random-repo", "description": "Other"},
    ]
    root = tmp_path / "proj"
    root.mkdir()
    (root / "modules").mkdir()
    with patch("marketplace._list_org_repos", return_value=fake_repos):
        result = list_marketplace_modules(root, "org", use_cache=False)
    assert len(result) == 1
    assert result[0]["repo_name"] == "talkie-module-foo"
    assert result[0]["shortname"] == "foo"
    assert result[0]["installed"] is False


def test_list_marketplace_modules_use_cache(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "modules").mkdir()
    _invalidate_cache("org")
    call_count = 0

    def fake_list(org: str, timeout: float = 10) -> list:
        nonlocal call_count
        call_count += 1
        return [
            {
                "name": "talkie-module-foo",
                "description": "Foo",
                "clone_url": "",
                "html_url": "",
            }
        ]

    with patch("marketplace._list_org_repos", side_effect=fake_list):
        list_marketplace_modules(root, "org", use_cache=True)
        list_marketplace_modules(root, "org", use_cache=True)
    assert call_count == 1
    with patch("marketplace._list_org_repos", side_effect=fake_list):
        list_marketplace_modules(root, "org", use_cache=False)
        list_marketplace_modules(root, "org", use_cache=False)
    assert call_count == 3


def test_invalidate_cache_removes_org(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "modules").mkdir()
    with patch(
        "marketplace._list_org_repos",
        return_value=[
            {
                "name": "talkie-module-foo",
                "description": "",
                "clone_url": "",
                "html_url": "",
            }
        ],
    ):
        list_marketplace_modules(root, "org1", use_cache=True)
    _invalidate_cache("org1")
    with patch("marketplace._list_org_repos", return_value=[]) as mock_list:
        list_marketplace_modules(root, "org1", use_cache=True)
    mock_list.assert_called_once()


@pytest.fixture
def modules_root(tmp_path: Path) -> Path:
    """Minimal modules tree with speech and rag for discovery."""
    for name in ["speech", "rag"]:
        d = tmp_path / name
        d.mkdir()
        (d / "config.yaml").write_text(f"{name}: {{}}\n")
        (d / "MODULE.yaml").write_text(f"name: {name}\nversion: '1.0.0'\n")
        (d / "docs").mkdir()
        (d / "docs" / "README.md").write_text(f"# {name}\n")
    return tmp_path


# ---- install_module (mocked git and GitHub) ----
def test_install_module_invalid_repo_name_returns_400(tmp_path: Path) -> None:
    ok, msg, code = install_module(tmp_path, "org", "not-valid")
    assert ok is False
    assert code == 400
    assert "Invalid" in msg


def test_install_module_empty_repo_name_returns_400(tmp_path: Path) -> None:
    ok, msg, code = install_module(tmp_path, "org", "")
    assert ok is False
    assert code == 400


def test_install_module_git_not_available_returns_400(tmp_path: Path) -> None:
    """When root is not a git repo, install returns 400."""
    with patch("marketplace.git_available", return_value=False):
        ok, msg, code = install_module(
            tmp_path, "talkie-assistant", "talkie-module-foo"
        )
    assert ok is False
    assert code == 400
    assert "git clone" in msg or "git" in msg.lower()


def test_install_module_repo_not_in_org_returns_400(talkie_root: Path) -> None:
    with patch("marketplace.git_available", return_value=True):
        with patch("marketplace._repo_exists_in_org", return_value=False):
            ok, msg, code = install_module(
                talkie_root, "talkie-assistant", "talkie-module-fake"
            )
    assert ok is False
    assert code == 400
    assert "not found" in msg or "Repository" in msg


def test_install_module_already_installed_returns_409(talkie_root: Path) -> None:
    """When modules/<shortname> already exists, install returns 409."""
    existing = talkie_root / "modules" / "speech"
    if not existing.exists():
        pytest.skip("modules/speech not present")
    with patch("marketplace.git_available", return_value=True):
        with patch("marketplace._repo_exists_in_org", return_value=True):
            ok, msg, code = install_module(
                talkie_root, "talkie-assistant", "talkie-module-speech"
            )
    assert ok is False
    assert code == 409
    assert "already" in msg.lower()


def test_install_module_success_mocks_subprocess(tmp_path: Path) -> None:
    """With git_available and repo in org, submodule add + update --init are run; returns 200."""
    # Make tmp_path look like a git repo for git_available
    (tmp_path / "modules").mkdir(exist_ok=True)
    target = tmp_path / "modules" / "newmod"
    assert not target.exists()
    with patch("marketplace.git_available", return_value=True):
        with patch("marketplace._repo_exists_in_org", return_value=True):
            with patch("marketplace.subprocess.run") as mock_run:
                mock_run.return_value = type(
                    "Result", (), {"returncode": 0, "stdout": "", "stderr": ""}
                )()
                ok, msg, code = install_module(
                    tmp_path, "talkie-assistant", "talkie-module-newmod"
                )
    assert ok is True
    assert code == 200
    assert msg == "modules/newmod"
    assert mock_run.call_count == 2
    calls = [c[0][0] for c in mock_run.call_args_list]
    assert [
        "git",
        "submodule",
        "add",
        "https://github.com/talkie-assistant/talkie-module-newmod.git",
        str(target),
    ] in [c[:5] for c in calls]
    assert "submodule" in " ".join(calls[0])
    assert "update" in " ".join(calls[1]) or "init" in " ".join(calls[1])


def test_install_module_submodule_add_fails_returns_500(tmp_path: Path) -> None:
    (tmp_path / "modules").mkdir(exist_ok=True)
    with patch("marketplace.git_available", return_value=True):
        with patch("marketplace._repo_exists_in_org", return_value=True):
            with patch("marketplace.subprocess.run") as mock_run:
                mock_run.return_value = type(
                    "Result",
                    (),
                    {"returncode": 1, "stdout": "", "stderr": "fatal: not a git repo"},
                )()
                ok, msg, code = install_module(tmp_path, "org", "talkie-module-foo")
    assert ok is False
    assert code == 500
    assert "fatal" in msg or "submodule" in msg.lower() or msg
