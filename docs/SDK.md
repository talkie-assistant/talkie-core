# Talkie SDK

The Talkie SDK is the single internal library used by the app and all modules. It provides config section access, speech abstractions, module discovery, and logging so shared logic lives in one place and modules follow a consistent contract.

## Where the SDK sits

- **App** (`run.py`, `config.py`, `app/pipeline.py`) uses the SDK for config normalization and discovery; pipeline uses SDK abstractions for capture/STT/TTS/speaker.
- **Modules** (`modules/speech`, `modules/rag`, `modules/browser`) use the SDK for config (by section), and the speech module implements SDK abstractions.
- The SDK **does not** import `app`, `modules.*`, `llm`, `persistence`, or `ui`, so modules can depend on it without pulling in the full app.

## Config

Config is merged elsewhere (see [MODULES.md](../MODULES.md)): module configs, then root `config.yaml`, then `config.user.yaml`. The SDK does not load files; it normalizes a section from an already-merged raw dict.

### Getting a normalized section

- **`sdk.get_section(raw_config, section, defaults, validators=None)`**  
  Generic helper: merges `raw_config[section]` with `defaults`, then applies optional `validators` (dict of key -> callable) for clamping/parsing. Returns a new dict.

- **`sdk.get_rag_section(raw_config)`**  
  Returns normalized RAG config (embedding_model, base_url, vector_db_path, chroma_host/port, top_k, chunk_size, etc.). Reads from `raw_config["rag"]` and `raw_config["ollama"]` for base_url.

- **`sdk.get_browser_section(raw_config)`**  
  Returns normalized browser config (enabled, chrome_app_name, fetch_timeout_sec, search_engine_url, cooldown_sec, etc.).

Example:

```python
from sdk import get_rag_section, get_browser_section

raw = load_config()  # or app config dict
rag_cfg = get_rag_section(raw)
browser_cfg = get_browser_section(raw)
```

## Abstractions

Speech-related interfaces and no-op implementations live in `sdk.abstractions` (re-exported from `sdk`):

- **`MicrophoneError`** – Exception when the microphone is unavailable.
- **`AudioCapture`** – Abstract: `start()`, `stop()`, `read_chunk(on_level=None)`.
- **`STTEngine`** – Abstract: `transcribe(audio_bytes) -> str`, `start()`, `stop()`.
- **`TTSEngine`** – Abstract: `speak(text)`, `wait_until_done()`, `stop()`.
- **`SpeakerFilter`** – Abstract: `accept(transcription, audio_bytes=None) -> bool`.

No-ops (for when a module is disabled): **`NoOpCapture`**, **`NoOpSTTEngine`**, **`NoOpTTSEngine`**, **`NoOpSpeakerFilter`**.

Example:

```python
from sdk import AudioCapture, STTEngine, TTSEngine, SpeakerFilter
# or from sdk.abstractions import ...
```

## Discovery

Module discovery finds subdirectories under a modules root that contain a config file and are not disabled by MODULE.yaml.

- **`sdk.discover_modules(modules_root: Path) -> list[tuple[str, Path]]`**  
  Returns `(module_name, config_path)` sorted by manifest order then directory name. `modules_root` is required (e.g. `project_root / "modules"`).

- **`sdk.get_module_config_paths(modules_root: Path) -> list[Path]`**  
  Returns the ordered list of config file paths (used for config merge).

Constants: **`MANIFEST_FILENAME`** (`"MODULE.yaml"`), **`DEFAULT_CONFIG_FILENAME`** (`"config.yaml"`).

Example:

```python
from pathlib import Path
from sdk import get_module_config_paths, discover_modules

root = Path(__file__).resolve().parent / "modules"
paths = get_module_config_paths(root)
for name, path in discover_modules(root):
    ...
```

## Logging

- **`sdk.get_logger(module_name: str) -> logging.Logger`**  
  Returns a logger with name `talkie.modules.<module_name>` for consistent log attribution.

Example:

```python
from sdk import get_logger
logger = get_logger("rag")
logger.info("RAG ready")
```

## Writing a module

1. **Config** – Do not duplicate section normalization. Use `sdk.get_rag_section(raw)` or `sdk.get_browser_section(raw)` (or a future section helper). If your module has its own section, use `sdk.get_section(raw, "mysection", defaults, validators)`.

2. **Speech** – If your module provides capture, STT, TTS, or speaker filter, implement the SDK abstractions (`sdk.AudioCapture`, etc.) so the pipeline can use them.

3. **Discovery** – Use only if your module needs to enumerate other modules or config paths; otherwise the app uses discovery for config loading.

4. **Runtime wiring** – The host discovers modules under `modules/` and calls `register(context)` on each module that provides it (two-phase: first to collect pipeline inputs like speech components, then to attach to the pipeline). See [MODULES.md](../MODULES.md) for context keys and phases. New runtime plugins only need to implement `register(context)`; no edits to `run_web.py` or `run.py` are required.

5. **Logging** – Prefer `sdk.get_logger("your_module")` for consistent names.

## API summary

| API | Description |
|-----|-------------|
| `get_section(raw_config, section, defaults, validators=None)` | Normalize a config section with defaults and optional validators. |
| `get_rag_section(raw_config)` | Normalized RAG section (rag + ollama base_url). |
| `get_browser_section(raw_config)` | Normalized browser section. |
| `discover_modules(modules_root)` | List (name, config_path) for modules under path. |
| `get_module_config_paths(modules_root)` | Ordered config paths for merge. |
| `get_logger(module_name)` | Logger named talkie.modules.<name>. |
| `AudioCapture`, `STTEngine`, `TTSEngine`, `SpeakerFilter` | Speech interfaces. |
| `NoOpCapture`, `NoOpSTTEngine`, `NoOpTTSEngine`, `NoOpSpeakerFilter` | No-op implementations. |
| `MicrophoneError` | Exception for mic failures. |
