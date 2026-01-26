"""
No-op speaker filter: accept all segments.
"""
from __future__ import annotations

from speaker.base import SpeakerFilter


class NoOpSpeakerFilter(SpeakerFilter):
    """Accepts all audio; no speaker verification."""

    def accept(self, transcription: str, audio_bytes: bytes | None = None) -> bool:
        return True
