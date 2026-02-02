"""
macOS text-to-speech via the built-in 'say' command.
Runs in a background thread so the pipeline is not blocked.
Uses /usr/bin/say so it works when PATH is limited (e.g. launched from Finder).
"""

from __future__ import annotations

import logging
import re
import subprocess
import threading

from .base import TTSEngine

logger = logging.getLogger(__name__)

_SAY_PATH = "/usr/bin/say"

# Known macOS 'say' voice names -> gender for filtering. Unknown voices are treated as "unknown".
_VOICE_GENDER: dict[str, str] = {
    "Agnes": "female",
    "Albert": "male",
    "Alex": "male",
    "Alice": "female",
    "Alva": "female",
    "Amelie": "female",
    "Anna": "female",
    "Bruce": "male",
    "Carmit": "female",
    "Daniel": "male",
    "Damayanti": "female",
    "Diego": "male",
    "Ellen": "female",
    "Fiona": "female",
    "Fred": "male",
    "Ioana": "female",
    "Joana": "female",
    "Junior": "male",
    "Kanya": "female",
    "Karen": "female",
    "Kathy": "female",
    "Kyoko": "female",
    "Laura": "female",
    "Lekha": "female",
    "Luciana": "female",
    "Mariska": "female",
    "Mei-Jia": "female",
    "Melina": "female",
    "Milena": "female",
    "Moira": "female",
    "Monica": "female",
    "Nora": "female",
    "Paulina": "female",
    "Ralph": "male",
    "Samantha": "female",
    "Sara": "female",
    "Satu": "female",
    "Tarik": "male",
    "Tessa": "female",
    "Thomas": "male",
    "Ting-Ting": "female",
    "Veena": "female",
    "Vicki": "female",
    "Victoria": "female",
    "Xander": "male",
    "Yelda": "female",
    "Yuna": "female",
    "Zosia": "female",
    "Zuzana": "female",
    # Base names that may appear in "Name (Locale)" style output
    "Aman": "female",
    "Amélie": "female",
    "Aru": "female",
    "Eddy": "male",
    "Flo": "female",
    "Soumya": "female",
}

# Voice list line format: "VoiceId  Lang  # comment" or "VoiceId\tLang\t...". Lang is xx_XX.
_LANG_RE = re.compile(r"\b[a-z]{2}_[A-Z]{2}\b")

# TTS rate (say -r words per minute): slow, normal, fast
TTS_RATE_WPM: dict[str, int] = {
    "slow": 120,
    "normal": 175,
    "fast": 220,
}


def get_rate_wpm(tts_rate: str | None) -> int | None:
    """Return WPM for tts_rate (slow/normal/fast), or None if invalid/missing."""
    if not (tts_rate and tts_rate.strip()):
        return None
    s = tts_rate.strip().lower()
    return TTS_RATE_WPM.get(s)


def get_available_voices_with_gender() -> list[dict[str, str]]:
    """Return list of {name, gender} for macOS 'say' voices. gender is 'male', 'female', or 'unknown'."""
    import shutil

    say_bin = shutil.which("say") or _SAY_PATH
    try:
        result = subprocess.run(
            [say_bin, "-v", "?"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return []
        voices: list[dict[str, str]] = []
        seen: set[str] = set()
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            # Full voice id is everything before the language code (e.g. "Eddy (English (US))").
            match = _LANG_RE.search(line)
            if match:
                name = line[: match.start()].strip()
            else:
                parts = line.split()
                name = parts[0] if parts else ""
            if not name or name in seen:
                continue
            seen.add(name)
            base = name.split()[0] if name else ""
            gender = _VOICE_GENDER.get(base, _VOICE_GENDER.get(name, "unknown"))
            voices.append({"name": name, "gender": gender})
        return sorted(voices, key=lambda x: x["name"])
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        return []


class SayEngine(TTSEngine):
    """
    Speak text using macOS 'say'. Runs in a non-daemon thread so playback
    can finish even if the app is closing. stop() terminates current playback.
    """

    def __init__(
        self,
        voice: str | None = None,
        speak_timeout_sec: float = 300.0,
        rate_wpm: int | None = None,
    ) -> None:
        self._voice = voice
        self._speak_timeout_sec = max(1.0, min(3600.0, float(speak_timeout_sec)))
        self._rate_wpm = rate_wpm if (rate_wpm is not None and rate_wpm > 0) else None
        self._speak_thread: threading.Thread | None = None
        self._speak_lock = threading.Lock()
        self._current_process: subprocess.Popen | None = None

    def speak(self, text: str) -> None:
        if not (text and text.strip()):
            return
        with self._speak_lock:
            if self._speak_thread is not None and self._speak_thread.is_alive():
                if self._current_process is not None:
                    try:
                        self._current_process.terminate()
                        self._current_process.wait(timeout=2)
                    except Exception:
                        pass
                    self._current_process = None
                self._speak_thread.join(timeout=5)
            self._speak_thread = threading.Thread(
                target=self._speak_sync,
                args=(text.strip(),),
                daemon=False,
                name="tts-say",
            )
            self._speak_thread.start()

    def wait_until_done(self) -> None:
        """Block until the current TTS playback finishes (avoids mic picking up speaker)."""
        with self._speak_lock:
            t = self._speak_thread
        if t is not None and t.is_alive():
            t.join(timeout=int(self._speak_timeout_sec))

    def stop(self) -> None:
        """Abort current playback so the user can interrupt by speaking again."""
        with self._speak_lock:
            p = self._current_process
        if p is not None:
            try:
                p.terminate()
                p.wait(timeout=2)
            except Exception:
                pass
            with self._speak_lock:
                self._current_process = None

    def _speak_sync(self, text: str) -> None:
        proc = None
        with self._speak_lock:
            self._current_process = None
        try:
            cmd = [_SAY_PATH]
            if self._voice:
                cmd.extend(["-v", self._voice])
            if self._rate_wpm is not None:
                cmd.extend(["-r", str(self._rate_wpm)])
            cmd.append(text)
            logger.info("TTS speaking (%d chars)", len(text))
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            with self._speak_lock:
                self._current_process = proc
            proc.wait(timeout=int(self._speak_timeout_sec))
        except subprocess.TimeoutExpired:
            if proc is not None and proc.poll() is None:
                proc.kill()
            logger.warning("TTS say timed out")
        except FileNotFoundError:
            logger.warning("TTS: 'say' not found (not macOS?)")
        except Exception as e:
            logger.exception("TTS say error: %s", e)
        finally:
            with self._speak_lock:
                if self._current_process is proc:
                    self._current_process = None
