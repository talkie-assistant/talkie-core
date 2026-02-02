"""
Core speech abstractions: interfaces and no-op implementations.
Used by the pipeline and by the speech module; concrete implementations live in modules.speech.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable


class MicrophoneError(Exception):
    """Raised when the microphone is unavailable or disconnected."""


class AudioCapture(ABC):
    """
    Capture audio chunks from a microphone.
    Use start() then read_chunk() in a loop; stop() to release.
    """

    @abstractmethod
    def start(self) -> None:
        """Open the audio input stream."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Stop and close the stream."""
        ...

    @abstractmethod
    def read_chunk(
        self, on_level: Callable[[float], None] | None = None
    ) -> bytes | None:
        """
        Read one chunk of audio. If on_level is provided, call it with RMS (0.0--1.0).
        Returns None if not running or on skip.
        """
        ...

    def get_sensitivity(self) -> float:
        """Current sensitivity (gain)."""
        return 1.0

    def set_sensitivity(self, value: float) -> None:
        """Update sensitivity at runtime. Clamped to 0.1--10.0."""
        pass


class STTEngine(ABC):
    """Interface for local speech-to-text. Implementations: Vosk, Whisper."""

    @abstractmethod
    def transcribe(self, audio_bytes: bytes) -> str:
        """
        Transcribe raw audio (e.g. int16 mono at 16kHz) to text.
        Returns empty string if nothing recognized.
        """
        ...

    def start(self) -> None:
        """Optional: load model / warmup. No-op by default."""
        pass

    def stop(self) -> None:
        """Optional: release model. No-op by default."""
        pass


class TTSEngine(ABC):
    """Speak text via system or external TTS."""

    @abstractmethod
    def speak(self, text: str) -> None:
        """Speak the given text."""
        ...

    def wait_until_done(self) -> None:
        """Block until playback finishes. No-op by default."""
        pass

    def stop(self) -> None:
        """Abort current playback. No-op by default."""
        pass


class SpeakerFilter(ABC):
    """Decide whether to process a segment as the target user."""

    @abstractmethod
    def accept(self, transcription: str, audio_bytes: bytes | None = None) -> bool:
        """Return True if this segment should be processed."""
        ...


# --- No-op implementations (used when speech module is disabled) ---


class NoOpCapture(AudioCapture):
    """Capture that never yields chunks; use when speech module is unavailable."""

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def read_chunk(
        self, on_level: Callable[[float], None] | None = None
    ) -> bytes | None:
        return None


class NoOpSTTEngine(STTEngine):
    """STT that always returns empty string."""

    def transcribe(self, audio_bytes: bytes) -> str:
        return ""


class NoOpTTSEngine(TTSEngine):
    """TTS that does nothing."""

    def speak(self, text: str) -> None:
        pass


class NoOpSpeakerFilter(SpeakerFilter):
    """Accepts all segments."""

    def accept(self, transcription: str, audio_bytes: bytes | None = None) -> bool:
        return True


__all__ = [
    "AudioCapture",
    "MicrophoneError",
    "NoOpCapture",
    "NoOpSpeakerFilter",
    "NoOpSTTEngine",
    "NoOpTTSEngine",
    "SpeakerFilter",
    "STTEngine",
    "TTSEngine",
]
