"""
macOS text-to-speech via the built-in 'say' command.
Runs in a background thread so the pipeline is not blocked.
Uses /usr/bin/say so it works when PATH is limited (e.g. launched from Finder).
"""
from __future__ import annotations

import logging
import subprocess
import threading

from tts.base import TTSEngine

logger = logging.getLogger(__name__)

# Full path so TTS works when app is launched from Finder (minimal PATH)
_SAY_PATH = "/usr/bin/say"


def get_available_voices() -> list[str]:
    """Return list of macOS 'say' voice names (e.g. Alex, Samantha). Empty if not macOS or say unavailable."""
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
        voices = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if parts:
                voices.append(parts[0])
        return sorted(voices)
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        return []


class SayEngine(TTSEngine):
    """
    Speak text using macOS 'say'. Runs in a non-daemon thread so playback
    can finish even if the app is closing. stop() terminates current playback.
    """

    def __init__(self, voice: str | None = None) -> None:
        self._voice = voice
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
            t.join(timeout=300)

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
            cmd.append(text)
            logger.info("TTS speaking (%d chars)", len(text))
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            with self._speak_lock:
                self._current_process = proc
            proc.wait(timeout=300)
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
