"""Tests for SDK abstractions: NoOp* implementations, MicrophoneError."""

from __future__ import annotations

from sdk import (
    MicrophoneError,
    NoOpCapture,
    NoOpSpeakerFilter,
    NoOpSTTEngine,
    NoOpTTSEngine,
)


def test_microphone_error_is_exception() -> None:
    err = MicrophoneError("mic unavailable")
    assert isinstance(err, Exception)
    assert "mic unavailable" in str(err)
    assert err.args[0] == "mic unavailable"


def test_noop_capture_read_chunk_returns_none() -> None:
    cap = NoOpCapture()
    assert cap.read_chunk() is None
    assert cap.read_chunk(on_level=lambda x: None) is None
    assert isinstance(cap.read_chunk(), (type(None), bytes))
    cap.start()
    assert cap.read_chunk() is None
    cap.stop()
    assert cap.read_chunk() is None


def test_noop_capture_get_sensitivity_returns_one() -> None:
    cap = NoOpCapture()
    assert cap.get_sensitivity() == 1.0
    assert isinstance(cap.get_sensitivity(), float)


def test_noop_capture_set_sensitivity_no_op() -> None:
    cap = NoOpCapture()
    cap.set_sensitivity(0.5)
    cap.set_sensitivity(2.0)
    assert cap.get_sensitivity() == 1.0


def test_noop_stt_engine_transcribe_returns_empty() -> None:
    stt = NoOpSTTEngine()
    assert stt.transcribe(b"") == ""
    assert stt.transcribe(b"\x00\x00\x00\x00") == ""
    assert isinstance(stt.transcribe(b"x"), str)
    assert len(stt.transcribe(b"anything")) == 0


def test_noop_stt_engine_start_stop_no_op() -> None:
    stt = NoOpSTTEngine()
    stt.start()
    stt.stop()
    assert stt.transcribe(b"x") == ""


def test_noop_tts_engine_speak_no_op() -> None:
    tts = NoOpTTSEngine()
    tts.speak("Hello.")
    tts.speak("")
    tts.speak("   ")


def test_noop_tts_engine_wait_until_done_stop_no_op() -> None:
    tts = NoOpTTSEngine()
    tts.wait_until_done()
    tts.stop()


def test_noop_speaker_filter_accept_returns_true() -> None:
    f = NoOpSpeakerFilter()
    assert f.accept("hello") is True
    assert f.accept("") is True
    assert f.accept("x", audio_bytes=b"") is True
    assert f.accept("x", audio_bytes=None) is True
    assert isinstance(f.accept("any"), bool)
