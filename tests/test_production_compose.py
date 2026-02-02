"""Tests for production mode: compose.production.yaml validity, config-only module list."""

from __future__ import annotations

from pathlib import Path

import yaml

import pytest

# Project root
_ROOT = Path(__file__).resolve().parent.parent


def test_compose_production_yaml_exists() -> None:
    path = _ROOT / "compose.production.yaml"
    assert path.is_file(), "compose.production.yaml must exist"


def test_compose_production_yaml_valid_structure() -> None:
    """Production compose has required services and uses image: (no build)."""
    path = _ROOT / "compose.production.yaml"
    with open(path) as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict)
    services = data.get("services")
    assert isinstance(services, dict), "compose.production.yaml must define services"
    required = [
        "talkie-core",
        "consul-server",
        "keydb",
        "haproxy",
        "chroma",
        "speech",
        "rag",
        "browser",
        "healthbeat",
    ]
    for name in required:
        assert name in services, f"compose.production.yaml must define service {name}"
    for name, svc in services.items():
        assert isinstance(svc, dict), f"service {name} must be a dict"
        assert "image" in svc, f"service {name} must have image: (no build in production)"
        assert "build" not in svc, f"service {name} must not have build: in production"
    assert "networks" in data
    assert "volumes" in data


def test_compose_production_talkie_core_exposes_8765() -> None:
    path = _ROOT / "compose.production.yaml"
    with open(path) as f:
        data = yaml.safe_load(f)
    core = data.get("services", {}).get("talkie-core", {})
    ports = core.get("ports", [])
    assert any("8765" in str(p) for p in ports), "talkie-core must expose 8765"
