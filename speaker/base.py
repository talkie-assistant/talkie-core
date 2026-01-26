"""
Abstract speaker filter (verification / diarization).
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class SpeakerFilter(ABC):
    """Decide whether to process a segment as the target user."""

    @abstractmethod
    def accept(self, transcription: str, audio_bytes: bytes | None = None) -> bool:
        """
        Return True if this segment should be processed (e.g. from the primary user).
        audio_bytes optional for embedding-based implementations.
        """
        ...
