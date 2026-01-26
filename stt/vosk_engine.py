"""
Vosk-based speech-to-text engine (low latency, Pi-friendly).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from stt.base import STTEngine

logger = logging.getLogger(__name__)


class VoskEngine(STTEngine):
    """
    Transcribe audio using a Vosk model. Expects 16kHz mono int16 PCM.
    """

    def __init__(self, model_path: str | None = None) -> None:
        self._model_path = model_path
        self._model: Any = None

    def start(self) -> None:
        path: Path | None = None
        if self._model_path:
            path = Path(self._model_path)
        if not path or not path.exists():
            path = Path(__file__).resolve().parent.parent.parent / "models" / "vosk-model-small-en-us-0.15"
        if not path.exists():
            logger.info(
                "No Vosk model found. Set config stt.vosk.model_path to a downloaded model dir (e.g. models/vosk-model-small-en-us-0.15). STT disabled."
            )
            self._model = None
            return
        try:
            from vosk import Model

            self._model = Model(str(path))
            logger.info("Vosk model loaded: %s", path)
        except Exception as e:
            logger.warning("Failed to load Vosk model from %s: %s. STT disabled.", path, e)
            self._model = None

    def stop(self) -> None:
        self._model = None

    def transcribe(self, audio_bytes: bytes) -> str:
        if self._model is None:
            return ""
        try:
            from vosk import KaldiRecognizer

            # New recognizer per chunk: Vosk FinalResult() finalizes the recognizer;
            # reuse after that raises. Model is reused (loaded in start()).
            rec = KaldiRecognizer(self._model, 16000)
            rec.AcceptWaveform(audio_bytes)
            result = json.loads(rec.FinalResult())
            text = (result.get("text") or "").strip()
            return text
        except Exception as e:
            logger.warning("Vosk transcribe error: %s", e)
            return ""
