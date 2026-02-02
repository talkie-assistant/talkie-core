"""Tests for SDK config section getters: get_rag_section, get_browser_section."""

from __future__ import annotations


from sdk import get_browser_section, get_rag_section


def test_get_rag_section_empty_returns_defaults() -> None:
    cfg = get_rag_section({})
    assert cfg["embedding_model"] == "nomic-embed-text"
    assert cfg["base_url"] == "http://localhost:11434"
    assert cfg["vector_db_path"] == "data/rag_chroma"
    assert 1 <= cfg["top_k"] <= 20
    assert 100 <= cfg["chunk_size"] <= 2000
    assert cfg["min_query_length"] >= 0


def test_get_rag_section_merges_ollama_base_url() -> None:
    raw = {"ollama": {"base_url": "http://192.168.1.1:11434/"}, "rag": {}}
    cfg = get_rag_section(raw)
    assert cfg["base_url"] == "http://192.168.1.1:11434"


def test_get_rag_section_clamps_top_k() -> None:
    raw = {"rag": {"top_k": 0}}
    cfg = get_rag_section(raw)
    assert cfg["top_k"] == 1
    raw = {"rag": {"top_k": 100}}
    cfg = get_rag_section(raw)
    assert cfg["top_k"] == 20


def test_get_browser_section_empty_returns_defaults() -> None:
    cfg = get_browser_section({})
    assert cfg["enabled"] is True
    assert "chrome" in cfg["chrome_app_name"].lower()
    assert cfg["search_engine_url"] == "https://duckduckgo.com/?q={query}"
    assert 5 <= cfg["fetch_timeout_sec"] <= 120
    assert cfg["cooldown_sec"] >= 0


def test_get_browser_section_preserves_search_url_template() -> None:
    raw = {"browser": {"search_engine_url": "https://example.com?q={query}"}}
    cfg = get_browser_section(raw)
    assert cfg["search_engine_url"] == "https://example.com?q={query}"


def test_get_browser_section_missing_query_placeholder_uses_duckduckgo() -> None:
    raw = {"browser": {"search_engine_url": "https://example.com"}}
    cfg = get_browser_section(raw)
    assert "{query}" in cfg["search_engine_url"]
    assert "duckduckgo" in cfg["search_engine_url"]
