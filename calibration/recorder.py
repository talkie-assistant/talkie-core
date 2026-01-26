"""
Record a fixed duration of microphone input for voice calibration.
Returns raw int16 mono audio and per-block RMS levels for analysis.
"""
from __future__ import annotations

import logging
import struct
import time
from typing import Callable

from audio.constants import INT16_MAX
from audio.level import chunk_rms_level

logger = logging.getLogger(__name__)

BLOCK_DURATION_SEC = 0.05


def record_seconds(
    duration_sec: float,
    sample_rate: int = 16000,
    device_id: int | None = None,
    on_progress: Callable[[int], None] | None = None,
) -> tuple[bytes, list[float]]:
    """
    Record from the default (or given) microphone for duration_sec.
    Returns (raw_int16_mono_bytes, rms_per_block) where rms_per_block are 0.0-1.0.
    on_progress(seconds_remaining) is called every second from a background read loop.
    """
    import sounddevice as sd

    block_frames = max(1, int(sample_rate * BLOCK_DURATION_SEC))
    total_frames = int(sample_rate * duration_sec)
    buffer: list[bytes] = []
    rms_list: list[float] = []
    last_progress_sec: int | None = None

    def _stream_callback(indata, _frames, _time_info, _status):  # noqa: ANN001
        if _status:
            logger.debug("Calibration recording status: %s", _status)
        chunk = indata.tobytes()
        buffer.append(chunk)
        rms_list.append(chunk_rms_level(chunk))

    stream = sd.InputStream(
        device=device_id,
        samplerate=sample_rate,
        channels=1,
        dtype="int16",
        blocksize=block_frames,
        callback=_stream_callback,
    )
    stream.start()
    try:
        start = time.monotonic()
        while True:
            elapsed = time.monotonic() - start
            remaining = duration_sec - elapsed
            if remaining <= 0:
                break
            sec_left = int(remaining)
            if on_progress and sec_left != last_progress_sec:
                last_progress_sec = sec_left
                on_progress(sec_left)
            time.sleep(0.2)
    finally:
        stream.stop()
        stream.close()

    raw = b"".join(buffer)
    # Trim to exact duration
    want_bytes = total_frames * 2
    if len(raw) > want_bytes:
        raw = raw[:want_bytes]
        rms_list = rms_list[: want_bytes // (block_frames * 2)]
    return (raw, rms_list)
