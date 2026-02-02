"""
List audio devices and handle disconnect/reconnect.
"""

from __future__ import annotations

import logging
from typing import Any

from sdk import MicrophoneError

logger = logging.getLogger(__name__)


def list_input_devices() -> list[dict[str, Any]]:
    """
    Return list of dicts with 'id', 'name', 'sample_rate' (default) for each input device.
    Uses sounddevice.
    """
    try:
        import sounddevice as sd

        devices = sd.query_devices()
        out = []
        for i, d in enumerate(devices):
            if d.get("max_input_channels", 0) > 0:
                out.append(
                    {
                        "id": i,
                        "name": d.get("name", "Unknown"),
                        "sample_rate": float(d.get("default_samplerate", 16000)),
                    }
                )
        return out
    except Exception as e:
        logger.exception("Failed to list input devices: %s", e)
        raise MicrophoneError("Cannot list microphone devices") from e


def get_default_input_device_id() -> int | None:
    """Return the default input device index, or None if none."""
    try:
        import sounddevice as sd

        return int(sd.default.device[0])
    except Exception:
        return None
