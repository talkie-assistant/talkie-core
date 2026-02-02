"""Tests for sdk.audio_utils (chunk_rms_level, INT16_MAX, resample_int16). app.audio_utils re-exports for backward compatibility."""

from __future__ import annotations

import struct

from app.audio_utils import INT16_MAX, chunk_rms_level, resample_int16


def test_int16_max_constant() -> None:
    assert INT16_MAX == 32767
    assert isinstance(INT16_MAX, int)


def test_chunk_rms_level_reexport() -> None:
    chunk = struct.pack("<4h", 100, 100, 100, 100)
    level = chunk_rms_level(chunk)
    assert isinstance(level, float)
    assert 0.0 <= level <= 1.0


# ---- resample_int16 ----
def test_resample_int16_same_rate_returns_unchanged() -> None:
    data = struct.pack("<100h", *([100] * 100))
    out = resample_int16(data, 16000, 16000)
    assert out == data
    assert len(out) == len(data)
    assert isinstance(out, bytes)


def test_resample_int16_half_rate_half_samples() -> None:
    data = struct.pack("<200h", *([0] * 200))
    out = resample_int16(data, 16000, 8000)
    assert isinstance(out, bytes)
    assert len(out) % 2 == 0
    assert len(out) == 200
    n_out = len(out) // 2
    assert n_out == 100


def test_resample_int16_zero_length_returns_empty() -> None:
    out = resample_int16(b"", 16000, 8000)
    assert out == b""
    assert isinstance(out, bytes)
    out2 = resample_int16(b"\x00\x00", 16000, 8000)
    assert out2 == b""
    assert len(out2) == 0


def test_resample_int16_invalid_rate_in_returns_empty() -> None:
    data = struct.pack("<10h", *([0] * 10))
    out = resample_int16(data, 0, 16000)
    assert out == b""
    out2 = resample_int16(data, -1, 16000)
    assert out2 == b""


def test_resample_int16_invalid_rate_out_returns_empty() -> None:
    data = struct.pack("<10h", *([0] * 10))
    out = resample_int16(data, 16000, 0)
    assert out == b""
    out2 = resample_int16(data, 16000, -1)
    assert out2 == b""


def test_resample_int16_odd_byte_length_handled() -> None:
    data = struct.pack("<5h", 0, 0, 0, 0, 0)
    out = resample_int16(data, 16000, 8000)
    assert isinstance(out, bytes)
    assert len(out) % 2 == 0


def test_resample_int16_double_rate_doubles_samples() -> None:
    data = struct.pack("<50h", *([100] * 50))
    out = resample_int16(data, 8000, 16000)
    assert isinstance(out, bytes)
    assert len(out) == 200
    assert len(out) // 2 == 100


def test_resample_int16_output_is_int16_little_endian() -> None:
    data = struct.pack("<20h", *list(range(-10, 10)))
    out = resample_int16(data, 16000, 16000)
    assert out == data
    samples = struct.unpack(f"<{len(out) // 2}h", out)
    assert all(-32768 <= s <= 32767 for s in samples)
