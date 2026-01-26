"""Tests for persistence.history_repo (profile-related methods)."""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from persistence.history_repo import HistoryRepo

_SCHEMA = """
CREATE TABLE interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    original_transcription TEXT NOT NULL,
    llm_response TEXT NOT NULL,
    corrected_response TEXT,
    exclude_from_profile INTEGER NOT NULL DEFAULT 0,
    weight REAL,
    speaker_id TEXT,
    session_id TEXT
);
"""


@pytest.fixture
def db_path() -> Path:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = Path(f.name)
    yield path
    path.unlink(missing_ok=True)


@pytest.fixture
def repo(db_path: Path) -> HistoryRepo:
    with sqlite3.connect(str(db_path)) as conn:
        conn.executescript(_SCHEMA)
    return HistoryRepo(lambda: sqlite3.connect(str(db_path)))


def _insert(
    conn: sqlite3.Connection,
    original: str,
    llm_response: str,
    corrected: str | None = None,
    exclude: int = 0,
) -> None:
    conn.execute(
        """INSERT INTO interactions (created_at, original_transcription, llm_response, corrected_response, exclude_from_profile)
           VALUES (datetime('now'), ?, ?, ?, ?)""",
        (original, llm_response, corrected, exclude),
    )
    conn.commit()


def test_get_accepted_for_profile_excludes_corrected(repo: HistoryRepo, db_path: Path) -> None:
    with sqlite3.connect(str(db_path)) as conn:
        _insert(conn, "hi", "Hello there", corrected=None)
        _insert(conn, "bye", "Goodbye", corrected="See you")
    accepted = repo.get_accepted_for_profile(limit=10)
    assert len(accepted) == 1
    assert accepted[0] == ("hi", "Hello there")


def test_get_accepted_respects_exclude(repo: HistoryRepo, db_path: Path) -> None:
    with sqlite3.connect(str(db_path)) as conn:
        _insert(conn, "a", "A", exclude=0)
        _insert(conn, "b", "B", exclude=1)
    accepted = repo.get_accepted_for_profile(limit=10)
    assert len(accepted) == 1
    assert accepted[0][1] == "A"


def test_update_exclude_from_profile(repo: HistoryRepo, db_path: Path) -> None:
    with sqlite3.connect(str(db_path)) as conn:
        _insert(conn, "x", "X", exclude=0)
        cur = conn.execute("SELECT id FROM interactions LIMIT 1")
        row = cur.fetchone()
    assert row is not None
    uid = row[0]
    repo.update_exclude_from_profile(uid, exclude=True)
    accepted = repo.get_accepted_for_profile(limit=10)
    assert len(accepted) == 0


def test_get_corrections_for_profile_excludes_excluded(repo: HistoryRepo, db_path: Path) -> None:
    with sqlite3.connect(str(db_path)) as conn:
        _insert(conn, "o1", "r1", corrected="c1", exclude=0)
        _insert(conn, "o2", "r2", corrected="c2", exclude=1)
    corrections = repo.get_corrections_for_profile(limit=10)
    assert len(corrections) == 1
    assert corrections[0] == ("r1", "c1")
