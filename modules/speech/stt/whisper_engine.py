"""
Whisper-based STT using faster-whisper (CTranslate2).
Expects 16 kHz mono int16 PCM; converts to float32 for transcription.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from .base import STTEngine

logger = logging.getLogger(__name__)


def ensure_whisper_model_downloaded(model_path: str = "base") -> None:
    """
    Download the Whisper model if not already cached (synchronous).
    No-op if the model is already present in the Hugging Face cache.
    Use from ./talkie download so first speech use does not block on network.
    """
    from faster_whisper import WhisperModel

    WhisperModel(model_path, device="cpu", compute_type="int8")


def _resolve_device(device: str) -> tuple[str, str]:
    """Return (device, compute_type). device is 'cpu' or 'cuda'."""
    want = (device or "cpu").strip().lower()
    if want == "cuda":
        return ("cuda", "float16")
    if want == "auto":
        try:
            import torch

            if torch.cuda.is_available():
                return ("cuda", "float16")
        except Exception:
            pass
        return ("cpu", "int8")
    return ("cpu", "int8")


class WhisperEngine(STTEngine):
    """
    Transcribe audio using faster-whisper. Expects 16 kHz mono int16 PCM.
    Model is loaded in start(); use config stt.whisper.model_path (e.g. "base", "small").
    Optional: device (cpu | cuda | auto), cpu_threads (CPU only), beam_size (1=faster, 5=more accurate).
    """

    def __init__(
        self,
        model_path: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        cfg = config or {}
        self._model_path = (
            model_path or cfg.get("model_path") or "base"
        ).strip() or "base"
        self._model: Any = None
        self._logged_no_model = False
        self._device, self._compute_type = _resolve_device(cfg.get("device") or "cpu")
        self._cpu_threads = cfg.get("cpu_threads")
        if self._cpu_threads is not None:
            self._cpu_threads = int(self._cpu_threads)
        self._beam_size = cfg.get("beam_size")
        if self._beam_size is not None:
            self._beam_size = int(self._beam_size)
        if self._beam_size is None or self._beam_size < 1:
            self._beam_size = 1  # faster; use 5 for better accuracy
        # no_speech_threshold: float or None; when set, pass to transcribe() and filter segments by no_speech_prob
        ns = cfg.get("no_speech_threshold")
        self._no_speech_threshold: float | None = None
        if ns is not None:
            try:
                self._no_speech_threshold = float(ns)
                if self._no_speech_threshold < 0 or self._no_speech_threshold > 1:
                    self._no_speech_threshold = 0.6
            except (TypeError, ValueError):
                pass
        # min_avg_logprob: float or None; when set, discard segments with avg_logprob below this (e.g. -1)
        ml = cfg.get("min_avg_logprob")
        self._min_avg_logprob: float | None = None
        if ml is not None:
            try:
                self._min_avg_logprob = float(ml)
            except (TypeError, ValueError):
                pass

    def start(self) -> None:
        if self._model is not None:
            return
        try:
            from faster_whisper import WhisperModel

            kwargs: dict[str, Any] = {"compute_type": self._compute_type}
            if self._device == "cuda":
                kwargs["device_index"] = 0
            if self._device == "cpu" and self._cpu_threads is not None:
                kwargs["cpu_threads"] = self._cpu_threads
            self._model = WhisperModel(self._model_path, device=self._device, **kwargs)
            logger.info(
                "Whisper model loaded: %s (device=%s, compute_type=%s)",
                self._model_path,
                self._device,
                self._compute_type,
            )
        except Exception as e:
            logger.warning(
                "Failed to load Whisper model (%s): %s. STT disabled.",
                self._model_path,
                e,
            )
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
            audio_array = (
                np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            )
            audio_array = np.ascontiguousarray(audio_array)
            no_speech_threshold = self._no_speech_threshold
            segments, _ = self._model.transcribe(
                audio_array,
                language="en",
                vad_filter=False,
                no_speech_threshold=no_speech_threshold,
                without_timestamps=True,
                beam_size=self._beam_size,
            )
            segments_list = list(segments)

            def _include_segment(s: Any) -> bool:
                if not (s.text and s.text.strip()):
                    return False
                if (
                    self._no_speech_threshold is not None
                    and getattr(s, "no_speech_prob", None) is not None
                ):
                    if s.no_speech_prob > self._no_speech_threshold:
                        return False
                if (
                    self._min_avg_logprob is not None
                    and getattr(s, "avg_logprob", None) is not None
                ):
                    if s.avg_logprob < self._min_avg_logprob:
                        return False
                return True

            text = " ".join(
                s.text.strip() for s in segments_list if _include_segment(s)
            ).strip()
            if not text:
                logger.info(
                    "Whisper returned no text for this chunk (%d segment(s)). Try speaking closer, raising sensitivity in config, or check mic sample rate is 16000 Hz.",
                    len(segments_list),
                )
            return text
        except Exception as e:
            logger.warning("Whisper transcribe error: %s", e)
            return ""

    def transcribe_with_confidence(
        self, audio_bytes: bytes
    ) -> tuple[str, float | None]:
        """
        Transcribe and return (text, confidence 0.0--1.0 or None).
        Confidence is the mean of (1 - no_speech_prob) over included segments.
        """
        if not audio_bytes:
            return ("", None)
        if self._model is None:
            if not self._logged_no_model:
                logger.warning(
                    "Whisper model not loaded; STT disabled. Check startup log for 'Failed to load Whisper model'."
                )
                self._logged_no_model = True
            return ("", None)
        try:
            audio_array = (
                np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            )
            audio_array = np.ascontiguousarray(audio_array)
            no_speech_threshold = self._no_speech_threshold
            segments, _ = self._model.transcribe(
                audio_array,
                language="en",
                vad_filter=False,
                no_speech_threshold=no_speech_threshold,
                without_timestamps=True,
                beam_size=self._beam_size,
            )
            segments_list = list(segments)

            def _include_segment(s: Any) -> bool:
                if not (s.text and s.text.strip()):
                    return False
                if (
                    self._no_speech_threshold is not None
                    and getattr(s, "no_speech_prob", None) is not None
                ):
                    if s.no_speech_prob > self._no_speech_threshold:
                        return False
                if (
                    self._min_avg_logprob is not None
                    and getattr(s, "avg_logprob", None) is not None
                ):
                    if s.avg_logprob < self._min_avg_logprob:
                        return False
                return True

            included = [s for s in segments_list if _include_segment(s)]
            text = " ".join(s.text.strip() for s in included).strip()
            conf = None
            probs = [
                1.0 - getattr(s, "no_speech_prob", 0.0)
                for s in included
                if getattr(s, "no_speech_prob", None) is not None
            ]
            if probs:
                conf = sum(probs) / len(probs)
                conf = max(0.0, min(1.0, conf))
            if not text:
                logger.info(
                    "Whisper returned no text for this chunk (%d segment(s)). Try speaking closer, raising sensitivity in config, or check mic sample rate is 16000 Hz.",
                    len(segments_list),
                )
            return (text, conf)
        except Exception as e:
            logger.warning("Whisper transcribe error: %s", e)
            return ("", None)
