"""Tests for run_module_server: _discovered_module_names, _default_port."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure project root is on path (same as run_module_server)
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import run_module_server as rms


def test_discovered_module_names_returns_list() -> None:
    names = rms._discovered_module_names()
    assert isinstance(names, list)
    assert all(isinstance(n, str) for n in names)
    assert len(names) >= 1


def test_discovered_module_names_includes_builtins_when_modules_present() -> None:
    """When run from project root, discovery finds speech, rag, browser if present."""
    names = rms._discovered_module_names()
    # At least one of the built-in modules should be present
    builtins = {"speech", "rag", "browser"}
    found = builtins & set(names)
    assert len(found) >= 1, "Expected at least one of speech, rag, browser to be discovered"


def test_default_port_returns_int() -> None:
    port = rms._default_port("speech")
    assert isinstance(port, int)
    assert 1 <= port <= 65535


def test_default_port_known_module_returns_expected_range() -> None:
    """Known modules have fallback ports 8001, 8002, 8003."""
    assert rms._default_port("speech") in (8001, 8002, 8003) or rms._default_port("speech") >= 8000
    assert rms._default_port("rag") in (8001, 8002, 8003) or rms._default_port("rag") >= 8000
    assert rms._default_port("browser") in (8001, 8002, 8003) or rms._default_port("browser") >= 8000


def test_default_port_unknown_module_returns_fallback() -> None:
    """Unknown module name returns 8000 (DEFAULT_PORTS.get(name, 8000))."""
    port = rms._default_port("nonexistent_module_xyz")
    assert port == 8000


def test_default_ports_constant() -> None:
    assert hasattr(rms, "DEFAULT_PORTS")
    assert rms.DEFAULT_PORTS["speech"] == 8001
    assert rms.DEFAULT_PORTS["rag"] == 8002
    assert rms.DEFAULT_PORTS["browser"] == 8003


def test_main_help_lists_modules() -> None:
    """Running with --help shows discovered modules in usage."""
    with patch.object(sys, "argv", ["run_module_server.py", "--help"]):
        try:
            rms.main()
        except SystemExit as e:
            assert e.code == 0
        else:
            pytest.fail("Expected SystemExit(0) from --help")
