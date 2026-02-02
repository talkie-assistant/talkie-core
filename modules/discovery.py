"""
Re-export module discovery from the SDK.
Provides backward-compatible default for modules_root (this package's parent directory).
"""

from __future__ import annotations

from pathlib import Path

from sdk.discovery import (
    DEFAULT_CONFIG_FILENAME,
    MANIFEST_FILENAME,
    discover_modules as _discover_modules,
    get_module_config_paths as _get_module_config_paths,
    get_modules_info as _get_modules_info,
    resolve_module_help_path as _resolve_module_help_path,
)


def discover_modules(modules_root: Path | None = None) -> list[tuple[str, Path]]:
    """Discover modules; if modules_root is None, use the modules/ directory next to this file."""
    if modules_root is None:
        modules_root = Path(__file__).resolve().parent
    return _discover_modules(modules_root)


def get_module_config_paths(modules_root: Path | None = None) -> list[Path]:
    """Return ordered config paths; if modules_root is None, use the modules/ directory next to this file."""
    if modules_root is None:
        modules_root = Path(__file__).resolve().parent
    return _get_module_config_paths(modules_root)


def get_modules_info(modules_root: Path | None = None) -> list[dict]:
    """Return module info (name, version, description, ui_id, etc.) for API/UI."""
    if modules_root is None:
        modules_root = Path(__file__).resolve().parent
    return _get_modules_info(modules_root)


def resolve_module_help_path(
    module_id: str, modules_root: Path | None = None
) -> Path | None:
    """Resolve module_id (dir name or ui_id) to path of help entry file, or None."""
    if modules_root is None:
        modules_root = Path(__file__).resolve().parent
    return _resolve_module_help_path(modules_root, module_id)


__all__ = [
    "DEFAULT_CONFIG_FILENAME",
    "MANIFEST_FILENAME",
    "discover_modules",
    "get_module_config_paths",
    "get_modules_info",
    "resolve_module_help_path",
]
