# Talkie SDK

The Talkie SDK is the single internal library used by the app and all modules. It provides config section access, speech abstractions, audio utilities, module discovery, and logging so shared logic lives in one place and modules follow a consistent contract.

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

## Audio utils

Shared audio helpers used by the pipeline and the speech module:

- **`sdk.chunk_rms_level(chunk: bytes | None) -> float`**  
  Returns RMS level of an int16 little-endian audio chunk normalized to 0.0--1.0. Returns 0.0 for None or empty/short chunk.

- **`sdk.INT16_MAX`**  
  Constant 32767 for int16 sample bounds.

- **`sdk.resample_int16(audio_bytes: bytes, rate_in: int, rate_out: int) -> bytes`**  
  Resample int16 mono PCM from rate_in to rate_out (e.g. 48k to 16k for web). Uses linear interpolation (numpy); returns bytes of int16 little-endian. Returns empty bytes if numpy is unavailable or rates invalid.

Example:

```python
from sdk import chunk_rms_level, INT16_MAX, resample_int16

level = chunk_rms_level(audio_chunk)
resampled = resample_int16(audio_bytes, 48000, 16000)
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

Module discovery finds subdirectories under a modules root that contain a config file and are not disabled by MODULE.yaml. The SDK loads MODULE.yaml itself (no app dependency).

- **`sdk.discover_modules(modules_root: Path) -> list[tuple[str, Path]]`**  
  Returns `(module_name, config_path)` sorted by manifest order then directory name. `modules_root` is required (e.g. `project_root / "modules"`).

- **`sdk.get_module_config_paths(modules_root: Path) -> list[Path]`**  
  Returns the ordered list of config file paths (used for config merge).

- **`sdk.get_enabled_from_config(config_path: Path) -> list[str]`**  
  Returns `modules.enabled` from a root config file (production mode when no `modules/` on disk). Returns `[]` if missing or invalid.

- **`sdk.get_modules_info(modules_root: Path) -> list[dict]`**  
  Returns full manifest-derived info per module: `id`, `name`, `version`, `description`, `order`, `config_path`, `module_dir`, `docs_path`, `help_entry`, `ui_id`. Used by API/UI for module list and help resolution.

- **`sdk.resolve_module_help_path(modules_root: Path, module_id: str) -> Path | None`**  
  Resolves `module_id` (directory name or `ui_id`) to the path of the help entry file (`docs_path/help_entry`). Returns `None` if not found.

Constants: **`MANIFEST_FILENAME`** (`"MODULE.yaml"`), **`DEFAULT_CONFIG_FILENAME`** (`"config.yaml"`), **`DEFAULT_VERSION`** (`"0.0.0"`), **`DEFAULT_DOCS_PATH`** (`"docs"`), **`DEFAULT_HELP_ENTRY`** (`"README.md"`).

Example:

```python
from pathlib import Path
from sdk import discover_modules, get_module_config_paths, get_modules_info, resolve_module_help_path

root = Path(__file__).resolve().parent / "modules"
paths = get_module_config_paths(root)
for name, path in discover_modules(root):
    ...
infos = get_modules_info(root)
help_path = resolve_module_help_path(root, "speech")
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

## Version

- **`sdk.__version__`** – SDK version string (e.g. `"0.1.0"`). Aligns with talkie-core when bundled.

## API summary

| API | Description |
|-----|-------------|
| `get_section(raw_config, section, defaults, validators=None)` | Normalize a config section with defaults and optional validators. |
| `get_rag_section(raw_config)` | Normalized RAG section (rag + ollama base_url). |
| `get_browser_section(raw_config)` | Normalized browser section. |
| `discover_modules(modules_root)` | List (name, config_path) for modules under path. |
| `get_module_config_paths(modules_root)` | Ordered config paths for merge. |
| `get_enabled_from_config(config_path)` | List of enabled module ids from config (production mode). |
| `get_modules_info(modules_root)` | List of module info dicts (id, name, version, description, docs_path, help_entry, ui_id, etc.). |
| `resolve_module_help_path(modules_root, module_id)` | Path to module help entry file, or None. |
| `get_logger(module_name)` | Logger named talkie.modules.<name>. |
| `MANIFEST_FILENAME`, `DEFAULT_CONFIG_FILENAME`, `DEFAULT_VERSION`, `DEFAULT_DOCS_PATH`, `DEFAULT_HELP_ENTRY` | Discovery constants. |
| `AudioCapture`, `STTEngine`, `TTSEngine`, `SpeakerFilter` | Speech interfaces. |
| `NoOpCapture`, `NoOpSTTEngine`, `NoOpTTSEngine`, `NoOpSpeakerFilter` | No-op implementations. |
| `MicrophoneError` | Exception for mic failures. |
| `chunk_rms_level(chunk)`, `INT16_MAX` | Audio level and constant. |
