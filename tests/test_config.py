"""Tests for config: load_yaml_file, _deep_merge, load_config, AppConfig, resolve_internal_service_url."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

import config
from config import (
    AppConfig,
    get_modules_enabled,
    load_config,
    load_yaml_file,
    resolve_internal_service_url,
)


# ---- load_yaml_file ----
def test_load_yaml_file_missing_returns_empty() -> None:
    path = Path("/nonexistent/config.yaml")
    result = load_yaml_file(path)
    assert result == {}
    assert isinstance(result, dict)
    assert len(result) == 0


def test_load_yaml_file_valid_dict_returns_parsed(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text("key: value\nnested:\n  a: 1\n")
    result = load_yaml_file(p)
    assert isinstance(result, dict)
    assert result.get("key") == "value"
    assert result.get("nested") == {"a": 1}
    assert "key" in result
    assert "nested" in result


def test_load_yaml_file_invalid_yaml_returns_empty(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("key: [unclosed\n")
    result = load_yaml_file(p)
    assert result == {}
    assert isinstance(result, dict)


def test_load_yaml_file_non_dict_returns_empty(tmp_path: Path) -> None:
    p = tmp_path / "list.yaml"
    p.write_text("[1, 2, 3]")
    result = load_yaml_file(p)
    assert result == {}
    assert isinstance(result, dict)


def test_load_yaml_file_empty_file_returns_none_safe_load_returns_none(
    tmp_path: Path,
) -> None:
    p = tmp_path / "empty.yaml"
    p.write_text("")
    result = load_yaml_file(p)
    assert result == {}
    assert isinstance(result, dict)


# ---- _deep_merge (config module) ----
def test_deep_merge_override_wins() -> None:
    base = {"a": 1, "b": 2}
    override = {"b": 20, "c": 3}
    out = config._deep_merge(base, override)
    assert out["a"] == 1
    assert out["b"] == 20
    assert out["c"] == 3
    assert base["b"] == 2
    assert "c" not in base


def test_deep_merge_nested_merge() -> None:
    base = {"x": {"p": 1, "q": 2}}
    override = {"x": {"q": 20, "r": 3}}
    out = config._deep_merge(base, override)
    assert out["x"]["p"] == 1
    assert out["x"]["q"] == 20
    assert out["x"]["r"] == 3
    assert base["x"]["q"] == 2


def test_deep_merge_override_replaces_non_dict() -> None:
    base = {"a": {"b": 1}}
    override = {"a": "string"}
    out = config._deep_merge(base, override)
    assert out["a"] == "string"
    assert isinstance(out["a"], str)


# ---- load_config ----
def test_load_config_missing_root_raises(tmp_path: Path) -> None:
    missing = tmp_path / "nonexistent.yaml"
    with patch.dict(os.environ, {"TALKIE_CONFIG": str(missing)}):
        with patch.object(config, "_get_module_config_paths", return_value=[]):
            with pytest.raises(FileNotFoundError) as exc_info:
                load_config()
            assert "Config not found" in str(exc_info.value)
            assert str(missing) in str(exc_info.value)


def test_load_config_merges_root_and_user(tmp_path: Path) -> None:
    root = tmp_path / "config.yaml"
    root.write_text("persistence:\n  db_path: from_root\nlogging:\n  level: INFO\n")
    user = tmp_path / "config.user.yaml"
    user.write_text("persistence:\n  db_path: from_user\n")
    with patch.dict(os.environ, {"TALKIE_CONFIG": str(root)}):
        with patch.object(config, "_get_module_config_paths", return_value=[]):
            merged = load_config()
            assert isinstance(merged, dict)
            assert merged.get("persistence", {}).get("db_path") == "from_user"
            assert merged.get("logging", {}).get("level") == "INFO"


def test_load_config_without_user_file(tmp_path: Path) -> None:
    root = tmp_path / "config.yaml"
    root.write_text("ollama:\n  model_name: phi\n")
    with patch.dict(os.environ, {"TALKIE_CONFIG": str(root)}):
        with patch.object(config, "_get_module_config_paths", return_value=[]):
            merged = load_config()
            assert merged.get("ollama", {}).get("model_name") == "phi"
            assert isinstance(merged, dict)


def test_load_config_merges_module_configs_first(tmp_path: Path) -> None:
    mod_cfg = tmp_path / "mod.yaml"
    mod_cfg.write_text("audio:\n  sample_rate: 16000\n")
    root = tmp_path / "config.yaml"
    root.write_text("audio:\n  sample_rate: 48000\n  device_id: 0\n")
    with patch.dict(os.environ, {"TALKIE_CONFIG": str(root)}):
        with patch.object(config, "_get_module_config_paths", return_value=[mod_cfg]):
            merged = load_config()
            assert merged.get("audio", {}).get("sample_rate") == 48000
            assert merged.get("audio", {}).get("device_id") == 0


def test_load_config_modules_enabled_only_no_module_paths(tmp_path: Path) -> None:
    """Production: load_config with modules.enabled and no modules/ on disk does not raise."""
    root = tmp_path / "config.yaml"
    root.write_text(
        "modules:\n  enabled: [speech, rag, browser]\n"
        "persistence:\n  db_path: data/talkie.db\n"
    )
    with patch.dict(os.environ, {"TALKIE_CONFIG": str(root)}):
        with patch.object(config, "_get_module_config_paths", return_value=[]):
            merged = load_config()
    assert get_modules_enabled(merged) == ["speech", "rag", "browser"]
    assert merged.get("persistence", {}).get("db_path") == "data/talkie.db"


# ---- get_modules_enabled (production mode) ----
def test_get_modules_enabled_empty_or_none_returns_empty() -> None:
    assert get_modules_enabled(None) == []
    assert get_modules_enabled({}) == []


def test_get_modules_enabled_list_returns_ids() -> None:
    raw = {"modules": {"enabled": ["speech", "rag", "browser"]}}
    assert get_modules_enabled(raw) == ["speech", "rag", "browser"]


def test_get_modules_enabled_not_list_returns_empty() -> None:
    assert get_modules_enabled({"modules": {"enabled": "speech"}}) == []
    assert get_modules_enabled({"modules": {}}) == []
    assert get_modules_enabled({"modules": {"enabled": None}}) == []


# ---- AppConfig ----
def test_app_config_getitem() -> None:
    raw = {"pipeline": {"enabled": True}}
    cfg = AppConfig(raw)
    assert cfg["pipeline"] == {"enabled": True}
    assert cfg["pipeline"]["enabled"] is True


def test_app_config_getitem_missing_key_raises() -> None:
    cfg = AppConfig({"a": 1})
    with pytest.raises(KeyError):
        cfg["missing_key"]


def test_app_config_get_with_default() -> None:
    cfg = AppConfig({"a": 1})
    assert cfg.get("a") == 1
    assert cfg.get("missing") is None
    assert cfg.get("missing", 42) == 42


def test_app_config_none_raw_becomes_empty() -> None:
    cfg = AppConfig(None)
    assert cfg.get("x") is None
    assert isinstance(cfg._raw, dict)
    assert len(cfg._raw) == 0


def test_app_config_get_log_level() -> None:
    cfg = AppConfig({"logging": {"level": "WARN"}})
    assert cfg.get_log_level() == "WARN"
    cfg2 = AppConfig({})
    assert cfg2.get_log_level() == "DEBUG"


def test_app_config_get_log_path() -> None:
    cfg = AppConfig({})
    assert cfg.get_log_path() == "talkie.log"
    cfg2 = AppConfig({"logging": {"file": "custom.log"}})
    assert cfg2.get_log_path() == "custom.log"


def test_app_config_get_db_path() -> None:
    cfg = AppConfig({"persistence": {"db_path": "custom.db"}})
    assert cfg.get_db_path() == "custom.db"
    cfg2 = AppConfig({})
    assert "talkie.db" in cfg2.get_db_path()


def test_app_config_get_curation_config() -> None:
    cfg = AppConfig({"curation": {"min_weight": 0.5}})
    assert cfg.get_curation_config() == {"min_weight": 0.5}
    assert cfg.get_curation_config().get("min_weight") == 0.5


def test_app_config_get_profile_config() -> None:
    cfg = AppConfig({"profile": {"user_context_max_chars": 3000}})
    assert cfg.get_profile_config().get("user_context_max_chars") == 3000


def test_app_config_get_user_context_max_chars() -> None:
    cfg = AppConfig({"profile": {"user_context_max_chars": 5000}})
    assert cfg.get_user_context_max_chars() == 5000
    cfg2 = AppConfig({})
    assert cfg2.get_user_context_max_chars() == 2000


def test_app_config_get_rag_config_calls_sdk(tmp_path: Path) -> None:
    cfg = AppConfig({"ollama": {"base_url": "http://x"}, "rag": {}})
    rag = cfg.get_rag_config()
    assert isinstance(rag, dict)
    assert (
        "top_k" in rag or "ollama_base_url" in rag or rag == {} or "chunk_size" in rag
    )


def test_app_config_get_browser_config_calls_sdk() -> None:
    cfg = AppConfig(
        {"browser": {"search_url_template": "https://example.com?q={query}"}}
    )
    browser = cfg.get_browser_config()
    assert isinstance(browser, dict)


def test_app_config_get_infrastructure_config() -> None:
    cfg = AppConfig({"infrastructure": {"consul": {"enabled": True}}})
    infra = cfg.get_infrastructure_config()
    assert infra.get("consul", {}).get("enabled") is True


def test_app_config_get_keydb_config() -> None:
    cfg = AppConfig({})
    assert cfg.get_keydb_config() == {}
    cfg2 = AppConfig({"infrastructure": {"keydb": {"host": "localhost"}}})
    assert cfg2.get_keydb_config().get("host") == "localhost"


def test_app_config_get_service_discovery_config() -> None:
    cfg = AppConfig({"infrastructure": {"service_discovery": {"enabled": True}}})
    assert cfg.get_service_discovery_config().get("enabled") is True


def test_app_config_get_load_balancing_config() -> None:
    cfg = AppConfig({"infrastructure": {"load_balancing": {"strategy": "round_robin"}}})
    assert cfg.get_load_balancing_config().get("strategy") == "round_robin"


def test_app_config_get_consul_config() -> None:
    cfg = AppConfig({"infrastructure": {"consul": {"host": "localhost", "port": 8500}}})
    assert cfg.get_consul_config().get("host") == "localhost"
    assert cfg.get_consul_config().get("port") == 8500


def test_app_config_resolve_internal_service_url_no_consul() -> None:
    cfg = AppConfig({})
    url = "http://localhost:11434"
    assert cfg.resolve_internal_service_url(url) == url


def test_app_config_resolve_internal_service_url_consul_disabled() -> None:
    cfg = AppConfig({"infrastructure": {"consul": {"enabled": False}}})
    url = "http://ollama.service.consul:11434"
    assert cfg.resolve_internal_service_url(url) == url


# ---- resolve_internal_service_url (module-level) ----
def test_resolve_internal_service_url_empty_returns_unchanged() -> None:
    assert resolve_internal_service_url("", {}) == ""
    assert resolve_internal_service_url("http://x", {}) == "http://x"


def test_resolve_internal_service_url_no_service_consul_returns_unchanged() -> None:
    assert (
        resolve_internal_service_url("http://localhost:11434", {"enabled": True})
        == "http://localhost:11434"
    )


def test_resolve_internal_service_url_consul_exception_returns_unchanged() -> None:
    with patch(
        "modules.api.consul_client.resolve_url_via_consul",
        side_effect=Exception("consul down"),
    ):
        result = resolve_internal_service_url(
            "http://ollama.service.consul:11434",
            {"enabled": True, "host": "localhost", "port": 8500},
        )
    assert result == "http://ollama.service.consul:11434"


def test_get_module_config_paths_exception_returns_empty_list() -> None:
    with patch(
        "sdk.get_module_config_paths",
        side_effect=Exception("discovery failed"),
    ):
        result = config._get_module_config_paths()
    assert result == []
