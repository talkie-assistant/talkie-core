"""
Orchestrator: audio -> STT -> speaker filter -> LLM -> persistence -> UI callbacks.
Runs the capture/transcribe/respond loop in a background thread.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Callable

from audio.capture import AudioCapture
from audio.device_utils import MicrophoneError
from audio.level import chunk_rms_level
from llm.client import OllamaClient
from llm.prompts import (
    build_document_qa_system_prompt,
    build_document_qa_user_prompt,
    build_regeneration_prompts,
    build_system_prompt,
    build_user_prompt,
    parse_regeneration_response,
)
from persistence.history_repo import HistoryRepo
from persistence.settings_repo import SettingsRepo
from persistence.training_repo import TrainingRepo
from profile.store import LanguageProfile
from speaker.base import SpeakerFilter
from speaker.noop_filter import NoOpSpeakerFilter
from stt.base import STTEngine
from stt.vosk_engine import VoskEngine
from stt.whisper_engine import WhisperEngine
from tts.base import TTSEngine
from tts.noop_engine import NoOpTTSEngine
from tts.say_engine import SayEngine

logger = logging.getLogger(__name__)


def _make_stt(config: dict) -> STTEngine:
    stt_cfg = config.get("stt", {})
    engine = (stt_cfg.get("engine") or "vosk").lower()
    if engine == "whisper":
        path = (stt_cfg.get("whisper") or {}).get("model_path")
        return WhisperEngine(model_path=path)
    path = (stt_cfg.get("vosk") or {}).get("model_path")
    return VoskEngine(model_path=path)


def _get_auto_sensitivity_config(audio_cfg: dict) -> dict:
    """Return auto-sensitivity options from config; disabled if not set."""
    enabled = audio_cfg.get("auto_sensitivity", False)
    return {
        "enabled": bool(enabled),
        "min_level": max(0.0, min(1.0, float(audio_cfg.get("auto_sensitivity_min_level", 0.002)))),
        "max_level": max(0.0, min(1.0, float(audio_cfg.get("auto_sensitivity_max_level", 0.08)))),
        "step": max(0.05, min(2.0, float(audio_cfg.get("auto_sensitivity_step", 0.25)))),
        "cooldown_chunks": max(1, int(audio_cfg.get("auto_sensitivity_cooldown_chunks", 3))),
    }


def _make_tts(config: dict, settings_repo: SettingsRepo | None = None) -> TTSEngine:
    tts_cfg = config.get("tts", {})
    if not tts_cfg.get("enabled", False):
        return NoOpTTSEngine()
    engine = (tts_cfg.get("engine") or "say").lower()
    if engine == "say":
        voice = None
        if settings_repo:
            try:
                voice = settings_repo.get("tts_voice")
            except Exception:
                pass
        if not voice:
            voice = tts_cfg.get("voice")
        if not voice:
            voice = "Daniel"
        return SayEngine(voice=voice)
    return NoOpTTSEngine()


def _apply_calibration_overlay(audio_cfg: dict, settings_repo: SettingsRepo | None) -> dict:
    """Overlay calibration_* from settings_repo onto audio config. Returns a new dict."""
    out = dict(audio_cfg)
    if not settings_repo:
        return out
    try:
        sens_s = settings_repo.get("calibration_sensitivity")
        if sens_s is not None and sens_s.strip():
            try:
                s = float(sens_s)
                out["sensitivity"] = max(0.5, min(10.0, s))
            except (TypeError, ValueError):
                logger.debug("Invalid calibration_sensitivity, using config")
        chunk_s = settings_repo.get("calibration_chunk_duration_sec")
        if chunk_s is not None and chunk_s.strip():
            try:
                c = float(chunk_s)
                out["chunk_duration_sec"] = max(4.0, min(15.0, c))
            except (TypeError, ValueError):
                logger.debug("Invalid calibration_chunk_duration_sec, using config")
    except Exception as e:
        logger.debug("Calibration overlay failed: %s", e)
    return out


def _apply_llm_calibration_overlay(llm_cfg: dict, settings_repo: SettingsRepo | None) -> dict:
    """Overlay calibration_min_transcription_length from settings_repo onto llm config. Returns a new dict."""
    out = dict(llm_cfg)
    if not settings_repo:
        return out
    try:
        min_len_s = settings_repo.get("calibration_min_transcription_length")
        if min_len_s is not None and min_len_s.strip():
            try:
                n = int(min_len_s)
                out["min_transcription_length"] = max(0, n)
            except (TypeError, ValueError):
                logger.debug("Invalid calibration_min_transcription_length, using config")
    except Exception as e:
        logger.debug("LLM calibration overlay failed: %s", e)
    return out


def create_pipeline(
    config: dict,
    history_repo: HistoryRepo,
    settings_repo: SettingsRepo | None = None,
    training_repo: TrainingRepo | None = None,
) -> Pipeline:
    """Build pipeline from config, history repo, optional settings repo, and optional training repo."""
    audio_cfg = _apply_calibration_overlay(config.get("audio", {}), settings_repo)
    capture = AudioCapture(
        device_id=audio_cfg.get("device_id"),
        sample_rate=int(audio_cfg.get("sample_rate", 16000)),
        chunk_duration_sec=float(audio_cfg.get("chunk_duration_sec", 5.0)),
        sensitivity=float(audio_cfg.get("sensitivity", 2.5)),
    )
    stt = _make_stt(config)
    speaker_filter = NoOpSpeakerFilter()
    ollama_cfg = config.get("ollama", {})
    client = OllamaClient(
        base_url=ollama_cfg.get("base_url", "http://localhost:11434"),
        model_name=ollama_cfg.get("model_name", "mistral"),
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
    tts = _make_tts(config, settings_repo)
    llm_cfg = _apply_llm_calibration_overlay(config.get("llm", {}), settings_repo)
    return Pipeline(
        capture=capture,
        stt=stt,
        speaker_filter=speaker_filter,
        llm_client=client,
        history_repo=history_repo,
        language_profile=profile,
        tts=tts,
        llm_prompt_config=llm_cfg,
        auto_sensitivity=_get_auto_sensitivity_config(audio_cfg),
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
        # Skip consecutive duplicate transcriptions so we only respond once per distinct phrase
        self._last_processed_transcription: str | None = None
        # Skip when transcription matches what we just spoke (echo from speaker into mic)
        self._last_spoken_response: str | None = None

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

    def set_on_training_transcription(self, callback: Callable[[str], None] | None) -> None:
        """Set callback invoked when in training mode with the transcribed text (e.g. to store as a fact)."""
        self._on_training_transcription = callback

    def set_rag_retriever(self, retriever: Callable[..., str] | None) -> None:
        """Set optional RAG retriever: (query, top_k=None) -> context string. Only invoked when document_qa_mode is True."""
        self._rag_retriever = retriever

    def set_rag_has_documents(self, has_documents: Callable[[], bool] | None) -> None:
        """Set optional callable to check if RAG has any indexed documents (for empty-state)."""
        self._rag_has_documents = has_documents

    def set_document_qa_mode(self, on: bool) -> None:
        """When True, next utterance is treated as a document question: retrieve and use document-QA prompts."""
        self._document_qa_mode = on

    def set_document_qa_top_k(self, top_k: int) -> None:
        """Number of chunks to retrieve when in document-QA mode."""
        self._document_qa_top_k = max(1, min(20, top_k))

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

    def start(self) -> None:
        if self._running:
            return
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
                logger.warning("Pipeline worker thread did not stop within timeout; may still be running")
            self._thread = None
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
            return
        except Exception as e:
            self._debug(f"Pipeline start failed: {e}")
            self._on_error(str(e))
            logger.exception("Pipeline start failed: %s", e)
            self._running = False
            self._capture.stop()
            return

        self._debug("Pipeline running (audio + STT started)")
        if not self._llm.check_connection():
            self._debug("Error: Ollama not reachable. Is it running?")
            self._on_error("Ollama not reachable. Is it running?")
            self._running = False
            self._capture.stop()
            self._stt.stop()
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

            self._debug("Audio level (chunk RMS, waveform): %.4f" % level)
            self._debug("Audio chunk received (%d bytes), transcribing..." % len(chunk))
            self._on_status("Transcribing...")
            try:
                text = self._stt.transcribe(chunk).strip()
            except Exception as e:
                logger.exception("STT transcribe failed: %s", e)
                self._debug("Error (STT transcribe): %s" % e)
                self._on_error("Speech recognition failed")
                continue
            if not text:
                min_l = self._auto_sensitivity.get("min_level", 0.002)
                max_l = self._auto_sensitivity.get("max_level", 0.08)
                self._debug("STT: (empty) level=%.4f (auto sens: %s, band %.4f–%.4f)" % (
                    level, "on" if self._auto_sensitivity.get("enabled") else "off", min_l, max_l))
                if level > max_l:
                    self._debug("High level but no transcription – check mic is 16000 Hz and STT engine (e.g. Whisper model loaded).")
                # Auto sensitivity: only when level is in "quiet" band; above max_l we don't assume too quiet
                if self._auto_sensitivity.get("enabled") and self._auto_sensitivity_cooldown <= 0:
                    if min_l <= level <= max_l:
                        step = self._auto_sensitivity.get("step", 0.25)
                        current = self._capture.get_sensitivity()
                        new_sens = min(10.0, current + step)
                        if new_sens > current:
                            self._capture.set_sensitivity(new_sens)
                            self._auto_sensitivity_cooldown = self._auto_sensitivity.get("cooldown_chunks", 3)
                            self._debug("Auto sensitivity: raised to %.1f (level=%.4f, no speech)" % (new_sens, level))
                            try:
                                self._on_sensitivity_adjusted(new_sens)
                            except Exception as e:
                                logger.debug("on_sensitivity_adjusted failed: %s", e)
                                self._debug("Error (sensitivity adjusted callback): %s" % e)
                if self._auto_sensitivity_cooldown > 0:
                    self._auto_sensitivity_cooldown -= 1
                continue

            self._debug("Transcription: " + text)

            try:
                min_len = self._llm_prompt_config.get("min_transcription_length")
                min_len = int(min_len) if min_len is not None else 0
            except (TypeError, ValueError):
                min_len = 0
            if min_len > 0 and len(text) < min_len:
                self._debug("Transcription too short (%d < %d), skipping LLM to avoid spurious responses" % (len(text), min_len))
                continue

            if not self._speaker_filter.accept(text, chunk):
                self._debug("Speaker filter: rejected")
                continue

            # Only process each distinct transcription once; skip consecutive duplicates
            text_normalized = text.strip()
            if text_normalized and self._last_processed_transcription is not None:
                if text_normalized == self._last_processed_transcription.strip():
                    self._debug("Same transcription as last; skipping to avoid repeating response")
                    continue
            self._last_processed_transcription = text_normalized or self._last_processed_transcription

            # Skip when transcription matches our last spoken response (mic picking up TTS = echo loop)
            if self._last_spoken_response and text_normalized:
                if text_normalized.lower() == self._last_spoken_response.strip().lower():
                    self._debug("Transcription matches last spoken response (echo); skipping")
                    continue

            # User started speaking again: abort any playing TTS so we can process this (retry).
            try:
                self._tts.stop()
            except Exception as e:
                logger.debug("TTS stop (abort on new speech) failed: %s", e)

            # Regeneration: raw transcription -> one sentence with high probability of user intent (Ollama).
            intent_sentence = text
            used_regeneration = False
            regeneration_certainty: int | None = None
            if self._llm_prompt_config.get("regeneration_enabled", True):
                request_certainty = self._llm_prompt_config.get("regeneration_request_certainty", True)
                reg_system, reg_user = build_regeneration_prompts(
                    text,
                    system_prompt=self._llm_prompt_config.get("regeneration_system_prompt"),
                    user_prompt_template=self._llm_prompt_config.get("regeneration_user_prompt_template"),
                    request_certainty=request_certainty,
                )
                self._debug("Ollama regeneration: raw -> intent sentence" + (" (with certainty)" if request_certainty else ""))
                regenerated = self._llm.generate(reg_user, reg_system)
                if regenerated and regenerated.strip():
                    intent_sentence, regeneration_certainty = parse_regeneration_response(regenerated)
                    used_regeneration = True
                    if regeneration_certainty is not None:
                        self._debug("Regenerated intent: %s (certainty %d%%)" % (intent_sentence, regeneration_certainty))
                    else:
                        self._debug("Regenerated intent: " + intent_sentence)
                else:
                    self._debug("Regeneration empty or fallback; using raw transcription")

            if self._training_mode and self._on_training_transcription is not None:
                self._debug("Training mode: saving sentence as fact")
                try:
                    self._on_training_transcription(text)
                    self._profile.invalidate_cache()
                except Exception as e:
                    logger.exception("Training transcription callback failed: %s", e)
                    self._debug("Error (training callback): %s" % e)
                self._on_status("Listening...")
                continue

            self._on_status("Responding...")

            if self._document_qa_mode:
                # Document Q&A: empty-state check, then retrieve and answer from context only.
                if not self._rag_has_documents or not self._rag_has_documents():
                    response = "No documents are indexed yet. Open Documents, add files, and click Vectorize."
                    self._debug("Document QA: no documents indexed, short-circuit")
                else:
                    retrieved_context = ""
                    if self._rag_retriever is not None:
                        try:
                            retrieved_context = self._rag_retriever(intent_sentence, self._document_qa_top_k) or ""
                        except Exception as e:
                            logger.exception("RAG retriever failed: %s", e)
                            self._debug("Error (RAG retriever): %s" % e)
                    system = build_document_qa_system_prompt(retrieved_context)
                    user_prompt = build_document_qa_user_prompt(intent_sentence)
                    self._debug("Document QA: Ollama with retrieved context (%d chars)" % len(retrieved_context))
                    response = self._llm.generate(user_prompt, system)
                    self._debug("Ollama API response (%d chars):" % len(response))
            else:
                use_regeneration_as_response = self._llm_prompt_config.get("use_regeneration_as_response", True)
                certainty_threshold = int(self._llm_prompt_config.get("regeneration_certainty_threshold", 70))
                certainty_threshold = max(0, min(100, certainty_threshold))

                # If we heard the full sentence and the LLM effectively agrees (same or nearly same), just repeat it.
                def _normalize_for_repeat(s: str) -> str:
                    s = (s or "").strip().lower()
                    s = " ".join(s.split())
                    return s.rstrip(".!? ")
                transcript_norm = _normalize_for_repeat(text_normalized)
                intent_norm = _normalize_for_repeat(intent_sentence)
                llm_agrees_repeat = (
                    used_regeneration
                    and transcript_norm
                    and intent_norm
                    and transcript_norm == intent_norm
                )
                if llm_agrees_repeat:
                    response = intent_sentence.strip()
                    self._debug("Heard full sentence; LLM agrees it makes sense — repeating it (skipping completion)")
                else:
                    skip_completion = (
                        use_regeneration_as_response
                        and used_regeneration
                        and (regeneration_certainty is None or regeneration_certainty >= certainty_threshold)
                    )
                    if skip_completion:
                        response = intent_sentence
                        self._debug(
                            "Using regenerated intent as response (skipping completion)"
                            + (" (certainty %d%% >= %d%%)" % (regeneration_certainty, certainty_threshold) if regeneration_certainty is not None else "")
                        )
                    else:
                        if used_regeneration and regeneration_certainty is not None:
                            self._debug("Certainty %d%% < %d%%, running completion call" % (regeneration_certainty, certainty_threshold))
                        try:
                            profile_context = self._profile.get_context_for_llm()
                        except Exception as e:
                            logger.exception("Profile get_context_for_llm failed: %s", e)
                            self._debug("Error (profile get_context_for_llm): %s" % e)
                            profile_context = ""
                        retrieved_context = ""
                        system = build_system_prompt(
                            profile_context,
                            system_base=self._llm_prompt_config.get("system_prompt"),
                            retrieved_context=retrieved_context or None,
                        )
                        user_prompt = build_user_prompt(
                            intent_sentence,
                            user_prompt_template=self._llm_prompt_config.get("user_prompt_template"),
                        )
                        model_name = self._llm.model_name
                        self._debug("Ollama API call: POST %s/api/generate model=%s" % (self._llm.base_url, model_name))
                        self._debug("Ollama system prompt (%d chars):" % len(system))
                        self._debug((system[:2000] + "...") if len(system) > 2000 else (system or "(empty)"))
                        self._debug("Ollama user prompt:")
                        self._debug(user_prompt)
                        response = self._llm.generate(user_prompt, system)
                        self._debug("Ollama API response (%d chars):" % len(response))
                        self._debug(response)

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

            self._on_response(response, interaction_id)
            self._last_spoken_response = (response or "").strip()
            try:
                self._tts.speak(response)
                self._debug("TTS: started speaking (speak again to abort and retry)")
            except Exception as e:
                logger.exception("TTS speak failed: %s", e)
                self._debug("Error (TTS): %s" % e)
            # Do not wait for TTS to finish; return to listening so user can speak to abort and retry.
            self._on_status("Listening...")

        self._debug("Pipeline stopped")
        self._capture.stop()
        self._stt.stop()
        if self._running:
            self._on_status("Stopped")
        self._running = False
