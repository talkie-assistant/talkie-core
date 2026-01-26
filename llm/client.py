"""
Ollama API client for local Mistral (or other) model.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

FALLBACK_MESSAGE = "I'm sorry, I couldn't generate a response right now. Please try again."


class OllamaClient:
    """
    Generate text via Ollama HTTP API (e.g. Mistral).
    On failure returns a safe fallback and logs.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model_name: str = "mistral",
        timeout_sec: float = 60.0,
        max_retries: int = 2,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries
        self._debug_log: None | object = None  # Callable[[str], None] set by pipeline

    def set_debug_log(self, callback: object) -> None:
        """Optional: set a callable(str) to log debug lines (e.g. HTTP request/response)."""
        self._debug_log = callback

    def _debug(self, msg: str) -> None:
        if callable(self._debug_log):
            self._debug_log(msg)

    def check_connection(self, timeout_sec: float = 5.0) -> bool:
        """Return True if Ollama is reachable (e.g. GET /api/tags)."""
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=timeout_sec)
            return r.status_code == 200
        except requests.RequestException:
            return False

    def generate(self, prompt: str, system: str | None = None) -> str:
        """
        Send prompt (and optional system) to Ollama; return the model's reply.
        On error returns FALLBACK_MESSAGE.
        """
        url = f"{self.base_url}/api/generate"
        payload: dict[str, Any] = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
        }
        if system:
            payload["system"] = system

        self._debug(f"Ollama POST {url} model={self.model_name}")

        for attempt in range(self.max_retries + 1):
            try:
                r = requests.post(url, json=payload, timeout=self.timeout_sec)
                self._debug(f"Ollama HTTP {r.status_code}")
                r.raise_for_status()
                data = r.json()
                reply = data.get("response")
                if isinstance(reply, str) and reply.strip():
                    self._debug("Ollama response OK (%d chars)" % len(reply.strip()))
                    return reply.strip()
                self._debug("Ollama response empty or invalid; returning fallback")
                return FALLBACK_MESSAGE
            except requests.RequestException as e:
                self._debug(f"Ollama error (attempt {attempt + 1}): {e}")
                logger.warning("Ollama request attempt %d failed: %s", attempt + 1, e)
                if attempt < self.max_retries:
                    time.sleep(1.0)
                else:
                    logger.exception("Ollama generate failed after retries")
                    self._debug("Ollama returning fallback after retries")
                    return FALLBACK_MESSAGE
            except Exception as e:
                self._debug("Ollama error: %s" % e)
                logger.exception("Ollama generate error: %s", e)
                return FALLBACK_MESSAGE
        self._debug("Ollama returning fallback (no successful attempt)")
        return FALLBACK_MESSAGE
