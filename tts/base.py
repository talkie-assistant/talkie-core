"""
Abstract text-to-speech engine for speaking LLM responses.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class TTSEngine(ABC):
    """Speak text (e.g. Ollama response) via system or external TTS."""

    @abstractmethod
    def speak(self, text: str) -> None:
        """
        Speak the given text. May block until playback finishes
        or return after starting playback; implement in a thread if needed.
        """
        ...

    def wait_until_done(self) -> None:
        """
        If speak() started playback in the background, block until playback finishes.
        No-op by default. Override so the pipeline can avoid processing mic input while TTS is playing (prevents echo).
        """
        pass

    def stop(self) -> None:
        """
        Abort current playback if any. No-op by default. Override so the pipeline
        can stop TTS when the user starts speaking again (abort and retry).
        """
        pass
