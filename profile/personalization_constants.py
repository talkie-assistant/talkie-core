"""
Canonical allowed values for personalization settings (response style, length, TTS rate).
Used by profile builder, SpeechFactory, and optionally API validation.
"""

from __future__ import annotations

# Response style: casual, formal, neutral (lowercase for storage/API)
RESPONSE_STYLE_VALUES = ("casual", "formal", "neutral")

# Response length: brief, standard, detailed
RESPONSE_LENGTH_VALUES = ("brief", "standard", "detailed")

# TTS rate: slow, normal, fast (macOS say -r words per minute)
TTS_RATE_VALUES = ("slow", "normal", "fast")
TTS_RATE_WPM: dict[str, int] = {
    "slow": 120,
    "normal": 175,
    "fast": 220,
}

# Optional max lengths for text fields (None = no server-side cap)
PREFERRED_NAME_MAX_CHARS = 200
TOPIC_HINTS_MAX_CHARS = 1000
