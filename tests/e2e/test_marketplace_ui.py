"""
E2E tests for Marketplace UI: load HTML, Marketplace tab, Refresh, Install, error paths, tab switch.
Run: pytest tests/e2e/test_marketplace_ui.py -m e2e
Requires: playwright install chromium
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e


def test_load_and_marketplace_tab(e2e_page, e2e_base_url: str) -> None:
    """Load the app, click Marketplace tab, assert panel is visible."""
    page = e2e_page
    page.goto(e2e_base_url + "/")
    page.wait_for_load_state("networkidle")

    # Page loaded
    main_heading = page.get_by_role("heading", name="Talkie")
    main_heading.wait_for(state="visible", timeout=10000)

    # Click Marketplace tab
    page.get_by_role("button", name="Marketplace").click()
    panel = page.locator("#panel-marketplace")
    panel.wait_for(state="visible", timeout=5000)
    assert panel.evaluate("el => el.classList.contains('active')")


def test_marketplace_refresh(e2e_page, e2e_base_url: str) -> None:
    """Open Marketplace, click Refresh, wait for modules request and table update."""
    page = e2e_page
    page.goto(e2e_base_url + "/")
    page.wait_for_load_state("networkidle")

    # Wait for initial load (loadMarketplace runs on tab switch)
    with page.expect_response(
        lambda r: "/api/marketplace/modules" in r.url and r.status == 200, timeout=10000
    ) as resp_info:
        page.get_by_role("button", name="Marketplace").click()
    resp_info.value

    panel = page.locator("#panel-marketplace")
    panel.wait_for(state="visible", timeout=5000)
    list_el = page.locator("#marketplaceList")
    list_el.wait_for(state="visible", timeout=5000)

    # Click Refresh
    with page.expect_response(
        lambda r: "/api/marketplace/modules" in r.url and r.status == 200, timeout=10000
    ) as resp_info:
        page.get_by_role("button", name="Refresh").click()
    resp_info.value
    # Table should still be there (rows or "No talkie-module*" message)
    assert list_el.is_visible()


def test_marketplace_install_mocked(e2e_page, e2e_base_url: str) -> None:
    """When Install is clicked, mock API to return success; assert toast/success."""
    page = e2e_page
    page.goto(e2e_base_url + "/")
    page.wait_for_load_state("networkidle")

    # Mock install endpoint to succeed without really installing
    page.route(
        "**/api/marketplace/install",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body='{"ok":true,"message":"Module added. Restart the app to load it."}',
        ),
    )

    with page.expect_response(
        lambda r: "/api/marketplace/modules" in r.url and r.status == 200, timeout=10000
    ) as resp_info:
        page.get_by_role("button", name="Marketplace").click()
    resp_info.value

    # Click first Install button if present (some rows show "Installed" with no button)
    install_btn = page.locator("button.marketplace-install").first
    if install_btn.count() == 0:
        pytest.skip("No installable module in list (all installed or list empty)")
    install_btn.click()

    # Success toast or message
    toast = page.locator(".toast.show, .toast")
    toast.wait_for(state="visible", timeout=5000)
    assert (
        "installed" in toast.text_content().lower()
        or "added" in toast.text_content().lower()
    )


def test_marketplace_list_error_shown(e2e_page, e2e_base_url: str) -> None:
    """When /api/marketplace/modules returns error, assert #marketplaceError is shown."""
    page = e2e_page
    page.route(
        "**/api/marketplace/modules",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body='{"modules":[],"error":"Could not load marketplace"}',
        ),
    )
    page.route(
        "**/api/marketplace/git-available",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body='{"git_available":true}'
        ),
    )

    page.goto(e2e_base_url + "/")
    page.wait_for_load_state("networkidle")
    with page.expect_response(
        lambda r: "/api/marketplace/modules" in r.url, timeout=10000
    ) as resp_info:
        page.get_by_role("button", name="Marketplace").click()
    resp_info.value
    err_el = page.locator("#marketplaceError")
    err_el.wait_for(state="visible", timeout=5000)
    assert (
        "Could not load marketplace" in err_el.text_content()
        or "error" in err_el.text_content().lower()
    )


def test_marketplace_empty_state(e2e_page, e2e_base_url: str) -> None:
    """When /api/marketplace/modules returns empty list, assert no-module message."""
    page = e2e_page
    page.route(
        "**/api/marketplace/modules",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body='{"modules":[]}',
        ),
    )
    page.route(
        "**/api/marketplace/git-available",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body='{"git_available":true}'
        ),
    )

    page.goto(e2e_base_url + "/")
    page.wait_for_load_state("networkidle")
    with page.expect_response(
        lambda r: "/api/marketplace/modules" in r.url, timeout=10000
    ) as resp_info:
        page.get_by_role("button", name="Marketplace").click()
    resp_info.value
    list_el = page.locator("#marketplaceList")
    list_el.wait_for(state="visible", timeout=5000)
    assert (
        "No talkie-module" in list_el.text_content()
        or "repos found" in list_el.text_content()
    )


def test_marketplace_git_not_available(e2e_page, e2e_base_url: str) -> None:
    """When git_available is false, assert git hint visible and Install disabled."""
    page = e2e_page
    page.route(
        "**/api/marketplace/git-available",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body='{"git_available":false}'
        ),
    )
    page.route(
        "**/api/marketplace/modules",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body='{"modules":[{"repo_name":"talkie-module-foo","shortname":"foo","description":"Foo","installed":false}]}',
        ),
    )

    page.goto(e2e_base_url + "/")
    page.wait_for_load_state("networkidle")
    with page.expect_response(
        lambda r: "/api/marketplace/git-available" in r.url, timeout=10000
    ) as resp_info:
        page.get_by_role("button", name="Marketplace").click()
    resp_info.value
    git_hint = page.locator("#marketplaceGitHint")
    git_hint.wait_for(state="visible", timeout=5000)
    install_btn = page.locator("button.marketplace-install").first
    if install_btn.count() > 0:
        assert install_btn.is_disabled()


def test_marketplace_install_failure(e2e_page, e2e_base_url: str) -> None:
    """When install returns 400, assert failure toast and Install button re-enabled."""
    page = e2e_page
    page.route(
        "**/api/marketplace/install",
        lambda route: route.fulfill(
            status=400,
            content_type="application/json",
            body='{"error":"Invalid repo name"}',
        ),
    )
    page.route(
        "**/api/marketplace/modules",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body='{"modules":[{"repo_name":"talkie-module-foo","shortname":"foo","description":"Foo","installed":false}]}',
        ),
    )
    page.route(
        "**/api/marketplace/git-available",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body='{"git_available":true}'
        ),
    )

    page.goto(e2e_base_url + "/")
    page.wait_for_load_state("networkidle")
    with page.expect_response(
        lambda r: "/api/marketplace/modules" in r.url, timeout=10000
    ) as resp_info:
        page.get_by_role("button", name="Marketplace").click()
    resp_info.value

    install_btn = page.locator("button.marketplace-install").first
    install_btn.wait_for(state="visible", timeout=5000)
    install_btn.click()

    toast = page.locator(".toast.show, .toast")
    toast.wait_for(state="visible", timeout=5000)
    assert (
        "fail" in toast.text_content().lower()
        or "invalid" in toast.text_content().lower()
        or "error" in toast.text_content().lower()
    )
    # Button should be re-enabled after error
    install_btn.wait_for(state="visible", timeout=3000)
    assert not install_btn.is_disabled()


def test_marketplace_tab_switch(e2e_page, e2e_base_url: str) -> None:
    """Switch Main -> Marketplace -> Main -> Marketplace; assert panel and content."""
    page = e2e_page
    page.goto(e2e_base_url + "/")
    page.wait_for_load_state("networkidle")

    page.get_by_role("button", name="Marketplace").click()
    panel = page.locator("#panel-marketplace")
    panel.wait_for(state="visible", timeout=5000)
    assert panel.evaluate("el => el.classList.contains('active')")

    page.get_by_role("button", name="Main").click()
    main_panel = page.locator("#panel-main")
    main_panel.wait_for(state="visible", timeout=3000)
    assert main_panel.evaluate("el => el.classList.contains('active')")

    page.get_by_role("button", name="Marketplace").click()
    panel.wait_for(state="visible", timeout=5000)
    assert panel.evaluate("el => el.classList.contains('active')")
    assert page.locator("#marketplaceList").is_visible()


def test_marketplace_heading_visible(e2e_page, e2e_base_url: str) -> None:
    """Basic a11y: Marketplace panel has heading and Refresh button visible."""
    page = e2e_page
    page.goto(e2e_base_url + "/")
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name="Marketplace").click()

    panel = page.locator("#panel-marketplace")
    panel.wait_for(state="visible", timeout=5000)
    # Heading "Module marketplace" (h2 in panel)
    heading = panel.locator("h2")
    heading.wait_for(state="visible", timeout=3000)
    assert "marketplace" in heading.text_content().lower()
    refresh = page.get_by_role("button", name="Refresh")
    assert refresh.is_visible()
