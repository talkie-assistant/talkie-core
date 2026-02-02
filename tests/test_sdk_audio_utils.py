"""Tests for sdk.audio_utils: chunk_rms_level, INT16_MAX."""

from __future__ import annotations

import struct

from sdk import INT16_MAX, chunk_rms_level


def test_int16_max_constant() -> None:
    assert INT16_MAX == 32767
    assert isinstance(INT16_MAX, int)


def test_chunk_rms_level_none_returns_zero() -> None:
    assert chunk_rms_level(None) == 0.0
    assert isinstance(chunk_rms_level(None), float)


def test_chunk_rms_level_empty_returns_zero() -> None:
    assert chunk_rms_level(b"") == 0.0
    assert chunk_rms_level(b"\x00") == 0.0
    assert chunk_rms_level(b"\x00\x00") == 0.0


def test_chunk_rms_level_silence_returns_zero() -> None:
    chunk = struct.pack("<100h", *([0] * 100))
    assert chunk_rms_level(chunk) == 0.0


def test_chunk_rms_level_full_scale_returns_one() -> None:
    chunk = struct.pack("<10h", *([INT16_MAX] * 10))
    assert chunk_rms_level(chunk) == 1.0
    assert isinstance(chunk_rms_level(chunk), float)


def test_chunk_rms_level_half_scale() -> None:
    half = 16384
    chunk = struct.pack("<10h", *([half] * 10))
    level = chunk_rms_level(chunk)
    assert 0.4 < level <= 1.0
    assert isinstance(level, float)


def test_chunk_rms_level_output_in_unit_interval() -> None:
    for val in [0, 100, 10000, 32767, -32768]:
        chunk = struct.pack("<20h", *([val] * 20))
        level = chunk_rms_level(chunk)
        assert 0.0 <= level <= 1.0
        assert isinstance(level, float)
