# Talkie-core

**TLDR:** Talkie-core is a local, voice-first app that helps people with reduced speech clarity communicate. You speak; it transcribes, clarifies with a local LLM, and shows (or speaks) the result. All processing stays on your machine.

## Stack (engineering view)

- **Runtime:** Python 3.11+, Pipenv. Entry: Web UI via `run_web.py` (FastAPI + WebSocket + static HTML at http://localhost:8765).
- **Audio → text:** Microphone capture (sounddevice) → STT (Whisper default, or Vosk). Optional speaker filter and calibration.
- **Text → response:** Local LLM via Ollama (e.g. phi, mistral). Optional two-step flow: raw STT → regeneration (intent/homophone fix) → completion. Profile built from user context, corrections, accepted responses, and training facts.
- **Persistence:** SQLite (history, settings, training). Optional curation and JSONL export for fine-tuning.
- **Optional modules:** RAG (documents in Chroma, Ollama embeddings), voice-controlled browser (search, open URL, store page for RAG). Modules are discovered under `modules/` and register with the pipeline; they can run in-process or as HTTP servers.
- **Optional infrastructure:** Podman (Compose) for Consul, KeyDB, HAProxy, Chroma, module servers, healthbeat, VictoriaMetrics, Grafana. Managed by the `./talkie` CLI.

Full documentation (features, configuration, architecture, modules, SDK, troubleshooting) lives in the **project wiki** (see the wiki link in the repository).

## Local dev: get running

1. **Requirements:** Python 3.11+, microphone, [Ollama](https://ollama.ai/) running with a model (e.g. `ollama pull phi`).
2. **Install:** `pipenv install`
3. **Start:** Use the Talkie-core CLI (do not run the Python process directly):
   - **Web UI only (no containers):** `./talkie start web` → open http://localhost:8765
   - **Full stack (containers + Web UI):** `./talkie start all`
4. **Optional:** Set `TALKIE_CONFIG` to the path of a different `config.yaml`.

Other useful commands: `./talkie status`, `./talkie logs <service> --follow`, `./talkie stop`, `./talkie help`. See the wiki for configuration, service groups (`core`, `modules`), and troubleshooting.

## Production install (image-only)

Run the thin installer to set up a minimal environment and pull images from GitHub Container Registry (GHCR):

```bash
curl -sSL https://raw.githubusercontent.com/talkie-assistant/talkie-core/main/install.sh | sh
```

This creates `~/.talkie` (or `TALKIE_HOME`) with the talkie script, `compose.production.yaml`, and config. Then:

```bash
$HOME/.talkie/talkie pull    # pull images from GHCR
$HOME/.talkie/talkie start   # start all services (Web UI in talkie-core container)
$HOME/.talkie/talkie app     # start and open http://localhost:8765
```

No Python or pipenv on the host; everything runs in containers. Edit `config.yaml` to set `modules.enabled` (e.g. `[speech, rag, browser]`). Pin a version with `TALKIE_IMAGE_TAG=v1.0.0` or set `image_tag` in config.

## Developer install (full dev env)

One-command setup for building from source (clone, submodules, pipenv, TALKIE_DEV=1):

```bash
curl -sSL https://raw.githubusercontent.com/talkie-assistant/talkie-core/main/install.sh | sh -s -- --developer-mode
```

Then `cd` into the clone and run `./talkie start` or `./talkie app` (build from source, Web UI via pipenv).

## Mode: development vs production

- **Development:** When run from a repo that has `compose.yaml` and `modules/`, the CLI uses `compose.yaml`, builds images from Dockerfiles, and runs the Web UI locally with pipenv. Set `TALKIE_DEV=1` or use `./talkie --dev` to force dev mode.
- **Production:** When run from an install dir (e.g. `~/.talkie`) with no `modules/` tree, the CLI uses `compose.production.yaml`, pulls images from GHCR, and runs the Web UI inside the talkie-core container. Set `TALKIE_DEV=0` or use `./talkie --production` to force production mode.

## Upgrade and troubleshooting

- **Production:** Run `./talkie pull` to refresh images (or set `TALKIE_IMAGE_TAG` to pin a version). Run `./talkie doctor` to check podman, config, mode, and container health.
- **Development:** `git pull && git submodule update --init --recursive && pipenv install --dev`. Then `./talkie build` and `./talkie start`.
- **Exit codes:** 0 = success, 1 = usage/config error, 2 = runtime/build/pull failure (e.g. `talkie doctor` exits 2 if issues found).

See the project wiki for full Troubleshooting, Configuration, and Module docs.

## Tests and code quality

```bash
pipenv install --dev
pipenv run pytest tests/ -v
pipenv run pytest tests/ --cov --cov-report=term-missing   # with coverage (requires pytest-cov)
pipenv run ruff check .
pipenv run ruff format .
```

Tests cover core app (pipeline, browse command, audio, web capture), config, LLM (client and prompts), persistence (database, history/settings/training repos), profile (builder, store, constants), curation (curator, export, scheduler), modules (discovery, browser, RAG, speech calibration, API retry/circuit breaker), SDK (config, abstractions, audio utils, logging), and the rifai downloader helpers. Tests use many assertions per case to specify behavior clearly.

- **API and flow tests:** Run with `pipenv run pytest tests/ -v`. Coverage is API and flow tests (no frontend unit tests).
- **E2E browser tests (Playwright):** Marketplace UI (load page, Marketplace tab, Refresh, Install). Run after `playwright install chromium`: `pipenv run pytest tests/e2e/ -m e2e -v`. E2E tests are skipped if Playwright or Chromium is not installed. See [docs/Testing.md](docs/Testing.md).
- **Frontend unit tests:** Not in scope; the web UI is a single HTML file with inline JS. Coverage for the UI is API tests plus E2E flow tests only.

Full testing documentation (catalog, how to run, coverage, per-module descriptions) is in the **project wiki** (Testing page).

`requirements.txt` is for the **rifai_scholar_downloader** subproject only; use Pipfile for the Talkie-core app.

## License

See repository.
