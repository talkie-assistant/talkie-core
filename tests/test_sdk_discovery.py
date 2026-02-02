"""Tests for sdk.discovery: get_modules_info, resolve_module_help_path, constants."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdk.discovery import (
    DEFAULT_CONFIG_FILENAME,
    DEFAULT_DOCS_PATH,
    DEFAULT_HELP_ENTRY,
    DEFAULT_VERSION,
    MANIFEST_FILENAME,
    get_modules_info,
    get_module_config_paths,
    resolve_module_help_path,
)


@pytest.fixture
def modules_root(tmp_path: Path) -> Path:
    """Create a temporary modules-like tree."""
    (tmp_path / "speech").mkdir()
    (tmp_path / "speech" / "config.yaml").write_text("audio: {}\n")
    (tmp_path / "rag").mkdir()
    (tmp_path / "rag" / "config.yaml").write_text("rag: {}\n")
    return tmp_path


def test_sdk_constants() -> None:
    assert MANIFEST_FILENAME == "MODULE.yaml"
    assert DEFAULT_CONFIG_FILENAME == "config.yaml"
    assert DEFAULT_VERSION == "0.0.0"
    assert DEFAULT_DOCS_PATH == "docs"
    assert DEFAULT_HELP_ENTRY == "README.md"


def test_get_modules_info_structure(modules_root: Path) -> None:
    infos = get_modules_info(modules_root)
    assert len(infos) >= 2
    for m in infos:
        assert m["docs_path"] == DEFAULT_DOCS_PATH
        assert m["help_entry"] == DEFAULT_HELP_ENTRY
        assert "version" in m
        assert isinstance(m["version"], str)
        assert isinstance(m["order"], int)


def test_get_modules_info_skips_disabled(modules_root: Path) -> None:
    (modules_root / "speech" / MANIFEST_FILENAME).write_text(
        "name: speech\nenabled: false\nversion: '1.0'\n"
    )
    infos = get_modules_info(modules_root)
    ids = [m["id"] for m in infos]
    assert "speech" not in ids
    assert "rag" in ids


def test_resolve_module_help_path_sdk_signature(modules_root: Path) -> None:
    """resolve_module_help_path(modules_root, module_id) - modules_root first."""
    (modules_root / "speech" / "docs").mkdir()
    (modules_root / "speech" / "docs" / "README.md").write_text("# Speech\n")
    path = resolve_module_help_path(modules_root, "speech")
    assert path is not None
    assert path.name == "README.md"
    assert path.is_file()


def test_resolve_module_help_path_nonexistent_root() -> None:
    root = Path("/nonexistent/modules/path")
    path = resolve_module_help_path(root, "speech")
    assert path is None


def test_get_module_config_paths_unchanged(modules_root: Path) -> None:
    """get_module_config_paths still returns paths only (backward compat)."""
    from sdk.discovery import discover_modules

    paths = get_module_config_paths(modules_root)
    discovered = discover_modules(modules_root)
    assert len(paths) == len(discovered)
    assert all(p.is_file() for p in paths)
