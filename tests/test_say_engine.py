"""Tests for modules.speech.tts.say_engine: SayEngine speak_timeout_sec, rate_wpm; get_rate_wpm."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from modules.speech.tts.say_engine import SayEngine, get_rate_wpm, TTS_RATE_WPM


def test_say_engine_init_default_timeout() -> None:
    engine = SayEngine(voice=None)
    assert engine._speak_timeout_sec == 300.0


def test_say_engine_init_custom_timeout() -> None:
    engine = SayEngine(voice="Daniel", speak_timeout_sec=60.0)
    assert engine._speak_timeout_sec == 60.0


def test_say_engine_init_timeout_clamped_min() -> None:
    engine = SayEngine(voice=None, speak_timeout_sec=0.5)
    assert engine._speak_timeout_sec == 1.0


def test_say_engine_init_timeout_clamped_max() -> None:
    engine = SayEngine(voice=None, speak_timeout_sec=5000.0)
    assert engine._speak_timeout_sec == 3600.0


def test_say_engine_init_rate_wpm_none() -> None:
    engine = SayEngine(voice=None, rate_wpm=None)
    assert engine._rate_wpm is None


def test_say_engine_init_rate_wpm_positive() -> None:
    engine = SayEngine(voice=None, rate_wpm=175)
    assert engine._rate_wpm == 175


def test_say_engine_init_rate_wpm_zero_stored_as_none() -> None:
    engine = SayEngine(voice=None, rate_wpm=0)
    assert engine._rate_wpm is None


def test_say_engine_init_rate_wpm_negative_stored_as_none() -> None:
    engine = SayEngine(voice=None, rate_wpm=-10)
    assert engine._rate_wpm is None


def test_say_engine_speak_includes_r_flag_when_rate_wpm_set() -> None:
    engine = SayEngine(voice=None, rate_wpm=175)
    with patch("modules.speech.tts.say_engine.subprocess.Popen", MagicMock()) as mock_popen:
        mock_popen.return_value.wait.return_value = 0
        engine._speak_sync("Hello")
    call_args = mock_popen.call_args[0][0]
    assert "-r" in call_args
    idx = call_args.index("-r")
    assert idx + 1 < len(call_args)
    assert call_args[idx + 1] == "175"


def test_say_engine_speak_no_r_flag_when_rate_wpm_none() -> None:
    engine = SayEngine(voice=None, rate_wpm=None)
    with patch("modules.speech.tts.say_engine.subprocess.Popen", MagicMock()) as mock_popen:
        mock_popen.return_value.wait.return_value = 0
        engine._speak_sync("Hello")
    call_args = mock_popen.call_args[0][0]
    assert "-r" not in call_args


def test_say_engine_speak_no_r_flag_when_rate_wpm_zero() -> None:
    engine = SayEngine(voice=None, rate_wpm=0)
    with patch("modules.speech.tts.say_engine.subprocess.Popen", MagicMock()) as mock_popen:
        mock_popen.return_value.wait.return_value = 0
        engine._speak_sync("Hello")
    call_args = mock_popen.call_args[0][0]
    assert "-r" not in call_args


def test_get_rate_wpm_valid() -> None:
    assert get_rate_wpm("slow") == TTS_RATE_WPM["slow"]
    assert get_rate_wpm("normal") == TTS_RATE_WPM["normal"]
    assert get_rate_wpm("fast") == TTS_RATE_WPM["fast"]
    assert get_rate_wpm("  normal  ") == 175


def test_get_rate_wpm_invalid_or_empty_returns_none() -> None:
    assert get_rate_wpm(None) is None
    assert get_rate_wpm("") is None
    assert get_rate_wpm("  ") is None
    assert get_rate_wpm("custom") is None
    assert get_rate_wpm("invalid") is None
