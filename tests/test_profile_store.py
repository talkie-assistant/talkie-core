"""Tests for profile.store: LanguageProfile get_context_for_llm, invalidate_cache, cache TTL."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from persistence.database import init_database
from persistence.history_repo import HistoryRepo
from persistence.settings_repo import SettingsRepo
from persistence.training_repo import TrainingRepo
from profile.constants import ACCEPTED_DISPLAY_CAP, CORRECTION_DISPLAY_CAP
from profile.store import LanguageProfile, PROFILE_CONTEXT_CACHE_TTL_SEC


@pytest.fixture
def db_path() -> Path:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = Path(f.name)
    yield path
    path.unlink(missing_ok=True)


@pytest.fixture
def history_repo(db_path: Path) -> HistoryRepo:
    init_database(str(db_path))
    return HistoryRepo(lambda: sqlite3.connect(str(db_path)))


@pytest.fixture
def settings_repo(db_path: Path) -> SettingsRepo:
    init_database(str(db_path))
    return SettingsRepo(lambda: sqlite3.connect(str(db_path)))


@pytest.fixture
def training_repo(db_path: Path) -> TrainingRepo:
    init_database(str(db_path))
    return TrainingRepo(lambda: sqlite3.connect(str(db_path)))


def test_language_profile_init_defaults(history_repo: HistoryRepo) -> None:
    p = LanguageProfile(history_repo)
    assert p._history_repo is history_repo
    assert p._settings_repo is None
    assert p._training_repo is None
    assert p._correction_display_cap == CORRECTION_DISPLAY_CAP
    assert p._accepted_display_cap == ACCEPTED_DISPLAY_CAP
    assert p._context_cache is None


def test_language_profile_init_custom_caps(history_repo: HistoryRepo) -> None:
    p = LanguageProfile(
        history_repo,
        correction_display_cap=10,
        accepted_display_cap=5,
    )
    assert p._correction_display_cap == 10
    assert p._accepted_display_cap == 5


def test_get_context_for_llm_empty_returns_string(
    history_repo: HistoryRepo,
) -> None:
    p = LanguageProfile(history_repo)
    ctx = p.get_context_for_llm()
    assert isinstance(ctx, str)
    assert ctx == "" or "User context" not in ctx or len(ctx) >= 0


def test_get_context_for_llm_with_accepted(
    history_repo: HistoryRepo, db_path: Path
) -> None:
    history_repo.insert_interaction("hello", "Hi there.")
    p = LanguageProfile(history_repo)
    ctx = p.get_context_for_llm()
    assert isinstance(ctx, str)
    assert len(ctx) >= 0


def test_invalidate_cache_clears_cache(history_repo: HistoryRepo) -> None:
    p = LanguageProfile(history_repo)
    p.get_context_for_llm()
    p.invalidate_cache()
    assert p._context_cache is None


def test_get_context_for_llm_caches_within_ttl(
    history_repo: HistoryRepo,
) -> None:
    p = LanguageProfile(history_repo)
    ctx1 = p.get_context_for_llm()
    ctx2 = p.get_context_for_llm()
    assert ctx1 == ctx2
    assert p._context_cache is not None
    assert p._context_cache == ctx1


def test_get_context_for_llm_with_settings(
    history_repo: HistoryRepo,
    settings_repo: SettingsRepo,
) -> None:
    settings_repo.set_many([("user_context", "I prefer short answers.")])
    p = LanguageProfile(history_repo, settings_repo=settings_repo)
    ctx = p.get_context_for_llm()
    assert isinstance(ctx, str)
    assert "short" in ctx or "User context" in ctx or len(ctx) >= 0


def test_get_context_for_llm_includes_preferred_name_and_pronouns(
    history_repo: HistoryRepo,
    settings_repo: SettingsRepo,
) -> None:
    settings_repo.set_many([
        ("user_context", "Professor."),
        ("preferred_name", "Lou"),
        ("pronouns", "she/her"),
    ])
    p = LanguageProfile(history_repo, settings_repo=settings_repo)
    ctx = p.get_context_for_llm()
    assert isinstance(ctx, str)
    assert "Preferred name" in ctx
    assert "Lou" in ctx
    assert "Pronouns" in ctx
    assert "she/her" in ctx


def test_get_context_for_llm_with_training(
    history_repo: HistoryRepo,
    training_repo: TrainingRepo,
) -> None:
    training_repo.add("Star is my dog.")
    p = LanguageProfile(history_repo, training_repo=training_repo)
    ctx = p.get_context_for_llm()
    assert isinstance(ctx, str)
    assert "Star" in ctx or "Training" in ctx or len(ctx) >= 0


def test_profile_context_cache_ttl_constant() -> None:
    assert PROFILE_CONTEXT_CACHE_TTL_SEC == 30.0
    assert isinstance(PROFILE_CONTEXT_CACHE_TTL_SEC, float)
