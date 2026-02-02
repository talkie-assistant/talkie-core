# Testing

## Overview

- **API and flow tests:** Pytest in `tests/`. Run with `pipenv run pytest tests/ -v`. Coverage is API and flow tests (no frontend unit tests).
- **E2E browser tests:** Playwright for the web UI (Marketplace tab, Refresh, Install). Run with `pipenv run pytest tests/e2e/ -m e2e -v` after installing Chromium: `playwright install chromium`. E2E tests are skipped if Playwright or Chromium is not installed.
- **Frontend unit tests:** Not in scope. The web UI is a single HTML file with inline JS; adding Jest/jsdom or similar would be a separate project. Coverage for the UI is API tests plus E2E flow tests only.

## Running tests

```bash
pipenv install --dev
pipenv run pytest tests/ -v
pipenv run pytest tests/ --cov --cov-report=term-missing   # with coverage
```

## E2E tests (Playwright)

1. Install dev dependencies and Chromium:
   ```bash
   pipenv install --dev
   pipenv run playwright install chromium
   ```
2. Run E2E tests (starts the web server in a subprocess on a dynamic port):
   ```bash
   pipenv run pytest tests/e2e/ -m e2e -v
   ```
3. To run all tests except E2E (faster): `pipenv run pytest tests/ -v -m "not e2e"`.

E2E tests cover: load page, Marketplace tab, Refresh, Install (mocked), error paths (list fails, empty list, git not available, install failure), tab switch, and basic visibility of heading and Refresh button. Screenshots on failure are saved to `tests/e2e/artifacts/` when available.
