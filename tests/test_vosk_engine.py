"""Tests for modules.speech.stt.vosk_engine: transcribe_with_confidence returns (text, None)."""

from __future__ import annotations

from unittest.mock import patch

from modules.speech.stt.vosk_engine import VoskEngine


def test_vosk_engine_transcribe_with_confidence_no_model_returns_empty_none() -> None:
    engine = VoskEngine(model_path="/nonexistent")
    engine._model = None
    text, confidence = engine.transcribe_with_confidence(b"\x00\x00" * 1000)
    assert text == ""
    assert confidence is None


def test_vosk_engine_transcribe_with_confidence_delegates_to_transcribe() -> None:
    engine = VoskEngine(model_path="/nonexistent")
    with patch.object(engine, "transcribe", return_value="hello world"):
        text, confidence = engine.transcribe_with_confidence(b"\x00\x00" * 8000)
    assert text == "hello world"
    assert confidence is None
