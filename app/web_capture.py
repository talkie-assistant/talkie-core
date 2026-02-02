"""
Audio capture that receives chunks over WebSocket from the browser.
Pipeline calls read_chunk(); the WebSocket handler calls put_chunk() with bytes from the client.
When client_sample_rate != 16000, resamples to 16 kHz before buffering.
"""

from __future__ import annotations

import threading
from collections import deque

from sdk import AudioCapture
from app.audio_utils import resample_int16

TARGET_SAMPLE_RATE = 16000


class WebSocketAudioCapture(AudioCapture):
    """
    Capture that buffers bytes from put_chunk() and returns chunk_size bytes from read_chunk().
    If client_sample_rate is set and != 16000, incoming bytes are resampled to 16 kHz before buffering.
    """

    def __init__(self, chunk_size_bytes: int, sample_rate: int = 16000) -> None:
        self._chunk_size = chunk_size_bytes
        self._sample_rate = sample_rate
        self._buffer: deque[bytes] = deque()
        self._buffer_len = 0
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._started = False
        self._sensitivity = 1.0
        self._client_sample_rate: int | None = None

    def start(self) -> None:
        with self._lock:
            self._started = True
            self._buffer.clear()
            self._buffer_len = 0

    def stop(self) -> None:
        with self._lock:
            self._started = False
            self._condition.notify_all()

    def set_client_sample_rate(self, rate: int | None) -> None:
        """Set the browser's actual sample rate (e.g. 48000). When != 16000, put_chunk resamples."""
        self._client_sample_rate = rate

    def put_chunk(self, data: bytes) -> None:
        """Called from WebSocket handler when browser sends audio bytes."""
        if not data:
            return
        rate_in = self._client_sample_rate or TARGET_SAMPLE_RATE
        if rate_in != TARGET_SAMPLE_RATE:
            data = resample_int16(data, rate_in, TARGET_SAMPLE_RATE)
        if not data:
            return
        with self._lock:
            if not self._started:
                return
            self._buffer.append(data)
            self._buffer_len += len(data)
            self._condition.notify_all()

    def read_chunk(self, on_level=None):
        """Block until we have chunk_size bytes, then return them. Returns None when stopped."""
        with self._condition:
            while self._started and self._buffer_len < self._chunk_size:
                self._condition.wait(timeout=0.3)
            if not self._started:
                return None
            if self._buffer_len < self._chunk_size:
                return None
            out = bytearray()
            while len(out) < self._chunk_size and self._buffer:
                b = self._buffer.popleft()
                self._buffer_len -= len(b)
                take = min(len(b), self._chunk_size - len(out))
                out.extend(b[:take])
                if len(b) > take:
                    remainder = b[take:]
                    self._buffer.appendleft(remainder)
                    self._buffer_len += len(remainder)
                    break
            return bytes(out) if out else None

    def get_sensitivity(self) -> float:
        return self._sensitivity

    def set_sensitivity(self, value: float) -> None:
        self._sensitivity = max(0.1, min(10.0, float(value)))
