"""
Normalized config section access for Talkie modules.
Provides get_section() and section-specific getters (RAG, browser) so
config normalization lives in one place; app and modules use these instead of duplicating logic.
"""

from __future__ import annotations

from typing import Any, Callable


def _clamp_int(value: Any, low: int, high: int, default: int) -> int:
    """Parse value to int and clamp to [low, high]; return default if value is None or invalid."""
    if value is None:
        return default
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def _parse_float(value: Any, low: float, high: float, default: float) -> float:
    """Parse value to float and clamp to [low, high]; return default if value is None or parsing fails."""
    if value is None:
        return default
    try:
        return max(low, min(high, float(value)))
    except (TypeError, ValueError):
        return default


def get_section(
    raw_config: dict,
    section: str,
    defaults: dict[str, Any],
    validators: dict[str, Callable[[Any], Any]] | None = None,
) -> dict[str, Any]:
    """
    Return a normalized config section by merging raw section with defaults and applying validators.

    Args:
        raw_config: Full merged config dict (e.g. from load_config()).
        section: Top-level key (e.g. "rag", "browser").
        defaults: Default values for the section; merged with raw_config.get(section, {}).
        validators: Optional dict mapping section key -> callable(value) -> value (e.g. clamp int).

    Returns:
        New dict with all keys from defaults, overridden by raw section, then validated.
    """
    validators = validators or {}
    raw_section = dict(raw_config.get(section) or {})
    out = dict(defaults)
    for k, v in raw_section.items():
        if k in out or k in defaults:
            out[k] = v
    for k, validator in validators.items():
        if k in out:
            try:
                out[k] = validator(out[k])
            except (TypeError, ValueError):
                pass
    return out


def get_rag_section(raw_config: dict) -> dict[str, Any]:
    """
    Return normalized RAG config from full raw config.
    Uses "rag" and "ollama" sections (base_url from ollama).
    """
    r = raw_config.get("rag") or {}
    ollama = raw_config.get("ollama") or {}
    chroma_host = r.get("chroma_host")
    chroma_host = (
        str(chroma_host).strip()
        if chroma_host is not None and str(chroma_host).strip()
        else None
    )
    return {
        "embedding_model": str(r.get("embedding_model", "nomic-embed-text")).strip()
        or "nomic-embed-text",
        "base_url": str(ollama.get("base_url", "http://localhost:11434")).rstrip("/"),
        "vector_db_path": str(r.get("vector_db_path", "data/rag_chroma")),
        "chroma_host": chroma_host,
        "chroma_port": _clamp_int(r.get("chroma_port"), 1, 65535, 8000),
        "top_k": _clamp_int(r.get("top_k"), 1, 20, 5),
        "document_qa_top_k": _clamp_int(r.get("document_qa_top_k"), 1, 20, 8),
        "chunk_size": _clamp_int(r.get("chunk_size"), 100, 2000, 500),
        "chunk_overlap": _clamp_int(r.get("chunk_overlap"), 0, 500, 100),
        "min_query_length": max(0, _clamp_int(r.get("min_query_length"), 0, 10000, 3)),
    }


def get_browser_section(raw_config: dict) -> dict[str, Any]:
    """
    Return normalized browser config from full raw config.
    """
    b = raw_config.get("browser") or {}
    search_url = (b.get("search_engine_url") or "").strip()
    if not search_url or "{query}" not in search_url:
        search_url = "https://duckduckgo.com/?q={query}"
    return {
        "enabled": bool(b.get("enabled", True)),
        "chrome_app_name": str(b.get("chrome_app_name", "Google Chrome")).strip()
        or "Google Chrome",
        "fetch_timeout_sec": _clamp_int(b.get("fetch_timeout_sec"), 5, 120, 20),
        "fetch_max_retries": _clamp_int(b.get("fetch_max_retries"), 0, 5, 2),
        "search_engine_url": search_url,
        "cooldown_sec": _parse_float(b.get("cooldown_sec"), 0.0, 3600.0, 2.0),
        "demo_delay_between_scenarios_sec": _parse_float(
            b.get("demo_delay_between_scenarios_sec"), 1.0, 300.0, 4.0
        ),
    }


__all__ = [
    "get_browser_section",
    "get_rag_section",
    "get_section",
]
