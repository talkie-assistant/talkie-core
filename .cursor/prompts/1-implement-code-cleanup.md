# Code Quality & Cleanup Audit

**Purpose:** This prompt is run periodically to clean the codebase and keep it production-ready. It guides a comprehensive search and cleanup of duplicate, unused, and inefficient code while preserving all existing functionality.

**Conventions:** Use `.yaml` (not `.yml`) for YAML files. In output or comments, use only these symbols for status: ✓ (success), ! (warning), ✗ (failure). Before **removing** any existing functionality, ask in a clear manner and get confirmation. Prefer batch changes where possible; report number of batches up front and remaining while completing. When fixing an error, scan the rest of the codebase for similar issues.

---

## 1. Duplicate Code Detection

- **App, SDK, and modules:** Search for duplicate functionality across `app/`, `sdk/`, and module servers: `modules/browser/server.py`, `modules/rag/server.py`, `modules/speech/server.py`, and the API layer `modules/api/` (server, clients: `browser_client.py`, `rag_client.py`, `speech_client.py`, retry, circuit_breaker, etc.).
- **Business logic:** Identify duplicate logic in `app/`, `llm/`, `profile/`, `curation/`, `persistence/`, and `sdk/`. Check for overlap between `app/audio_utils.py` and `sdk/audio_utils.py`, and between `app/abstractions.py` and `sdk/abstractions.py` (canonical source is `sdk/abstractions.py`; `app/abstractions.py` re-exports for backward compatibility).
- **Module internals:** Look for duplicate patterns across `modules/browser/`, `modules/rag/`, and `modules/speech/` (e.g. base classes in `*/base.py`, config loading, server startup).
- **Persistence:** Find duplicate query or repo patterns in `persistence/` (`database.py`, `history_repo.py`, `settings_repo.py`, `training_repo.py`, `schema.sql`).
- **Web:** Check for duplicate logic in `web/` (`index.html`, `audio-worklet.js`).
- **Validation/parsing:** Identify duplicate validation or parsing logic across the repo.

---

## 2. Unused Code Identification

- **Dead code:** Find code that is never executed (unreachable branches, unused functions/classes).
- **Imports and dependencies:** Identify unused imports per file. For dependencies, check **Pipfile** (main app); `requirements.txt` is used only by `rifai_scholar_downloader/` and by module Docker builds (`modules/api/`, `modules/browser/`, `modules/rag/`, `modules/speech/`). Remove unused packages from Pipfile only when confirmed unused project-wide.
- **Entry points and servers:** Locate unused entry points (`run.py`, `run_web.py`, `run_module_server.py`, `talkie` CLI) and unused module servers or API endpoints.
- **Web assets:** Find unused or obsolete assets in `web/`.
- **Persistence and schema:** Identify unused tables, columns, or repo methods relative to `persistence/schema.sql` and call sites.
- **Configuration:** Find unused options in root `config.yaml` and in `modules/browser/config.yaml`, `modules/rag/config.yaml`, `modules/speech/config.yaml`. Cross-check with `config.py` and `sdk/config.py`.
- **Rifai subproject:** Within `rifai_scholar_downloader/`, flag unused modules or dependencies in its `requirements.txt`.

---

## 3. Code Consolidation

- **Safely** consolidate duplicate functionality into `sdk/` or shared helpers in `app/`. Prefer extending `sdk/` for shared contracts and utilities so modules and app both depend on one place.
- **Abstractions:** Use `sdk/abstractions.py` as the single source of truth for speech-related interfaces and no-ops. Keep `app/abstractions.py` as a re-export for backward compatibility unless a deliberate migration away from `app.abstractions` is agreed; do not remove it without explicit confirmation.
- **Base classes:** Use or introduce shared base classes in modules (e.g. `modules/speech/stt/base.py`, `modules/speech/tts/base.py`, `modules/browser/base.py`) and consistent client patterns in `modules/api/`.
- **Config and discovery:** Prefer `sdk.config`, `sdk.discovery`, and `sdk.logging` over duplicated logic in app or modules. See `docs/SDK.md` and `MODULES.md`.
- Consolidate common operations into utility modules (e.g. under `sdk/` or shared app helpers) where it reduces duplication without breaking encapsulation.

---

## 4. Cleanup Actions

- Remove unused imports; fix or remove unused variables and dead code.
- Delete dead code and unreachable branches after confirming no callers (including tests and CLI).
- Remove or deprecate unused entry points, module endpoints, or CLI commands only after explicit confirmation.
- Clean up unused persistence schema or repo methods only after verifying no references (including migrations or future use).
- Remove unused configuration keys only after confirming they are not documented as user-facing or used by scripts.
- Delete unused web assets and obsolete files.
- When removing a dependency from Pipfile, ensure it is not referenced in `rifai_scholar_downloader/` or in module `requirements.txt`; leave module Docker deps to their own files.

---

## 5. Refactoring Opportunities

- Extract common patterns into base classes or ABCs in `sdk/` or module `base.py` files.
- Align on shared interfaces (e.g. `sdk.abstractions`, `sdk.config`) and avoid re-implementing the same contract in app or modules.
- Consolidate similar validation or parsing logic into a single place (e.g. config validation, URL or path parsing).
- Align repo and client patterns across `persistence/` and `modules/api/` (e.g. error handling, retries, timeouts).
- Ensure new code in modules uses `sdk` (config, discovery, logging, abstractions) rather than app-specific imports where the SDK is the intended contract.

---

## 6. Testing & Validation

Run after cleanup to ensure nothing is broken:

```bash
# Unit and integration tests
pipenv run pytest tests/ -v

# With coverage (optional)
pipenv run pytest tests/ --cov --cov-report=term-missing

# Exclude E2E for a quick check (optional)
pipenv run pytest tests/ -v -m "not e2e"

# E2E (Playwright); run after: pipenv run playwright install chromium
pipenv run pytest tests/e2e/ -m e2e -v

# Lint and format
pipenv run ruff check .
pipenv run ruff format .

# Type checking (optional)
pipenv run mypy .
```

If the project uses a single top-level entry for quality, prefer the same commands as in `README.md` and `docs/Testing.md`.

---

## 7. Documentation Update

- **API and modules:** Update `docs/MODULE_API.md` and `docs/SDK.md` for any removed or changed endpoints, or for consolidated utilities and shared modules.
- **Testing:** Adjust `docs/Testing.md` if test layout, markers (e.g. `e2e`), or commands change.
- **Structure and usage:** Update `MODULES.md`, `modules/README.md`, and root `README.md` as needed for consolidated code, new shared modules, or changed entry points.
- **Changelog:** Record cleanup actions (removed dead code, consolidated duplicates, dependency removals) in the project’s changelog or release notes if one is maintained.

---

## Goals

- Reduce codebase size by removing duplicates and dead code.
- Improve maintainability and readability.
- Eliminate technical debt without breaking behavior.
- **Maintain all existing functionality;** do not remove features or APIs without explicit confirmation.
- Keep the codebase in a production-ready state for periodic audits.
- Optimize for resource efficiency: aim to reduce the application's memory usage and, where applicable, lower CPU consumption, without sacrificing functionality, stability, or accuracy.
- Assess memory and CPU footprint in the process of cleanup; prefer approaches that maintain or improve performance characteristics and resource efficiency.

