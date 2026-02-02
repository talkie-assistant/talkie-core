"""Integration tests: installer idempotency, talkie --dev vs production mode selection."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent


def _run(cmd: list[str], cwd: Path | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, **(env or {})}
    return subprocess.run(
        cmd,
        cwd=str(cwd or _ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.mark.skipif(not (_ROOT / "install.sh").is_file(), reason="install.sh not in repo")
def test_installer_idempotency_does_not_overwrite_config(tmp_path: Path) -> None:
    """Run install.sh twice; second run must not overwrite existing config.yaml."""
    install_sh = _ROOT / "install.sh"
    env = {"TALKIE_HOME": str(tmp_path)}
    out1 = _run(["bash", str(install_sh)], env=env)
    assert out1.returncode == 0, f"First install failed: {out1.stderr}"
    config = tmp_path / "config.yaml"
    assert config.is_file(), "First install should create config.yaml"
    marker = "idempotency_marker: preserved"
    config.write_text(config.read_text() + "\n# " + marker + "\n")
    out2 = _run(["bash", str(install_sh)], env=env)
    assert out2.returncode == 0, f"Second install failed: {out2.stderr}"
    content = config.read_text()
    assert marker in content, "Second install must not overwrite config.yaml (idempotency)"


@pytest.mark.skipif(not (_ROOT / "talkie").exists(), reason="talkie script not in repo")
def test_talkie_doctor_dev_mode_shows_development() -> None:
    """TALKIE_DEV=1 ./talkie doctor should report development mode."""
    out = _run(["./talkie", "doctor"], env={**os.environ, "TALKIE_DEV": "1"})
    assert out.returncode == 0, f"talkie doctor failed: {out.stderr}"
    combined = (out.stdout + out.stderr).lower()
    assert "development" in combined or "compose.yaml" in combined, (
        "Expected development mode in doctor output"
    )


@pytest.mark.skipif(not (_ROOT / "talkie").exists(), reason="talkie script not in repo")
def test_talkie_doctor_production_mode_shows_production() -> None:
    """TALKIE_DEV=0 ./talkie doctor should report production mode."""
    out = _run(["./talkie", "doctor"], env={**os.environ, "TALKIE_DEV": "0"})
    assert out.returncode == 0, f"talkie doctor failed: {out.stderr}"
    combined = (out.stdout + out.stderr).lower()
    assert "production" in combined or "compose.production" in combined, (
        "Expected production mode in doctor output"
    )
