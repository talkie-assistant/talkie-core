# Plan: Split modules into separate repositories

This document lists each module to be separated, the proposed repository for it, and the steps to perform the split. The main repo (talkie-core) will include them as **git submodules** under `modules/<name>/`.

---

## Modules to separate

| Module   | Current path      | Proposed repository        | Description |
|----------|-------------------|----------------------------|-------------|
| **Speech** | `modules/speech/` | `talkie-module-speech`    | Audio capture, STT, TTS, speaker filter, calibration. |
| **RAG**    | `modules/rag/`    | `talkie-module-rag`       | Document ingest, embedding, retrieval for LLM context. |
| **Browser**| `modules/browser/`| `talkie-module-browser`   | Voice-controlled web: search, open URL, store page for RAG. |

**GitHub organization:** Create these three repos under your GitHub organization. Use `<ORG>` below as the org name (e.g. `talkie-app` or your org).

- `https://github.com/<ORG>/talkie-module-speech`
- `https://github.com/<ORG>/talkie-module-rag`
- `https://github.com/<ORG>/talkie-module-browser`

---

## What stays in the main repo (talkie-core)

- **Shared module infrastructure** (required for discovery and server mode):
  - `modules/api/` (clients, server base, Consul, circuit breaker, etc.)
  - `modules/discovery.py` (re-exports from `sdk.discovery`; optional default `modules_root`)
  - `modules/__init__.py`
- **SDK** (`sdk/`) – config, discovery, abstractions, logging. Module repos do **not** copy this; the main app provides it on `sys.path` when running.
- **App entry points:** `run_web.py`, `run_module_server.py`, `config.py`, etc.
- **No** in-repo copies of `modules/speech`, `modules/rag`, `modules/browser` – those become submodule pointers only.

---

## What goes into each module repository

Each module repo’s **root** is the module root (same layout as current `modules/<name>/`):

- `MODULE.yaml` (name, version, description, order, docs_path, help_entry, ui_id)
- `config.yaml` (module-only config keys)
- `docs/` (e.g. `docs/README.md` for H-key help)
- `__init__.py` with `register(context)` if the module has runtime integration
- Module-specific code (e.g. `server.py`, `stt/`, `tts/`, `store.py`, etc.)

**Do not** put `modules/api` or `sdk` in a module repo. The main Talkie repo provides those when the module is used inside the Talkie tree.

---

## Execution steps (high level)

1. **Create the three empty repos** in the GitHub organization (you).
2. **For each module (speech, rag, browser):**
   - Copy `modules/<name>/` contents into a new directory (e.g. via `rsync`), excluding `__pycache__` and `*.pyc`.
   - `git init`, initial commit, add remote, push to the new repo.
3. **In talkie-core:** Remove the in-repo `modules/speech`, `modules/rag`, `modules/browser` directories and add each as a submodule at the same path:
   - `git submodule add https://github.com/<ORG>/talkie-module-speech.git modules/speech`
   - Same for `talkie-module-rag` → `modules/rag`, `talkie-module-browser` → `modules/browser`.
4. **Documentation:** Update main repo README (and wiki) with clone instructions: `git clone --recurse-submodules` or `git submodule update --init --recursive` after clone.

Detailed commands are in **docs/MODULE_SUBMODULES_MIGRATION.md**.

---

## Summary table

| Module   | Proposed repo            | Hosting |
|----------|--------------------------|---------|
| Speech   | `talkie-module-speech`   | GitHub org `<ORG>` |
| RAG      | `talkie-module-rag`      | GitHub org `<ORG>` |
| Browser  | `talkie-module-browser`  | GitHub org `<ORG>` |

---

## Questions

1. **Organization name:** What is the GitHub organization name? (I used `<ORG>` in the plan; we can replace it once you confirm.)
2. **Main repo location:** Will `talkie-core` (or the main app repo) also live under this org, or stay under your user? (No change to the plan either way; only docs/URLs may reference it.)
3. **Repo naming:** Are `talkie-module-speech`, `talkie-module-rag`, and `talkie-module-browser` the names you want, or do you prefer something else (e.g. `talkie-speech`, `talkie-rag`, `talkie-browser`)?
4. **Other modules:** Do you expect to add more modules in separate repos later? (The same pattern applies; this plan doesn’t need to change.)
5. **Visibility:** Should the new repos be public or private? (The migration doc assumes public; we can note private if you prefer.)
