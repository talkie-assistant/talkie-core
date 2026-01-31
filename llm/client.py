"""
Ollama API client for local Mistral (or other) model.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

FALLBACK_MESSAGE = (
    "I'm sorry, I couldn't generate a response right now. Please try again."
)

MEMORY_ERROR_MESSAGE = "The model needs more memory than is available. Try a smaller model in Ollama or free some memory."

# Default generation options: enough length for full sentences, lower temperature for instruction-following.
DEFAULT_OPTIONS: dict[str, Any] = {"num_predict": 256, "temperature": 0.4}


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
        options: dict[str, Any] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries
        self._options: dict[str, Any] = {**DEFAULT_OPTIONS}
        if options:
            self._options.update({k: v for k, v in options.items() if v is not None})
        self._debug_log: None | object = None  # Callable[[str], None] set by pipeline
        self._resolved_model: str | None = (
            None  # full tag from /api/tags, e.g. mistral:latest
        )

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

    def check_model_available(self, timeout_sec: float = 5.0) -> bool:
        """Return True if the configured model is available (from /api/tags)."""
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=timeout_sec)
            if r.status_code != 200:
                return False
            data = r.json()
            models = data.get("models") or []
            names = {m.get("name", "").split(":")[0] for m in models if m.get("name")}
            return self.model_name.split(":")[0] in names
        except requests.RequestException:
            return False

    def _get_model_for_api(self) -> str:
        """
        Return the model name to send to Ollama. Resolves config name (e.g. mistral)
        to the full tag from /api/tags (e.g. mistral:latest) so generate() works.
        """
        if self._resolved_model is not None:
            return self._resolved_model
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=5.0)
            if r.status_code != 200:
                return self.model_name
            data = r.json()
            models = data.get("models") or []
            base = self.model_name.split(":")[0]
            for m in models:
                name = m.get("name") or ""
                if name == self.model_name or name.startswith(base + ":"):
                    self._resolved_model = name
                    return name
            return self.model_name
        except requests.RequestException:
            return self.model_name

    def generate(self, prompt: str, system: str | None = None) -> str:
        """
        Send prompt (and optional system) to Ollama; return the model's reply.
        On error returns FALLBACK_MESSAGE.
        """
        url = f"{self.base_url}/api/generate"
        model_for_api = self._get_model_for_api()
        payload: dict[str, Any] = {
            "model": model_for_api,
            "prompt": prompt,
            "stream": False,
            "options": self._options,
        }
        if system:
            payload["system"] = system

        self._debug(f"Ollama POST {url} model={model_for_api}")

        for attempt in range(self.max_retries + 1):
            start = time.perf_counter()
            try:
                r = requests.post(url, json=payload, timeout=self.timeout_sec)
                elapsed = time.perf_counter() - start
                self._debug(f"Ollama HTTP {r.status_code} ({elapsed:.2f}s)")
                r.raise_for_status()
                data = r.json()
                reply = data.get("response")
                if isinstance(reply, str) and reply.strip():
                    self._debug("Ollama response OK (%d chars)" % len(reply.strip()))
                    return reply.strip()
                self._debug("Ollama response empty or invalid; returning fallback")
                return FALLBACK_MESSAGE
            except requests.RequestException as e:
                elapsed = time.perf_counter() - start
                if (
                    hasattr(e, "response")
                    and e.response is not None
                    and e.response.status_code == 500
                ):
                    try:
                        body = e.response.text
                        if body:
                            logger.warning("Ollama 500 response body: %s", body[:500])
                            self._debug(f"Ollama 500 body: {body[:200]}...")
                            try:
                                data = json.loads(body)
                                err = (data.get("error") or "").lower()
                                if "memory" in err or "system memory" in err:
                                    return MEMORY_ERROR_MESSAGE
                            except (json.JSONDecodeError, TypeError):
                                pass
                    except Exception:
                        pass
                self._debug(f"Ollama error (attempt {attempt + 1}) after {elapsed:.2f}s: {e}")
                logger.warning(
                    "Ollama request attempt %d failed after %.2fs: %s",
                    attempt + 1,
                    elapsed,
                    e,
                )
                if attempt < self.max_retries:
                    time.sleep(1.0)
                else:
                    logger.exception("Ollama generate failed after retries")
                    self._debug("Ollama returning fallback after retries")
                    return FALLBACK_MESSAGE
            except Exception as e:
                elapsed = time.perf_counter() - start
                self._debug("Ollama error after %.2fs: %s" % (elapsed, e))
                logger.exception("Ollama generate error after %.2fs: %s", elapsed, e)
                return FALLBACK_MESSAGE
        self._debug("Ollama returning fallback (no successful attempt)")
        return FALLBACK_MESSAGE
