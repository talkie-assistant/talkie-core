"""
SQLite connection and schema initialization for Talkie.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Callable, Generator, TypeVar

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


def with_connection(
    connector: Callable[[], sqlite3.Connection],
    fn: Callable[[sqlite3.Connection], _T],
    *,
    commit: bool = False,
) -> _T:
    """
    Obtain a connection, call fn(conn), and close in finally.
    If commit=True, commit on success and rollback on exception.
    """
    conn = connector()
    try:
        result = fn(conn)
        if commit:
            conn.commit()
        return result
    except Exception:
        if commit:
            conn.rollback()
        raise
    finally:
        conn.close()

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    """Apply performance and robustness PRAGMAs. Safe to call on every connection."""
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")

def _run_migrations(conn: sqlite3.Connection) -> None:
    """Run idempotent migrations for existing DBs (e.g. add new columns)."""
    cur = conn.execute("PRAGMA table_info(interactions)")
    columns = {row[1] for row in cur.fetchall()}
    if "exclude_from_profile" not in columns:
        conn.execute(
            "ALTER TABLE interactions ADD COLUMN exclude_from_profile INTEGER NOT NULL DEFAULT 0"
        )
        logger.debug("Added exclude_from_profile to interactions")
    if "weight" not in columns:
        conn.execute("ALTER TABLE interactions ADD COLUMN weight REAL")
        logger.debug("Added weight to interactions")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_interactions_weight ON interactions(weight) WHERE weight IS NOT NULL"
    )


def init_database(db_path: str) -> None:
    """
    Create the database file if needed and apply schema.
    Idempotent; safe to call on every startup.
    """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    schema_sql = _SCHEMA_PATH.read_text()
    with sqlite3.connect(db_path) as conn:
        _apply_pragmas(conn)
        conn.executescript(schema_sql)
        _run_migrations(conn)
    logger.info("Schema applied to %s", db_path)


def get_connection(db_path: str) -> sqlite3.Connection:
    """
    Return a new SQLite connection. Caller must close it or use as context manager.
    Applies WAL and busy_timeout for concurrent use and lock robustness.
    """
    conn = sqlite3.connect(db_path, check_same_thread=False)
    _apply_pragmas(conn)
    return conn


def connection_context(db_path: str) -> Generator[sqlite3.Connection, None, None]:
    """Context manager yielding a connection that is committed and closed on exit."""
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
