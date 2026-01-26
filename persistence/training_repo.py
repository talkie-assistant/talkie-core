"""
Repository for training_facts: context sentences the user spoke in training mode (e.g. "Star is my dog").
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable

import sqlite3

from persistence.database import with_connection

logger = logging.getLogger(__name__)

# Max facts to include in LLM context (oldest dropped when over limit)
TRAINING_FACTS_PROFILE_LIMIT = 100


class TrainingRepo:
    """
    Read/write training_facts table. Used by training mode UI and by profile for LLM context.
    """

    def __init__(self, connector: Callable[[], sqlite3.Connection]) -> None:
        self._connector = connector

    def add(self, text: str) -> int:
        """Insert a training fact; return its id. Raises on DB error."""
        text = (text or "").strip()
        if not text:
            raise ValueError("Training fact text cannot be empty")

        def insert(conn: sqlite3.Connection) -> int:
            cur = conn.execute(
                "INSERT INTO training_facts (text, created_at) VALUES (?, ?)",
                (text, datetime.utcnow().isoformat() + "Z"),
            )
            conn.commit()
            return cur.lastrowid or 0

        try:
            return with_connection(self._connector, insert, commit=False)
        except sqlite3.Error as e:
            logger.exception("TrainingRepo.add failed: %s", e)
            raise

    def list_all(self) -> list[tuple[int, str, str]]:
        """Return list of (id, text, created_at) ordered by created_at ascending."""
        def select(conn: sqlite3.Connection) -> list[tuple[int, str, str]]:
            cur = conn.execute(
                "SELECT id, text, created_at FROM training_facts ORDER BY created_at ASC"
            )
            return [(row[0], row[1], row[2]) for row in cur.fetchall()]

        try:
            return with_connection(self._connector, select)
        except sqlite3.Error as e:
            logger.exception("TrainingRepo.list_all failed: %s", e)
            raise

    def delete(self, fact_id: int) -> None:
        """Delete a training fact by id. Raises on DB error."""
        def delete_one(conn: sqlite3.Connection) -> None:
            conn.execute("DELETE FROM training_facts WHERE id = ?", (fact_id,))
            conn.commit()

        try:
            with_connection(self._connector, delete_one, commit=False)
        except sqlite3.Error as e:
            logger.exception("TrainingRepo.delete failed: %s", e)
            raise

    def get_for_profile(self, limit: int = TRAINING_FACTS_PROFILE_LIMIT) -> list[str]:
        """Return the most recent N training fact texts for LLM context (newest first in list)."""
        def select(conn: sqlite3.Connection) -> list[str]:
            cur = conn.execute(
                """
                SELECT text FROM training_facts
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            return [row[0] for row in cur.fetchall()]

        try:
            return with_connection(self._connector, select)
        except sqlite3.Error as e:
            logger.exception("TrainingRepo.get_for_profile failed: %s", e)
            return []
