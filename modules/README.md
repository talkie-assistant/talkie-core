# Talkie module standard (developer requirements)

This document instructs developers on how to build **self-contained modules** that integrate with Talkie. Each module must follow the layout, manifest, config, and docs standards below so the app can discover, merge config, and show help (H key) correctly.

**SDK**: Config normalization, discovery, and logging live in the **`sdk`** package. See [docs/SDK.md](../docs/SDK.md) for full API. Use `sdk.get_rag_section(raw)`, `sdk.get_browser_section(raw)`, and `sdk.abstractions` instead of importing from `app`.

---

## Required layout

Each module must live in a direct subdirectory of `modules/` and include:

| Item | Required | Description |
|------|----------|-------------|
| `config.yaml` | Yes | Module-specific config keys; merged with main config at runtime. |
| `MODULE.yaml` | Yes | Manifest with `name`, `version`, `description`, `order`, `enabled`, `config_file`. |
| `docs/` | Yes | Directory containing at least one entry doc (e.g. `docs/README.md`) used for H-key help. |
| `__init__.py` | No | Optional; implement `register(context)` for runtime integration. |

Minimum layout:

```
modules/
  myfeature/
    MODULE.yaml
    config.yaml
    docs/
      README.md
```

With runtime:

```
modules/
  myfeature/
    MODULE.yaml
    config.yaml
    docs/
      README.md
    __init__.py   # register(context)
```

---

## Config

- **Rule**: Each module's `config.yaml` must contain only that module's config keys (and any nested keys the main app expects, e.g. `browser.*`, `rag.*`). Do not duplicate root-level keys that belong to the app.
- **Merge order**: Module configs (in discovery order) → root `config.yaml` → `config.user.yaml`. Later sources override earlier (deep merge).
- **Override**: Users override module defaults in the root `config.yaml` or `config.user.yaml`.

---

## MODULE.yaml manifest

Required. All modules must have a manifest.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `name` | string | Yes | directory name | Display/log name. |
| `version` | string | Yes | (warn, use 0.0.0) | Semver (e.g. `1.0.0`). |
| `description` | string | No | (none) | Short description for UI/API. |
| `order` | number | No | 0 | Merge order; lower values merged first. |
| `enabled` | boolean | No | true | If false, module is skipped. |
| `config_file` | string | No | config.yaml | Config filename inside module dir. |
| `docs_path` | string | No | docs | Directory for docs (relative to module dir). |
| `help_entry` | string | No | README.md | Entry file for H-key help (under `docs_path`). |
| `ui_id` | string | No | (none) | UI identifier (e.g. browser → `web`) for help lookup. |

Example:

```yaml
name: myfeature
version: "1.0.0"
description: My optional feature.
order: 40
enabled: true
config_file: config.yaml
docs_path: docs
help_entry: README.md
ui_id: myui   # optional; used when Web UI shows this module by a different id
```

---

## Documentation (`docs/`)

- **Location**: Markdown only, inside `{module_dir}/docs`.
- **Entry doc**: At least one file (e.g. `docs/README.md` or `docs/index.md`) is used as the main help content when the user presses **H** or **h** and that module is active.
- **Optional**: Additional `.md` files (e.g. `docs/commands.md`, `docs/config.md`) linked from the entry or listed in manifest.

The app serves the entry doc via `GET /api/modules/{id}/help` (id = directory name or `ui_id`) and renders it in the help modal.

---

## Runtime integration (optional)

- **Entry point**: In the module's `__init__.py`, define `def register(context: dict) -> None`.
- **Two phases**: The app calls `register(context)` twice: once before the pipeline exists (phase 1), once after (phase 2). In phase 1, set `context["speech_components"]` if your module provides speech. In phase 2, use `context["pipeline"]` and set `context["rag_service"]` or call `pipeline.set_web_handler(...)` as needed.
- **Discovery**: No edits to `run_web.py` or `run.py` are required; the app discovers modules and calls `register(context)` for each.

See [MODULES.md](../MODULES.md) in the project root for context keys and legacy entry points.

---

## Server mode (optional)

When a module runs as an HTTP server, its config lives under `config.modules.<name>.server`. Standard keys: `enabled`, `host`, `port`, `timeout_sec`, `retry_max`, `circuit_breaker_*`, `api_key`, `use_service_discovery`, `endpoints`. See root `config.yaml` under `modules.speech.server`, `modules.rag.server`, or `modules.browser.server` for the template. API contract: [docs/MODULE_API.md](../docs/MODULE_API.md).

---

## Adding a new module (step-by-step)

1. Create a directory under `modules/`, e.g. `modules/myfeature/`.
2. Add `config.yaml` with only your module's config keys.
3. Add `MODULE.yaml` with `name`, `version`, `description`, `order`, `enabled`, `config_file`, and optionally `docs_path`, `help_entry`, `ui_id`.
4. Add `docs/` with at least `docs/README.md` (or `help_entry` you specified). This will be shown when the user presses H and your module is active.
5. Optionally add `__init__.py` with `register(context)` for pipeline integration.
6. No changes to core app code are required; discovery and config merge are automatic.

---

## When the module is a git submodule

If the module lives in a separate repo and is included as a git submodule under `modules/<name>/`:

- **Layout**: Same as above (`MODULE.yaml`, `config.yaml`, `docs/`, optional `__init__.py`). The main app discovers it by scanning `modules/`.
- **Dependencies**: The module repo does not copy `modules/api` or `sdk`; when used by Talkie, the main repo provides them on `sys.path`. Document in the module repo that it must be run from the Talkie tree (e.g. clone into `modules/<name>/` and run from project root).
- **Clone**: After cloning the main repo, run `git submodule update --init --recursive` to fetch module submodules.

### Main repo: including modules as submodules

To break modules out into separate projects and include them via git submodules:

1. Create separate repos (e.g. `talkie-module-speech`, `talkie-module-rag`, `talkie-module-browser`) with the same layout (config, MODULE.yaml, docs/, code). Do not copy `modules/api` or `sdk` into the module repo.
2. In the main repo, remove the in-repo module directory (e.g. `modules/speech`) and add the submodule:
   ```bash
   git submodule add <url-of-module-repo> modules/speech
   ```
   Repeat for each module. This creates/updates `.gitmodules` and records the submodule commit.
3. Keep `modules/api/`, `modules/discovery.py`, and `modules/__init__.py` in the main repo (shared infrastructure).
4. Clone/update: After cloning the main repo, run `git submodule update --init --recursive` to fetch all module submodules.
5. **run_module_server.py**: Module list is derived from `discover_modules()`; any discovered module with a `server` submodule that defines `main()` can be launched. Default ports come from config (`modules.<name>.server.port`) or the built-in fallback map.

---

## Adding a module to the marketplace

The in-app **Marketplace** (Web UI) lists module repos from the **talkie-assistant** GitHub organization and lets users install them as git submodules with one click. To make your module appear there:

1. Create a repository under the **talkie-assistant** org with name `talkie-module-<shortname>` (e.g. `talkie-module-weather`). The shortname becomes the directory under `modules/` when installed (e.g. `modules/weather`).
2. The **repo root** must be the module root: same layout as above—`MODULE.yaml`, `config.yaml`, `docs/` (e.g. `docs/README.md`), and optional `__init__.py` with `register(context)`. See the module standard in this README and the wiki [Modules](https://github.com/talkie-core.wiki/Modules) doc.
3. Do **not** include `modules/api` or `sdk` in the module repo; the main Talkie app provides them when the module is used inside the Talkie tree.
4. Once the repo is **public**, it appears in the in-app Marketplace; users can click **Install** to add it as a git submodule (requires a git clone of talkie-core).

**Compatibility:** Your module must work with the current talkie-core **SDK** and **modules/api**. Breaking changes in talkie-core may require module updates; follow the module standard and [docs/SDK.md](../docs/SDK.md) for the contract.

---

## Summary

- **Config**: Module-only keys in `config.yaml`; merged at runtime (module configs → root → user).
- **Manifest**: Required `MODULE.yaml` with `name`, `version`, and optional `docs_path`, `help_entry`, `ui_id`.
- **Docs**: Markdown in `docs/`; entry doc is shown in the H-key help modal when that module is active.
- **Runtime**: Optional `register(context)` in `__init__.py`; two-phase registration.
- **Server**: Optional; document `modules.<name>.server` and standard API.
