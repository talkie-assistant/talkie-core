"""
Shared audio utilities: RMS level from int16 chunks and resampling.
Used by app pipeline, speech module server, and speech module internals.
"""

from __future__ import annotations

import logging
import struct

logger = logging.getLogger(__name__)

INT16_MAX = 32767


def chunk_rms_level(chunk: bytes | None) -> float:
    """
    Return RMS level of chunk (int16 little-endian) normalized to 0.0--1.0.
    Returns 0.0 for None, empty, or too short chunk; never raises.
    """
    if chunk is None or len(chunk) < 2:
        return 0.0
    try:
        n = len(chunk) // 2
        samples = struct.unpack(f"<{n}h", chunk)
        total = sum(s * s for s in samples)
        rms = (total / n) ** 0.5 if n else 0.0
        return min(1.0, rms / INT16_MAX)
    except (struct.error, ZeroDivisionError, ValueError) as e:
        logger.debug("chunk_rms_level failed: %s", e)
        return 0.0


def resample_int16(audio_bytes: bytes, rate_in: int, rate_out: int) -> bytes:
    """
    Resample int16 mono PCM from rate_in to rate_out.
    Uses linear interpolation (numpy). Returns bytes of int16 little-endian.
    """
    if rate_in <= 0 or rate_out <= 0:
        return b""
    if rate_in == rate_out:
        return audio_bytes
    n = len(audio_bytes) // 2
    if n == 0:
        return b""
    try:
        import numpy as np
    except ImportError:
        logger.warning("resample_int16 requires numpy")
        return b""
    samples = np.frombuffer(audio_bytes, dtype=np.int16)
    num_out = int(round(n * rate_out / rate_in))
    if num_out == 0:
        return b""
    x_old = np.arange(n, dtype=np.float64)
    x_new = np.linspace(0, n - 1, num_out, dtype=np.float64)
    resampled = np.interp(x_new, x_old, samples.astype(np.float64))
    out = np.clip(resampled, -32768, 32767).astype(np.int16)
    return out.tobytes()


__all__ = ["INT16_MAX", "chunk_rms_level", "resample_int16"]
