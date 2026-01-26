"""
Repository for interaction history and corrections.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable, TypedDict

import sqlite3

from persistence.database import with_connection

logger = logging.getLogger(__name__)

# Max length for stored transcription and LLM response to avoid unbounded DB growth.
MAX_TEXT_LENGTH = 65536
TRUNCATED_SUFFIX = " [truncated]"


def _truncate_for_storage(text: str, max_len: int = MAX_TEXT_LENGTH) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - len(TRUNCATED_SUFFIX)] + TRUNCATED_SUFFIX


class InteractionRecord(TypedDict):
    id: int
    created_at: str
    original_transcription: str
    llm_response: str
    corrected_response: str | None
    exclude_from_profile: int
    weight: float | None
    speaker_id: str | None
    session_id: str | None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_interaction_record(r: tuple) -> InteractionRecord:
    """
    Map a SELECT row to InteractionRecord. Handles full (9 cols), no-weight (8),
    and legacy (7 cols, no exclude_from_profile or weight) schemas by row length.
    """
    if len(r) >= 9:
        return {
            "id": r[0],
            "created_at": r[1],
            "original_transcription": r[2],
            "llm_response": r[3],
            "corrected_response": r[4],
            "exclude_from_profile": r[5],
            "weight": r[6],
            "speaker_id": r[7],
            "session_id": r[8],
        }
    if len(r) >= 8:
        return {
            "id": r[0],
            "created_at": r[1],
            "original_transcription": r[2],
            "llm_response": r[3],
            "corrected_response": r[4],
            "exclude_from_profile": r[5],
            "weight": None,
            "speaker_id": r[6],
            "session_id": r[7],
        }
    # Legacy 7 columns: no exclude_from_profile, no weight
    return {
        "id": r[0],
        "created_at": r[1],
        "original_transcription": r[2],
        "llm_response": r[3],
        "corrected_response": r[4],
        "exclude_from_profile": 0,
        "weight": None,
        "speaker_id": r[5],
        "session_id": r[6],
    }


def _has_column(conn: sqlite3.Connection, column: str) -> bool:
    """Return True if interactions table has the given column."""
    cur = conn.execute("PRAGMA table_info(interactions)")
    return column in {row[1] for row in cur.fetchall()}


class HistoryRepo:
    """
    Insert and query interactions; update corrections.
    Connector is a callable that returns a new sqlite3.Connection (e.g. get_connection(path)).
    """

    def __init__(self, connector: Callable[[], sqlite3.Connection]) -> None:
        self._connector = connector
        self._has_exclude_from_profile: bool | None = None

    def _schema_has_exclude_from_profile(self, conn: sqlite3.Connection) -> bool:
        if self._has_exclude_from_profile is None:
            self._has_exclude_from_profile = _has_column(conn, "exclude_from_profile")
        return self._has_exclude_from_profile

    def insert_interaction(
        self,
        original_transcription: str,
        llm_response: str,
        *,
        speaker_id: str | None = None,
        session_id: str | None = None,
    ) -> int:
        """
        Insert one interaction. Returns the new row id.
        """
        def insert(conn: sqlite3.Connection) -> int:
            orig = _truncate_for_storage(original_transcription)
            resp = _truncate_for_storage(llm_response)
            cur = conn.execute(
                """
                INSERT INTO interactions (created_at, original_transcription, llm_response, speaker_id, session_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (_now_iso(), orig, resp, speaker_id, session_id),
            )
            return cur.lastrowid or 0
        return with_connection(self._connector, insert, commit=True)

    def update_correction(self, interaction_id: int, corrected_response: str) -> None:
        """Update the corrected_response for an interaction (user/caregiver edit)."""
        def update(conn: sqlite3.Connection) -> None:
            conn.execute(
                "UPDATE interactions SET corrected_response = ? WHERE id = ?",
                (corrected_response, interaction_id),
            )
        with_connection(self._connector, update, commit=True)

    def list_recent(self, limit: int = 100) -> list[InteractionRecord]:
        """Return most recent interactions (newest first)."""
        def query(conn: sqlite3.Connection) -> list[InteractionRecord]:
            if self._schema_has_exclude_from_profile(conn):
                cur = conn.execute(
                    """
                    SELECT id, created_at, original_transcription, llm_response,
                           corrected_response, COALESCE(exclude_from_profile, 0), weight, speaker_id, session_id
                    FROM interactions
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
            else:
                cur = conn.execute(
                    """
                    SELECT id, created_at, original_transcription, llm_response,
                           corrected_response, speaker_id, session_id
                    FROM interactions
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
            return [_row_to_interaction_record(r) for r in cur.fetchall()]
        return with_connection(self._connector, query)

    def get_corrections_for_profile(self, limit: int = 200) -> list[tuple[str, str]]:
        """
        Return list of (llm_response, corrected_response) for interactions
        that have a correction and are not excluded from profile.
        """
        def query(conn: sqlite3.Connection) -> list[tuple[str, str]]:
            if self._schema_has_exclude_from_profile(conn):
                cur = conn.execute(
                    """
                    SELECT llm_response, corrected_response
                    FROM interactions
                    WHERE corrected_response IS NOT NULL AND corrected_response != ''
                      AND (exclude_from_profile = 0 OR exclude_from_profile IS NULL)
                    ORDER BY COALESCE(weight, 0) DESC, created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
            else:
                cur = conn.execute(
                    """
                    SELECT llm_response, corrected_response
                    FROM interactions
                    WHERE corrected_response IS NOT NULL AND corrected_response != ''
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
            return [(r[0], r[1]) for r in cur.fetchall()]
        return with_connection(self._connector, query)

    def get_accepted_for_profile(self, limit: int = 50) -> list[tuple[str, str]]:
        """
        Return (original_transcription, llm_response) for interactions
        with no correction and not excluded from profile.
        """
        def query(conn: sqlite3.Connection) -> list[tuple[str, str]]:
            if self._schema_has_exclude_from_profile(conn):
                cur = conn.execute(
                    """
                    SELECT original_transcription, llm_response
                    FROM interactions
                    WHERE corrected_response IS NULL
                      AND (exclude_from_profile = 0 OR exclude_from_profile IS NULL)
                    ORDER BY COALESCE(weight, 0) DESC, created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
            else:
                cur = conn.execute(
                    """
                    SELECT original_transcription, llm_response
                    FROM interactions
                    WHERE corrected_response IS NULL
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
            return [(r[0] or "", r[1] or "") for r in cur.fetchall()]
        return with_connection(self._connector, query)

    def update_exclude_from_profile(self, interaction_id: int, exclude: bool) -> None:
        """Set exclude_from_profile to 1 if exclude else 0 for the given interaction."""
        def update(conn: sqlite3.Connection) -> None:
            conn.execute(
                "UPDATE interactions SET exclude_from_profile = ? WHERE id = ?",
                (1 if exclude else 0, interaction_id),
            )
        try:
            with_connection(self._connector, update, commit=True)
        except sqlite3.Error as e:
            logger.exception("HistoryRepo.update_exclude_from_profile failed: %s", e)
            raise

    def list_for_curation(self, limit: int = 10_000) -> list[InteractionRecord]:
        """Return interactions for curation (oldest first), including weight and correction status."""
        def query(conn: sqlite3.Connection) -> list[InteractionRecord]:
            has_weight = _has_column(conn, "weight")
            sel = """
                SELECT id, created_at, original_transcription, llm_response,
                       corrected_response, COALESCE(exclude_from_profile, 0)
            """
            if has_weight:
                sel += ", weight, speaker_id, session_id"
            else:
                sel += ", speaker_id, session_id"
            cur = conn.execute(
                sel + " FROM interactions ORDER BY created_at ASC LIMIT ?",
                (limit,),
            )
            return [_row_to_interaction_record(r) for r in cur.fetchall()]
        return with_connection(self._connector, query)

    def update_weight(self, interaction_id: int, weight: float | None) -> None:
        """Set weight for an interaction. None clears the weight."""
        def update(conn: sqlite3.Connection) -> None:
            conn.execute(
                "UPDATE interactions SET weight = ? WHERE id = ?",
                (weight, interaction_id),
            )
        try:
            with_connection(self._connector, update, commit=True)
        except sqlite3.Error as e:
            logger.exception("HistoryRepo.update_weight failed: %s", e)
            raise

    def update_weights_batch(self, updates: list[tuple[int, float]]) -> None:
        """Set weight for multiple interactions in one transaction."""
        if not updates:
            return
        def batch(conn: sqlite3.Connection) -> None:
            for iid, w in updates:
                conn.execute("UPDATE interactions SET weight = ? WHERE id = ?", (w, iid))
        try:
            with_connection(self._connector, batch, commit=True)
        except sqlite3.Error as e:
            logger.exception("HistoryRepo.update_weights_batch failed: %s", e)
            raise

    def set_exclude_batch(self, interaction_ids: list[int], exclude: bool) -> None:
        """Set exclude_from_profile for multiple interactions."""
        if not interaction_ids:
            return
        val = 1 if exclude else 0
        def batch(conn: sqlite3.Connection) -> None:
            for iid in interaction_ids:
                conn.execute(
                    "UPDATE interactions SET exclude_from_profile = ? WHERE id = ?",
                    (val, iid),
                )
        try:
            with_connection(self._connector, batch, commit=True)
        except sqlite3.Error as e:
            logger.exception("HistoryRepo.set_exclude_batch failed: %s", e)
            raise

    def list_ids_older_than(self, created_before_iso: str) -> list[int]:
        """Return interaction ids with created_at < created_before_iso."""
        def query(conn: sqlite3.Connection) -> list[int]:
            cur = conn.execute(
                "SELECT id FROM interactions WHERE created_at < ?",
                (created_before_iso,),
            )
            return [row[0] for row in cur.fetchall()]
        return with_connection(self._connector, query)

    def delete_interactions(self, interaction_ids: list[int]) -> int:
        """Delete interactions by id. Returns number deleted."""
        if not interaction_ids:
            return 0
        def delete(conn: sqlite3.Connection) -> int:
            placeholders = ",".join("?" * len(interaction_ids))
            cur = conn.execute(
                f"DELETE FROM interactions WHERE id IN ({placeholders})",
                interaction_ids,
            )
            return cur.rowcount
        try:
            return with_connection(self._connector, delete, commit=True)
        except sqlite3.Error as e:
            logger.exception("HistoryRepo.delete_interactions failed: %s", e)
            raise
