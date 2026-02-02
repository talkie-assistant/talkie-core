# Changelog

## Unreleased

### Module registration and docs

- **register(context):** Single `register(context)` entry point per module. The app discovers modules under `modules/` and calls `register(context)` in two phases (pipeline inputs then pipeline attachment). New modules plug in without editing `run_web.py` or `run.py`. Speech, RAG, and browser implement `register(context)`; local server startup in `run.py` uses discovery instead of a hardcoded module list. MODULES.md and docs/SDK.md document the context keys and two-phase flow.
- **README:** Auto sensitivity documented as implemented (enable with `audio.auto_sensitivity: true` and related keys). To-do section updated: module registration done; code quality audit/cleanup noted below.

### Code quality and cleanup

- **resample_int16:** Moved from `app/audio_utils.py` into `sdk/audio_utils.py`; `app/audio_utils` re-exports from SDK for backward compatibility. SDK and docs/SDK.md now document `chunk_rms_level`, `INT16_MAX`, and `resample_int16`.
- **Docstrings:** `modules/speech/__init__.py` SpeechFactory docstring updated from "app.abstractions" to "sdk.abstractions". `tests/test_audio_utils.py` docstring updated to reflect SDK as source.
- **Unused imports/vars:** Removed unused `git_available` (module_cmd.py), `MODULE_PREFIX` (tests/test_marketplace.py), `MagicMock` (tests/test_vosk_engine.py); fixed unused `e` in tests/test_api_marketplace.py. Added noqa for FastAPI `File(...)` in run_web.py (B008). Ruff F401/F841/B008 pass.
- **chunk_rms_level:** Consolidated duplicate implementation from `app/audio_utils.py` and `modules/speech/audio/level.py` into `sdk/audio_utils.py`. App and speech module now use the SDK; `app/audio_utils` and `modules/speech/audio/level` re-export for backward compatibility. Speech server imports `chunk_rms_level` from `sdk.audio_utils`.
- **Ruff F841:** Removed unused variable `conversation_context` in `app/pipeline.py` and unused mock binding in `tests/test_browser.py`. All ruff checks pass.
- **Module servers:** Consolidated duplicate error response logic into `BaseModuleServer` helpers: `_service_unavailable_response()`, `_error_response(status_code, error_code, message)`, and `_require_service(service)`. Browser, RAG, and speech module servers now use these helpers instead of inline `JSONResponse` blocks. Metrics attributes are initialized before middleware that uses them.
- **run.py:** Removed duplicate and redundant imports inside `_maybe_start_local_servers`; added top-level `requests` and `subprocess` where used. Local module server list now comes from `modules.discovery.discover_modules()` instead of a hardcoded list.
- **Ruff:** Applied `ruff format` project-wide; fixed E402 (module-level import) in `run_web.py`. Audit scope for further consolidation remains in `.cursor/prompts/1-implement-code-cleanup.md`.
- **Tests:** Calibration tests now pass `AppConfig(config)` to `create_pipeline` so config has `resolve_internal_service_url` (fixes two previously failing tests).
- **Documentation:** Persistence pattern (repos use `with_connection` and log+re-raise on `sqlite3.Error`) documented in `persistence/database.py`. Module server config template (same structure for `modules.<name>.server`) documented in MODULES.md. README notes that `requirements.txt` is for the rifai_scholar_downloader subproject; main app uses Pipfile. MODULE_API.md documents the shared response helpers for implementers.
