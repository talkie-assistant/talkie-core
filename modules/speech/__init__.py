"""
Speech module: single internal library for audio capture, STT, TTS, speaker filter, calibration.
All construction goes through SpeechFactory; public API: create_speech_components(), apply_*_overlay().
"""

from __future__ import annotations

import logging
from typing import Any, NamedTuple

logger = logging.getLogger(__name__)


# --- Calibration overlay (shared logic; used by factory and public API) ---


def _overlay_audio_calibration(audio_cfg: dict, settings_repo: Any) -> dict:
    """Overlay calibration_* from settings_repo onto audio config. Returns new dict."""
    out = dict(audio_cfg)
    if settings_repo is None:
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


def _overlay_llm_calibration(llm_cfg: dict, settings_repo: Any) -> dict:
    """Overlay calibration_min_transcription_length from settings_repo onto llm config. Returns new dict."""
    out = dict(llm_cfg)
    if settings_repo is None:
        return out
    try:
        min_len_s = settings_repo.get("calibration_min_transcription_length")
        if min_len_s is not None and min_len_s.strip():
            try:
                n = int(min_len_s)
                out["min_transcription_length"] = max(0, n)
            except (TypeError, ValueError):
                logger.debug(
                    "Invalid calibration_min_transcription_length, using config"
                )
    except Exception as e:
        logger.debug("LLM calibration overlay failed: %s", e)
    return out


def apply_calibration_overlay(audio_cfg: dict, settings_repo: Any) -> dict:
    """Public API: overlay calibration_* from settings_repo onto audio config. Returns a new dict."""
    return _overlay_audio_calibration(audio_cfg, settings_repo)


def apply_llm_calibration_overlay(llm_cfg: dict, settings_repo: Any) -> dict:
    """Public API: overlay calibration_min_transcription_length onto llm config. Returns a new dict."""
    return _overlay_llm_calibration(llm_cfg, settings_repo)


# --- Factory: single place for constructing speech components (OOP) ---


class SpeechComponents(NamedTuple):
    """Immutable bundle of capture, STT, TTS, speaker filter, and auto_sensitivity config."""

    capture: Any
    stt: Any
    tts: Any
    speaker_filter: Any
    auto_sensitivity: dict


class SpeechFactory:
    """
    Builds all speech components from config and optional settings.
    Single responsibility: construction; uses app.abstractions interfaces.
    """

    def __init__(self, config: dict, settings_repo: Any = None) -> None:
        self._config = config
        self._settings_repo = settings_repo
        self._audio_cfg = _overlay_audio_calibration(
            config.get("audio", {}), settings_repo
        )

    def _auto_sensitivity_config(self) -> dict:
        cfg = self._audio_cfg
        enabled = cfg.get("auto_sensitivity", False)
        return {
            "enabled": bool(enabled),
            "min_level": max(
                0.0, min(1.0, float(cfg.get("auto_sensitivity_min_level", 0.002)))
            ),
            "max_level": max(
                0.0, min(1.0, float(cfg.get("auto_sensitivity_max_level", 0.08)))
            ),
            "step": max(0.05, min(2.0, float(cfg.get("auto_sensitivity_step", 0.25)))),
            "cooldown_chunks": max(
                1, int(cfg.get("auto_sensitivity_cooldown_chunks", 3))
            ),
        }

    def create_capture(self) -> Any:
        from .audio.capture import AudioCapture

        return AudioCapture(
            device_id=self._audio_cfg.get("device_id"),
            sample_rate=int(self._audio_cfg.get("sample_rate", 16000)),
            chunk_duration_sec=float(self._audio_cfg.get("chunk_duration_sec", 5.0)),
            sensitivity=float(self._audio_cfg.get("sensitivity", 2.5)),
        )

    def create_stt(self) -> Any:
        from .stt.vosk_engine import VoskEngine
        from .stt.whisper_engine import WhisperEngine

        stt_cfg = self._config.get("stt", {})
        engine = (stt_cfg.get("engine") or "vosk").lower()
        if engine == "whisper":
            whisper_cfg = (stt_cfg.get("whisper") or {}).copy()
            path = whisper_cfg.pop("model_path", None)
            return WhisperEngine(model_path=path, config=whisper_cfg)
        path = (stt_cfg.get("vosk") or {}).get("model_path")
        return VoskEngine(model_path=path)

    def create_tts(self) -> Any:
        from .tts.noop_engine import NoOpTTSEngine
        from .tts.say_engine import SayEngine

        tts_cfg = self._config.get("tts", {})
        if not tts_cfg.get("enabled", False):
            return NoOpTTSEngine()
        engine = (tts_cfg.get("engine") or "say").lower()
        if engine == "say":
            voice = None
            if self._settings_repo:
                try:
                    voice = self._settings_repo.get("tts_voice")
                except Exception:
                    pass
            if not voice:
                voice = tts_cfg.get("voice")
            if not voice:
                voice = "Daniel"
            return SayEngine(voice=voice)
        return NoOpTTSEngine()

    def create_speaker_filter(self) -> Any:
        from .calibration.voice_profile import is_voice_profile_available
        from .speaker.noop_filter import NoOpSpeakerFilter
        from .speaker.voice_filter import VoiceProfileSpeakerFilter

        if is_voice_profile_available(self._settings_repo):
            sample_rate = int(self._audio_cfg.get("sample_rate", 16000))
            logger.info(
                "Using saved voice profile: only the calibrated speaker will be accepted"
            )
            return VoiceProfileSpeakerFilter(
                settings_repo=self._settings_repo,
                sample_rate=sample_rate,
            )
        return NoOpSpeakerFilter()

    def create_components(self) -> SpeechComponents:
        """Build and return the full speech component bundle."""
        return SpeechComponents(
            capture=self.create_capture(),
            stt=self.create_stt(),
            tts=self.create_tts(),
            speaker_filter=self.create_speaker_filter(),
            auto_sensitivity=self._auto_sensitivity_config(),
        )


def create_speech_components(
    config: dict, settings_repo: Any = None
) -> SpeechComponents:
    """
    Single entry point: build capture, STT, TTS, and speaker filter from config.
    Applies calibration overlay; returns SpeechComponents.
    The speaker filter enforces the configured voice profile so the app only
    listens to the calibrated speaker; used by all modules and entry points
    (web, run, and remote speech server when it uses the same settings DB).
    If server mode is enabled, returns remote API clients instead.
    """
    # Check if server mode is enabled
    from modules.api.config import get_module_server_config, get_module_base_url

    server_config = get_module_server_config(config, "speech")
    if server_config is not None:
        # Server mode: return remote API clients
        from modules.api.client import ModuleAPIClient
        from modules.api.speech_client import (
            RemoteAudioCapture,
            RemoteSTTEngine,
            RemoteTTSEngine,
            RemoteSpeakerFilter,
        )

        base_url = get_module_base_url(server_config)
        client = ModuleAPIClient(
            base_url=base_url,
            timeout_sec=server_config["timeout_sec"],
            retry_max=server_config["retry_max"],
            retry_delay_sec=server_config["retry_delay_sec"],
            circuit_breaker_failure_threshold=server_config[
                "circuit_breaker_failure_threshold"
            ],
            circuit_breaker_recovery_timeout_sec=server_config[
                "circuit_breaker_recovery_timeout_sec"
            ],
            api_key=server_config["api_key"],
            module_name="speech",
            use_service_discovery=server_config.get("use_service_discovery", False),
            consul_host=server_config.get("consul_host"),
            consul_port=server_config.get("consul_port", 8500),
            keydb_host=server_config.get("keydb_host"),
            keydb_port=server_config.get("keydb_port", 6379),
            load_balancing_strategy=server_config.get(
                "load_balancing_strategy", "health_based"
            ),
            health_check_interval_sec=server_config.get(
                "health_check_interval_sec", 30.0
            ),
        )

        # Get auto_sensitivity config from local config (not from server)
        factory = SpeechFactory(config, settings_repo)
        auto_sensitivity = factory._auto_sensitivity_config()

        return SpeechComponents(
            capture=RemoteAudioCapture(client),
            stt=RemoteSTTEngine(client),
            tts=RemoteTTSEngine(client),
            speaker_filter=RemoteSpeakerFilter(client),
            auto_sensitivity=auto_sensitivity,
        )

    # In-process mode: return local implementations
    return SpeechFactory(config, settings_repo).create_components()


def register(context: dict) -> None:
    """
    Register speech components with the app context (two-phase).
    Phase 1 (context has no "pipeline"): set context["speech_components"].
    Phase 2 (context has "pipeline"): no-op; pipeline was built with those components.
    """
    if context.get("pipeline") is not None:
        return
    config = context.get("config")
    settings_repo = context.get("settings_repo")
    if config is None:
        return
    try:
        from modules.speech.tts.noop_engine import NoOpTTSEngine

        comps = create_speech_components(config, settings_repo)
        # Server uses NoOpTTSEngine so only the browser speaks
        context["speech_components"] = comps._replace(tts=NoOpTTSEngine())
    except Exception as e:
        logger.debug("Speech module register (phase 1) failed: %s", e)


__all__ = [
    "SpeechComponents",
    "SpeechFactory",
    "apply_calibration_overlay",
    "apply_llm_calibration_overlay",
    "create_speech_components",
    "register",
]
