# Talkie-core

Local, voice-first app for people with reduced speech clarity: you speak; it transcribes, clarifies with a local LLM, and shows (or speaks) the result. All processing stays on your machine.

**Full documentation** (features, configuration, architecture, modules, SDK, troubleshooting) is in the **[project wiki](https://github.com/talkie-assistant/talkie-core/wiki)**.

---

## Architecture (summary)

- **Core:** Python 3.11+, Pipenv. Web UI: FastAPI + WebSocket + static HTML at http://localhost:8765. Entry: `run_web.py`; do not run it directly—use the **Talkie CLI** (`./talkie`).
- **Pipeline:** Microphone → STT (Whisper or Vosk) → optional regeneration → LLM (Ollama) → response. Profile built from user context, corrections, accepted responses, and training facts. Optional TTS (browser speaks in web UI).
- **Persistence:** SQLite (history, settings, training). Optional curation and JSONL export.
- **Modules:** Speech, RAG, browser live under `modules/`; discovered and registered in two phases via `register(context)`. Can run in-process or as HTTP servers.
- **Infrastructure (optional):** Podman Compose for Consul, KeyDB, HAProxy, Chroma, module servers, VictoriaMetrics, Grafana. Managed by `./talkie`.

See the wiki [Architecture](https://github.com/talkie-assistant/talkie-core/wiki/Architecture) and [Development](https://github.com/talkie-assistant/talkie-core/wiki/Development) for details.

---

## Get started (dev environment)

1. **Requirements:** Python 3.11+, microphone, [Ollama](https://ollama.ai/) with a model (e.g. `ollama pull phi`).
2. **Clone:** `git clone --recurse-submodules https://github.com/talkie-assistant/talkie-core.git` (or `git submodule update --init --recursive` after clone).
3. **Install:** `pipenv install` (and `pipenv install --dev` for tests).
4. **Run:** Use the CLI only—do not run Python directly.
   - Web UI only: `./talkie start web` → open http://localhost:8765
   - Full stack (containers + Web UI): `./talkie start all`
5. **Config:** Optional `TALKIE_CONFIG=/path/to/config.yaml`. See wiki [Configuration](https://github.com/talkie-assistant/talkie-core/wiki/Configuration).

Other commands: `./talkie status`, `./talkie logs <service> --follow`, `./talkie stop`, `./talkie help`.

---

## Tests and code quality

```bash
pipenv install --dev
pipenv run pytest tests/ -v
pipenv run pytest tests/ --cov --cov-report=term-missing
pipenv run ruff check .
pipenv run ruff format .
```

E2E (Playwright): `pipenv run playwright install chromium` then `pipenv run pytest tests/e2e/ -m e2e -v`. See wiki [Testing](https://github.com/talkie-assistant/talkie-core/wiki/Testing).

---

## Production and install

- **Image-only install:** `curl -sSL https://raw.githubusercontent.com/talkie-assistant/talkie-core/main/install.sh | sh` → `~/.talkie/talkie pull` and `~/.talkie/talkie start`.
- **Developer install (from source):** Same script with `--developer-mode`; then run from clone with `./talkie start` or `./talkie app`.

See wiki for [Troubleshooting](https://github.com/talkie-assistant/talkie-core/wiki/Troubleshooting), [Security](https://github.com/talkie-assistant/talkie-core/wiki/Security), and [Changelog](https://github.com/talkie-assistant/talkie-core/wiki/Changelog).

---

## License

See repository.
