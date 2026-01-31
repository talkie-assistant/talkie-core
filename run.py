#!/usr/bin/env python3
"""
Talkie entry point: load config, initialize database, start web UI and pipeline.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

from config import AppConfig, load_config

logger = logging.getLogger(__name__)

# Ensure project root is on path
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# Podman Ollama disabled; use local Ollama (run: ollama serve). Uncomment to auto-start talkie-ollama container.
# def _ensure_podman_ollama_if_localhost(base_url: str) -> None:
#     """
#     If Ollama is configured for localhost:11434, try to start the Podman
#     Ollama container (talkie-ollama) so the app uses the Podman version.
#     No-op if base_url is not localhost or if podman/container is unavailable.
#     """
#     if not base_url:
#         return
#     url = (base_url or "").strip().lower().rstrip("/")
#     if url in ("http://localhost:11434", "http://127.0.0.1:11434"):
#         try:
#             subprocess.run(
#                 ["podman", "start", "talkie-ollama"],
#                 capture_output=True,
#                 timeout=10,
#                 check=False,
#             )
#         except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
#             pass


def _maybe_start_local_servers(config: dict) -> None:
    """
    Start local module servers if they're configured to run on localhost.
    Servers are started as background subprocesses.
    """
    from modules.api.config import get_module_server_config, get_module_base_url
    from modules.discovery import discover_modules

    modules_root = _ROOT / "modules"
    try:
        discovered = discover_modules(modules_root)
    except Exception:
        discovered = []

    modules_to_start = []
    for _name, config_path in discovered:
        module_name = config_path.parent.name
        server_config = get_module_server_config(config, module_name)
        if server_config is None:
            continue
        # Only start if host is localhost
        if server_config["host"] in ("localhost", "127.0.0.1", "::1"):
            base_url = get_module_base_url(server_config)
            # Check if server is already running
            try:
                response = requests.get(f"{base_url}/health", timeout=1.0)
                if response.status_code == 200:
                    logger.info(
                        "%s module server already running at %s", module_name, base_url
                    )
                    continue
            except Exception:
                pass  # Server not running, start it

            modules_to_start.append((module_name, server_config))

    if not modules_to_start:
        return
    root = Path(__file__).resolve().parent

    for module_name, server_config in modules_to_start:
        port = server_config["port"]
        api_key = server_config.get("api_key")

        # Start server as subprocess
        cmd = [
            sys.executable,
            "-m",
            f"modules.{module_name}.server",
            "--host",
            "localhost",
            "--port",
            str(port),
        ]
        if api_key:
            cmd.extend(["--api-key", api_key])

        try:
            logger.info("Starting %s module server on port %d", module_name, port)
            process = subprocess.Popen(
                cmd,
                cwd=str(root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            # Give server a moment to start
            time.sleep(1.0)
            # Check if it's still running
            if process.poll() is None:
                logger.info(
                    "%s module server started (PID: %d)", module_name, process.pid
                )
            else:
                logger.warning("%s module server failed to start", module_name)
        except Exception as e:
            logger.warning("Failed to start %s module server: %s", module_name, e)


def validate_config(config: dict) -> None:
    """Validate required config values. Raises ValueError with a clear message if invalid."""
    if not config:
        raise ValueError("Config is empty")
    audio = config.get("audio") or {}
    sr = audio.get("sample_rate", 16000)
    try:
        sr = int(sr)
    except (TypeError, ValueError):
        raise ValueError(
            "config.audio.sample_rate must be a positive integer"
        ) from None
    if sr <= 0:
        raise ValueError("config.audio.sample_rate must be positive")
    chunk = audio.get("chunk_duration_sec", 5.0)
    try:
        chunk = float(chunk)
    except (TypeError, ValueError):
        raise ValueError(
            "config.audio.chunk_duration_sec must be a positive number"
        ) from None
    if chunk <= 0:
        raise ValueError("config.audio.chunk_duration_sec must be positive")
    sens = audio.get("sensitivity", 2.5)
    try:
        sens = float(sens)
    except (TypeError, ValueError):
        raise ValueError("config.audio.sensitivity must be a number") from None
    if not (0.1 <= sens <= 10.0):
        raise ValueError("config.audio.sensitivity must be between 0.1 and 10.0")
    ollama = config.get("ollama") or {}
    model = ollama.get("model_name", "mistral")
    if not model or not str(model).strip():
        raise ValueError("config.ollama.model_name must be non-empty")

    base_url = ollama.get("base_url", "http://localhost:11434")
    from config import resolve_internal_service_url

    consul_cfg = (config.get("infrastructure") or {}).get("consul") or {}
    base_url = resolve_internal_service_url(base_url, consul_cfg)
    # _ensure_podman_ollama_if_localhost(base_url)  # disabled; use local ollama serve

    # Ensure Ollama is reachable and the configured model is available (fail fast)
    from llm.client import OllamaClient

    client = OllamaClient(base_url=base_url, model_name=str(model).strip())
    if not client.check_connection(timeout_sec=5.0):
        raise ValueError(
            f"Ollama is not reachable at {base_url}. "
            "Run ollama serve (local Ollama). Or start Podman Ollama if you re-enable it in compose/scripts."
        )
    # Wait briefly for model (e.g. still pulling); then warn and continue so Web UI can start
    wait_sec = 15
    interval_sec = 5
    for elapsed in range(0, wait_sec, interval_sec):
        if client.check_model_available(timeout_sec=5.0):
            break
        if elapsed + interval_sec >= wait_sec:
            logger.warning(
                "Ollama model '%s' is not available. Web UI will start; LLM calls will fail until you run: ollama pull %s",
                model,
                model,
            )
            break
        time.sleep(interval_sec)


def bootstrap_config_and_db(root: Path) -> tuple[AppConfig, Path]:
    """
    Load and validate config, set up logging, initialize database.
    Returns (config, db_path). Single place for entry-point startup.
    """
    config_path = os.environ.get("TALKIE_CONFIG", str(root / "config.yaml"))
    raw = load_config()
    validate_config(raw)
    config = AppConfig(raw)
    log_level = config.get_log_level()
    level = getattr(logging, log_level.upper(), logging.DEBUG)
    log_fmt = "%(asctime)s %(levelname)s %(name)s %(message)s"
    logging.basicConfig(level=level, format=log_fmt)
    log_path = config.get_log_path()
    if log_path:
        path = Path(log_path) if os.path.isabs(log_path) else root / log_path
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(path, encoding="utf-8")
        fh.setLevel(level)
        fh.setFormatter(logging.Formatter(log_fmt))
        logging.getLogger().addHandler(fh)
    logger.info("Config path: %s", config_path)
    from persistence.database import init_database

    db_path = Path(config.get_db_path())
    db_path.parent.mkdir(parents=True, exist_ok=True)
    init_database(str(db_path))
    logger.info("Database initialized at %s", db_path)
    return (config, db_path)


def main() -> None:
    """Start the web UI (run_web)."""
    from run_web import main as web_main

    web_main()


if __name__ == "__main__":
    main()
