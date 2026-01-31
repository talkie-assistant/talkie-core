"""
Voice profile calibration: enroll user voice, persist embedding, compare at runtime.
Ensures the app listens only to the enrolled speaker (not TTS echo or other people).
Uses resemblyzer for speaker embeddings when available; otherwise enrollment is no-op.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# Minimum duration (seconds) of audio for a usable enrollment
VOICE_ENROLLMENT_MIN_SEC = 3.0
# Default similarity threshold: accept segment only if cosine sim >= this.
# 0.62 balances accepting the enrolled user (mic/room variation) vs rejecting others and TTS echo.
VOICE_PROFILE_SIMILARITY_THRESHOLD_DEFAULT = 0.62
# Settings keys
SETTINGS_KEY_EMBEDDING = "voice_profile_embedding"
SETTINGS_KEY_THRESHOLD = "voice_profile_threshold"

_encoder: Any = None


def _get_encoder() -> Any | None:
    """Lazy-load resemblyzer VoiceEncoder. Returns None if not available."""
    global _encoder
    if _encoder is not None:
        return _encoder
    try:
        from resemblyzer import VoiceEncoder

        _encoder = VoiceEncoder(verbose=False)
        return _encoder
    except ImportError as e:
        logger.debug("resemblyzer not available: %s", e)
        return None
    except Exception as e:
        logger.warning("VoiceEncoder failed to load (resemblyzer/torch): %s", e)
        return None


def _bytes_to_wav_float(audio_bytes: bytes, sample_rate: int = 16000) -> np.ndarray:
    """Convert raw int16 mono bytes to float32 wav in [-1, 1]."""
    samples = np.frombuffer(audio_bytes, dtype=np.int16)
    return (samples.astype(np.float32) / 32768.0).flatten()


def enroll_user_voice(
    audio_bytes: bytes,
    sample_rate: int,
    settings_repo: Any | None = None,
) -> tuple[bool, str]:
    """
    Compute speaker embedding from enrollment audio and persist it.

    Requires at least VOICE_ENROLLMENT_MIN_SEC of audio. Uses resemblyzer when
    available. Returns (success, message). Never raises.
    """
    try:
        duration_sec = len(audio_bytes) / (2 * sample_rate)
        if duration_sec < VOICE_ENROLLMENT_MIN_SEC:
            return (
                False,
                f"Need at least {VOICE_ENROLLMENT_MIN_SEC:.0f} seconds of audio; got {duration_sec:.1f}s",
            )
        encoder = _get_encoder()
        if encoder is None:
            return (
                False,
                "Speaker recognition not available (install resemblyzer and torch).",
            )
        if settings_repo is None:
            return False, "Settings repository not available."
        wav = _bytes_to_wav_float(audio_bytes, sample_rate)
        if sample_rate != 16000:
            return False, "Sample rate must be 16000 Hz for voice enrollment."
        embed = encoder.embed_utterance(wav)
        embedding_list = embed.tolist()
        settings_repo.set(SETTINGS_KEY_EMBEDDING, json.dumps(embedding_list))
        return True, f"Voice profile saved ({duration_sec:.1f}s). App will prefer your voice."
    except Exception as e:
        logger.exception("Voice enrollment failed: %s", e)
        return False, str(e)


def load_embedding(settings_repo: Any | None) -> np.ndarray | None:
    """Load persisted voice profile embedding. Returns None if missing or invalid."""
    if settings_repo is None:
        return None
    raw = settings_repo.get(SETTINGS_KEY_EMBEDDING)
    if not raw or not raw.strip():
        return None
    try:
        data = json.loads(raw)
        if not isinstance(data, list) or len(data) < 10:
            return None
        return np.array(data, dtype=np.float32)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def get_similarity_threshold(settings_repo: Any | None) -> float:
    """Return configured similarity threshold, or default."""
    if settings_repo is None:
        return VOICE_PROFILE_SIMILARITY_THRESHOLD_DEFAULT
    raw = settings_repo.get(SETTINGS_KEY_THRESHOLD)
    if raw is None or not raw.strip():
        return VOICE_PROFILE_SIMILARITY_THRESHOLD_DEFAULT
    try:
        return max(0.0, min(1.0, float(raw)))
    except (TypeError, ValueError):
        return VOICE_PROFILE_SIMILARITY_THRESHOLD_DEFAULT


def clear_voice_profile(settings_repo: Any | None) -> None:
    """Remove stored voice profile so the app accepts all speakers again."""
    if settings_repo is None:
        return
    try:
        settings_repo.delete(SETTINGS_KEY_EMBEDDING)
    except Exception as e:
        logger.debug("Clear voice profile failed: %s", e)


def is_voice_profile_available(settings_repo: Any | None) -> bool:
    """True if a voice profile is stored and speaker verification can be used."""
    return load_embedding(settings_repo) is not None


def similarity_to_user(
    audio_bytes: bytes,
    sample_rate: int,
    user_embedding: np.ndarray,
    encoder: Any,
) -> float:
    """
    Compute cosine similarity between segment embedding and enrolled user embedding.
    Returns value in [0, 1] (embeddings are L2-normed); higher = more likely same speaker.
    """
    wav = _bytes_to_wav_float(audio_bytes, sample_rate)
    if len(wav) < sample_rate * 0.5:
        return 0.0
    try:
        seg_embed = encoder.embed_utterance(wav)
        sim = float(np.dot(seg_embed, user_embedding))
        return max(0.0, min(1.0, sim))
    except Exception as e:
        logger.debug("Similarity computation failed: %s", e)
        return 0.0
