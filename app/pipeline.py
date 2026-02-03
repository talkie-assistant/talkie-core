"""
Orchestrator: audio -> STT -> speaker filter -> LLM -> persistence -> UI callbacks.
Runs the capture/transcribe/respond loop in a background thread.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime
from typing import Callable

from sdk import (
    AudioCapture,
    MicrophoneError,
    NoOpCapture,
    NoOpSpeakerFilter,
    NoOpSTTEngine,
    NoOpTTSEngine,
    SpeakerFilter,
    STTEngine,
    TTSEngine,
    chunk_rms_level,
)
from app.browse_command import BrowseCommandMatcher
from llm.client import FALLBACK_MESSAGE, MEMORY_ERROR_MESSAGE, OllamaClient
from llm.prompts import (
    build_document_qa_system_prompt,
    build_document_qa_user_prompt,
    build_regeneration_prompts,
    build_system_prompt,
    build_user_prompt,
    parse_regeneration_response,
    strip_certainty_from_response,
)
from persistence.history_repo import HistoryRepo, InteractionRecord
from persistence.settings_repo import SettingsRepo
from persistence.training_repo import TrainingRepo
from profile.store import LanguageProfile

logger = logging.getLogger(__name__)


def _only_search_instruction_if_list(text: str) -> str:
    """If text looks like a numbered list of search results (1. X 2. Y), return only the instruction sentence."""
    if not text or not text.strip():
        return text
    t = text.strip()
    if re.search(r"\s+2\.\s+", t) or re.match(r"^\s*1\.\s+.+\s+2\.\s+", t):
        m = re.search(
            r"Say\s+'open\s+\d+'\s+through\s+'open\s+(\d+)'\s+to\s+open\s+a\s+result",
            t,
            re.I,
        )
        return (
            f"Say 'open 1' through 'open {m.group(1)}' to open a result."
            if m
            else "Say open and a number to open a result."
        )
    return t


def create_pipeline(
    config: dict,
    history_repo: HistoryRepo,
    settings_repo: SettingsRepo | None = None,
    training_repo: TrainingRepo | None = None,
    capture: AudioCapture | None = None,
    stt: STTEngine | None = None,
    tts: TTSEngine | None = None,
    speaker_filter: SpeakerFilter | None = None,
    auto_sensitivity: dict | None = None,
    llm_prompt_config: dict | None = None,
) -> Pipeline:
    """
    Build pipeline from config and optional injected speech components.

    When speech components are filled from the speech module, the speaker filter
    (voice profile when configured) is always used so the app only responds to
    the calibrated speaker for all entry points and modules (web, run, remote).
    """
    if capture is None or stt is None or tts is None or speaker_filter is None:
        try:
            from modules.speech import create_speech_components

            comps = create_speech_components(config, settings_repo)
            capture = capture if capture is not None else comps.capture
            stt = stt if stt is not None else comps.stt
            tts = tts if tts is not None else comps.tts
            # Always use speech module's speaker filter when available (enforces voice profile)
            speaker_filter = (
                speaker_filter if speaker_filter is not None else comps.speaker_filter
            )
            if auto_sensitivity is None:
                auto_sensitivity = comps.auto_sensitivity
        except ImportError:
            capture = capture if capture is not None else NoOpCapture()
            stt = stt if stt is not None else NoOpSTTEngine()
            tts = tts if tts is not None else NoOpTTSEngine()
            speaker_filter = (
                speaker_filter if speaker_filter is not None else NoOpSpeakerFilter()
            )
            if auto_sensitivity is None:
                auto_sensitivity = {"enabled": False}

    if llm_prompt_config is None:
        try:
            from modules.speech import apply_llm_calibration_overlay

            llm_prompt_config = apply_llm_calibration_overlay(
                config.get("llm", {}), settings_repo
            )
        except ImportError:
            llm_prompt_config = config.get("llm", {}) or {}

    ollama_cfg = config.get("ollama", {})
    base_url = config.resolve_internal_service_url(
        ollama_cfg.get("base_url", "http://localhost:11434")
    )
    ollama_model = ollama_cfg.get("model_name", "mistral")
    logger.info(
        "Ollama model from config: %s (change config.yaml and restart Web UI to switch)",
        ollama_model,
    )
    client = OllamaClient(
        base_url=base_url,
        model_name=ollama_model,
        timeout_sec=float(ollama_cfg.get("timeout_sec", 45)),
        options=ollama_cfg.get("options"),
    )
    profile_cfg = config.get("profile", {})
    correction_limit = int(profile_cfg.get("correction_limit", 200))
    accepted_limit = int(profile_cfg.get("accepted_limit", 50))
    correction_display_cap = profile_cfg.get("correction_display_cap")
    accepted_display_cap = profile_cfg.get("accepted_display_cap")
    profile = LanguageProfile(
        history_repo,
        settings_repo=settings_repo,
        training_repo=training_repo,
        correction_limit=correction_limit,
        accepted_limit=accepted_limit,
        correction_display_cap=correction_display_cap,
        accepted_display_cap=accepted_display_cap,
    )
    browse_cfg = config.get("browser", {}) or {}
    tts_cfg = config.get("tts", {}) or {}
    stt_cfg = config.get("stt", {}) or {}
    wait_until_done_before_listen = bool(
        tts_cfg.get("wait_until_done_before_listen", False)
    )
    stt_min_confidence: float | None = None
    try:
        mc = stt_cfg.get("min_confidence")
        if mc is not None:
            stt_min_confidence = float(mc)
            if stt_min_confidence < 0 or stt_min_confidence > 1:
                stt_min_confidence = None
    except (TypeError, ValueError):
        pass
    vad_min_level: float | None = None
    try:
        vml = (config.get("audio") or {}).get("vad_min_level")
        if vml is not None:
            vad_min_level = float(vml)
            if vad_min_level < 0 or vad_min_level > 1:
                vad_min_level = None
    except (TypeError, ValueError):
        pass
    try:
        browse_cooldown_sec = float(browse_cfg.get("cooldown_after_tts_sec", 12.0))
        browse_cooldown_sec = max(0.0, min(60.0, browse_cooldown_sec))
    except (TypeError, ValueError):
        browse_cooldown_sec = 12.0
    return Pipeline(
        capture=capture,
        stt=stt,
        speaker_filter=speaker_filter,
        llm_client=client,
        history_repo=history_repo,
        language_profile=profile,
        tts=tts,
        llm_prompt_config=llm_prompt_config,
        auto_sensitivity=auto_sensitivity or {"enabled": False},
        browse_cooldown_after_tts_sec=browse_cooldown_sec,
        wait_until_done_before_listen=wait_until_done_before_listen,
        stt_min_confidence=stt_min_confidence,
        vad_min_level=vad_min_level,
    )


class Pipeline:
    """
    Runs the loop in a worker thread: read chunk -> STT -> filter -> LLM -> persist -> UI.
    """

    def __init__(
        self,
        capture: AudioCapture,
        stt: STTEngine,
        speaker_filter: SpeakerFilter,
        llm_client: OllamaClient,
        history_repo: HistoryRepo,
        language_profile: LanguageProfile,
        tts: TTSEngine,
        llm_prompt_config: dict | None = None,
        auto_sensitivity: dict | None = None,
        browse_cooldown_after_tts_sec: float = 12.0,
        wait_until_done_before_listen: bool = False,
        stt_min_confidence: float | None = None,
        vad_min_level: float | None = None,
    ) -> None:
        self._capture = capture
        self._stt = stt
        self._speaker_filter = speaker_filter
        self._llm = llm_client
        self._history = history_repo
        self._profile = language_profile
        self._tts = tts
        self._llm_prompt_config = llm_prompt_config or {}
        self._auto_sensitivity = auto_sensitivity or {"enabled": False}
        self._browse_cooldown_after_tts_sec = max(
            0.0, min(60.0, browse_cooldown_after_tts_sec)
        )
        self._wait_until_done_before_listen = bool(wait_until_done_before_listen)
        self._stt_min_confidence = stt_min_confidence
        self._vad_min_level = vad_min_level

        self._on_status: Callable[[str], None] = lambda _: None
        self._on_response: Callable[[str, int], None] = lambda _t, _i: None
        self._on_error: Callable[[str], None] = lambda _: None
        self._on_debug: Callable[[str], None] = lambda _: None
        self._on_volume: Callable[[float], None] = lambda _: None
        self._on_sensitivity_adjusted: Callable[[float], None] = lambda _: None
        self._on_training_transcription: Callable[[str], None] | None = None

        self._running = False
        self._thread: threading.Thread | None = None
        self._auto_sensitivity_cooldown = 0
        self._training_mode = False
        # Optional RAG: callable(query, top_k=None) -> retrieved context string; only called when document_qa_mode
        self._rag_retriever: Callable[..., str] | None = None
        self._rag_has_documents: Callable[[], bool] | None = None
        self._document_qa_mode = False
        self._document_qa_top_k = 8
        # Optional web/browse: voice-controlled browser (voice only)
        self._web_mode = False
        self._web_handler: Callable[..., str | None] | None = None
        self._on_web_selection: Callable[[str | None], None] = lambda _: None
        self._on_open_url: Callable[[str], None] = lambda _: None
        # Skip only when the same text appears in the immediately previous chunk (consecutive duplicate)
        self._previous_chunk_transcription: str | None = None
        # Do not listen to yourself: filter out our own TTS from being treated as user input.
        self._last_spoken_response: str | None = None
        self._recent_spoken_responses: list[
            str
        ] = []  # last N spoken (echo filter against all)
        self._recent_spoken_max = 3
        # Skip browse commands for N seconds after we spoke (avoid TTS echo / mishear triggering actions).
        self._last_tts_time: float = 0.0
        # Quit confirmation modal: when True, next "yes"/"no" is handled as quit confirm/cancel.
        self._quit_modal_pending: bool = False
        self._on_quit_confirmed: Callable[[], None] = lambda: None
        self._on_close_quit_modal: Callable[[], None] = lambda: None
        # Executor for parallel work (prefetch profile + recent during regeneration). Created in start(), shut down in stop().
        self._executor: ThreadPoolExecutor | None = None
        self._browse_matcher = BrowseCommandMatcher()

    def _push_spoken(self, text: str) -> None:
        """Record spoken TTS so we can filter it out from STT (do not listen to yourself)."""
        s = (text or "").strip()
        self._last_spoken_response = s or self._last_spoken_response
        if s:
            self._recent_spoken_responses = [s] + [
                x for x in self._recent_spoken_responses if x != s
            ][: self._recent_spoken_max - 1]
            self._last_tts_time = time.monotonic()

    def _should_skip_tts(
        self,
        spoken_text: str,
        is_error_fallback: bool,
        last_spoken_norm: str,
    ) -> bool:
        """Return True if TTS should be skipped (error fallback, empty, or same as last spoken)."""
        if is_error_fallback:
            return True
        if not (spoken_text or "").strip():
            return True
        spoken_norm = " ".join((spoken_text or "").strip().lower().split())
        if last_spoken_norm and spoken_norm == last_spoken_norm:
            return True
        return False

    def set_ui_callbacks(
        self,
        on_status: Callable[[str], None],
        on_response: Callable[[str, int], None],
        on_error: Callable[[str], None],
        on_debug: Callable[[str], None] | None = None,
        on_volume: Callable[[float], None] | None = None,
        on_sensitivity_adjusted: Callable[[float], None] | None = None,
    ) -> None:
        self._on_status = on_status
        self._on_response = on_response
        self._on_error = on_error
        if on_debug is not None:
            self._on_debug = on_debug
            self._llm.set_debug_log(lambda m: self._debug(m))
        if on_volume is not None:
            self._on_volume = on_volume
        if on_sensitivity_adjusted is not None:
            self._on_sensitivity_adjusted = on_sensitivity_adjusted

    def get_sensitivity(self) -> float:
        return self._capture.get_sensitivity()

    def set_sensitivity(self, value: float) -> None:
        self._capture.set_sensitivity(value)

    def set_training_mode(self, enabled: bool) -> None:
        """When True, transcriptions are passed to on_training_transcription and not sent to the LLM."""
        self._training_mode = enabled

    def set_on_training_transcription(
        self, callback: Callable[[str], None] | None
    ) -> None:
        """Set callback invoked when in training mode with the transcribed text (e.g. to store as a fact)."""
        self._on_training_transcription = callback

    def set_rag_retriever(self, retriever: Callable[..., str] | None) -> None:
        """Set optional RAG retriever: (query, top_k=None) -> context string. Only invoked when document_qa_mode is True."""
        self._rag_retriever = retriever

    def set_rag_has_documents(self, has_documents: Callable[[], bool] | None) -> None:
        """Set optional callable to check if RAG has any indexed documents (for empty-state)."""
        self._rag_has_documents = has_documents

    def set_document_qa_mode(self, on: bool) -> None:
        """When True, next utterance is treated as a document question: retrieve and use document-QA prompts. Clears web mode."""
        self._document_qa_mode = on
        if on:
            self._web_mode = False

    def set_document_qa_top_k(self, top_k: int) -> None:
        """Number of chunks to retrieve when in document-QA mode."""
        self._document_qa_top_k = max(1, min(20, top_k))

    def set_web_mode(self, on: bool) -> None:
        """Set browse mode on/off (e.g. from voice 'start browsing' / 'stop browsing'). When on, document_qa_mode is cleared."""
        self._web_mode = on
        if on:
            self._document_qa_mode = False

    def set_web_handler(
        self,
        handler: Callable[..., str | None] | None,
    ) -> None:
        """Set optional web handler: (utterance, set_web_mode[, set_web_selection]) -> message or None if not a browse command."""
        self._web_handler = handler

    def set_on_web_selection(
        self, callback: Callable[[str | None], None] | None
    ) -> None:
        """Set callback for selected link display: (display_text) or (None) to clear. Used by overlay."""
        self._on_web_selection = callback if callback is not None else lambda _: None

    def set_on_open_url(self, callback: Callable[[str], None] | None) -> None:
        """Set callback to open a URL (e.g. on main thread or on client when remote). Called when click_link resolves a URL."""
        self._on_open_url = callback if callback is not None else lambda _: None

    def set_quit_modal_pending(self, value: bool) -> None:
        """When True, next utterance is treated as yes/no for quit confirmation (say or click)."""
        self._quit_modal_pending = value

    def set_on_quit_confirmed(self, callback: Callable[[], None] | None) -> None:
        """Set callback invoked when user confirms quit (e.g. say Yes or click Yes)."""
        self._on_quit_confirmed = callback if callback is not None else lambda: None

    def set_on_close_quit_modal(self, callback: Callable[[], None] | None) -> None:
        """Set callback invoked when user cancels quit (e.g. say No); used to close the modal in the UI."""
        self._on_close_quit_modal = callback if callback is not None else lambda: None

    def get_web_mode(self) -> bool:
        """True when browse mode is on (voice-controlled web)."""
        return self._web_mode

    def has_web_handler(self) -> bool:
        """True when a web/browse handler is set (browser module loaded)."""
        return self._web_handler is not None

    def speak(self, text: str) -> None:
        """Speak text via TTS (e.g. ready message). Safe to call from main thread."""
        if not text or not text.strip():
            return
        try:
            self._tts.speak(text.strip())
        except Exception as e:
            logger.debug("TTS speak failed: %s", e)

    def _debug(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self._on_debug(f"[{ts}] {msg}")

    def _prefetch_profile_and_recent(
        self, turns: int
    ) -> tuple[str, list[InteractionRecord]]:
        """Fetch profile context and recent interactions (for use in parallel with regeneration)."""
        profile_ctx = ""
        try:
            profile_ctx = self._profile.get_context_for_llm()
        except Exception as e:
            logger.debug("Prefetch profile failed: %s", e)
        recent: list[InteractionRecord] = []
        if turns > 0:
            try:
                recent = self._history.list_recent(limit=turns)
            except Exception as e:
                logger.debug("Prefetch list_recent failed: %s", e)
        return (profile_ctx, recent)

    def invalidate_profile_cache(self) -> None:
        """Invalidate the language profile cache so the next LLM request uses fresh corrections/accepted."""
        self._profile.invalidate_cache()

    def start(self) -> None:
        if self._running:
            return
        # New executor each start; the previous one may have been shut down in stop().
        self._executor = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="talkie-core-pipeline"
        )
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        # Do not call _capture.stop() here: the stream must be closed by the worker
        # thread. Closing from the main thread while the worker is in read_chunk()
        # causes a PortAudio SIGSEGV (PaUtil_ReadRingBuffer).
        if self._thread is not None:
            self._thread.join(timeout=7.0)
            if self._thread.is_alive():
                logger.warning(
                    "Pipeline worker thread did not stop within timeout; may still be running"
                )
            self._thread = None
        if self._executor is not None:
            self._executor.shutdown(wait=True)
            self._executor = None
        self._stt.stop()
        self._on_status("Stopped")

    def _run_loop(self) -> None:
        self._debug("Pipeline thread started")
        self._on_status("Starting...")
        try:
            self._capture.start()
            self._debug("Audio capture started")
            self._stt.start()
            self._debug("STT started")
        except MicrophoneError as e:
            self._debug(f"Pipeline start failed: {e}")
            self._on_error("Microphone disconnected or unavailable")
            logger.exception("Pipeline start failed: %s", e)
            self._running = False
            self._capture.stop()
            self._on_status("Stopped")
            return
        except Exception as e:
            self._debug(f"Pipeline start failed: {e}")
            self._on_error(str(e))
            logger.exception("Pipeline start failed: %s", e)
            self._running = False
            self._capture.stop()
            self._on_status("Stopped")
            return

        self._debug("Pipeline running (audio + STT started)")
        if not self._llm.check_connection():
            self._debug("Error: Ollama not reachable. Is it running?")
            self._on_error("Ollama not reachable. Is it running?")
            self._running = False
            self._capture.stop()
            self._stt.stop()
            self._on_status("Stopped")
            return

        while self._running:
            try:
                self._on_status("Listening...")
                chunk = self._capture.read_chunk(on_level=self._on_volume)
            except MicrophoneError:
                self._on_debug("Microphone disconnected")
                self._on_error("Microphone disconnected")
                break
            if not self._running:
                break
            if chunk is None:
                continue

            try:
                level = chunk_rms_level(chunk)
                self._on_volume(level)
            except Exception as e:
                logger.debug("Volume callback failed: %s", e)
                self._debug("Error (volume callback): %s" % e)

            if (
                self._vad_min_level is not None
                and level is not None
                and level < self._vad_min_level
            ):
                self._debug(
                    "VAD: chunk RMS %.4f below threshold %.4f; skipping STT"
                    % (level, self._vad_min_level)
                )
                continue

            self._debug("Audio level (chunk RMS, waveform): %.4f" % level)
            self._debug("Audio chunk received (%d bytes), transcribing..." % len(chunk))
            self._on_status("Transcribing...")
            try:
                if self._stt_min_confidence is not None and hasattr(
                    self._stt, "transcribe_with_confidence"
                ):
                    text, confidence = self._stt.transcribe_with_confidence(chunk)
                    text = (text or "").strip()
                    if confidence is not None and confidence < self._stt_min_confidence:
                        self._debug(
                            "STT confidence %.2f below threshold %.2f; treating as empty"
                            % (confidence, self._stt_min_confidence)
                        )
                        text = ""
                else:
                    text = self._stt.transcribe(chunk).strip()
            except Exception as e:
                logger.exception("STT transcribe failed: %s", e)
                self._debug("Error (STT transcribe): %s" % e)
                self._on_error("Speech recognition failed")
                continue
            if not text:
                min_l = self._auto_sensitivity.get("min_level", 0.002)
                max_l = self._auto_sensitivity.get("max_level", 0.08)
                self._debug(
                    "STT: (empty) level=%.4f (auto sens: %s, band %.4f–%.4f)"
                    % (
                        level,
                        "on" if self._auto_sensitivity.get("enabled") else "off",
                        min_l,
                        max_l,
                    )
                )
                if level > max_l:
                    self._debug(
                        "High level but no transcription – check mic is 16000 Hz and STT engine (e.g. Whisper model loaded)."
                    )
                # Auto sensitivity: only when level is in "quiet" band; above max_l we don't assume too quiet
                if (
                    self._auto_sensitivity.get("enabled")
                    and self._auto_sensitivity_cooldown <= 0
                ):
                    if min_l <= level <= max_l:
                        step = self._auto_sensitivity.get("step", 0.25)
                        current = self._capture.get_sensitivity()
                        new_sens = min(10.0, current + step)
                        if new_sens > current:
                            self._capture.set_sensitivity(new_sens)
                            self._auto_sensitivity_cooldown = (
                                self._auto_sensitivity.get("cooldown_chunks", 3)
                            )
                            self._debug(
                                "Auto sensitivity: raised to %.1f (level=%.4f, no speech)"
                                % (new_sens, level)
                            )
                            try:
                                self._on_sensitivity_adjusted(new_sens)
                            except Exception as e:
                                logger.debug("on_sensitivity_adjusted failed: %s", e)
                                self._debug(
                                    "Error (sensitivity adjusted callback): %s" % e
                                )
                if self._auto_sensitivity_cooldown > 0:
                    self._auto_sensitivity_cooldown -= 1
                continue

            self._debug("Transcription: " + text)

            try:
                min_level = self._llm_prompt_config.get("min_audio_level")
                min_level = float(min_level) if min_level is not None else 0.0
            except (TypeError, ValueError):
                min_level = 0.0
            if min_level > 0 and level < min_level:
                self._debug(
                    "Audio level below threshold (%.4f < %.4f); skipping to avoid false triggers"
                    % (level, min_level)
                )
                continue

            try:
                min_len = self._llm_prompt_config.get("min_transcription_length")
                min_len = int(min_len) if min_len is not None else 0
            except (TypeError, ValueError):
                min_len = 0
            # Allow short transcriptions that are browse commands (e.g. "open 2", "open 6") so open-by-number works.
            is_short_browse = (
                min_len > 0
                and len(text) < min_len
                and self._web_handler is not None
                and (
                    self._browse_matcher.is_browse_command(text)
                    or self._browse_matcher.is_open_number_only(text)
                )
            )
            if min_len > 0 and len(text) < min_len and not is_short_browse:
                self._debug(
                    "Transcription too short (%d < %d), skipping LLM to avoid spurious responses"
                    % (len(text), min_len)
                )
                continue
            if is_short_browse:
                self._debug("Short transcription allowed (browse command): %s" % text)

            if not self._speaker_filter.accept(text, chunk):
                reason = None
                if hasattr(self._speaker_filter, "get_last_reject_reason"):
                    reason = self._speaker_filter.get_last_reject_reason()
                self._debug(
                    "Speaker filter: rejected"
                    + (
                        f" ({reason})"
                        if reason
                        else " (voice did not match enrolled profile)"
                    )
                )
                continue

            # Skip only when same text as immediately previous chunk (consecutive duplicate); respond every time they talk otherwise
            text_normalized = text.strip()
            if text_normalized and self._previous_chunk_transcription is not None:
                if text_normalized == self._previous_chunk_transcription.strip():
                    self._debug("Same transcription as previous chunk; skipping")
                    continue
            self._previous_chunk_transcription = text_normalized

            # Do not listen to yourself: skip when transcription matches any recent TTS (mic picking up our own voice).
            if text_normalized and self._recent_spoken_responses:
                trans_lower = text_normalized.lower()

                def _norm_echo(s: str) -> str:
                    return " ".join(
                        "".join(
                            c if c.isalnum() else " " for c in (s or "").lower()
                        ).split()
                    )

                nt = _norm_echo(text_normalized)
                is_echo = False
                for last in self._recent_spoken_responses:
                    if not last:
                        continue
                    last_lower = last.strip().lower()
                    if trans_lower == last_lower:
                        is_echo = True
                        break
                    ns = _norm_echo(last)
                    if nt and ns:
                        # Substring match: only treat as echo when transcription isn't meaningfully longer (user adding words = new input).
                        if len(nt) >= 20 and (nt in ns or ns in nt):
                            # User said more than we spoke (e.g. repeated phrase + "finish the sentence") -> not echo.
                            if len(nt) > len(ns) + 15:
                                continue
                            is_echo = True
                            break
                        trans_words = set(nt.split())
                        spoken_words = set(ns.split())
                        if len(trans_words) >= 4 and spoken_words:
                            if (
                                len(trans_words & spoken_words) / len(trans_words)
                                >= 0.75
                            ):
                                is_echo = True
                                break
                if is_echo:
                    self._debug("Transcription is our own voice (echo); skipping")
                    continue

            # User started speaking again: abort any playing TTS so we can process this (retry).
            try:
                self._tts.stop()
            except Exception as e:
                logger.debug("TTS stop (abort on new speech) failed: %s", e)

            # Quit confirmation: if modal is pending, only accept "yes" or "no".
            if self._quit_modal_pending and text:
                norm = (text or "").strip().lower()
                if norm in ("yes", "no"):
                    self._quit_modal_pending = False
                    if norm == "yes":
                        self._on_quit_confirmed()
                        return
                    try:
                        self._on_close_quit_modal()
                    except Exception:
                        pass
                    self._on_status("Cancelled.")
                    self._on_response("Cancelled.", 0)
                    continue

            try:
                self._on_status("Responding...")
                # Regeneration: raw transcription -> one sentence with high probability of user intent (Ollama).
                # Prefetch profile + recent context in parallel with regeneration to hide their latency.
                intent_sentence = text
                used_regeneration = False
                regeneration_certainty: int | None = None
                profile_context_prefetch: str | None = None
                recent_list_prefetch: list[InteractionRecord] | None = None
                try:
                    turns = int(
                        self._llm_prompt_config.get("conversation_context_turns", 0)
                        or 0
                    )
                except (TypeError, ValueError):
                    turns = 0

                # Skip regeneration when we will take the browse path: one path per utterance (browse OR speech).
                if self._web_mode and self._web_handler is not None:
                    intent_sentence = text
                    used_regeneration = False
                elif (
                    self._web_handler is not None
                    and self._browse_matcher.is_browse_command(text)
                ):
                    intent_sentence = text
                    used_regeneration = False
                elif self._llm_prompt_config.get("regeneration_enabled", True):
                    request_certainty = self._llm_prompt_config.get(
                        "regeneration_request_certainty", True
                    )
                    reg_system, reg_user = build_regeneration_prompts(
                        text,
                        system_prompt=self._llm_prompt_config.get("system_prompt")
                        or self._llm_prompt_config.get(
                            "regeneration_system_prompt"
                        ),
                        user_prompt_template=self._llm_prompt_config.get(
                            "regeneration_user_prompt_template"
                        ),
                        request_certainty=request_certainty,
                    )
                    self._debug(
                        "Ollama regeneration: raw -> intent sentence"
                        + (" (with certainty)" if request_certainty else "")
                    )
                    if not self._running or self._executor is None:
                        regenerated = self._llm.generate(reg_user, reg_system)
                        profile_context_prefetch, recent_list_prefetch = (
                            self._prefetch_profile_and_recent(turns)
                        )
                    else:
                        submitted = False
                        try:
                            future_regen = self._executor.submit(
                                self._llm.generate, reg_user, reg_system
                            )
                            future_ctx = self._executor.submit(
                                self._prefetch_profile_and_recent, turns
                            )
                            submitted = True
                        except RuntimeError as e:
                            if (
                                "shutdown" in str(e).lower()
                                or "futures" in str(e).lower()
                            ):
                                regenerated = self._llm.generate(reg_user, reg_system)
                                profile_context_prefetch, recent_list_prefetch = (
                                    self._prefetch_profile_and_recent(turns)
                                )
                            else:
                                raise
                        if submitted:
                            try:
                                regenerated = future_regen.result(
                                    timeout=self._llm.timeout_sec + 10
                                )
                                profile_ctx, recent_list = future_ctx.result(timeout=30)
                                profile_context_prefetch = profile_ctx
                                recent_list_prefetch = recent_list
                            except FuturesTimeoutError:
                                regenerated = self._llm.generate(reg_user, reg_system)
                                profile_context_prefetch, recent_list_prefetch = (
                                    self._prefetch_profile_and_recent(turns)
                                )
                            except Exception as e:
                                logger.debug(
                                    "Parallel prefetch or regen failed, falling back to sequential: %s",
                                    e,
                                )
                                regenerated = self._llm.generate(reg_user, reg_system)
                                profile_context_prefetch, recent_list_prefetch = (
                                    self._prefetch_profile_and_recent(turns)
                                )
                    if regenerated and regenerated.strip():
                        intent_sentence, regeneration_certainty = (
                            parse_regeneration_response(regenerated)
                        )
                        # Don't treat LLM error messages as successful regeneration (avoids repeat logic echoing user's words).
                        if intent_sentence.strip() in (
                            MEMORY_ERROR_MESSAGE.strip(),
                            FALLBACK_MESSAGE.strip(),
                        ):
                            used_regeneration = False
                            intent_sentence = text
                            self._debug(
                                "Regeneration returned error message; using raw transcription"
                            )
                        else:
                            used_regeneration = True
                        # If model wrongly returned "I didn't catch that" for a clear test phrase or greeting, use transcription.
                        if (
                            used_regeneration
                            and intent_sentence.strip()
                            .lower()
                            .startswith("i didn't catch that")
                        ):
                            norm = text.strip().lower().rstrip(".")
                            if norm in (
                                "test 123",
                                "hello",
                                "hi",
                                "hey",
                                "good morning",
                                "good afternoon",
                                "good evening",
                            ) or (norm.startswith("test ") and len(norm) <= 30):
                                intent_sentence = text.strip()
                                self._debug(
                                    "Model said 'I didn't catch that' for clear phrase; using transcription"
                                )
                        if used_regeneration and regeneration_certainty is not None:
                            self._debug(
                                "Regenerated intent: %s (certainty %d%%)"
                                % (intent_sentence, regeneration_certainty)
                            )
                        elif used_regeneration:
                            self._debug("Regenerated intent: " + intent_sentence)
                    else:
                        self._debug(
                            "Regeneration empty or fallback; using raw transcription"
                        )

                if self._training_mode and self._on_training_transcription is not None:
                    self._debug("Training mode: saving sentence as fact")
                    try:
                        self._on_training_transcription(text)
                        self._profile.invalidate_cache()
                    except Exception as e:
                        logger.exception(
                            "Training transcription callback failed: %s", e
                        )
                        self._debug("Error (training callback): %s" % e)
                    self._on_status("Listening...")
                    continue

                # Optional web/browse: only respond to commands (search, scroll, click, etc.); do not enter for conversation.
                if (
                    self._web_handler is not None
                    and self._browse_matcher.is_browse_command(intent_sentence, text)
                ):
                    # Always use raw transcription for browse so regeneration cannot inject "and chrome", "in Chrome", etc.
                    browse_utterance = (text or "").strip() or intent_sentence
                    if self._web_mode:
                        browse_utterance = self._browse_matcher.first_single_command(
                            browse_utterance
                        )
                    # Skip browse during cooldown after we spoke (avoid TTS echo / mishear triggering clicks).
                    # Exception: allow scroll, go_back, and open N immediately so they feel responsive.
                    if (
                        self._browse_cooldown_after_tts_sec > 0
                        and self._last_tts_time > 0
                        and (time.monotonic() - self._last_tts_time)
                        < self._browse_cooldown_after_tts_sec
                        and not self._browse_matcher.is_scroll_or_go_back_only(
                            browse_utterance
                        )
                        and not self._browse_matcher.is_open_number_only(
                            browse_utterance
                        )
                    ):
                        self._debug(
                            "Browse: skipping (cooldown %.0fs after TTS)"
                            % self._browse_cooldown_after_tts_sec
                        )
                        self._on_status("Listening...")
                        continue
                    # In web mode only act on a clear command that starts the utterance (wait for command; no echo/continuation).
                    if not self._browse_matcher.starts_with_browse_command(
                        browse_utterance
                    ):
                        self._debug(
                            "Browse: skipping (wait for command; utterance does not start with command)"
                        )
                        self._on_status("Listening...")
                        continue
                    self._on_status("Responding... (browse)")
                    self._debug(
                        "Browse: using raw transcription: '%s'"
                        % (
                            browse_utterance[:80] + "..."
                            if len(browse_utterance) > 80
                            else browse_utterance
                        )
                    )
                    intent_preview = (browse_utterance or "").strip()
                    if len(intent_preview) > 80:
                        intent_preview = intent_preview[:80] + "..."
                    self._debug("Browse: handling '%s'" % intent_preview)
                    web_response = None
                    try:
                        web_response = self._web_handler(
                            browse_utterance,
                            self.set_web_mode,
                            self._on_web_selection,
                            self._on_open_url,
                        )
                    except TypeError:
                        try:
                            web_response = self._web_handler(
                                browse_utterance,
                                self.set_web_mode,
                                self._on_web_selection,
                            )
                        except TypeError:
                            web_response = self._web_handler(
                                browse_utterance, self.set_web_mode
                            )
                    except Exception as e:
                        logger.exception("Web handler failed: %s", e)
                        self._debug("[ERROR] Web handler failed: %s" % e)
                        web_response = "Could not complete that action."
                    if web_response is not None:
                        resp_preview = (web_response or "").strip()
                        if len(resp_preview) > 100:
                            resp_preview = resp_preview[:100] + "..."
                        self._debug("Browse result: %s" % resp_preview)
                        try:
                            interaction_id = self._history.insert_interaction(
                                original_transcription=text,
                                llm_response=web_response,
                            )
                            self._profile.invalidate_cache()
                        except Exception as e:
                            logger.exception("Failed to save interaction: %s", e)
                            interaction_id = 0
                        spoken_text = strip_certainty_from_response(web_response or "")
                        spoken_text = _only_search_instruction_if_list(spoken_text)
                        self._on_response(spoken_text, interaction_id)
                        prev_spoken_norm = (
                            " ".join(
                                (self._last_spoken_response or "")
                                .strip()
                                .lower()
                                .split()
                            )
                            if self._last_spoken_response
                            else ""
                        )
                        self._push_spoken(spoken_text)
                        if self._should_skip_tts(spoken_text, False, prev_spoken_norm):
                            self._debug(
                                "Skipping TTS: same as last spoken (avoid repeating)"
                            )
                        else:
                            try:
                                self._tts.speak(spoken_text)
                                self._debug(
                                    "TTS: started speaking (speak again to abort and retry)"
                                )
                            except Exception as e:
                                logger.exception("TTS speak failed: %s", e)
                                self._debug("Error (TTS): %s" % e)
                        if self._wait_until_done_before_listen:
                            try:
                                self._tts.wait_until_done()
                            except Exception as e:
                                logger.debug("TTS wait_until_done: %s", e)
                        self._on_status("Listening...")
                        continue

                    # Web mode: no output when no command was executed (handler returned None).
                    if self._web_mode:
                        self._on_status("Listening...")
                        continue

                self._on_status("Responding...")

                # Web mode: only output when we executed a browse command; otherwise no TTS, no save.
                if self._web_mode:
                    self._on_status("Listening...")
                    continue

                # Build recent-context data once so we can block repeats on every response path
                recent_reply_norms = set()
                recent_user_phrase_norms = set()

                def _norm(s: str) -> str:
                    return " ".join((s or "").strip().lower().split())

                if turns > 0:
                    recent = (
                        recent_list_prefetch
                        if recent_list_prefetch is not None
                        else self._history.list_recent(limit=turns)
                    )
                    try:
                        recent_chrono = list(reversed(recent))
                        lines = []
                        for rec in recent_chrono:
                            user = (rec.get("original_transcription") or "").strip()
                            resp = (
                                rec.get("corrected_response")
                                or rec.get("llm_response")
                                or ""
                            ).strip()
                            if user or resp:
                                lines.append(
                                    "User: %s\nAssistant: %s"
                                    % (user or "(no speech)", resp or "(no response)")
                                )
                            if resp:
                                recent_reply_norms.add(_norm(resp))
                            if user:
                                recent_user_phrase_norms.add(_norm(user))
                        if lines:
                            self._debug(
                                "Included %d recent turn(s) for context / repeat check"
                                % len(lines)
                            )
                    except Exception as e:
                        logger.debug("Failed to build recent context: %s", e)

                if self._document_qa_mode:
                    # Document Q&A: empty-state check, then retrieve and answer from context only.
                    if not self._rag_has_documents or not self._rag_has_documents():
                        response = "No documents are indexed yet. Open Documents, add files, and click Vectorize."
                        self._debug("Document QA: no documents indexed, short-circuit")
                    else:
                        retrieved_context = ""
                        if self._rag_retriever is not None:
                            try:
                                retrieved_context = (
                                    self._rag_retriever(
                                        intent_sentence, self._document_qa_top_k
                                    )
                                    or ""
                                )
                            except Exception as e:
                                logger.exception("RAG retriever failed: %s", e)
                                self._debug("Error (RAG retriever): %s" % e)
                        system = build_document_qa_system_prompt(retrieved_context)
                        user_prompt = build_document_qa_user_prompt(intent_sentence)
                        self._debug(
                            "Document QA: Ollama with retrieved context (%d chars)"
                            % len(retrieved_context)
                        )
                        response = self._llm.generate(user_prompt, system)
                        self._debug("Ollama API response (%d chars):" % len(response))
                else:
                    use_regeneration_as_response = self._llm_prompt_config.get(
                        "use_regeneration_as_response", True
                    )
                    certainty_threshold = int(
                        self._llm_prompt_config.get(
                            "regeneration_certainty_threshold", 70
                        )
                    )
                    certainty_threshold = max(0, min(100, certainty_threshold))

                    # If we heard the full sentence and the LLM effectively agrees (same or nearly same), just repeat it —
                    # unless the utterance looks like a request/command (user wants an action or completed reply, not an echo).
                    def _normalize_for_repeat(s: str) -> str:
                        s = (s or "").strip().lower()
                        s = " ".join(s.split())
                        return s.rstrip(".!? ")

                    def _looks_like_request(u: str) -> bool:
                        u = (u or "").strip().lower()
                        if not u or len(u) < 6:
                            return False
                        return (
                            u.startswith("please take me")
                            or u.startswith("take me ")
                            or u.startswith("take me to")
                            or u.startswith("go to ")
                            or u.startswith("go to the ")
                            or u.startswith("open ")
                            or u.startswith("open the ")
                            or u.startswith("turn on ")
                            or u.startswith("turn off ")
                            or u.startswith("i need ")
                            or u.startswith("i want to ")
                            or " take me " in u
                            or " take me to " in u
                        )

                    transcript_norm = _normalize_for_repeat(text_normalized)
                    intent_norm = _normalize_for_repeat(intent_sentence)
                    llm_agrees_repeat = (
                        used_regeneration
                        and transcript_norm
                        and intent_norm
                        and transcript_norm == intent_norm
                        and not _looks_like_request(intent_sentence)
                    )
                    if llm_agrees_repeat:
                        response = intent_sentence.strip()
                        self._debug(
                            "Heard full sentence; LLM agrees it makes sense — repeating it (skipping completion)"
                        )
                    else:
                        skip_completion = (
                            use_regeneration_as_response
                            and used_regeneration
                            and (
                                regeneration_certainty is None
                                or regeneration_certainty >= certainty_threshold
                            )
                        )
                        if skip_completion:
                            response = intent_sentence
                            self._debug(
                                "Using regenerated intent as response (skipping completion)"
                                + (
                                    " (certainty %d%% >= %d%%)"
                                    % (regeneration_certainty, certainty_threshold)
                                    if regeneration_certainty is not None
                                    else ""
                                )
                            )
                        else:
                            if used_regeneration and regeneration_certainty is not None:
                                self._debug(
                                    "Certainty %d%% < %d%%, running completion call"
                                    % (regeneration_certainty, certainty_threshold)
                                )
                            if profile_context_prefetch is not None:
                                profile_context = profile_context_prefetch
                            else:
                                try:
                                    profile_context = (
                                        self._profile.get_context_for_llm()
                                    )
                                except Exception as e:
                                    logger.exception(
                                        "Profile get_context_for_llm failed: %s", e
                                    )
                                    self._debug(
                                        "Error (profile get_context_for_llm): %s" % e
                                    )
                                    profile_context = ""
                            retrieved_context = ""
                            # Use only current sentence in prompt; history is used only for repeat check, not in the prompt.
                            system = build_system_prompt(
                                profile_context,
                                system_base=self._llm_prompt_config.get(
                                    "system_prompt"
                                ),
                                retrieved_context=retrieved_context or None,
                                conversation_context=None,
                            )
                            user_prompt = build_user_prompt(
                                intent_sentence,
                                user_prompt_template=self._llm_prompt_config.get(
                                    "user_prompt_template"
                                ),
                            )
                            model_name = self._llm.model_name
                            self._debug(
                                "Ollama API call: POST %s/api/generate model=%s"
                                % (self._llm.base_url, model_name)
                            )
                            self._debug(
                                "Ollama system prompt (%d chars):" % len(system)
                            )
                            self._debug(
                                (system[:2000] + "...")
                                if len(system) > 2000
                                else (system or "(empty)")
                            )
                            self._debug("Ollama user prompt:")
                            self._debug(user_prompt)
                            response = self._llm.generate(user_prompt, system)
                            self._debug(
                                "Ollama API response (%d chars):" % len(response)
                            )
                            self._debug(response)

                # One repeat check for every response path: never repeat a recent assistant or user phrase or last spoken.
                # Don't replace error messages with intent/raw so the user sees the error once instead of their words echoed.
                if response and response.strip() not in (
                    MEMORY_ERROR_MESSAGE.strip(),
                    FALLBACK_MESSAGE.strip(),
                ):
                    rn = _norm(response)
                    last_spoken_norm = (
                        _norm(self._last_spoken_response)
                        if self._last_spoken_response
                        else ""
                    )
                    is_repeat = (
                        rn in recent_reply_norms
                        or rn in recent_user_phrase_norms
                        or (last_spoken_norm and rn == last_spoken_norm)
                    )
                    # Also treat as repeat if response is nearly the same (one contains the other, len > 10 to avoid false positives)
                    if not is_repeat and len(rn) > 10:
                        for prev in recent_reply_norms | (
                            {last_spoken_norm} if last_spoken_norm else set()
                        ):
                            if len(prev) > 10 and (rn in prev or prev in rn):
                                is_repeat = True
                                break
                    if is_repeat:
                        self._debug(
                            "Response repeated a recent phrase; using intent then raw transcription"
                        )
                        response = intent_sentence
                        rn2 = _norm(response)
                        if (
                            rn2 in recent_reply_norms
                            or rn2 in recent_user_phrase_norms
                            or (
                                self._last_spoken_response
                                and rn2 == _norm(self._last_spoken_response)
                            )
                        ):
                            response = text
                            self._debug(
                                "Intent was also a repeat; using raw transcription"
                            )

                if not (response or "").strip():
                    response = (
                        intent_sentence or text or ""
                    ).strip() or FALLBACK_MESSAGE
                    self._debug(
                        "Response empty; using intent/transcription/fallback: %s"
                        % (response[:50] + "..." if len(response) > 50 else response)
                    )

                try:
                    interaction_id = self._history.insert_interaction(
                        original_transcription=text,
                        llm_response=response,
                    )
                    self._profile.invalidate_cache()
                    self._debug(f"Saved interaction id={interaction_id}")
                except Exception as e:
                    logger.exception("Failed to save interaction: %s", e)
                    self._debug("Error (save interaction): %s" % e)
                    self._on_error("Could not save to history")
                    interaction_id = 0

                spoken_text = strip_certainty_from_response(response or "")
                self._on_response(spoken_text, interaction_id)
                prev_spoken_norm = (
                    _norm(self._last_spoken_response)
                    if self._last_spoken_response
                    else ""
                )
                self._push_spoken(spoken_text)
                is_error_fallback = (spoken_text or "").strip() in (
                    FALLBACK_MESSAGE.strip(),
                    MEMORY_ERROR_MESSAGE.strip(),
                )
                if self._should_skip_tts(
                    spoken_text, is_error_fallback, prev_spoken_norm
                ):
                    if is_error_fallback:
                        self._debug("Skipping TTS: error fallback (show in UI only)")
                    else:
                        self._debug(
                            "Skipping TTS: same as last spoken (avoid repeating)"
                        )
                else:
                    try:
                        self._tts.speak(spoken_text)
                        self._debug(
                            "TTS: started speaking (speak again to abort and retry)"
                        )
                    except Exception as e:
                        logger.exception("TTS speak failed: %s", e)
                        self._debug("Error (TTS): %s" % e)
                if self._wait_until_done_before_listen:
                    try:
                        self._tts.wait_until_done()
                    except Exception as e:
                        logger.debug("TTS wait_until_done: %s", e)
                self._on_status("Listening...")
            except Exception as e:
                logger.exception("Respond block failed: %s", e)
                self._debug("Error (respond): %s" % e)
                self._on_error("Response failed; check Ollama and log.")
                self._on_status("Listening...")

        self._debug("Pipeline stopped")
        self._capture.stop()
        self._stt.stop()
        if self._running:
            self._on_status("Stopped")
        self._running = False
