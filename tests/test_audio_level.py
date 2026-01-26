"""Tests for audio.level chunk_rms_level."""
from __future__ import annotations

import struct

import pytest

from audio.level import chunk_rms_level


def test_none_returns_zero() -> None:
    assert chunk_rms_level(None) == 0.0


def test_empty_returns_zero() -> None:
    assert chunk_rms_level(b"") == 0.0


def test_too_short_returns_zero() -> None:
    assert chunk_rms_level(b"\x00") == 0.0


def test_silence_returns_zero() -> None:
    chunk = struct.pack("<100h", *([0] * 100))
    assert chunk_rms_level(chunk) == 0.0


def test_full_scale_returns_one() -> None:
    # 32767 in int16 LE
    chunk = struct.pack("<h", 32767)
    assert chunk_rms_level(chunk) == 1.0


def test_half_scale() -> None:
    chunk = struct.pack("<100h", *([16384] * 100))
    level = chunk_rms_level(chunk)
    assert 0.4 < level <= 1.0
