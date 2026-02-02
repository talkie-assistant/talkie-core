"""
E2E fixtures: Playwright browser/page and test server (subprocess).
Skips all E2E tests if Playwright is not installed.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

# Skip entire e2e module if Playwright not installed
pytest.importorskip("playwright")

# Project root (talkie-core)
_ROOT = Path(__file__).resolve().parent.parent.parent


def _free_port() -> int:
    """Return a free port on 127.0.0.1."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def e2e_base_url() -> str:
    """
    Start the real web server in a subprocess on a dynamic port; wait until ready; yield base URL.
    Terminate the process on teardown.
    """
    port = _free_port()
    env = {**dict(__import__("os").environ), "TALKIE_WEB_PORT": str(port)}
    run_web = _ROOT / "run_web.py"
    proc = subprocess.Popen(
        [sys.executable, str(run_web)],
        cwd=str(_ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        base = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            try:
                import urllib.request

                req = urllib.request.Request(base + "/", method="GET")
                with urllib.request.urlopen(req, timeout=2) as r:
                    if r.status == 200:
                        yield base
                        return
            except Exception:
                time.sleep(0.2)
        pytest.fail("E2E server did not become ready in 15s")
    finally:
        proc.terminate()
        proc.wait(timeout=5)


@pytest.fixture
def e2e_page(e2e_base_url: str):
    """
    Playwright browser context and page. Uses a fresh page per test.
    Closes context and browser on teardown.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                base_url=e2e_base_url,
                ignore_https_errors=True,
            )
            context.set_default_timeout(15000)
            context.set_default_navigation_timeout(15000)
            page = context.new_page()
            try:
                yield page
            finally:
                context.close()
        finally:
            browser.close()


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """On E2E test failure, save page screenshot to tests/e2e/artifacts/ if page is available."""
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" and report.failed and "e2e_page" in item.fixturenames:
        try:
            page = item.funcargs.get("e2e_page")
            if page and hasattr(page, "screenshot"):
                artifacts = _ROOT / "tests" / "e2e" / "artifacts"
                artifacts.mkdir(parents=True, exist_ok=True)
                path = artifacts / f"{item.name}.png"
                page.screenshot(path=str(path))
        except Exception:
            pass
