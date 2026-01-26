"""Tests for persistence.training_repo."""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from persistence.training_repo import TrainingRepo

_SCHEMA = """
CREATE TABLE training_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_training_facts_created_at ON training_facts(created_at);
"""


@pytest.fixture
def db_path() -> Path:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = Path(f.name)
    yield path
    path.unlink(missing_ok=True)


@pytest.fixture
def repo(db_path: Path) -> TrainingRepo:
    with sqlite3.connect(str(db_path)) as conn:
        conn.executescript(_SCHEMA)
    return TrainingRepo(lambda: sqlite3.connect(str(db_path)))


def test_add_and_list(repo: TrainingRepo) -> None:
    id1 = repo.add("Star is my dog.")
    assert id1 > 0
    id2 = repo.add("Susan is my wife.")
    assert id2 > 0
    rows = repo.list_all()
    assert len(rows) == 2
    assert rows[0][1] == "Star is my dog."
    assert rows[1][1] == "Susan is my wife."


def test_add_empty_raises(repo: TrainingRepo) -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        repo.add("   ")


def test_delete(repo: TrainingRepo) -> None:
    id1 = repo.add("One.")
    repo.add("Two.")
    repo.delete(id1)
    rows = repo.list_all()
    assert len(rows) == 1
    assert rows[0][1] == "Two."


def test_get_for_profile(repo: TrainingRepo) -> None:
    repo.add("First.")
    repo.add("Second.")
    facts = repo.get_for_profile(limit=10)
    assert "Second." in facts
    assert "First." in facts
    assert len(facts) == 2
