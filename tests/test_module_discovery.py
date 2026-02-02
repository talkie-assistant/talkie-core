the github """Tests for modules.discovery: discover_modules, get_module_config_paths, get_modules_info, resolve_module_help_path."""

from __future__ import annotations

from pathlib import Path

import pytest

from modules.discovery import (
    DEFAULT_CONFIG_FILENAME,
    MANIFEST_FILENAME,
    discover_modules,
    get_module_config_paths,
    get_modules_info,
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


def test_discover_modules_finds_subdirs_with_config(modules_root: Path) -> None:
    found = discover_modules(modules_root)
    names = [n for n, _ in found]
    assert "speech" in names
    assert "rag" in names
    assert len(found) == 2
    for name, config_path in found:
        assert config_path.is_file()
        assert config_path.name == "config.yaml"
        assert config_path.parent.name in ("speech", "rag")


def test_discover_modules_skips_dir_without_config(modules_root: Path) -> None:
    (modules_root / "no_config").mkdir()
    found = discover_modules(modules_root)
    names = [n for n, _ in found]
    assert "no_config" not in names


def test_discover_modules_skips_disabled_by_manifest(modules_root: Path) -> None:
    manifest = "name: speech\nenabled: false\n"
    (modules_root / "speech" / MANIFEST_FILENAME).write_text(manifest)
    found = discover_modules(modules_root)
    names = [n for n, _ in found]
    assert "speech" not in names
    assert "rag" in names


def test_discover_modules_uses_custom_config_file(modules_root: Path) -> None:
    (modules_root / "custom").mkdir()
    (modules_root / "custom" / "my_config.yaml").write_text("x: 1\n")
    manifest = "name: custom\nconfig_file: my_config.yaml\n"
    (modules_root / "custom" / MANIFEST_FILENAME).write_text(manifest)
    found = discover_modules(modules_root)
    names = [n for n, _ in found]
    assert "custom" in names
    custom_path = next(p for n, p in found if n == "custom")
    assert custom_path.name == "my_config.yaml"


def test_discover_modules_respects_order(modules_root: Path) -> None:
    (modules_root / "speech" / MANIFEST_FILENAME).write_text(
        "name: speech\norder: 20\n"
    )
    (modules_root / "rag" / MANIFEST_FILENAME).write_text("name: rag\norder: 10\n")
    found = discover_modules(modules_root)
    assert found[0][0] == "rag"
    assert found[1][0] == "speech"


def test_get_module_config_paths_returns_paths_only(modules_root: Path) -> None:
    paths = get_module_config_paths(modules_root)
    assert len(paths) == 2
    assert all(isinstance(p, Path) for p in paths)
    assert all(p.is_file() for p in paths)


def test_discover_modules_skips_pycache(modules_root: Path) -> None:
    (modules_root / "__pycache__").mkdir()
    found = discover_modules(modules_root)
    names = [n for n, _ in found]
    assert "__pycache__" not in names


def test_discover_modules_nonexistent_root_returns_empty() -> None:
    assert discover_modules(Path("/nonexistent/modules/path")) == []
    assert get_module_config_paths(Path("/nonexistent/modules/path")) == []


def test_constants() -> None:
    assert MANIFEST_FILENAME == "MODULE.yaml"
    assert DEFAULT_CONFIG_FILENAME == "config.yaml"


# ---- get_modules_info ----


def test_get_modules_info_returns_list_with_expected_keys(modules_root: Path) -> None:
    infos = get_modules_info(modules_root)
    assert len(infos) == 2
    for m in infos:
        assert "id" in m
        assert "name" in m
        assert "version" in m
        assert "description" in m
        assert "order" in m
        assert "config_path" in m
        assert "module_dir" in m
        assert "docs_path" in m
        assert "help_entry" in m
        assert "ui_id" in m
        assert m["docs_path"] == "docs"
        assert m["help_entry"] == "README.md"


def test_get_modules_info_version_default_when_missing(modules_root: Path) -> None:
    (modules_root / "speech" / MANIFEST_FILENAME).write_text("name: speech\nenabled: true\n")
    infos = get_modules_info(modules_root)
    speech_info = next((m for m in infos if m["id"] == "speech"), None)
    assert speech_info is not None
    assert speech_info["version"] == "0.0.0"


def test_get_modules_info_version_and_ui_id_from_manifest(modules_root: Path) -> None:
    (modules_root / "speech" / MANIFEST_FILENAME).write_text(
        "name: speech\nversion: '2.0.0'\ndescription: Audio\norder: 5\n"
    )
    (modules_root / "rag" / MANIFEST_FILENAME).write_text(
        "name: rag\nversion: '1.0.0'\nui_id: documents\n"
    )
    infos = get_modules_info(modules_root)
    speech_info = next((m for m in infos if m["id"] == "speech"), None)
    rag_info = next((m for m in infos if m["id"] == "rag"), None)
    assert speech_info is not None
    assert speech_info["version"] == "2.0.0"
    assert speech_info["description"] == "Audio"
    assert speech_info["order"] == 5
    assert rag_info is not None
    assert rag_info["ui_id"] == "documents"


def test_get_modules_info_empty_for_nonexistent_root() -> None:
    infos = get_modules_info(Path("/nonexistent/modules/path"))
    assert infos == []


def test_get_modules_info_respects_order(modules_root: Path) -> None:
    (modules_root / "speech" / MANIFEST_FILENAME).write_text("name: speech\norder: 20\n")
    (modules_root / "rag" / MANIFEST_FILENAME).write_text("name: rag\norder: 10\n")
    infos = get_modules_info(modules_root)
    assert infos[0]["id"] == "rag"
    assert infos[1]["id"] == "speech"


# ---- resolve_module_help_path ----


def test_resolve_module_help_path_by_id_when_file_exists(modules_root: Path) -> None:
    (modules_root / "speech" / "docs").mkdir()
    (modules_root / "speech" / "docs" / "README.md").write_text("# Speech\n")
    path = resolve_module_help_path("speech", modules_root)
    assert path is not None
    assert path.name == "README.md"
    assert "speech" in str(path)
    assert path.is_file()


def test_resolve_module_help_path_by_ui_id_when_file_exists(modules_root: Path) -> None:
    (modules_root / "rag" / MANIFEST_FILENAME).write_text(
        "name: rag\nversion: '1.0'\nui_id: documents\n"
    )
    (modules_root / "rag" / "docs").mkdir()
    (modules_root / "rag" / "docs" / "README.md").write_text("# RAG\n")
    path = resolve_module_help_path("documents", modules_root)
    assert path is not None
    assert path.name == "README.md"
    assert "rag" in str(path)


def test_resolve_module_help_path_returns_none_when_entry_missing(modules_root: Path) -> None:
    # No docs/README.md
    path = resolve_module_help_path("speech", modules_root)
    assert path is None


def test_resolve_module_help_path_returns_none_for_unknown_id(modules_root: Path) -> None:
    path = resolve_module_help_path("unknown_module", modules_root)
    assert path is None


def test_resolve_module_help_path_uses_custom_docs_path_and_entry(modules_root: Path) -> None:
    (modules_root / "speech" / MANIFEST_FILENAME).write_text(
        "name: speech\nversion: '1.0'\ndocs_path: help\nhelp_entry: index.md\n"
    )
    (modules_root / "speech" / "help").mkdir()
    (modules_root / "speech" / "help" / "index.md").write_text("# Help\n")
    path = resolve_module_help_path("speech", modules_root)
    assert path is not None
    assert path.name == "index.md"
    assert "help" in str(path)
