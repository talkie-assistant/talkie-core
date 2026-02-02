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
        conn.execute("CREATE TABLE user_settings (key TEXT PRIMARY KEY, value TEXT)")
    return SettingsRepo(lambda: sqlite3.connect(str(db_path)))


def test_get_missing_returns_none(repo: SettingsRepo) -> None:
    assert repo.get("user_context") is None
    assert repo.get("other") is None
    assert repo.get("") is None
    assert repo.get("calibration_sensitivity") is None


def test_user_context_max_chars_constant_positive() -> None:
    assert USER_CONTEXT_MAX_CHARS > 0
    assert isinstance(USER_CONTEXT_MAX_CHARS, int)


def test_set_then_get(repo: SettingsRepo) -> None:
    repo.set("user_context", "PhD at Brown.")
    got = repo.get("user_context")
    assert got is not None
    assert got == "PhD at Brown."
    assert isinstance(got, str)


def test_set_overwrites(repo: SettingsRepo) -> None:
    repo.set("user_context", "First.")
    assert repo.get("user_context") == "First."
    repo.set("user_context", "Second.")
    assert repo.get("user_context") == "Second."
    assert repo.get("user_context") != "First."


def test_user_context_truncated(repo: SettingsRepo) -> None:
    long_val = "x" * (USER_CONTEXT_MAX_CHARS + 500)
    repo.set("user_context", long_val)
    got = repo.get("user_context")
    assert got is not None
    assert len(got) == USER_CONTEXT_MAX_CHARS
    assert got == "x" * USER_CONTEXT_MAX_CHARS
    assert got != long_val


def test_set_many_then_get(repo: SettingsRepo) -> None:
    repo.set_many(
        [
            ("calibration_sensitivity", "2.5"),
            ("calibration_chunk_duration_sec", "7.0"),
            ("tts_voice", "Samantha"),
        ]
    )
    assert repo.get("calibration_sensitivity") == "2.5"
    assert repo.get("calibration_chunk_duration_sec") == "7.0"
    assert repo.get("tts_voice") == "Samantha"
    assert repo.get("nonexistent") is None


def test_set_many_empty_list_no_op(repo: SettingsRepo) -> None:
    repo.set("key_a", "value_a")
    repo.set_many([])
    assert repo.get("key_a") == "value_a"


def test_set_empty_string_value(repo: SettingsRepo) -> None:
    repo.set("calibration_sensitivity", "")
    got = repo.get("calibration_sensitivity")
    assert got is not None
    assert got == ""


def test_set_unicode_value(repo: SettingsRepo) -> None:
    val = "Hello \u00e9 \u4e2d"
    repo.set("user_context", val)
    assert repo.get("user_context") == val
    assert "\u00e9" in repo.get("user_context")
    assert "\u4e2d" in repo.get("user_context")


def test_delete_removes_key(repo: SettingsRepo) -> None:
    repo.set("calibration_sensitivity", "2.0")
    assert repo.get("calibration_sensitivity") == "2.0"
    repo.delete("calibration_sensitivity")
    assert repo.get("calibration_sensitivity") is None
    repo.set("calibration_sensitivity", "3.0")
    assert repo.get("calibration_sensitivity") == "3.0"


def test_delete_missing_key_no_error(repo: SettingsRepo) -> None:
    repo.delete("nonexistent_key")
    repo.delete("")
    assert repo.get("nonexistent_key") is None


def test_delete_many_removes_all(repo: SettingsRepo) -> None:
    repo.set_many(
        [
            ("calibration_sensitivity", "1.5"),
            ("calibration_chunk_duration_sec", "8.0"),
        ]
    )
    repo.delete_many(["calibration_sensitivity", "calibration_chunk_duration_sec"])
    assert repo.get("calibration_sensitivity") is None
    assert repo.get("calibration_chunk_duration_sec") is None


def test_delete_many_empty_list_no_op(repo: SettingsRepo) -> None:
    repo.set("k", "v")
    repo.delete_many([])
    assert repo.get("k") == "v"


def test_set_many_overwrites_existing(repo: SettingsRepo) -> None:
    repo.set("tts_voice", "Daniel")
    repo.set_many([("tts_voice", "Samantha")])
    assert repo.get("tts_voice") == "Samantha"


def test_get_many_empty_keys_returns_empty_dict(repo: SettingsRepo) -> None:
    assert repo.get_many([]) == {}


def test_get_many_missing_key_returns_none(repo: SettingsRepo) -> None:
    result = repo.get_many(["missing"])
    assert result == {"missing": None}


def test_get_many_mixed_present_missing(repo: SettingsRepo) -> None:
    repo.set("a", "val_a")
    repo.set("c", "val_c")
    result = repo.get_many(["a", "b", "c"])
    assert result == {"a": "val_a", "b": None, "c": "val_c"}


def test_get_many_matches_individual_get(repo: SettingsRepo) -> None:
    repo.set_many([("k1", "v1"), ("k2", "v2"), ("k3", "v3")])
    many = repo.get_many(["k1", "k2", "k3"])
    assert many["k1"] == repo.get("k1")
    assert many["k2"] == repo.get("k2")
    assert many["k3"] == repo.get("k3")
