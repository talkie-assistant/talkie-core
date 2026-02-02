"""Optional production smoke: run talkie-core container and hit / or /health (skip if image/podman missing)."""

from __future__ import annotations

import socket
import subprocess
import time
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent

# Image to run (default latest from GHCR)
TALKIE_CORE_IMAGE = "ghcr.io/talkie-assistant/talkie-core:latest"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _podman_available() -> bool:
    try:
        r = subprocess.run(
            ["podman", "version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _image_available(image: str) -> bool:
    try:
        r = subprocess.run(
            ["podman", "image", "exists", image],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


@pytest.mark.skipif(not _podman_available(), reason="podman not available")
@pytest.mark.skipif(not _image_available(TALKIE_CORE_IMAGE), reason="talkie-core image not present (run talkie pull)")
def test_production_smoke_core_container_serves_root() -> None:
    """Run talkie-core container, GET / returns 200 (optional smoke; skip if image missing)."""
    port = _free_port()
    config_dir = _ROOT / "config.yaml"
    data_dir = _ROOT / "data"
    if not config_dir.is_file():
        config_dir = _ROOT / "config.yaml.example"
    mounts = []
    if config_dir.is_file():
        mounts.extend(["-v", f"{config_dir}:/app/config.yaml:ro"])
    if data_dir.is_dir():
        mounts.extend(["-v", f"{data_dir}:/app/data"])
    cmd = [
        "podman", "run", "--rm",
        "-p", f"{port}:8765",
        *mounts,
        TALKIE_CORE_IMAGE,
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=str(_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        base = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 25.0
        while time.monotonic() < deadline:
            try:
                import urllib.request
                req = urllib.request.Request(base + "/", method="GET")
                with urllib.request.urlopen(req, timeout=2) as r:
                    if r.status == 200:
                        proc.terminate()
                        proc.wait(timeout=5)
                        return
            except Exception:
                time.sleep(0.3)
        pytest.fail("Core container did not serve / within 25s")
    finally:
        proc.terminate()
        proc.wait(timeout=10)
