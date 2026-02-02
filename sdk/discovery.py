"""
Module discovery: find all modules under a modules root and their config paths.
A module is a subdirectory that contains config.yaml (or the file named in MODULE.yaml).
MODULE.yaml manifest: name, version (required, default 0.0.0), description, enabled,
order, config_file; optional docs_path, help_entry, ui_id.
Callers must pass modules_root (e.g. project_root / "modules"); no default to avoid wrong paths.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "MODULE.yaml"
DEFAULT_CONFIG_FILENAME = "config.yaml"
DEFAULT_VERSION = "0.0.0"
DEFAULT_DOCS_PATH = "docs"
DEFAULT_HELP_ENTRY = "README.md"


def _load_manifest(module_dir: Path) -> dict[str, Any]:
    """Load MODULE.yaml from module_dir. Returns {} if missing or invalid."""
    from config import load_yaml_file

    path = module_dir / MANIFEST_FILENAME
    data = load_yaml_file(path)
    if not data and path.exists():
        logger.debug("Could not load %s (invalid or empty)", path)
    return data


def _normalize_manifest(manifest: dict[str, Any], module_dir: Path) -> dict[str, Any]:
    """Apply defaults for version, docs_path, help_entry, ui_id; warn if version missing."""
    out = dict(manifest)
    if "version" not in out or out["version"] is None:
        logger.warning(
            "Module %s: manifest missing 'version', defaulting to %s",
            module_dir.name,
            DEFAULT_VERSION,
        )
        out["version"] = DEFAULT_VERSION
    else:
        out["version"] = str(out["version"]).strip()
    out.setdefault("docs_path", DEFAULT_DOCS_PATH)
    out.setdefault("help_entry", DEFAULT_HELP_ENTRY)
    if "ui_id" not in out:
        out["ui_id"] = None
    return out


def discover_modules(modules_root: Path) -> list[tuple[str, Path]]:
    """
    Discover modules under modules_root. A module is a subdirectory that contains
    config.yaml (or the config_file from MODULE.yaml) and is not disabled.

    Args:
        modules_root: Path to the modules directory (e.g. project_root / "modules").

    Returns:
        List of (module_name, config_path) sorted by manifest order then directory name.
    """
    if not modules_root.is_dir():
        return []

    result: list[
        tuple[str, str, int, Path]
    ] = []  # (name, sort_key, order, config_path)

    for candidate in sorted(modules_root.iterdir()):
        if not candidate.is_dir():
            continue
        if candidate.name.startswith(".") or candidate.name == "__pycache__":
            continue
        manifest = _load_manifest(candidate)
        if manifest.get("enabled") is False:
            continue
        config_file = manifest.get("config_file") or DEFAULT_CONFIG_FILENAME
        config_path = candidate / config_file
        if not config_path.is_file():
            continue
        name = manifest.get("name") or candidate.name
        order = (
            int(manifest.get("order", 0))
            if isinstance(manifest.get("order"), (int, float))
            else 0
        )
        result.append((name, candidate.name, order, config_path))

    result.sort(key=lambda x: (x[2], x[1]))
    return [(name, config_path) for name, _sk, _order, config_path in result]


def get_modules_info(modules_root: Path) -> list[dict[str, Any]]:
    """
    Return list of discovered modules with full manifest-derived info for API/UI.
    Each item: id (dir name), name, version, description, order, config_path, module_dir,
    docs_path, help_entry, ui_id.
    """
    if not modules_root.is_dir():
        return []
    result: list[tuple[int, str, str, Path, Path, dict[str, Any]]] = []
    for candidate in sorted(modules_root.iterdir()):
        if not candidate.is_dir():
            continue
        if candidate.name.startswith(".") or candidate.name == "__pycache__":
            continue
        manifest = _load_manifest(candidate)
        if manifest.get("enabled") is False:
            continue
        config_file = manifest.get("config_file") or DEFAULT_CONFIG_FILENAME
        config_path = candidate / config_file
        if not config_path.is_file():
            continue
        manifest = _normalize_manifest(manifest, candidate)
        order = (
            int(manifest.get("order", 0))
            if isinstance(manifest.get("order"), (int, float))
            else 0
        )
        result.append(
            (
                order,
                manifest.get("name") or candidate.name,
                candidate.name,
                config_path,
                candidate,
                manifest,
            )
        )
    result.sort(key=lambda x: (x[0], x[2]))
    infos = []
    for _order, name, dir_name, config_path, module_dir, m in result:
        infos.append(
            {
                "id": dir_name,
                "name": name,
                "version": m.get("version", DEFAULT_VERSION),
                "description": m.get("description") or "",
                "order": _order,
                "config_path": str(config_path),
                "module_dir": str(module_dir),
                "docs_path": m.get("docs_path", DEFAULT_DOCS_PATH),
                "help_entry": m.get("help_entry", DEFAULT_HELP_ENTRY),
                "ui_id": m.get("ui_id"),
            }
        )
    return infos


def resolve_module_help_path(modules_root: Path, module_id: str) -> Path | None:
    """
    Resolve module_id (directory name or ui_id) to the path of the help entry file.
    Returns path to docs_path/help_entry if it exists, else None.
    """
    infos = get_modules_info(modules_root)
    for info in infos:
        if info["id"] == module_id or info.get("ui_id") == module_id:
            module_dir = Path(info["module_dir"])
            docs_path = info.get("docs_path") or DEFAULT_DOCS_PATH
            help_entry = info.get("help_entry") or DEFAULT_HELP_ENTRY
            entry = module_dir / docs_path / help_entry
            if entry.is_file():
                return entry
            return None
    return None


def get_module_config_paths(modules_root: Path) -> list[Path]:
    """
    Return ordered list of config file paths for discovered modules (for config merge).

    Args:
        modules_root: Path to the modules directory.
    """
    return [path for _name, path in discover_modules(modules_root)]
