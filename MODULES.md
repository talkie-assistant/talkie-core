# Talkie module standard

The app discovers **modules** by scanning the `modules/` directory. Adding a new subdirectory with the required structure is enough for config to be merged; optional runtime wiring is documented below.

**Developer requirements**: For the full self-contained module standard (manifest with version, docs in `docs/`, H-key help), see [modules/README.md](modules/README.md).

**SDK**: Config normalization, speech abstractions, discovery, and logging for modules live in the **`sdk`** package. See [docs/SDK.md](docs/SDK.md) for full API and usage. Modules should use `sdk.get_rag_section(raw)`, `sdk.get_browser_section(raw)`, and `sdk.abstractions` (e.g. `AudioCapture`, `STTEngine`) instead of duplicating logic or importing from `app`.

## What the app recognizes

- **Location**: Any direct subdirectory of `modules/` (e.g. `modules/myfeature/`).
- **Config**: The directory must contain a config file (by default `config.yaml`). Its contents are merged into the app config in discovery order (see below).
- **Optional manifest**: A file named `MODULE.yaml` in the module directory can override name, order, and whether the module is enabled.

## Directory structure

Minimum:

```
modules/
  myfeature/
    config.yaml     # required for discovery
```

With manifest:

```
modules/
  myfeature/
    MODULE.yaml     # optional
    config.yaml     # required (or path given in MODULE.yaml config_file)
    __init__.py     # optional; use for runtime entry points
```

## MODULE.yaml manifest

Optional. If present, it can define:

| Key           | Type    | Default        | Description |
|---------------|---------|----------------|-------------|
| `name`        | string  | directory name | Display/log name for the module. |
| `description` | string  | (none)         | Short description. |
| `enabled`     | boolean | true           | If false, the module is skipped (no config merge). |
| `order`       | number  | 0              | Merge order: lower values are merged first. Ties are broken by directory name. |
| `config_file` | string  | config.yaml    | Config filename inside this module directory. |

Example:

```yaml
name: myfeature
description: My optional feature.
order: 40
enabled: true
config_file: config.yaml
```

## Config merge order

1. Module configs in **discovery order** (each module’s `config.yaml` or `config_file`). Order is: `order` value from MODULE.yaml (default 0), then directory name.
2. Root `config.yaml` (or path from `TALKIE_CONFIG`).
3. `config.user.yaml` in the same directory as the root config, if it exists.

Later sources override earlier ones (deep merge).

## Module server config (HTTP API)

When a module runs as an HTTP server (e.g. speech, rag, browser), its config lives under `config.modules.<name>.server`. All module server blocks share the same structure so you can copy one block when adding a new module. Typical keys: `enabled`, `host`, `port`, `timeout_sec`, `retry_max`, `retry_delay_sec`, `health_check_interval_sec`, `circuit_breaker_failure_threshold`, `circuit_breaker_recovery_timeout_sec`, `api_key`, `use_service_discovery`, `endpoints`. See root `config.yaml` under `modules.speech.server`, `modules.rag.server`, or `modules.browser.server` for the template.

## Adding a new module (config only)

1. Create a directory under `modules/`, e.g. `modules/myfeature/`.
2. Add `config.yaml` with your default keys (they will be merged into the app config).
3. Optionally add `MODULE.yaml` to set `order` or `enabled`.
4. No code changes in the core app are required for your config to be loaded.

## Runtime integration (optional)

Config discovery is automatic (via `sdk.discovery`). The app discovers modules under `modules/` and calls **`register(context)`** on each module that provides it. No edits to `run_web.py` or `run.py` are needed for new modules.

### Two-phase registration

The app calls `register(context)` twice per module:

1. **Phase 1** (no `context["pipeline"]`): Modules that provide pipeline inputs may set `context["speech_components"]` (e.g. speech sets capture, STT, TTS, speaker filter, auto_sensitivity). Other modules no-op.
2. **Phase 2** (after pipeline is created, `context["pipeline"]` set): Modules attach to the pipeline (e.g. rag sets retriever and `context["rag_service"]`; browser sets web handler). Speech no-ops in phase 2.

### Context keys

| Key | Phase | Description |
|-----|-------|-------------|
| `config` | 1, 2 | App config (AppConfig or dict-like). |
| `settings_repo` | 1, 2 | Settings repository. |
| `history_repo` | 1, 2 | History repository. |
| `training_repo` | 1, 2 | Training facts repository. |
| `conn_factory` | 1, 2 | DB connection factory. |
| `broadcast` | 1, 2 | Callable(msg) to send JSON to all WebSocket clients. |
| `web_capture` | 1, 2 | WebSocket audio capture for the pipeline. |
| `speech_components` | 1 (set by speech) | Capture, STT, TTS, speaker filter, auto_sensitivity. |
| `pipeline` | 2 | The pipeline instance. |
| `rag_service` | 2 (set by rag) | RAG service for Documents UI. |

### Adding a new runtime module

1. Create a directory under `modules/` with `config.yaml` (and optionally `MODULE.yaml`).
2. In the module's `__init__.py`, define `def register(context: dict) -> None`. In phase 1, set `context["speech_components"]` if your module provides speech; in phase 2, use `context["pipeline"]` and set `context["rag_service"]` or call `pipeline.set_web_handler(...)` as needed.
3. No changes to `run_web.py` or `run.py` are required; the app discovers and calls `register(context)` for every discovered module.

Legacy entry points (`create_speech_components`, `register_with_pipeline`, `create_web_handler`) remain available for direct use; the built-in modules use them inside `register(context)`.

## Summary

- **Config**: Add `modules/<name>/config.yaml` (and optionally `MODULE.yaml`). The app will discover and merge it.
- **SDK**: Use `sdk` for config section access, abstractions, discovery, and logging; see [docs/SDK.md](docs/SDK.md).
- **Runtime**: Implement `register(context)` in your module's `__init__.py`; the app discovers modules and calls it in two phases (see above).
