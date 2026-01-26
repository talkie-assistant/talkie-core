"""
No-op TTS: do nothing (when TTS is disabled).
"""
from __future__ import annotations

from tts.base import TTSEngine


class NoOpTTSEngine(TTSEngine):
    """Does not speak; use when TTS is disabled in config."""

    def speak(self, text: str) -> None:
        pass
