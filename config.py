"""
Minimal config wrapper: single place for keys and defaults; dict-like access for existing callers.
Config is merged from module configs, root config.yaml, and optional config.user.yaml.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

_CONFIG_ROOT = Path(__file__).resolve().parent
_MODULES_ROOT = _CONFIG_ROOT / "modules"


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base. override wins for conflicts. Returns new dict."""
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_yaml_file(path: Path) -> dict:
    """Load a YAML file; return {} if missing or invalid. Single place for safe YAML loading."""
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _load_yaml(path: Path) -> dict:
    """Load a YAML file for config merge; delegates to load_yaml_file."""
    return load_yaml_file(path)


def _get_module_config_paths() -> list[Path]:
    """Discover modules and return ordered config file paths (for merging)."""
    try:
        from sdk import get_module_config_paths

        return get_module_config_paths(_MODULES_ROOT)
    except Exception:
        return []


def get_modules_enabled(raw_config: dict | None) -> list[str]:
    """
    Return list of enabled module ids from config (production mode).
    Used when modules/ is not on disk; config.modules.enabled is the source of truth.
    """
    if not raw_config:
        return []
    mod = raw_config.get("modules")
    if not isinstance(mod, dict):
        return []
    enabled = mod.get("enabled")
    if isinstance(enabled, list):
        return [str(x) for x in enabled if x]
    return []


def load_config() -> dict:
    """
    Load merged config: discovered module configs -> root config.yaml -> config.user.yaml.
    Module configs are discovered from modules/ (each subdir with config.yaml or MODULE.yaml).
    Root config path from TALKIE_CONFIG or project root/config.yaml.
    """
    config_path = os.environ.get("TALKIE_CONFIG", str(_CONFIG_ROOT / "config.yaml"))
    root_path = Path(config_path)
    config_dir = root_path.parent

    merged = {}
    for mod_path in _get_module_config_paths():
        data = _load_yaml(mod_path)
        if data:
            merged = _deep_merge(merged, data)

    if root_path.exists():
        root_data = _load_yaml(root_path)
        if root_data:
            merged = _deep_merge(merged, root_data)
    else:
        raise FileNotFoundError(f"Config not found: {root_path}")

    user_path = config_dir / "config.user.yaml"
    if user_path.exists():
        user_data = _load_yaml(user_path)
        if user_data:
            merged = _deep_merge(merged, user_data)

    return merged


def resolve_internal_service_url(url: str, consul_config: dict) -> str:
    """
    If url contains *.service.consul, resolve it via Consul (authoritative name
    server for internal services). Otherwise return url unchanged.
    """
    if not url or ".service.consul" not in (url or "").lower():
        return url
    if not consul_config or not consul_config.get("enabled", True):
        return url
    try:
        from modules.api.consul_client import resolve_url_via_consul

        host = str(consul_config.get("host", "localhost"))
        port = int(consul_config.get("port", 8500))
        return resolve_url_via_consul(url, host, port)
    except Exception:
        return url


class AppConfig:
    """
    Wraps the raw YAML config dict. Use get_* for typed access with defaults;
    use .get(section, default) for dict-like access (e.g. pipeline, ui).
    """

    def __init__(self, raw: dict) -> None:
        self._raw = raw if raw is not None else {}

    def __getitem__(self, key: str):
        return self._raw[key]

    def get(self, key: str, default=None):
        return self._raw.get(key, default)

    def get_log_level(self) -> str:
        return str(self.get("logging", {}).get("level", "DEBUG"))

    def get_log_path(self) -> str | None:
        """Path for log file (root logger). Default talkie.log."""
        return self.get("logging", {}).get("file", "talkie.log")

    def get_db_path(self) -> str:
        return str(self.get("persistence", {}).get("db_path", "data/talkie.db"))

    def get_curation_config(self) -> dict:
        return self.get("curation") or {}

    def get_profile_config(self) -> dict:
        return self.get("profile") or {}

    def get_user_context_max_chars(self) -> int:
        return int(self.get_profile_config().get("user_context_max_chars", 2000))

    def get_rag_config(self) -> dict:
        """RAG: embedding model, vector DB path or Chroma server (host/port), top_k, chunk settings."""
        from sdk import get_rag_section

        return get_rag_section(self._raw)

    def get_browser_config(self) -> dict:
        """Browser: enabled, chrome app name, fetch timeout/retries, search URL, cooldown, demo delay."""
        from sdk import get_browser_section

        return get_browser_section(self._raw)

    def get_infrastructure_config(self) -> dict:
        """Infrastructure: Consul, KeyDB, service discovery, load balancing."""
        return self.get("infrastructure") or {}

    def get_consul_config(self) -> dict:
        """Consul configuration."""
        return self.get_infrastructure_config().get("consul") or {}

    def get_keydb_config(self) -> dict:
        """KeyDB configuration."""
        return self.get_infrastructure_config().get("keydb") or {}

    def get_service_discovery_config(self) -> dict:
        """Service discovery configuration."""
        return self.get_infrastructure_config().get("service_discovery") or {}

    def get_load_balancing_config(self) -> dict:
        """Load balancing configuration."""
        return self.get_infrastructure_config().get("load_balancing") or {}

    def resolve_internal_service_url(self, url: str) -> str:
        """
        If url contains *.service.consul, resolve it via Consul (authoritative
        name server for internal services). Otherwise return url unchanged.
        """
        return resolve_internal_service_url(url, self.get_consul_config())
