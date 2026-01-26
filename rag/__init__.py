"""
RAG service: ingest documents (chunk, embed, store in Chroma), retrieve context for LLM.
"""
from __future__ import annotations

import logging
from pathlib import Path

from rag.embed import OllamaEmbedClient, resolve_embedding_model
from rag.store import RAGStore

logger = logging.getLogger(__name__)


class RAGService:
    """
    Facade: ingest(paths), retrieve(query) -> str, list_indexed_sources(), remove_from_index(source), clear_index().
    Uses config for embedding model, Chroma path, top_k, chunk settings.
    """

    def __init__(self, config: dict) -> None:
        self._config = config
        self._embed = OllamaEmbedClient(
            base_url=config["base_url"],
            model_name=config["embedding_model"],
        )
        self._store = RAGStore(
            vector_db_path=config["vector_db_path"],
            embed_client=self._embed,
            chunk_size=config["chunk_size"],
            chunk_overlap=config["chunk_overlap"],
        )
        self._top_k = config["top_k"]
        self._document_qa_top_k = config.get("document_qa_top_k", config["top_k"])
        self._min_query_length = config.get("min_query_length", 3)

    def ingest(self, paths: list[Path]) -> None:
        """Read, chunk, embed, and store documents; replace existing chunks for same source."""
        self._store.add_documents(paths)

    def retrieve(self, query: str, top_k: int | None = None, min_query_length: int | None = None) -> str:
        """Return formatted context string for the LLM, or empty string."""
        k = top_k if top_k is not None else self._top_k
        mql = min_query_length if min_query_length is not None else self._min_query_length
        return self._store.retrieve(query, top_k=k, min_query_length=mql)

    def get_document_qa_top_k(self) -> int:
        return self._document_qa_top_k

    def list_indexed_sources(self) -> list[str]:
        return self._store.list_indexed_sources()

    def remove_from_index(self, source: str) -> None:
        self._store.remove_from_index(source)

    def clear_index(self) -> None:
        self._store.clear_index()

    def has_documents(self) -> bool:
        """True if the collection has at least one chunk (for empty-state check)."""
        return self._store.count() > 0
