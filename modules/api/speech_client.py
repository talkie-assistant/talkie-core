"""
Remote speech module API clients that implement the speech abstractions.
"""

from __future__ import annotations

import logging
from typing import Callable

from sdk import (
    AudioCapture,
    MicrophoneError,
    SpeakerFilter,
    STTEngine,
    TTSEngine,
)
from modules.api.client import ModuleAPIClient

logger = logging.getLogger(__name__)


class RemoteAudioCapture(AudioCapture):
    """Remote audio capture via HTTP API."""

    def __init__(self, client: ModuleAPIClient) -> None:
        self._client = client
        self._sensitivity = 1.0
        self._started = False

    def start(self) -> None:
        """Start audio capture on remote server."""
        try:
            self._client._request("POST", "/capture/start")
            self._started = True
        except Exception as e:
            logger.exception("Failed to start remote capture: %s", e)
            raise MicrophoneError(f"Remote capture start failed: {e}") from e

    def stop(self) -> None:
        """Stop audio capture on remote server."""
        try:
            if self._started:
                self._client._request("POST", "/capture/stop")
                self._started = False
        except Exception as e:
            logger.warning("Failed to stop remote capture: %s", e)

    def read_chunk(
        self, on_level: Callable[[float], None] | None = None
    ) -> bytes | None:
        """Read audio chunk from remote server."""
        if not self._started:
            return None
        try:
            response = self._client._request("POST", "/capture/read_chunk")
            audio_base64 = response.get("audio_base64", "")
            level = response.get("level", 0.0)

            if on_level is not None:
                try:
                    on_level(level)
                except Exception as e:
                    logger.debug("on_level callback failed: %s", e)

            if audio_base64:
                return self._client._decode_audio(audio_base64)
            return None
        except Exception as e:
            logger.debug("Remote capture read_chunk failed: %s", e)
            return None

    def get_sensitivity(self) -> float:
        """Get current sensitivity from remote server."""
        try:
            response = self._client._request("GET", "/capture/sensitivity")
            self._sensitivity = float(response.get("sensitivity", 1.0))
            return self._sensitivity
        except Exception as e:
            logger.debug("Failed to get remote sensitivity: %s", e)
            return self._sensitivity

    def set_sensitivity(self, value: float) -> None:
        """Set sensitivity on remote server."""
        value = max(0.1, min(10.0, value))
        try:
            self._client._request(
                "POST", "/capture/sensitivity", json_data={"sensitivity": value}
            )
            self._sensitivity = value
        except Exception as e:
            logger.debug("Failed to set remote sensitivity: %s", e)


class RemoteSTTEngine(STTEngine):
    """Remote STT engine via HTTP API."""

    def __init__(self, client: ModuleAPIClient) -> None:
        self._client = client
        self._started = False

    def start(self) -> None:
        """Start STT engine on remote server."""
        try:
            self._client._request("POST", "/stt/start")
            self._started = True
        except Exception as e:
            logger.warning("Failed to start remote STT: %s", e)

    def stop(self) -> None:
        """Stop STT engine on remote server."""
        try:
            if self._started:
                self._client._request("POST", "/stt/stop")
                self._started = False
        except Exception as e:
            logger.warning("Failed to stop remote STT: %s", e)

    def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe audio via remote server."""
        text, _ = self.transcribe_with_confidence(audio_bytes)
        return text

    def transcribe_with_confidence(
        self, audio_bytes: bytes
    ) -> tuple[str, float | None]:
        """Transcribe via remote server; returns (text, confidence or None)."""
        try:
            audio_base64 = self._client._encode_audio(audio_bytes)
            response = self._client._request(
                "POST",
                "/stt/transcribe",
                json_data={"audio_base64": audio_base64},
                timeout=30.0,  # Longer timeout for transcription
            )
            text = response.get("text", "").strip()
            conf = response.get("confidence")
            if conf is not None:
                try:
                    conf = float(conf)
                    conf = max(0.0, min(1.0, conf))
                except (TypeError, ValueError):
                    conf = None
            return (text, conf)
        except Exception as e:
            logger.debug("Remote STT transcribe failed: %s", e)
            return ("", None)


class RemoteTTSEngine(TTSEngine):
    """Remote TTS engine via HTTP API."""

    def __init__(self, client: ModuleAPIClient) -> None:
        self._client = client

    def speak(self, text: str) -> None:
        """Speak text via remote server."""
        if not text or not text.strip():
            return
        try:
            self._client._request(
                "POST", "/tts/speak", json_data={"text": text.strip()}
            )
        except Exception as e:
            logger.debug("Remote TTS speak failed: %s", e)

    def stop(self) -> None:
        """Stop TTS playback on remote server."""
        try:
            self._client._request("POST", "/tts/stop")
        except Exception as e:
            logger.debug("Remote TTS stop failed: %s", e)


class RemoteSpeakerFilter(SpeakerFilter):
    """Remote speaker filter via HTTP API."""

    def __init__(self, client: ModuleAPIClient) -> None:
        self._client = client
        self._last_reject_reason: str | None = None

    def get_last_reject_reason(self) -> str | None:
        """Return a short reason for the last rejection, or None."""
        return self._last_reject_reason

    def accept(self, transcription: str, audio_bytes: bytes | None = None) -> bool:
        """Check if transcription should be accepted via remote server."""
        self._last_reject_reason = None
        try:
            data: dict[str, str] = {"transcription": transcription}
            if audio_bytes is not None:
                data["audio_base64"] = self._client._encode_audio(audio_bytes)
            response = self._client._request(
                "POST", "/speaker_filter/accept", json_data=data
            )
            accept = bool(response.get("accept", True))
            if not accept:
                self._last_reject_reason = response.get("reason")
            return accept
        except Exception as e:
            logger.debug("Remote speaker filter accept failed: %s", e)
            return True  # Default to accept on error
