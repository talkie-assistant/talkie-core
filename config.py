"""
Minimal config wrapper: single place for keys and defaults; dict-like access for existing callers.
Config is centralized in a single YAML file (see config.yaml).
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

_CONFIG_ROOT = Path(__file__).resolve().parent


def load_config() -> dict:
    """Load config from config.yaml or path in TALKIE_CONFIG. Single loader for app and CLI."""
    config_path = os.environ.get("TALKIE_CONFIG", _CONFIG_ROOT / "config.yaml")
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path) as f:
        return yaml.safe_load(f) or {}


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
        return str(self.get("logging", {}).get("level", "INFO"))

    def get_db_path(self) -> str:
        return str(self.get("persistence", {}).get("db_path", "data/talkie.db"))

    def get_curation_config(self) -> dict:
        return self.get("curation") or {}

    def get_profile_config(self) -> dict:
        return self.get("profile") or {}

    def get_user_context_max_chars(self) -> int:
        return int(self.get_profile_config().get("user_context_max_chars", 2000))

    def get_rag_config(self) -> dict:
        """RAG: embedding model, vector DB path, top_k, chunk settings."""
        r = self.get("rag") or {}
        ollama = self.get("ollama") or {}
        return {
            "embedding_model": str(r.get("embedding_model", "nomic-embed-text")).strip() or "nomic-embed-text",
            "base_url": str(ollama.get("base_url", "http://localhost:11434")).rstrip("/"),
            "vector_db_path": str(r.get("vector_db_path", "data/rag_chroma")),
            "top_k": max(1, min(20, int(r.get("top_k", 5)))),
            "document_qa_top_k": max(1, min(20, int(r.get("document_qa_top_k", 8)))),
            "chunk_size": max(100, min(2000, int(r.get("chunk_size", 500)))),
            "chunk_overlap": max(0, min(500, int(r.get("chunk_overlap", 100)))),
            "min_query_length": max(0, int(r.get("min_query_length", 3))),
        }
