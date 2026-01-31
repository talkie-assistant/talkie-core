"""Tests for persistence.training_repo."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from persistence.training_repo import TRAINING_FACTS_PROFILE_LIMIT, TrainingRepo

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
    assert isinstance(id1, int)
    id2 = repo.add("Susan is my wife.")
    assert id2 > 0
    assert id2 != id1
    rows = repo.list_all()
    assert len(rows) == 2
    assert rows[0][1] == "Star is my dog."
    assert rows[1][1] == "Susan is my wife."
    assert rows[0][0] == id1
    assert rows[1][0] == id2
    assert len(rows[0]) == 3
    assert isinstance(rows[0][2], str)


def test_add_empty_raises(repo: TrainingRepo) -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        repo.add("   ")
    with pytest.raises(ValueError, match="cannot be empty"):
        repo.add("")


def test_delete(repo: TrainingRepo) -> None:
    id1 = repo.add("One.")
    repo.add("Two.")
    repo.delete(id1)
    rows = repo.list_all()
    assert len(rows) == 1
    assert rows[0][1] == "Two."
    assert rows[0][0] != id1


def test_get_for_profile(repo: TrainingRepo) -> None:
    repo.add("First.")
    repo.add("Second.")
    facts = repo.get_for_profile(limit=10)
    assert "Second." in facts
    assert "First." in facts
    assert len(facts) == 2
    assert facts[0] == "Second."
    assert facts[1] == "First."
    assert isinstance(facts, list)
    assert all(isinstance(f, str) for f in facts)


def test_get_for_profile_respects_limit(repo: TrainingRepo) -> None:
    repo.add("A.")
    repo.add("B.")
    repo.add("C.")
    one = repo.get_for_profile(limit=1)
    assert len(one) == 1
    assert one[0] == "C."
    two = repo.get_for_profile(limit=2)
    assert len(two) == 2
    assert "C." in two and "B." in two


def test_list_all_order_ascending(repo: TrainingRepo) -> None:
    repo.add("First.")
    repo.add("Second.")
    rows = repo.list_all()
    assert rows[0][1] == "First."
    assert rows[1][1] == "Second."


def test_training_facts_profile_limit_constant() -> None:
    assert TRAINING_FACTS_PROFILE_LIMIT == 100
    assert isinstance(TRAINING_FACTS_PROFILE_LIMIT, int)


def test_get_for_profile_empty_returns_list(repo: TrainingRepo) -> None:
    facts = repo.get_for_profile(limit=10)
    assert facts == []
    assert isinstance(facts, list)


def test_delete_nonexistent_id_no_error(repo: TrainingRepo) -> None:
    repo.add("Only.")
    repo.delete(99999)
    rows = repo.list_all()
    assert len(rows) == 1
    assert rows[0][1] == "Only."


def test_add_strips_whitespace(repo: TrainingRepo) -> None:
    uid = repo.add("  stripped  ")
    rows = repo.list_all()
    assert len(rows) == 1
    assert rows[0][1] == "stripped"
    assert rows[0][0] == uid
