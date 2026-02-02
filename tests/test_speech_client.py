"""Tests for modules.api.speech_client: RemoteSTTEngine transcribe and transcribe_with_confidence."""

from __future__ import annotations

from unittest.mock import MagicMock

from modules.api.speech_client import RemoteSTTEngine


def test_remote_stt_transcribe_returns_text_from_api() -> None:
    client = MagicMock()
    client._encode_audio.return_value = "base64abc"
    client._request.return_value = {"text": "hello from server"}

    engine = RemoteSTTEngine(client)
    assert engine.transcribe(b"\x00\x00" * 100) == "hello from server"
    client._request.assert_called_once()


def test_remote_stt_transcribe_with_confidence_returns_text_and_confidence() -> None:
    client = MagicMock()
    client._encode_audio.return_value = "base64abc"
    client._request.return_value = {"text": "hello", "confidence": 0.92}

    engine = RemoteSTTEngine(client)
    text, conf = engine.transcribe_with_confidence(b"\x00\x00" * 100)
    assert text == "hello"
    assert conf == 0.92


def test_remote_stt_transcribe_with_confidence_no_confidence_in_response() -> None:
    client = MagicMock()
    client._encode_audio.return_value = "base64abc"
    client._request.return_value = {"text": "hello"}

    engine = RemoteSTTEngine(client)
    text, conf = engine.transcribe_with_confidence(b"\x00\x00" * 100)
    assert text == "hello"
    assert conf is None


def test_remote_stt_transcribe_with_confidence_clamps_above_one() -> None:
    client = MagicMock()
    client._encode_audio.return_value = "base64abc"
    client._request.return_value = {"text": "hi", "confidence": 1.5}

    engine = RemoteSTTEngine(client)
    text, conf = engine.transcribe_with_confidence(b"\x00\x00" * 100)
    assert text == "hi"
    assert conf == 1.0


def test_remote_stt_transcribe_with_confidence_clamps_below_zero() -> None:
    client = MagicMock()
    client._encode_audio.return_value = "base64abc"
    client._request.return_value = {"text": "hi", "confidence": -0.1}

    engine = RemoteSTTEngine(client)
    text, conf = engine.transcribe_with_confidence(b"\x00\x00" * 100)
    assert text == "hi"
    assert conf == 0.0


def test_remote_stt_transcribe_with_confidence_invalid_confidence_returns_none() -> (
    None
):
    client = MagicMock()
    client._encode_audio.return_value = "base64abc"
    client._request.return_value = {"text": "hi", "confidence": "high"}

    engine = RemoteSTTEngine(client)
    text, conf = engine.transcribe_with_confidence(b"\x00\x00" * 100)
    assert text == "hi"
    assert conf is None


def test_remote_stt_transcribe_with_confidence_on_error_returns_empty_none() -> None:
    client = MagicMock()
    client._encode_audio.return_value = "base64abc"
    client._request.side_effect = ConnectionError("network error")

    engine = RemoteSTTEngine(client)
    text, conf = engine.transcribe_with_confidence(b"\x00\x00" * 100)
    assert text == ""
    assert conf is None
