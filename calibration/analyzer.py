"""
Analyze a calibration recording: RMS levels and optional STT + LLM to suggest sensitivity, chunk_duration_sec, min_transcription_length.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

SENSITIVITY_MIN = 0.5
SENSITIVITY_MAX = 10.0
CHUNK_DURATION_MIN = 4.0
CHUNK_DURATION_MAX = 15.0
MIN_TRANSCRIPTION_LENGTH_MIN = 0
MIN_TRANSCRIPTION_LENGTH_MAX = 10


def _sensitivity_from_rms(rms_list: list[float]) -> float:
    """
    Map mean speech RMS (0-1) to suggested sensitivity.
    Quiet speech (low RMS) needs higher sensitivity.
    """
    if not rms_list:
        return 2.5
    # Use non-silent blocks (e.g. above 0.005) to estimate speech level
    speech = [r for r in rms_list if r > 0.005]
    if not speech:
        # All very quiet -> suggest high sensitivity
        return 3.5
    mean_rms = sum(speech) / len(speech)
    # Heuristic: very quiet < 0.02 -> 3.5-4, quiet 0.02-0.05 -> 2.5-3, normal 0.05-0.1 -> 1.5-2, louder > 0.1 -> 1.0
    if mean_rms < 0.02:
        return 3.5
    if mean_rms < 0.05:
        return 2.5
    if mean_rms < 0.1:
        return 1.5
    return 1.0


def _parse_llm_calibration_reply(reply: str) -> dict[str, Any] | None:
    """Extract JSON object from LLM reply; expect sensitivity, chunk_duration_sec, min_transcription_length."""
    reply = reply.strip()
    # Try to find a JSON object
    match = re.search(r"\{[^{}]*\}", reply)
    if not match:
        return None
    try:
        data = json.loads(match.group())
        return {
            "sensitivity": data.get("sensitivity"),
            "chunk_duration_sec": data.get("chunk_duration_sec"),
            "min_transcription_length": data.get("min_transcription_length"),
        }
    except (json.JSONDecodeError, TypeError):
        return None


def analyze_recording(
    audio_bytes: bytes,
    sample_rate: int,
    rms_list: list[float],
    *,
    expected_phrase: str = "",
    stt_engine: Any = None,
    llm_client: Any = None,
) -> dict[str, Any]:
    """
    Suggest calibration from a recording.

    Uses RMS to suggest sensitivity. If stt_engine is provided, transcribes the
    recording. If llm_client and (expected_phrase or transcript) are present,
    asks the LLM for suggested sensitivity, chunk_duration_sec, and
    min_transcription_length; otherwise uses rule-based defaults.

    Returns dict with keys: sensitivity (float), chunk_duration_sec (float),
    min_transcription_length (int), and optionally transcript (str).
    """
    sensitivity = max(SENSITIVITY_MIN, min(SENSITIVITY_MAX, _sensitivity_from_rms(rms_list)))
    chunk_duration_sec = 7.0
    min_transcription_length = 3
    transcript = ""

    if stt_engine and audio_bytes:
        try:
            stt_engine.start()
            transcript = (stt_engine.transcribe(audio_bytes) or "").strip()
        except Exception as e:
            logger.debug("Calibration STT failed: %s", e)
        finally:
            try:
                stt_engine.stop()
            except Exception:
                pass

    use_llm = llm_client and (expected_phrase or transcript)
    if use_llm:
        mean_rms = sum(rms_list) / len(rms_list) if rms_list else 0.0
        prompt = (
            "A speech-impaired user was asked to say: \"%s\". "
            "Speech recognition heard: \"%s\". "
            "Mean audio level (RMS 0-1): %.4f. "
            "Suggest calibration: sensitivity (0.5-10, higher for quieter speech), "
            "chunk_duration_sec (4-15, longer if they need more time between words), "
            "min_transcription_length (0-5). "
            "Reply with only a JSON object: {\"sensitivity\": number, \"chunk_duration_sec\": number, \"min_transcription_length\": number}."
        ) % (expected_phrase or "(free speech)", transcript or "(nothing heard)", mean_rms)
        try:
            reply = llm_client.generate(prompt)
            parsed = _parse_llm_calibration_reply(reply)
            if parsed:
                if isinstance(parsed.get("sensitivity"), (int, float)):
                    sensitivity = max(SENSITIVITY_MIN, min(SENSITIVITY_MAX, float(parsed["sensitivity"])))
                if isinstance(parsed.get("chunk_duration_sec"), (int, float)):
                    chunk_duration_sec = max(
                        CHUNK_DURATION_MIN,
                        min(CHUNK_DURATION_MAX, float(parsed["chunk_duration_sec"])),
                    )
                if isinstance(parsed.get("min_transcription_length"), (int, float)):
                    min_transcription_length = max(
                        MIN_TRANSCRIPTION_LENGTH_MIN,
                        min(MIN_TRANSCRIPTION_LENGTH_MAX, int(parsed["min_transcription_length"])),
                    )
        except Exception as e:
            logger.debug("Calibration LLM suggestion failed: %s", e)

    result: dict[str, Any] = {
        "sensitivity": round(sensitivity, 1),
        "chunk_duration_sec": round(chunk_duration_sec, 1),
        "min_transcription_length": min_transcription_length,
    }
    if transcript:
        result["transcript"] = transcript
    return result
