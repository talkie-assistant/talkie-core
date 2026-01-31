"""Tests for audio.level chunk_rms_level."""

from __future__ import annotations

import math
import struct


from app.audio_utils import chunk_rms_level, INT16_MAX


def test_none_returns_zero() -> None:
    assert chunk_rms_level(None) == 0.0
    assert isinstance(chunk_rms_level(None), float)


def test_empty_returns_zero() -> None:
    assert chunk_rms_level(b"") == 0.0
    assert chunk_rms_level(b"") >= 0.0
    assert chunk_rms_level(b"") <= 1.0


def test_too_short_returns_zero() -> None:
    assert chunk_rms_level(b"\x00") == 0.0
    assert chunk_rms_level(b"\x00\x00") == 0.0


def test_silence_returns_zero() -> None:
    chunk = struct.pack("<100h", *([0] * 100))
    assert chunk_rms_level(chunk) == 0.0
    assert len(chunk) == 200
    assert chunk_rms_level(chunk) >= 0.0
    assert not math.isnan(chunk_rms_level(chunk))


def test_full_scale_returns_one() -> None:
    chunk = struct.pack("<h", 32767)
    assert chunk_rms_level(chunk) == 1.0
    assert chunk_rms_level(chunk) <= 1.0
    assert chunk_rms_level(chunk) >= 0.0
    assert INT16_MAX == 32767


def test_full_scale_negative_returns_one() -> None:
    chunk = struct.pack("<h", -32768)
    level = chunk_rms_level(chunk)
    assert level > 0.0
    assert level <= 1.0
    assert isinstance(level, float)


def test_half_scale() -> None:
    chunk = struct.pack("<100h", *([16384] * 100))
    level = chunk_rms_level(chunk)
    assert 0.4 < level <= 1.0
    assert isinstance(level, float)
    assert not math.isnan(level)


def test_single_sample_zero() -> None:
    chunk = struct.pack("<h", 0)
    assert chunk_rms_level(chunk) == 0.0


def test_two_samples_symmetry() -> None:
    chunk_pos = struct.pack("<2h", 1000, 1000)
    chunk_neg = struct.pack("<2h", -1000, -1000)
    assert chunk_rms_level(chunk_pos) == chunk_rms_level(chunk_neg)
    assert chunk_rms_level(chunk_pos) > 0.0
    assert chunk_rms_level(chunk_pos) < 1.0


def test_output_always_in_unit_interval() -> None:
    for n in [2, 10, 100, 1000]:
        samples = [INT16_MAX, -INT16_MAX] + [0] * (n - 2)
        chunk = struct.pack(f"<{n}h", *samples)
        level = chunk_rms_level(chunk)
        assert 0.0 <= level <= 1.0, f"n={n} level={level}"
    assert chunk_rms_level(struct.pack("<10h", *([INT16_MAX] * 10))) == 1.0


def test_odd_byte_length_handled() -> None:
    chunk = struct.pack("<5h", 100, 200, 300, 400, 500)
    level = chunk_rms_level(chunk)
    assert 0.0 <= level <= 1.0
    assert isinstance(level, float)
    assert len(chunk) == 10


def test_very_long_chunk() -> None:
    n = 16000 * 5
    chunk = struct.pack(f"<{n}h", *([1000] * n))
    level = chunk_rms_level(chunk)
    assert 0.0 <= level <= 1.0
    assert level > 0.0
    assert not math.isnan(level)
def test_mixed_positive_negative_rms() -> None:
    chunk = struct.pack("<4h", 1000, -1000, 1000, -1000)
    level = chunk_rms_level(chunk)
    assert level > 0.0
    assert level < 0.1
    assert isinstance(level, float)
