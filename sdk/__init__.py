"""
Talkie SDK: shared library for the app and all modules.

Provides a single public surface for config section access, speech abstractions,
module discovery, audio utilities, and logging. Import from this package only;
do not depend on app or modules from within the SDK.

Example:
    from sdk import get_rag_section, get_browser_section
    cfg = get_rag_section(raw_config)

    from sdk import AudioCapture, STTEngine
    from sdk import discover_modules, get_module_config_paths, get_modules_info, resolve_module_help_path
    from sdk import chunk_rms_level, INT16_MAX, resample_int16
    from sdk import get_logger
"""

from __future__ import annotations

from sdk.abstractions import (
    AudioCapture,
    MicrophoneError,
    NoOpCapture,
    NoOpSpeakerFilter,
    NoOpSTTEngine,
    NoOpTTSEngine,
    SpeakerFilter,
    STTEngine,
    TTSEngine,
)
from sdk.audio_utils import INT16_MAX, chunk_rms_level, resample_int16
from sdk.config import get_browser_section, get_rag_section, get_section
from sdk.discovery import (
    DEFAULT_CONFIG_FILENAME,
    DEFAULT_DOCS_PATH,
    DEFAULT_HELP_ENTRY,
    DEFAULT_VERSION,
    MANIFEST_FILENAME,
    discover_modules,
    get_enabled_from_config,
    get_module_config_paths,
    get_modules_info,
    resolve_module_help_path,
)
from sdk.logging import get_logger

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_CONFIG_FILENAME",
    "DEFAULT_DOCS_PATH",
    "DEFAULT_HELP_ENTRY",
    "DEFAULT_VERSION",
    "INT16_MAX",
    "MANIFEST_FILENAME",
    "AudioCapture",
    "MicrophoneError",
    "NoOpCapture",
    "NoOpSpeakerFilter",
    "NoOpSTTEngine",
    "NoOpTTSEngine",
    "SpeakerFilter",
    "STTEngine",
    "TTSEngine",
    "chunk_rms_level",
    "resample_int16",
    "discover_modules",
    "get_browser_section",
    "get_enabled_from_config",
    "get_logger",
    "get_module_config_paths",
    "get_modules_info",
    "get_rag_section",
    "get_section",
    "resolve_module_help_path",
]
