"""Tests for calibration: mapping, persistence, and create_pipeline overlay."""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ui.calibration_dialog import (
    CHUNK_DURATION_MAX,
    CHUNK_DURATION_MIN,
    PAUSE_CHOICES,
    SENSITIVITY_MAX,
    SENSITIVITY_MIN,
    VOLUME_CHOICES,
)


def test_volume_choices_in_sensitivity_range() -> None:
    """Each volume choice maps to a value within allowed sensitivity range."""
    for _label, value in VOLUME_CHOICES:
        assert SENSITIVITY_MIN <= value <= SENSITIVITY_MAX


def test_pause_choices_in_chunk_duration_range() -> None:
    """Each pause choice maps to a value within allowed chunk_duration range."""
    for _label, value in PAUSE_CHOICES:
        assert CHUNK_DURATION_MIN <= value <= CHUNK_DURATION_MAX


def test_apply_calibration_overlay_uses_repo_values() -> None:
    """Overlay applies calibration_sensitivity and calibration_chunk_duration_sec from repo."""
    from app.pipeline import _apply_calibration_overlay

    repo = MagicMock()
    repo.get = lambda k: {"calibration_sensitivity": "3.0", "calibration_chunk_duration_sec": "9.0"}.get(k)
    audio_cfg = {"sensitivity": 2.5, "chunk_duration_sec": 7.0}
    out = _apply_calibration_overlay(audio_cfg, repo)
    assert out["sensitivity"] == 3.0
    assert out["chunk_duration_sec"] == 9.0


def test_apply_calibration_overlay_clamps_values() -> None:
    """Overlay clamps sensitivity and chunk_duration to valid ranges."""
    from app.pipeline import _apply_calibration_overlay

    repo = MagicMock()
    repo.get = lambda k: {"calibration_sensitivity": "100", "calibration_chunk_duration_sec": "1.0"}.get(k)
    audio_cfg = {"sensitivity": 2.5, "chunk_duration_sec": 7.0}
    out = _apply_calibration_overlay(audio_cfg, repo)
    assert out["sensitivity"] == 10.0
    assert out["chunk_duration_sec"] == 4.0


def test_apply_calibration_overlay_missing_keys_unchanged() -> None:
    """Missing or empty repo keys leave config unchanged."""
    from app.pipeline import _apply_calibration_overlay

    repo = MagicMock()
    repo.get = lambda k: None
    audio_cfg = {"sensitivity": 2.5, "chunk_duration_sec": 7.0}
    out = _apply_calibration_overlay(audio_cfg, repo)
    assert out["sensitivity"] == 2.5
    assert out["chunk_duration_sec"] == 7.0


def test_apply_calibration_overlay_none_repo_returns_copy() -> None:
    """None repo returns copy of config."""
    from app.pipeline import _apply_calibration_overlay

    audio_cfg = {"sensitivity": 2.5, "chunk_duration_sec": 7.0}
    out = _apply_calibration_overlay(audio_cfg, None)
    assert out == audio_cfg
    assert out is not audio_cfg


def test_apply_llm_calibration_overlay_uses_repo_value() -> None:
    """Overlay applies calibration_min_transcription_length from repo."""
    from app.pipeline import _apply_llm_calibration_overlay

    repo = MagicMock()
    repo.get = lambda k: "5" if k == "calibration_min_transcription_length" else None
    llm_cfg = {"min_transcription_length": 3}
    out = _apply_llm_calibration_overlay(llm_cfg, repo)
    assert out["min_transcription_length"] == 5


def test_apply_llm_calibration_overlay_clamps_non_negative() -> None:
    """Overlay clamps min_transcription_length to >= 0."""
    from app.pipeline import _apply_llm_calibration_overlay

    repo = MagicMock()
    repo.get = lambda k: "-1" if k == "calibration_min_transcription_length" else None
    llm_cfg = {"min_transcription_length": 3}
    out = _apply_llm_calibration_overlay(llm_cfg, repo)
    assert out["min_transcription_length"] == 0


def test_apply_llm_calibration_overlay_invalid_falls_back() -> None:
    """Invalid or missing repo value leaves config unchanged."""
    from app.pipeline import _apply_llm_calibration_overlay

    repo = MagicMock()
    repo.get = lambda k: "not_a_number" if k == "calibration_min_transcription_length" else None
    llm_cfg = {"min_transcription_length": 3}
    out = _apply_llm_calibration_overlay(llm_cfg, repo)
    assert out["min_transcription_length"] == 3


def test_apply_llm_calibration_overlay_none_repo_returns_copy() -> None:
    """None repo returns copy of llm config."""
    from app.pipeline import _apply_llm_calibration_overlay

    llm_cfg = {"min_transcription_length": 3}
    out = _apply_llm_calibration_overlay(llm_cfg, None)
    assert out == llm_cfg
    assert out is not llm_cfg


def test_create_pipeline_uses_calibration_sensitivity() -> None:
    """create_pipeline overlays calibration_sensitivity so pipeline capture has it."""
    from persistence.database import init_database
    from app.pipeline import create_pipeline
    from persistence.history_repo import HistoryRepo
    from persistence.settings_repo import SettingsRepo
    from persistence.training_repo import TrainingRepo

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        init_database(str(db_path))
        conn_factory = lambda: sqlite3.connect(str(db_path))
        history_repo = HistoryRepo(conn_factory)
        settings_repo = SettingsRepo(conn_factory)
        settings_repo.set_many([("calibration_sensitivity", "2.0")])
        training_repo = TrainingRepo(conn_factory)

        config = {
            "audio": {"sensitivity": 2.5, "chunk_duration_sec": 7.0, "sample_rate": 16000},
            "stt": {"engine": "vosk", "vosk": {"model_path": "models/vosk-model-small-en-us-0.15"}},
            "ollama": {"base_url": "http://localhost:11434", "model_name": "mistral"},
            "profile": {},
            "tts": {"enabled": False},
            "llm": {"min_transcription_length": 3},
        }
        pipeline = create_pipeline(config, history_repo, settings_repo, training_repo)
        assert pipeline.get_sensitivity() == 2.0
    finally:
        db_path.unlink(missing_ok=True)


def test_create_pipeline_uses_calibration_min_transcription_length() -> None:
    """create_pipeline overlays calibration_min_transcription_length into llm_prompt_config."""
    from persistence.database import init_database
    from app.pipeline import create_pipeline
    from persistence.history_repo import HistoryRepo
    from persistence.settings_repo import SettingsRepo
    from persistence.training_repo import TrainingRepo

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        init_database(str(db_path))
        conn_factory = lambda: sqlite3.connect(str(db_path))
        history_repo = HistoryRepo(conn_factory)
        settings_repo = SettingsRepo(conn_factory)
        settings_repo.set_many([("calibration_min_transcription_length", "7")])
        training_repo = TrainingRepo(conn_factory)

        config = {
            "audio": {"sensitivity": 2.5, "chunk_duration_sec": 7.0, "sample_rate": 16000},
            "stt": {"engine": "vosk", "vosk": {"model_path": "models/vosk-model-small-en-us-0.15"}},
            "ollama": {"base_url": "http://localhost:11434", "model_name": "mistral"},
            "profile": {},
            "tts": {"enabled": False},
            "llm": {"min_transcription_length": 3},
        }
        pipeline = create_pipeline(config, history_repo, settings_repo, training_repo)
        assert pipeline._llm_prompt_config.get("min_transcription_length") == 7
    finally:
        db_path.unlink(missing_ok=True)


def test_analyze_recording_rule_based_sensitivity() -> None:
    """analyze_recording suggests higher sensitivity for quieter RMS."""
    from calibration.analyzer import analyze_recording

    # Dummy 0.1s of audio (16000 * 0.1 * 2 bytes)
    silent = b"\x00\x00" * 800
    rms_quiet = [0.01] * 20
    rms_loud = [0.15] * 20
    out_quiet = analyze_recording(silent, 16000, rms_quiet)
    out_loud = analyze_recording(silent, 16000, rms_loud)
    assert out_quiet["sensitivity"] >= out_loud["sensitivity"]
    assert 0.5 <= out_quiet["sensitivity"] <= 10.0
    assert 4.0 <= out_quiet["chunk_duration_sec"] <= 15.0
    assert 0 <= out_quiet["min_transcription_length"] <= 10
