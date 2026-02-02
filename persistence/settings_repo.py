"""
Repository for user_settings key-value store (e.g. user_context).
"""

from __future__ import annotations

import logging
from typing import Callable

import sqlite3

from persistence.database import with_connection

logger = logging.getLogger(__name__)

# Default when not provided (e.g. tests); app uses config.yaml profile.user_context_max_chars
USER_CONTEXT_MAX_CHARS = 2000


class SettingsRepo:
    """
    Read/write user_settings table. On DB errors, logs and re-raises so callers can show UI message.
    get() returns None for missing key; set() raises on failure.
    """

    def __init__(
        self,
        connector: Callable[[], sqlite3.Connection],
        user_context_max_chars: int | None = None,
    ) -> None:
        self._connector = connector
        self._user_context_max_chars = (
            user_context_max_chars
            if user_context_max_chars is not None
            else USER_CONTEXT_MAX_CHARS
        )

    def get(self, key: str) -> str | None:
        """Return value for key, or None if not found."""

        def get_one(conn: sqlite3.Connection) -> str | None:
            cur = conn.execute("SELECT value FROM user_settings WHERE key = ?", (key,))
            row = cur.fetchone()
            return row[0] if row else None

        try:
            return with_connection(self._connector, get_one)
        except sqlite3.Error as e:
            logger.exception("SettingsRepo.get failed: %s", e)
            raise

    def get_many(self, keys: list[str]) -> dict[str, str | None]:
        """Return dict of key -> value for each key; missing keys get value None. Empty keys -> {}."""

        if not keys:
            return {}

        def get_batch(conn: sqlite3.Connection) -> dict[str, str | None]:
            placeholders = ",".join("?" * len(keys))
            cur = conn.execute(
                "SELECT key, value FROM user_settings WHERE key IN (" + placeholders + ")",
                keys,
            )
            rows = cur.fetchall()
            result: dict[str, str | None] = {k: None for k in keys}
            for row in rows:
                result[row[0]] = row[1]
            return result

        try:
            return with_connection(self._connector, get_batch)
        except sqlite3.Error as e:
            logger.exception("SettingsRepo.get_many failed: %s", e)
            raise

    def set(self, key: str, value: str) -> None:
        """Store value for key. Truncates user_context to configured max chars if key is 'user_context'."""
        if key == "user_context" and len(value) > self._user_context_max_chars:
            value = value[: self._user_context_max_chars]
        try:
            with_connection(
                self._connector,
                lambda conn: conn.execute(
                    """
                    INSERT INTO user_settings (key, value) VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (key, value),
                ),
                commit=True,
            )
        except sqlite3.Error as e:
            logger.exception("SettingsRepo.set failed: %s", e)
            raise

    def set_many(self, pairs: list[tuple[str, str]]) -> None:
        """Store multiple key/value pairs in one transaction. On failure, rolls back."""
        if not pairs:
            return

        def do_set_many(conn: sqlite3.Connection) -> None:
            for key, value in pairs:
                if key == "user_context" and len(value) > self._user_context_max_chars:
                    value = value[: self._user_context_max_chars]
                conn.execute(
                    """
                    INSERT INTO user_settings (key, value) VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (key, value),
                )

        try:
            with_connection(self._connector, do_set_many, commit=True)
        except sqlite3.Error as e:
            logger.exception("SettingsRepo.set_many failed: %s", e)
            raise

    def delete(self, key: str) -> None:
        """Remove key from user_settings. No-op if key is missing."""
        try:
            with_connection(
                self._connector,
                lambda conn: conn.execute(
                    "DELETE FROM user_settings WHERE key = ?", (key,)
                ),
                commit=True,
            )
        except sqlite3.Error as e:
            logger.exception("SettingsRepo.delete failed: %s", e)
            raise

    def delete_many(self, keys: list[str]) -> None:
        """Remove multiple keys in one transaction. On failure, rolls back."""
        if not keys:
            return

        def do_delete_many(conn: sqlite3.Connection) -> None:
            for key in keys:
                conn.execute("DELETE FROM user_settings WHERE key = ?", (key,))

        try:
            with_connection(self._connector, do_delete_many, commit=True)
        except sqlite3.Error as e:
            logger.exception("SettingsRepo.delete_many failed: %s", e)
            raise
