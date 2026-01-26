"""
Whisper-based STT using faster-whisper (CTranslate2).
Expects 16 kHz mono int16 PCM; converts to float32 for transcription.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

from stt.base import STTEngine

logger = logging.getLogger(__name__)


class WhisperEngine(STTEngine):
    """
    Transcribe audio using faster-whisper. Expects 16 kHz mono int16 PCM.
    Model is loaded in start(); use config stt.whisper.model_path (e.g. "base", "small").
    """

    def __init__(self, model_path: str | None = None) -> None:
        self._model_path = model_path or "small"
        self._model: Any = None
        self._logged_no_model = False

    def start(self) -> None:
        if self._model is not None:
            return
        try:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self._model_path,
                device="cpu",
                compute_type="int8",
            )
            logger.info("Whisper model loaded: %s", self._model_path)
        except Exception as e:
            logger.warning("Failed to load Whisper model (%s): %s. STT disabled.", self._model_path, e)
            self._model = None

    def stop(self) -> None:
        self._model = None
        self._logged_no_model = False

    def transcribe(self, audio_bytes: bytes) -> str:
        if not audio_bytes:
            return ""
        if self._model is None:
            if not self._logged_no_model:
                logger.warning(
                    "Whisper model not loaded; STT disabled. Check startup log for 'Failed to load Whisper model'."
                )
                self._logged_no_model = True
            return ""
        try:
            # 16 kHz mono int16 LE -> float32 [-1, 1]; contiguous for faster-whisper
            audio_array = (
                np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            )
            audio_array = np.ascontiguousarray(audio_array)
            # vad_filter=False: always transcribe the full chunk; VAD often filters out
            # quiet or atypical speech and returns empty
            # no_speech_threshold=None: do not skip segments as "silence"; produces text for quiet/atypical speech
            # without_timestamps=True: avoid timestamp tokens for short chunks; can improve reliability
            segments, _ = self._model.transcribe(
                audio_array,
                language="en",
                vad_filter=False,
                no_speech_threshold=None,
                without_timestamps=True,
            )
            segments_list = list(segments)
            text = " ".join(s.text.strip() for s in segments_list if s.text).strip()
            if not text:
                logger.info(
                    "Whisper returned no text for this chunk (%d segment(s)). Try speaking closer, raising sensitivity in config, or check mic sample rate is 16000 Hz.",
                    len(segments_list),
                )
            return text
        except Exception as e:
            logger.warning("Whisper transcribe error: %s", e)
            return ""
