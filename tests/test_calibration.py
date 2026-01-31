"""Tests for calibration: mapping, persistence, and create_pipeline overlay."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock


from modules.speech.calibration.constants import (
    CALIBRATION_STEPS,
    CHUNK_DURATION_MAX,
    CHUNK_DURATION_MIN,
    PAUSE_CHOICES,
    SENSITIVITY_MAX,
    SENSITIVITY_MIN,
    VOLUME_CHOICES,
)
from modules.speech.calibration.voice_profile import (
    VOICE_ENROLLMENT_MIN_SEC,
    clear_voice_profile,
    get_similarity_threshold,
    is_voice_profile_available,
    load_embedding,
)


def test_volume_choices_in_sensitivity_range() -> None:
    """Each volume choice maps to a value within allowed sensitivity range."""
    for _label, value in VOLUME_CHOICES:
        assert SENSITIVITY_MIN <= value <= SENSITIVITY_MAX


def test_volume_choices_count_and_ordering() -> None:
    """Volume choices are non-empty and sensitivity increases with quieter labels."""
    assert len(VOLUME_CHOICES) >= 1
    values = [v for _l, v in VOLUME_CHOICES]
    assert all(isinstance(v, (int, float)) for v in values)
    assert values == sorted(values, reverse=False)


def test_pause_choices_in_chunk_duration_range() -> None:
    """Each pause choice maps to a value within allowed chunk_duration range."""
    for _label, value in PAUSE_CHOICES:
        assert CHUNK_DURATION_MIN <= value <= CHUNK_DURATION_MAX


def test_pause_choices_count_and_ordering() -> None:
    """Pause choices are non-empty and chunk_duration increases with more pausing."""
    assert len(PAUSE_CHOICES) >= 1
    values = [v for _l, v in PAUSE_CHOICES]
    assert all(isinstance(v, (int, float)) for v in values)
    assert values == sorted(values, reverse=False)


def test_apply_calibration_overlay_uses_repo_values() -> None:
    """Overlay applies calibration_sensitivity and calibration_chunk_duration_sec from repo."""
    from modules.speech import apply_calibration_overlay

    repo = MagicMock()
    repo.get = lambda k: {
        "calibration_sensitivity": "3.0",
        "calibration_chunk_duration_sec": "9.0",
    }.get(k)
    audio_cfg = {"sensitivity": 2.5, "chunk_duration_sec": 7.0}
    out = apply_calibration_overlay(audio_cfg, repo)
    assert out["sensitivity"] == 3.0
    assert out["chunk_duration_sec"] == 9.0
    assert out is not audio_cfg
    assert set(out.keys()) == set(audio_cfg.keys())
    assert isinstance(out["sensitivity"], float)
    assert isinstance(out["chunk_duration_sec"], float)


def test_apply_calibration_overlay_clamps_values() -> None:
    """Overlay clamps sensitivity and chunk_duration to valid ranges."""
    from modules.speech import apply_calibration_overlay

    repo = MagicMock()
    repo.get = lambda k: {
        "calibration_sensitivity": "100",
        "calibration_chunk_duration_sec": "1.0",
    }.get(k)
    audio_cfg = {"sensitivity": 2.5, "chunk_duration_sec": 7.0}
    out = apply_calibration_overlay(audio_cfg, repo)
    assert out["sensitivity"] == 10.0
    assert out["chunk_duration_sec"] == 4.0
    assert out["sensitivity"] == SENSITIVITY_MAX
    assert out["chunk_duration_sec"] == CHUNK_DURATION_MIN


def test_apply_calibration_overlay_missing_keys_unchanged() -> None:
    """Missing or empty repo keys leave config unchanged."""
    from modules.speech import apply_calibration_overlay

    repo = MagicMock()
    repo.get = lambda k: None
    audio_cfg = {"sensitivity": 2.5, "chunk_duration_sec": 7.0}
    out = apply_calibration_overlay(audio_cfg, repo)
    assert out["sensitivity"] == 2.5
    assert out["chunk_duration_sec"] == 7.0
    assert out == audio_cfg
    assert out is not audio_cfg


def test_apply_calibration_overlay_none_repo_returns_copy() -> None:
    """None repo returns copy of config."""
    from modules.speech import apply_calibration_overlay

    audio_cfg = {"sensitivity": 2.5, "chunk_duration_sec": 7.0}
    out = apply_calibration_overlay(audio_cfg, None)
    assert out == audio_cfg
    assert out is not audio_cfg
    assert isinstance(out, dict)
    assert len(out) == len(audio_cfg)
    out["sensitivity"] = 999.0
    assert audio_cfg["sensitivity"] == 2.5


def test_apply_llm_calibration_overlay_uses_repo_value() -> None:
    """Overlay applies calibration_min_transcription_length from repo."""
    from modules.speech import apply_llm_calibration_overlay

    repo = MagicMock()
    repo.get = lambda k: "5" if k == "calibration_min_transcription_length" else None
    llm_cfg = {"min_transcription_length": 3}
    out = apply_llm_calibration_overlay(llm_cfg, repo)
    assert out["min_transcription_length"] == 5
    assert out is not llm_cfg
    assert isinstance(out["min_transcription_length"], int)


def test_apply_llm_calibration_overlay_clamps_non_negative() -> None:
    """Overlay clamps min_transcription_length to >= 0."""
    from modules.speech import apply_llm_calibration_overlay

    repo = MagicMock()
    repo.get = lambda k: "-1" if k == "calibration_min_transcription_length" else None
    llm_cfg = {"min_transcription_length": 3}
    out = apply_llm_calibration_overlay(llm_cfg, repo)
    assert out["min_transcription_length"] == 0
    assert isinstance(out["min_transcription_length"], int)
    assert out["min_transcription_length"] >= 0


def test_apply_llm_calibration_overlay_invalid_falls_back() -> None:
    """Invalid or missing repo value leaves config unchanged."""
    from modules.speech import apply_llm_calibration_overlay

    repo = MagicMock()
    repo.get = (
        lambda k: "not_a_number"
        if k == "calibration_min_transcription_length"
        else None
    )
    llm_cfg = {"min_transcription_length": 3}
    out = apply_llm_calibration_overlay(llm_cfg, repo)
    assert out["min_transcription_length"] == 3
    assert out == llm_cfg
    assert out is not llm_cfg


def test_apply_llm_calibration_overlay_none_repo_returns_copy() -> None:
    """None repo returns copy of llm config."""
    from modules.speech import apply_llm_calibration_overlay

    llm_cfg = {"min_transcription_length": 3}
    out = apply_llm_calibration_overlay(llm_cfg, None)
    assert out == llm_cfg
    assert out is not llm_cfg
    out["min_transcription_length"] = 99
    assert llm_cfg["min_transcription_length"] == 3


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

        def conn_factory():
            return sqlite3.connect(str(db_path))

        history_repo = HistoryRepo(conn_factory)
        settings_repo = SettingsRepo(conn_factory)
        settings_repo.set_many([("calibration_sensitivity", "2.0")])
        training_repo = TrainingRepo(conn_factory)

        config = {
            "audio": {
                "sensitivity": 2.5,
                "chunk_duration_sec": 7.0,
                "sample_rate": 16000,
            },
            "stt": {
                "engine": "vosk",
                "vosk": {"model_path": "models/vosk-model-small-en-us-0.15"},
            },
            "ollama": {"base_url": "http://localhost:11434", "model_name": "mistral"},
            "profile": {},
            "tts": {"enabled": False},
            "llm": {"min_transcription_length": 3},
        }
        from config import AppConfig

        app_config = AppConfig(config)
        pipeline = create_pipeline(
            app_config, history_repo, settings_repo, training_repo
        )
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

        def conn_factory():
            return sqlite3.connect(str(db_path))

        history_repo = HistoryRepo(conn_factory)
        settings_repo = SettingsRepo(conn_factory)
        settings_repo.set_many([("calibration_min_transcription_length", "7")])
        training_repo = TrainingRepo(conn_factory)

        config = {
            "audio": {
                "sensitivity": 2.5,
                "chunk_duration_sec": 7.0,
                "sample_rate": 16000,
            },
            "stt": {
                "engine": "vosk",
                "vosk": {"model_path": "models/vosk-model-small-en-us-0.15"},
            },
            "ollama": {"base_url": "http://localhost:11434", "model_name": "mistral"},
            "profile": {},
            "tts": {"enabled": False},
            "llm": {"min_transcription_length": 3},
        }
        from config import AppConfig

        app_config = AppConfig(config)
        pipeline = create_pipeline(
            app_config, history_repo, settings_repo, training_repo
        )
        assert pipeline._llm_prompt_config.get("min_transcription_length") == 7
    finally:
        db_path.unlink(missing_ok=True)


def test_analyze_recording_rule_based_sensitivity() -> None:
    """analyze_recording suggests higher sensitivity for quieter RMS."""
    from modules.speech.calibration import analyze_recording

    # Dummy 0.1s of audio (16000 * 0.1 * 2 bytes)
    silent = b"\x00\x00" * 800
    rms_quiet = [0.01] * 20
    rms_loud = [0.15] * 20
    out_quiet = analyze_recording(silent, 16000, rms_quiet)
    out_loud = analyze_recording(silent, 16000, rms_loud)
    assert out_quiet["sensitivity"] >= out_loud["sensitivity"]
    assert SENSITIVITY_MIN <= out_quiet["sensitivity"] <= SENSITIVITY_MAX
    assert SENSITIVITY_MIN <= out_loud["sensitivity"] <= SENSITIVITY_MAX
    assert CHUNK_DURATION_MIN <= out_quiet["chunk_duration_sec"] <= CHUNK_DURATION_MAX
    assert 0 <= out_quiet["min_transcription_length"] <= 10
    assert isinstance(out_quiet["sensitivity"], (int, float))
    assert isinstance(out_quiet["chunk_duration_sec"], (int, float))
    assert isinstance(out_quiet["min_transcription_length"], int)


def test_analyze_recording_return_shape() -> None:
    """analyze_recording returns dict with required keys and no transcript when no STT."""
    from modules.speech.calibration import analyze_recording

    silent = b"\x00\x00" * 800
    rms = [0.05] * 10
    out = analyze_recording(silent, 16000, rms)
    assert isinstance(out, dict)
    assert "sensitivity" in out
    assert "chunk_duration_sec" in out
    assert "min_transcription_length" in out
    assert out["sensitivity"] == round(out["sensitivity"], 1)
    assert out["chunk_duration_sec"] == round(out["chunk_duration_sec"], 1)


def test_analyze_recording_empty_rms_defaults() -> None:
    """Empty RMS list yields default sensitivity in range."""
    from modules.speech.calibration import analyze_recording

    out = analyze_recording(b"", 16000, [])
    assert "sensitivity" in out
    assert SENSITIVITY_MIN <= out["sensitivity"] <= SENSITIVITY_MAX
    assert CHUNK_DURATION_MIN <= out["chunk_duration_sec"] <= CHUNK_DURATION_MAX
    assert 0 <= out["min_transcription_length"] <= 10


def test_apply_calibration_overlay_whitespace_only_repo_value_unchanged() -> None:
    """Repo value that is only whitespace leaves config unchanged."""
    from modules.speech import apply_calibration_overlay

    repo = MagicMock()
    repo.get = lambda k: "   " if k == "calibration_sensitivity" else None
    audio_cfg = {"sensitivity": 2.5, "chunk_duration_sec": 7.0}
    out = apply_calibration_overlay(audio_cfg, repo)
    assert out["sensitivity"] == 2.5
    assert out["chunk_duration_sec"] == 7.0


def test_apply_llm_calibration_overlay_empty_string_unchanged() -> None:
    """Repo value empty string leaves min_transcription_length unchanged."""
    from modules.speech import apply_llm_calibration_overlay

    repo = MagicMock()
    repo.get = lambda k: "" if k == "calibration_min_transcription_length" else None
    llm_cfg = {"min_transcription_length": 4}
    out = apply_llm_calibration_overlay(llm_cfg, repo)
    assert out["min_transcription_length"] == 4


def test_calibration_steps_include_voice_enrollment() -> None:
    """Calibration steps list includes voice enrollment as first step."""
    assert len(CALIBRATION_STEPS) >= 1
    first = CALIBRATION_STEPS[0]
    assert first.get("id") == "voice_enrollment"
    assert (
        "voice" in (first.get("title") or "").lower()
        or "record" in (first.get("title") or "").lower()
    )
    assert first.get("min_seconds", 0) >= VOICE_ENROLLMENT_MIN_SEC


def test_voice_profile_load_embedding_none_when_missing() -> None:
    """load_embedding returns None when settings have no profile."""
    repo = MagicMock()
    repo.get = lambda k: None
    assert load_embedding(repo) is None


def test_voice_profile_is_available_false_when_no_embedding() -> None:
    """is_voice_profile_available is False when no embedding stored."""
    repo = MagicMock()
    repo.get = lambda k: None
    assert is_voice_profile_available(repo) is False


def test_voice_profile_is_available_true_when_embedding_stored() -> None:
    """is_voice_profile_available is True when valid embedding list stored (10+ elements)."""
    repo = MagicMock()
    # load_embedding requires list of at least 10 elements
    repo.get = (
        lambda k: "[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]"
        if k == "voice_profile_embedding"
        else None
    )
    assert is_voice_profile_available(repo) is True


def test_voice_profile_enroll_too_short_audio_fails() -> None:
    """enroll_user_voice returns False when audio is shorter than min duration."""
    from modules.speech.calibration.voice_profile import enroll_user_voice

    # 1 second at 16kHz mono int16 = 32000 bytes
    short = b"\x00\x00" * 8000
    repo = MagicMock()
    success, msg = enroll_user_voice(short, 16000, repo)
    assert success is False
    assert "second" in msg.lower() or "duration" in msg.lower() or "3" in msg


def test_voice_profile_get_similarity_threshold_default() -> None:
    """get_similarity_threshold returns default when key missing."""
    repo = MagicMock()
    repo.get = lambda k: None
    assert get_similarity_threshold(repo) == 0.62


def test_voice_profile_clear_calls_delete() -> None:
    """clear_voice_profile deletes the embedding key."""
    repo = MagicMock()
    clear_voice_profile(repo)
    repo.delete.assert_called_once()
    assert "voice" in repo.delete.call_args[0][0].lower()
