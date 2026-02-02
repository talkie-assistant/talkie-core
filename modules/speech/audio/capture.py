"""
Continuous microphone capture for Talkie.
"""

from __future__ import annotations

import logging
import struct
from typing import Any, Callable, Iterator

from sdk import AudioCapture as AudioCaptureBase, MicrophoneError
from .constants import INT16_MAX, INT16_MIN
from .level import chunk_rms_level

logger = logging.getLogger(__name__)

# Block size for level reporting: report RMS this often for real-time waveform (~20/sec at 16kHz)
LEVEL_BLOCK_DURATION_SEC = 0.05


class AudioCapture(AudioCaptureBase):
    """
    Capture audio chunks from the configured microphone.
    Use start() then read_chunk() in a loop; stop() to release the device.
    Sensitivity (gain) is applied so quiet speech can be boosted (e.g. 2.0-4.0).
    When on_level is passed to read_chunk(), level is reported every LEVEL_BLOCK_DURATION_SEC
    for real-time waveform display.
    """

    def __init__(
        self,
        device_id: int | None = None,
        sample_rate: int = 16000,
        chunk_duration_sec: float = 5.0,
        sensitivity: float = 2.5,
    ) -> None:
        self.device_id = device_id
        self.sample_rate = sample_rate
        self.chunk_frames = int(sample_rate * chunk_duration_sec)
        self._block_frames = max(1, int(sample_rate * LEVEL_BLOCK_DURATION_SEC))
        self.sensitivity = max(0.1, min(10.0, float(sensitivity)))
        self._running = False
        self._stream: Any = None
        self._buffer = bytearray()

    def set_sensitivity(self, value: float) -> None:
        """Update sensitivity at runtime (e.g. from UI). Clamped to 0.1–10.0."""
        self.sensitivity = max(0.1, min(10.0, float(value)))

    def get_sensitivity(self) -> float:
        return self.sensitivity

    def start(self) -> None:
        """Open the audio input stream."""
        import sounddevice as sd

        if self._running:
            return
        try:
            self._stream = sd.InputStream(
                device=self.device_id,
                samplerate=self.sample_rate,
                channels=1,
                dtype="int16",
                blocksize=self._block_frames,
            )
            self._stream.start()
            self._running = True
            logger.info(
                "Audio capture started (device=%s, rate=%s, sensitivity=%.2f)",
                self.device_id,
                self.sample_rate,
                self.sensitivity,
            )
        except Exception as e:
            logger.exception("Failed to start audio capture: %s", e)
            raise MicrophoneError("Microphone failed to start") from e

    def stop(self) -> None:
        """Stop and close the stream."""
        self._running = False
        self._buffer.clear()
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                logger.warning("Error closing audio stream: %s", e)
            self._stream = None

    def read_chunk(
        self, on_level: Callable[[float], None] | None = None
    ) -> bytes | None:
        """
        Read one chunk of audio (chunk_frames samples as int16).
        If on_level is provided, call it with RMS (0.0--1.0) for each small block so the
        UI can show real-time level (e.g. waveform). Returns None if not running or on
        recoverable skip; raises MicrophoneError on device failure.
        """
        import sounddevice as sd

        if not self._running or self._stream is None:
            return None
        chunk_bytes = self.chunk_frames * 2
        try:
            while len(self._buffer) < chunk_bytes:
                data, _ = self._stream.read(self._block_frames)
                if data is None or len(data) == 0:
                    return None
                raw = data.tobytes()
                if self.sensitivity != 1.0:
                    raw = self._apply_gain(raw)
                if on_level is not None:
                    on_level(chunk_rms_level(raw))
                self._buffer.extend(raw)
            result = bytes(self._buffer[:chunk_bytes])
            del self._buffer[:chunk_bytes]
            return result
        except sd.PortAudioError as e:
            logger.exception("PortAudio error reading chunk: %s", e)
            raise MicrophoneError("Microphone disconnected or unavailable") from e
        except Exception as e:
            logger.exception("Error reading audio chunk: %s", e)
            raise MicrophoneError("Microphone error") from e

    def _apply_gain(self, raw: bytes) -> bytes:
        """Apply sensitivity gain to int16 LE audio; clip to avoid overflow."""
        try:
            import numpy as np

            arr = np.frombuffer(raw, dtype=np.int16)
            scaled = np.clip(
                (arr.astype(np.float64) * self.sensitivity).round(),
                INT16_MIN,
                INT16_MAX,
            ).astype(np.int16)
            return scaled.tobytes()
        except ImportError:
            pass
        n = len(raw) // 2
        samples = struct.unpack(f"<{n}h", raw)
        scaled = [
            max(INT16_MIN, min(INT16_MAX, int(s * self.sensitivity))) for s in samples
        ]
        return struct.pack(f"<{n}h", *scaled)

    def read_chunks(self) -> Iterator[bytes]:
        """Iterate over chunks until stop() is called. Yields bytes; on error raises MicrophoneError."""
        while self._running:
            chunk = self.read_chunk()
            if chunk is not None:
                yield chunk
