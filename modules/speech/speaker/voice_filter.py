"""
Speaker filter that accepts only audio matching the enrolled user voice profile.
Rejects TTS echo and other speakers when a voice profile is calibrated.
"""

from __future__ import annotations

import logging
from typing import Any

from sdk.abstractions import SpeakerFilter

from modules.speech.calibration.voice_profile import (
    _get_encoder,
    get_similarity_threshold,
    load_embedding,
    similarity_to_user,
)

logger = logging.getLogger(__name__)

# Minimum audio length (seconds) to run verification; shorter segments are accepted to avoid false rejects
MIN_VERIFY_SEC = 0.5


class VoiceProfileSpeakerFilter(SpeakerFilter):
    """
    Accepts a segment only if its speaker embedding matches the enrolled user profile.
    When no profile is stored, accepts all (backward compatible). Does not pick up
    the app's own TTS (pipeline also skips by text match) or other people.
    """

    def __init__(
        self,
        settings_repo: Any | None = None,
        sample_rate: int = 16000,
    ) -> None:
        self._settings_repo = settings_repo
        self._sample_rate = sample_rate
        self._encoder: Any = None
        self._profile_loaded = False
        self._cached_embedding: Any = None
        self._cached_threshold: float | None = None
        self._last_reject_reason: str | None = None

    def _ensure_encoder(self) -> Any | None:
        if self._encoder is None:
            self._encoder = _get_encoder()
        return self._encoder

    def _ensure_profile_cached(self) -> None:
        """Load voice profile embedding and threshold once from settings; reuse for all segments."""
        if self._profile_loaded:
            return
        self._profile_loaded = True
        self._cached_embedding = load_embedding(self._settings_repo)
        self._cached_threshold = (
            get_similarity_threshold(self._settings_repo)
            if self._cached_embedding is not None
            else None
        )

    def get_last_reject_reason(self) -> str | None:
        """Return a short reason for the last rejection, or None."""
        return self._last_reject_reason

    def accept(self, transcription: str, audio_bytes: bytes | None = None) -> bool:
        self._last_reject_reason = None
        self._ensure_profile_cached()
        if self._cached_embedding is None:
            return True
        # When a voice profile is enrolled, only accept if we can verify the speaker.
        if audio_bytes is None:
            self._last_reject_reason = "no audio to verify"
            logger.debug("Speaker filter: rejected (no audio to verify)")
            return False
        if len(audio_bytes) < self._sample_rate * 2 * MIN_VERIFY_SEC:
            return True  # Too short to verify; accept to avoid rejecting short user utterances
        encoder = self._ensure_encoder()
        if encoder is None:
            self._last_reject_reason = "voice profile enrolled but resemblyzer unavailable"
            logger.warning(
                "Speaker filter: voice profile enrolled but resemblyzer unavailable; rejecting (only calibrated speaker allowed)"
            )
            return False
        threshold = self._cached_threshold
        sim = similarity_to_user(
            audio_bytes,
            self._sample_rate,
            self._cached_embedding,
            encoder,
        )
        if threshold is not None and sim >= threshold:
            return True
        self._last_reject_reason = f"similarity {sim:.2f} < {threshold:.2f}"
        logger.debug(
            "Speaker filter: rejected (similarity %.2f < %.2f)",
            sim,
            threshold,
        )
        return False
