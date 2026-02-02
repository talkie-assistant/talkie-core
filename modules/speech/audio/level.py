"""
Compute volume level from raw audio chunk (int16 LE) for waveform/level display.
Re-exports SDK implementation for use within the speech module.
"""

from __future__ import annotations

from sdk import chunk_rms_level

__all__ = ["chunk_rms_level"]
