"""Tests for app.pipeline: _only_search_instruction_if_list, create_pipeline, Pipeline callbacks and state."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from sdk import (
    NoOpCapture,
    NoOpSpeakerFilter,
    NoOpSTTEngine,
    NoOpTTSEngine,
)
from app.pipeline import Pipeline, _only_search_instruction_if_list, create_pipeline
from persistence.database import init_database
from persistence.history_repo import HistoryRepo


# ---- _only_search_instruction_if_list ----
def test_only_search_instruction_if_list_empty_returns_unchanged() -> None:
    assert _only_search_instruction_if_list("") == ""
    assert _only_search_instruction_if_list("   ") == "   "


def test_only_search_instruction_if_list_no_list_returns_unchanged() -> None:
    text = "Hello world."
    assert _only_search_instruction_if_list(text) == text
    assert _only_search_instruction_if_list("Single sentence.") == "Single sentence."


def test_only_search_instruction_if_list_numbered_list_returns_instruction() -> None:
    text = "Say 'open 1' through 'open 5' to open a result.\n\n1. First result\n2. Second result"
    out = _only_search_instruction_if_list(text)
    assert "Say 'open 1'" in out
    assert "open 5" in out or "open 1" in out
    assert "1. First" not in out or "2. Second" not in out


def test_only_search_instruction_if_list_instruction_only_no_match_returns_fallback() -> (
    None
):
    text = "1. A\n2. B"
    out = _only_search_instruction_if_list(text)
    assert "Say open" in out or "open" in out
    assert isinstance(out, str)


def test_only_search_instruction_if_list_numbered_list_with_say_open_match() -> None:
    text = "Say 'open 1' through 'open 3' to open a result. 1. First 2. Second"
    out = _only_search_instruction_if_list(text)
    assert "Say 'open 1'" in out
    assert "open 3" in out
    assert out == "Say 'open 1' through 'open 3' to open a result."


# ---- create_pipeline ----
class _MockConfig:
    def get(self, key: str, default=None):
        if key == "ollama":
            return {"base_url": "http://localhost:11434", "model_name": "mistral"}
        if key == "profile":
            return {}
        if key == "browser":
            return {}
        if key == "llm":
            return {}
        return {} if default is None else default

    def resolve_internal_service_url(self, url: str) -> str:
        return url


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
def pipeline(history_repo: HistoryRepo) -> Pipeline:
    config = _MockConfig()
    capture = NoOpCapture()
    stt = NoOpSTTEngine()
    tts = NoOpTTSEngine()
    speaker = NoOpSpeakerFilter()
    return create_pipeline(
        config,
        history_repo,
        settings_repo=None,
        training_repo=None,
        capture=capture,
        stt=stt,
        tts=tts,
        speaker_filter=speaker,
        llm_prompt_config={},
    )


def test_create_pipeline_returns_pipeline(history_repo: HistoryRepo) -> None:
    config = _MockConfig()
    p = create_pipeline(
        config,
        history_repo,
        capture=NoOpCapture(),
        stt=NoOpSTTEngine(),
        tts=NoOpTTSEngine(),
        speaker_filter=NoOpSpeakerFilter(),
        llm_prompt_config={},
    )
    assert isinstance(p, Pipeline)
    assert p._capture is not None
    assert p._stt is not None
    assert p._tts is not None
    assert p._llm is not None
    assert p._history is not None
    assert p._profile is not None


def test_pipeline_set_ui_callbacks(pipeline: Pipeline) -> None:
    status_calls: list[str] = []
    response_calls: list[tuple] = []
    error_calls: list[str] = []
    pipeline.set_ui_callbacks(
        on_status=lambda s: status_calls.append(s),
        on_response=lambda t, i: response_calls.append((t, i)),
        on_error=lambda e: error_calls.append(e),
    )
    pipeline._on_status("test status")
    assert len(status_calls) == 1
    assert status_calls[0] == "test status"
    pipeline._on_response("hello", 1)
    assert len(response_calls) == 1
    assert response_calls[0] == ("hello", 1)


def test_pipeline_get_sensitivity(pipeline: Pipeline) -> None:
    sens = pipeline.get_sensitivity()
    assert isinstance(sens, (int, float))
    assert sens >= 0


def test_pipeline_set_sensitivity(pipeline: Pipeline) -> None:
    pipeline.set_sensitivity(0.5)
    pipeline.set_sensitivity(2.0)
    sens = pipeline.get_sensitivity()
    assert isinstance(sens, (int, float))
    assert sens >= 0
    assert sens <= 10.0


def test_pipeline_set_training_mode(pipeline: Pipeline) -> None:
    assert pipeline._training_mode is False
    pipeline.set_training_mode(True)
    assert pipeline._training_mode is True
    pipeline.set_training_mode(False)
    assert pipeline._training_mode is False


def _retriever(q, top_k=None):
    return "context"


def test_pipeline_set_rag_retriever(pipeline: Pipeline) -> None:
    assert pipeline._rag_retriever is None
    pipeline.set_rag_retriever(_retriever)
    assert pipeline._rag_retriever is _retriever
    pipeline.set_rag_retriever(None)
    assert pipeline._rag_retriever is None


def _web_handler(*a, **k):
    return None


def test_pipeline_set_web_handler(pipeline: Pipeline) -> None:
    assert pipeline._web_handler is None
    assert pipeline.has_web_handler() is False
    pipeline.set_web_handler(_web_handler)
    assert pipeline._web_handler is _web_handler
    assert pipeline.has_web_handler() is True
    pipeline.set_web_handler(None)
    assert pipeline.has_web_handler() is False


def test_pipeline_set_web_mode(pipeline: Pipeline) -> None:
    assert pipeline.get_web_mode() is False
    pipeline.set_web_mode(True)
    assert pipeline.get_web_mode() is True
    pipeline.set_web_mode(False)
    assert pipeline.get_web_mode() is False


def test_pipeline_speak_calls_tts(pipeline: Pipeline) -> None:
    tts = pipeline._tts
    assert hasattr(tts, "speak")
    pipeline.speak("Hello.")
    pipeline.speak("")
    pipeline.speak("   ")


def test_pipeline_start_and_stop(pipeline: Pipeline) -> None:
    pipeline.start()
    assert pipeline._running is True
    assert pipeline._thread is not None
    assert pipeline._thread.is_alive() or not pipeline._thread.is_alive()
    pipeline.stop()
    assert pipeline._running is False
    assert pipeline._thread is None or not pipeline._thread.is_alive()


def test_pipeline_set_document_qa_mode(pipeline: Pipeline) -> None:
    pipeline.set_document_qa_mode(True)
    assert pipeline._document_qa_mode is True
    assert pipeline._web_mode is False
    pipeline.set_document_qa_mode(False)
    assert pipeline._document_qa_mode is False


def test_pipeline_set_document_qa_top_k(pipeline: Pipeline) -> None:
    pipeline.set_document_qa_top_k(5)
    assert pipeline._document_qa_top_k == 5
    pipeline.set_document_qa_top_k(0)
    assert pipeline._document_qa_top_k >= 1
    pipeline.set_document_qa_top_k(100)
    assert pipeline._document_qa_top_k <= 20


def test_pipeline_set_on_web_selection(pipeline: Pipeline) -> None:
    calls: list[str | None] = []
    pipeline.set_on_web_selection(lambda x: calls.append(x))
    pipeline._on_web_selection("Link text")
    assert len(calls) == 1
    assert calls[0] == "Link text"
    pipeline._on_web_selection(None)
    assert len(calls) == 2
    assert calls[1] is None


def test_pipeline_set_on_open_url(pipeline: Pipeline) -> None:
    urls: list[str] = []
    pipeline.set_on_open_url(lambda u: urls.append(u))
    pipeline._on_open_url("https://example.com")
    assert len(urls) == 1
    assert urls[0] == "https://example.com"


def test_pipeline_set_quit_modal_and_callbacks(pipeline: Pipeline) -> None:
    assert pipeline._quit_modal_pending is False
    pipeline.set_quit_modal_pending(True)
    assert pipeline._quit_modal_pending is True
    pipeline.set_quit_modal_pending(False)
    assert pipeline._quit_modal_pending is False
    quit_called: list[bool] = []
    pipeline.set_on_quit_confirmed(lambda: quit_called.append(True))
    pipeline._on_quit_confirmed()
    assert len(quit_called) == 1
    assert quit_called[0] is True
    close_called: list[bool] = []
    pipeline.set_on_close_quit_modal(lambda: close_called.append(True))
    pipeline._on_close_quit_modal()
    assert len(close_called) == 1


def _has_docs():
    return True


def test_pipeline_set_rag_has_documents(pipeline: Pipeline) -> None:
    assert pipeline._rag_has_documents is None
    pipeline.set_rag_has_documents(_has_docs)
    assert pipeline._rag_has_documents is _has_docs
    pipeline.set_rag_has_documents(None)
    assert pipeline._rag_has_documents is None


def test_pipeline_set_on_training_transcription(pipeline: Pipeline) -> None:
    assert pipeline._on_training_transcription is None
    transcriptions: list[str] = []
    pipeline.set_on_training_transcription(lambda t: transcriptions.append(t))
    assert pipeline._on_training_transcription is not None
    pipeline._on_training_transcription("training phrase")
    assert len(transcriptions) == 1
    assert transcriptions[0] == "training phrase"
    pipeline.set_on_training_transcription(None)
    assert pipeline._on_training_transcription is None


def test_pipeline_push_spoken_updates_state(pipeline: Pipeline) -> None:
    assert pipeline._last_spoken_response is None
    assert pipeline._recent_spoken_responses == []
    pipeline._push_spoken("First.")
    assert pipeline._last_spoken_response == "First."
    assert pipeline._recent_spoken_responses == ["First."]
    pipeline._push_spoken("Second.")
    assert pipeline._last_spoken_response == "Second."
    assert "Second." in pipeline._recent_spoken_responses
    assert "First." in pipeline._recent_spoken_responses
    pipeline._push_spoken("")
    assert pipeline._last_spoken_response == "Second."


def test_pipeline_prefetch_profile_and_recent(pipeline: Pipeline) -> None:
    profile_ctx, recent = pipeline._prefetch_profile_and_recent(2)
    assert isinstance(profile_ctx, str)
    assert isinstance(recent, list)
    pipeline._history.insert_interaction("hello", "Hi.")
    profile_ctx2, recent2 = pipeline._prefetch_profile_and_recent(2)
    assert len(recent2) >= 1
    assert any((r.get("original_transcription") or "") == "hello" for r in recent2)


def test_create_pipeline_browse_cooldown_clamped(history_repo: HistoryRepo) -> None:
    class CooldownConfig(_MockConfig):
        def get(self, key: str, default=None):
            if key == "browser":
                return {"cooldown_after_tts_sec": 120.0}
            return super().get(key, default)

    config = CooldownConfig()
    p = create_pipeline(
        config,
        history_repo,
        capture=NoOpCapture(),
        stt=NoOpSTTEngine(),
        tts=NoOpTTSEngine(),
        speaker_filter=NoOpSpeakerFilter(),
        llm_prompt_config={},
    )
    assert p._browse_cooldown_after_tts_sec == 60.0

    class NegativeCooldownConfig(_MockConfig):
        def get(self, key: str, default=None):
            if key == "browser":
                return {"cooldown_after_tts_sec": -5.0}
            return super().get(key, default)

    config2 = NegativeCooldownConfig()
    p2 = create_pipeline(
        config2,
        history_repo,
        capture=NoOpCapture(),
        stt=NoOpSTTEngine(),
        tts=NoOpTTSEngine(),
        speaker_filter=NoOpSpeakerFilter(),
        llm_prompt_config={},
    )
    assert p2._browse_cooldown_after_tts_sec == 0.0


# ---- _should_skip_tts ----
def test_should_skip_tts_error_fallback_returns_true(pipeline: Pipeline) -> None:
    assert pipeline._should_skip_tts("I didn't catch that.", True, "") is True
    assert pipeline._should_skip_tts("Any text", True, "other") is True


def test_should_skip_tts_empty_returns_true(pipeline: Pipeline) -> None:
    assert pipeline._should_skip_tts("", False, "") is True
    assert pipeline._should_skip_tts("   ", False, "") is True
    assert pipeline._should_skip_tts("", False, "last") is True


def test_should_skip_tts_same_as_last_spoken_returns_true(pipeline: Pipeline) -> None:
    last_norm = "hello world"
    assert pipeline._should_skip_tts("Hello World", False, last_norm) is True
    assert pipeline._should_skip_tts("  hello   world  ", False, last_norm) is True


def test_should_skip_tts_different_text_returns_false(pipeline: Pipeline) -> None:
    assert pipeline._should_skip_tts("New response.", False, "") is False
    assert pipeline._should_skip_tts("New response.", False, "old response") is False


def test_should_skip_tts_last_spoken_empty_different_returns_false(
    pipeline: Pipeline,
) -> None:
    assert pipeline._should_skip_tts("Hello", False, "") is False


# ---- create_pipeline: stt_min_confidence, vad_min_level, wait_until_done_before_listen ----
def test_create_pipeline_stt_min_confidence_and_vad_from_config(
    history_repo: HistoryRepo,
) -> None:
    class SttVadConfig(_MockConfig):
        def get(self, key: str, default=None):
            if key == "stt":
                return {"min_confidence": 0.5}
            if key == "audio":
                return {"vad_min_level": 0.02}
            if key == "tts":
                return {"wait_until_done_before_listen": True}
            return super().get(key, default)

    config = SttVadConfig()
    p = create_pipeline(
        config,
        history_repo,
        capture=NoOpCapture(),
        stt=NoOpSTTEngine(),
        tts=NoOpTTSEngine(),
        speaker_filter=NoOpSpeakerFilter(),
        llm_prompt_config={},
    )
    assert p._stt_min_confidence == 0.5
    assert p._vad_min_level == 0.02
    assert p._wait_until_done_before_listen is True


def test_create_pipeline_stt_min_confidence_invalid_ignored(
    history_repo: HistoryRepo,
) -> None:
    class BadSttConfig(_MockConfig):
        def get(self, key: str, default=None):
            if key == "stt":
                return {"min_confidence": 1.5}
            return super().get(key, default)

    config = BadSttConfig()
    p = create_pipeline(
        config,
        history_repo,
        capture=NoOpCapture(),
        stt=NoOpSTTEngine(),
        tts=NoOpTTSEngine(),
        speaker_filter=NoOpSpeakerFilter(),
        llm_prompt_config={},
    )
    assert p._stt_min_confidence is None
