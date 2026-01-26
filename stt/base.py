"""
Abstract speech-to-text engine interface.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class STTEngine(ABC):
    """Interface for local STT. Implementations: Vosk, Whisper."""

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
