"""Tests for persistence.settings_repo."""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from persistence.settings_repo import SettingsRepo, USER_CONTEXT_MAX_CHARS


@pytest.fixture
def db_path() -> Path:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = Path(f.name)
    yield path
    path.unlink(missing_ok=True)


@pytest.fixture
def repo(db_path: Path) -> SettingsRepo:
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "CREATE TABLE user_settings (key TEXT PRIMARY KEY, value TEXT)"
        )
    return SettingsRepo(lambda: sqlite3.connect(str(db_path)))


def test_get_missing_returns_none(repo: SettingsRepo) -> None:
    assert repo.get("user_context") is None
    assert repo.get("other") is None


def test_set_then_get(repo: SettingsRepo) -> None:
    repo.set("user_context", "PhD at Brown.")
    assert repo.get("user_context") == "PhD at Brown."


def test_set_overwrites(repo: SettingsRepo) -> None:
    repo.set("user_context", "First.")
    repo.set("user_context", "Second.")
    assert repo.get("user_context") == "Second."


def test_user_context_truncated(repo: SettingsRepo) -> None:
    long_val = "x" * (USER_CONTEXT_MAX_CHARS + 500)
    repo.set("user_context", long_val)
    got = repo.get("user_context")
    assert got is not None
    assert len(got) == USER_CONTEXT_MAX_CHARS


def test_set_many_then_get(repo: SettingsRepo) -> None:
    repo.set_many([
        ("calibration_sensitivity", "2.5"),
        ("calibration_chunk_duration_sec", "7.0"),
        ("tts_voice", "Samantha"),
    ])
    assert repo.get("calibration_sensitivity") == "2.5"
    assert repo.get("calibration_chunk_duration_sec") == "7.0"
    assert repo.get("tts_voice") == "Samantha"


def test_delete_removes_key(repo: SettingsRepo) -> None:
    repo.set("calibration_sensitivity", "2.0")
    assert repo.get("calibration_sensitivity") == "2.0"
    repo.delete("calibration_sensitivity")
    assert repo.get("calibration_sensitivity") is None


def test_delete_missing_key_no_error(repo: SettingsRepo) -> None:
    repo.delete("nonexistent_key")


def test_delete_many_removes_all(repo: SettingsRepo) -> None:
    repo.set_many([
        ("calibration_sensitivity", "1.5"),
        ("calibration_chunk_duration_sec", "8.0"),
    ])
    repo.delete_many(["calibration_sensitivity", "calibration_chunk_duration_sec"])
    assert repo.get("calibration_sensitivity") is None
    assert repo.get("calibration_chunk_duration_sec") is None
