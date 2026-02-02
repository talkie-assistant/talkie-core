"""Tests for modules.speech.stt.whisper_engine: config, segment filtering, transcribe_with_confidence."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from modules.speech.stt.whisper_engine import WhisperEngine


def _segment(text: str, no_speech_prob: float = 0.0, avg_logprob: float = -0.2):
    return SimpleNamespace(
        text=text,
        no_speech_prob=no_speech_prob,
        avg_logprob=avg_logprob,
    )


def test_whisper_engine_init_no_speech_threshold_from_config() -> None:
    engine = WhisperEngine(config={"no_speech_threshold": 0.6})
    assert engine._no_speech_threshold == 0.6


def test_whisper_engine_init_no_speech_threshold_invalid_clamped() -> None:
    engine = WhisperEngine(config={"no_speech_threshold": 1.5})
    assert engine._no_speech_threshold == 0.6
    engine2 = WhisperEngine(config={"no_speech_threshold": -0.1})
    assert engine2._no_speech_threshold == 0.6


def test_whisper_engine_init_min_avg_logprob_from_config() -> None:
    engine = WhisperEngine(config={"min_avg_logprob": -1.0})
    assert engine._min_avg_logprob == -1.0


def test_whisper_engine_init_min_avg_logprob_none_when_not_set() -> None:
    engine = WhisperEngine(config={})
    assert engine._no_speech_threshold is None
    assert engine._min_avg_logprob is None


def test_whisper_engine_transcribe_empty_bytes_returns_empty() -> None:
    engine = WhisperEngine(config={})
    assert engine.transcribe(b"") == ""
    engine._model = MagicMock()
    assert engine.transcribe(b"") == ""


def test_whisper_engine_transcribe_no_model_returns_empty() -> None:
    engine = WhisperEngine(config={})
    engine._model = None
    assert engine.transcribe(b"\x00\x00" * 100) == ""


def test_whisper_engine_transcribe_filters_no_speech_segments() -> None:
    engine = WhisperEngine(config={"no_speech_threshold": 0.6})
    engine._model = MagicMock()
    segments = [
        _segment("hello", no_speech_prob=0.2, avg_logprob=-0.1),
        _segment("world", no_speech_prob=0.9, avg_logprob=-0.1),
    ]
    engine._model.transcribe.return_value = (iter(segments), None)

    audio = b"\x00\x00" * 8000
    result = engine.transcribe(audio)
    assert "hello" in result
    assert "world" not in result


def test_whisper_engine_transcribe_filters_low_avg_logprob_when_configured() -> None:
    engine = WhisperEngine(config={"min_avg_logprob": -0.5})
    engine._model = MagicMock()
    segments = [
        _segment("good", no_speech_prob=0.0, avg_logprob=-0.2),
        _segment("bad", no_speech_prob=0.0, avg_logprob=-1.5),
    ]
    engine._model.transcribe.return_value = (iter(segments), None)

    audio = b"\x00\x00" * 8000
    result = engine.transcribe(audio)
    assert "good" in result
    assert "bad" not in result


def test_whisper_engine_transcribe_with_confidence_returns_tuple() -> None:
    engine = WhisperEngine(config={})
    engine._model = MagicMock()
    segments = [
        _segment("hi", no_speech_prob=0.1, avg_logprob=-0.1),
        _segment("there", no_speech_prob=0.2, avg_logprob=-0.1),
    ]
    engine._model.transcribe.return_value = (iter(segments), None)

    audio = b"\x00\x00" * 8000
    text, confidence = engine.transcribe_with_confidence(audio)
    assert text == "hi there"
    assert confidence is not None
    assert 0 <= confidence <= 1
    assert abs(confidence - (0.9 + 0.8) / 2) < 0.01


def test_whisper_engine_transcribe_with_confidence_no_segments_returns_none_conf() -> (
    None
):
    engine = WhisperEngine(config={"no_speech_threshold": 0.5})
    engine._model = MagicMock()
    segments = [
        _segment("silence", no_speech_prob=0.99, avg_logprob=-0.1),
    ]
    engine._model.transcribe.return_value = (iter(segments), None)

    audio = b"\x00\x00" * 8000
    text, confidence = engine.transcribe_with_confidence(audio)
    assert text == ""
    assert confidence is None


def test_whisper_engine_transcribe_with_confidence_empty_bytes() -> None:
    engine = WhisperEngine(config={})
    assert engine.transcribe_with_confidence(b"") == ("", None)


def test_whisper_engine_transcribe_with_confidence_no_model() -> None:
    engine = WhisperEngine(config={})
    engine._model = None
    assert engine.transcribe_with_confidence(b"\x00\x00" * 100) == ("", None)
