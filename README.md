# Talkie

A Python application for laptop or Raspberry Pi that helps people with speech impairments (e.g., Parkinson's) communicate more clearly. All processing runs locally.

## Features

- **Audio input**: Continuous microphone capture with configurable sensitivity (gain)
- **Speech recognition**: Local STT (Whisper or Vosk). Whisper default for best accuracy; Vosk for lighter/Pi use
- **Speaker filtering**: Pluggable filter (no-op by default; extensible to verification/diarization)
- **LLM**: Local model via Ollama (e.g. phi, mistral) for sentence completion and clarification from partial speech
- **Two-step flow (optional)**: Raw STT → regeneration (intent/homophone correction) → completion; configurable certainty threshold to skip second call
- **Response display**: Web-based UI with large, high-contrast text at http://localhost:8765
- **Volume display**: Waveform-style strip showing microphone input level
- **History**: SQLite storage of transcriptions, LLM responses, and corrections
- **Correction and personalization**: Edit past responses in the UI; language profile built from corrections, accepted responses, and optional user context (e.g. "PhD, professor at Brown")
- **Learning profile**: User context (Settings), corrections, and accepted completions tailor vocabulary and style; History "Use for learning" checkbox controls what is used for learning
- **Scheduled curation**: Optional in-app or cron: pattern recognition, weighting (higher for corrections and recurring patterns), optional prune; higher-weighted examples preferred in profile
- **Audio training**: Record short facts (e.g. "Star is my dog") via the Train (T) button; injected into LLM context
- **Export for fine-tuning**: Export curated interactions to JSONL (instruction/input/output) for Ollama, Unsloth, or other tools
- **RAG / documents**: Upload TXT/PDF, vectorize with Ollama embeddings, store in Chroma; "Ask documents" mode to query by voice
- **Voice-controlled web (optional)**: Browse mode: search, open URL, store current page for RAG—all by voice. Disable with `browser.enabled: false`
- **Voice calibration**: Record user speech, analyze level (and optional STT/LLM), suggest sensitivity and settings
- **TTS (optional)**: Text-to-speech for responses (e.g. macOS "say" with configurable voice)
- **Infrastructure (optional)**: Consul, KeyDB, HAProxy, service discovery, load balancing for module servers; managed via `./talkie`

## Requirements

- Python 3.11+
- Microphone
- [Ollama](https://ollama.ai/) running with an LLM (e.g. `ollama pull phi` or `ollama pull mistral`). Default in `config.yaml` is `phi`.
- STT: **Whisper** (default) or Vosk. Use Vosk on Raspberry Pi if Whisper is too slow.

## Setup

The main app uses **Pipfile** for dependencies. Install and run:

```bash
pipenv install
pipenv run python run_web.py
```

Note: `requirements.txt` is for the **rifai_scholar_downloader** subproject only; use Pipfile for the Talkie app.

Then open http://localhost:8765. Optional: set `TALKIE_CONFIG` to the path of a different `config.yaml`.

## Service Management

For managing infrastructure services (Consul, KeyDB, HAProxy, etc.):

```bash
# Start all services
./talkie start

# Start specific service groups
./talkie start infrastructure  # Consul, KeyDB, HAProxy, etc.
./talkie start core            # Ollama, Chroma
./talkie start modules         # Module servers

# Check status
./talkie status

# View logs
./talkie logs consul-server --follow

# Health check
./talkie health

# Stop services
./talkie stop

# Restart services
./talkie restart

# Clean up
./talkie clean containers
```

See `./talkie help` for all commands.

### macOS with Ollama

**Podman (recommended):** Run `./talkie app` or `./talkie start core`. Ollama runs in a Podman container (`talkie-ollama`); the script starts it, pulls the configured model if missing, and warms the model so the first request does not 500. Logs: `podman logs talkie-ollama`.

**Without Podman:** Run Ollama from the menu bar or start it with `ollama serve`. Ensure a model is available (e.g. `ollama pull phi` or `ollama pull mistral`). Default `config.yaml` uses `http://localhost:11434` and `model_name: "phi"`. Speech-to-text defaults to **Whisper** (`base` in config; use `small` or `medium` for better accuracy). On a Raspberry Pi or low-RAM machine, set `stt.engine: vosk` and use a Vosk model from [alphacephei.com/vosk/models](https://alphacephei.com/vosk/models). For best accuracy (especially with impaired speech), set `stt.whisper.model_path: "medium"` (needs ~5GB RAM).

## Configuration

Config is merged from module configs (`modules/speech/config.yaml`, etc.), root `config.yaml`, and optional `config.user.yaml` (user overrides, e.g. from Settings). Edit `config.yaml` (and optionally `config.user.yaml`) to set:

- **Audio**: `audio.device_id`, `audio.sample_rate`, `audio.chunk_duration_sec`, `audio.sensitivity` (gain; default 3.0)
- **STT**: `stt.engine` (`whisper` or `vosk`), `stt.whisper.model_path` (`base`, `small`, `medium`, `large-v3`); see "Speech-to-text accuracy" below
- **Ollama**: `ollama.base_url`, `ollama.model_name`, `ollama.timeout_sec`
- **LLM**: `llm.system_prompt`, `llm.user_prompt_template`, `llm.export_instruction`, `llm.min_transcription_length`, `llm.conversation_context_turns`; regeneration: `llm.regeneration_enabled`, `llm.use_regeneration_as_response`, `llm.regeneration_certainty_threshold`, `llm.regeneration_system_prompt`, etc.
- **TTS**: `tts.enabled`, `tts.engine`, `tts.voice`
- **Persistence**: `persistence.db_path`
- **Curation**: `curation.interval_hours` (0 = disabled), `curation.correction_weight_bump`, `curation.pattern_count_weight_scale`, `curation.delete_older_than_days`, `curation.max_interactions_to_curate`
- **Profile**: `profile.correction_limit`, `profile.accepted_limit`, `profile.user_context_max_chars` (or in `profile/constants.py`)
- **UI**: `ui.fullscreen`, `ui.high_contrast`, `ui.font_size`, `ui.response_font_size`; env `TALKIE_WEB_HOST`, `TALKIE_WEB_PORT` (default 8765)
- **RAG**: `rag.embedding_model`, `rag.vector_db_path`, `rag.chroma_host`, `rag.chroma_port` (if using Chroma in Podman)
- **Browser**: `browser.enabled`, `browser.chrome_app_name`, `browser.search_engine_url`, etc.
- **Logging**: `logging.level`, `logging.file`

## Speech-to-text accuracy

Talkie uses **faster-whisper** (Whisper) by default. Among free, local STT options, Whisper is one of the most accurate and is used in research for dysarthric and speech-impaired speech (e.g. Parkinson's). Vosk is lighter and faster but less accurate.

- **Default**: `stt.engine: whisper`, `stt.whisper.model_path: "base"` (config default) or `"small"` — balance of speed and accuracy.
- **Best accuracy** (especially for unclear or impaired speech): set `stt.whisper.model_path: "medium"` (~5GB RAM, slower). Optional: `audio.chunk_duration_sec: 5` or `6` for more context.
- **Lighter / Pi**: set `stt.engine: vosk` and use a [Vosk model](https://alphacephei.com/vosk/models); for better Vosk accuracy use a larger model (e.g. `vosk-model-en-us-0.22`).

Other free options (e.g. Sherpa-ONNX, cloud APIs) can match or exceed Whisper in some setups, but Whisper via faster-whisper is a strong choice for local, offline use and impaired speech.

## Troubleshooting: wrong or repeated phrase ("not hearing" / "says the same thing")

If the app keeps saying an unrelated phrase (e.g. "can you help me understand my bill") instead of what you said, the cause is usually:

1. **STT mishearing** – Background noise or quiet speech gets transcribed as a few words; the LLM then "completes" that into a common phrase. Check the debug log (if enabled) for "You said: …" to see what was actually transcribed.
2. **Config changes that help**  
   - Increase `audio.sensitivity` (e.g. 3.0–4.0) if your voice is quiet, or decrease it if the mic is picking up too much noise.  
   - Set `llm.min_transcription_length` (e.g. 4 or 5) so very short/noisy transcriptions are not sent to the LLM.  
   - The system prompt in `config.yaml` now tells the model to output "I didn't catch that." when the transcription is unclear and to never invent sentences.
3. **Microphone** – Confirm the correct mic in system settings; in `config.yaml` you can set `audio.device_id` to a specific device index if needed.

## Curation and fine-tuning

A **curator** runs pattern recognition on the interaction history, assigns a **weight** to each sentence/phrase (corrected and frequently used patterns get higher weight), and can exclude or delete entries. The language profile uses these weights so heavier examples are prioritized. Run it on a schedule (in-app or cron) or once via CLI.

- **In-app**: Set `curation.interval_hours` in `config.yaml` (e.g. `24`). A background thread runs the curator every N hours while the app is open.
- **CLI (once or cron)**:
  ```bash
  pipenv run python -m curation
  ```
- **Export for fine-tuning**: Write high-weight and corrected interactions to JSONL for external training:
  ```bash
  pipenv run python -m curation --export data/talkie_export.jsonl [--limit 5000]
  ```
  Each line is a JSON object with `instruction`, `input`, `output`. You can then use that file with Ollama (e.g. custom Modelfile/system prompt), Unsloth, or other fine-tuning tools to train or fine-tune a model on the user’s speech patterns.

## RAG / Documents

You can upload documents (TXT, PDF), vectorize them with Ollama embeddings, and query them by voice.

1. **Documents dialog** (Documents button): Add files, then click **Vectorize** to chunk, embed (Ollama), and store in Chroma at `data/rag_chroma` (config: `rag.vector_db_path`). The dialog shows indexed documents; you can **Remove from index** or **Clear all**.
2. **Ask documents (?)** button: Turn it on, then speak a question. The app retrieves relevant chunks and the LLM answers using only that context. Document Q&A responses are stored in History like regular answers.
3. **Embedding model**: Set `rag.embedding_model` in `config.yaml` (default `nomic-embed-text`). Run `ollama pull nomic-embed-text`. If the model is missing, the app tries fallbacks or shows a clear error.
4. **Vector DB in Podman** (optional): Run Chroma in a container with `podman compose up -d` (see `compose.yaml`). Set `rag.chroma_host` and optionally `rag.chroma_port` in `config.yaml`. If `chroma_host` is unset, the app uses an embedded Chroma store at `rag.vector_db_path`.

RAG retrieval runs only when "Ask documents" is on, so normal conversation has no extra latency. Training facts (Train dialog) remain in the system prompt as before.

## Tests

```bash
pipenv install --dev
pipenv run pytest tests/ -v
```

Code quality: `pipenv run ruff check .` and `pipenv run ruff format .`.

## Scholar PDF downloader (rifai_scholar_downloader)

Optional tool to download **openly available** PDFs for a Google Scholar author (default: Dr. Abdalla Rifai). Output goes under `downloads/` by default. Resumable and idempotent.

```bash
pip install -r requirements.txt
python -m rifai_scholar_downloader.cli
```

See `rifai_scholar_downloader/README.md` for setup, usage examples, and limitations (rate limits, paywalls, no CAPTCHA bypass).

## Project structure

Core (application root):

- `app/` – Pipeline orchestration, speech abstractions, audio level helper
- `config.py` – Config loading (merges module configs, root `config.yaml`, optional `config.user.yaml`)
- `llm/` – Ollama client and prompts
- `profile/` – Language profile (user context, corrections, accepted pairs) and constants
- `persistence/` – SQLite schema, history repo, settings repo; migrations in `database.py`
- `curation/` – Curator (pattern recognition, weighting, add/remove), scheduler, CLI, and JSONL export for fine-tuning
- `web/` – Web UI static assets (index.html); FastAPI + WebSocket in `run_web.py`
- `rifai_scholar_downloader/` – Resumable Google Scholar author PDF downloader (open-access only)

**Modules** (optional features under `modules/`):

- `modules/speech/` – Audio capture, STT (Vosk, Whisper), TTS (say), speaker filter, calibration; each has its own `config.yaml` merged into the main config
- `modules/rag/` – Document ingestion (chunk, embed via Ollama, Chroma store), retrieval; plugin entry point `register_with_pipeline()`
- `modules/browser/` – Voice-controlled web (search, open URL, store page for RAG); plugin entry point `create_web_handler()`

The app composes these at startup: if a module is missing or fails to load, the rest of the app still runs (e.g. without RAG or browser). Core depends only on abstractions and plugin APIs so modules can be maintained or removed independently.

## Modular design

Talkie is split into **core** and **modules** so the codebase stays maintainable and contributors can work on one area (speech, RAG, web) without touching the rest.

- **Core** defines interfaces (e.g. in `app/abstractions.py`) and wires optional plugins in `run_web.py`. Pipeline accepts injected speech components and optional RAG/web handlers.
- **Modules** live under `modules/`: `speech`, `rag`, `browser`. Each module can provide a default `config.yaml` in its directory; the main `config.yaml` (and optional `config.user.yaml`) are merged on top. To disable a module, omit or remove its directory, or set the relevant config (e.g. `browser.enabled: false`).
- **Configuration**: Root `config.yaml` plus optional `config.user.yaml` (written by the Settings UI). Module defaults are in `modules/<name>/config.yaml`. Load order: module configs merged first, then root config, then user overrides. Some settings take effect after restart.
- **Debugging**: Errors and warnings appear in the web UI debug area and in `talkie.log` with `[ERROR]` / `[WARN]` prefixes. Safe to leave debug on for troubleshooting.

## To-do

- **Module registration**: Single `register(context)` entry point per module so new modules can plug in without editing `run.py` (see MODULES.md).
- **Auto sensitivity**: Implement automatic sensitivity adjustment when STT returns empty but audio level indicates possible speech; config has `audio.auto_sensitivity` (manual only for now).
- **Code quality**: Continue consolidation of duplicate logic in module servers and API clients; remove unused code and config; see `.cursor/prompts/1-implement-code-cleanup.md` for audit scope.

## License

See repository.
