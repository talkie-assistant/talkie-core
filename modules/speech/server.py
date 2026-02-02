"""
Speech module HTTP server.
Exposes audio capture, STT, TTS, and speaker filter via REST API.
"""

from __future__ import annotations

import argparse
import base64
from typing import Any

from fastapi import Request, status

from sdk import get_logger
from modules.api.server import BaseModuleServer
from modules.speech import SpeechFactory, SpeechComponents

logger = get_logger("speech")


class SpeechModuleServer(BaseModuleServer):
    """HTTP server for speech module."""

    def __init__(
        self,
        config: dict[str, Any],
        settings_repo: Any = None,
        host: str = "localhost",
        port: int = 8001,
        api_key: str | None = None,
    ) -> None:
        super().__init__(
            module_name="speech",
            module_version="1.0.0",
            host=host,
            port=port,
            api_key=api_key,
        )
        self._config = config
        self._settings_repo = settings_repo
        self._factory = SpeechFactory(config, settings_repo)
        self._components: SpeechComponents | None = None
        self._setup_endpoints()

    def _setup_endpoints(self) -> None:
        """Set up speech-specific endpoints."""

        @self._app.post("/capture/start")
        async def capture_start() -> dict[str, Any]:
            """Start audio capture."""
            try:
                if r := self._require_service(self._components):
                    return r
                self._components.capture.start()
                return {"success": True}
            except Exception as e:
                logger.exception("Capture start failed: %s", e)
                return self._error_response(
                    status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", str(e)
                )

        @self._app.post("/capture/stop")
        async def capture_stop() -> dict[str, Any]:
            """Stop audio capture."""
            try:
                if r := self._require_service(self._components):
                    return r
                self._components.capture.stop()
                return {"success": True}
            except Exception as e:
                logger.exception("Capture stop failed: %s", e)
                return self._error_response(
                    status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", str(e)
                )

        @self._app.post("/capture/read_chunk")
        async def capture_read_chunk(request: Request) -> dict[str, Any]:
            """Read audio chunk."""
            try:
                if r := self._require_service(self._components):
                    return r
                chunk = self._components.capture.read_chunk()
                if chunk is None:
                    return {"audio_base64": "", "level": 0.0}
                # Calculate level
                from sdk import chunk_rms_level

                level = chunk_rms_level(chunk)
                audio_base64 = base64.b64encode(chunk).decode("utf-8")
                return {"audio_base64": audio_base64, "level": level}
            except Exception as e:
                logger.exception("Capture read_chunk failed: %s", e)
                return self._error_response(
                    status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", str(e)
                )

        @self._app.get("/capture/sensitivity")
        async def capture_get_sensitivity() -> dict[str, Any]:
            """Get sensitivity."""
            try:
                if r := self._require_service(self._components):
                    return r
                sensitivity = self._components.capture.get_sensitivity()
                return {"sensitivity": sensitivity}
            except Exception as e:
                logger.exception("Get sensitivity failed: %s", e)
                return self._error_response(
                    status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", str(e)
                )

        @self._app.post("/capture/sensitivity")
        async def capture_set_sensitivity(request: Request) -> dict[str, Any]:
            """Set sensitivity."""
            try:
                if r := self._require_service(self._components):
                    return r
                data = await request.json()
                sensitivity = float(data.get("sensitivity", 1.0))
                self._components.capture.set_sensitivity(sensitivity)
                return {"success": True, "sensitivity": sensitivity}
            except Exception as e:
                logger.exception("Set sensitivity failed: %s", e)
                return self._error_response(
                    status.HTTP_400_BAD_REQUEST, "invalid_request", str(e)
                )

        @self._app.post("/stt/transcribe")
        async def stt_transcribe(request: Request) -> dict[str, Any]:
            """Transcribe audio. Returns text and optional confidence (0--1) when the engine supports it."""
            try:
                if r := self._require_service(self._components):
                    return r
                data = await request.json()
                audio_base64 = data.get("audio_base64", "")
                audio_bytes = base64.b64decode(audio_base64)
                stt = self._components.stt
                if hasattr(stt, "transcribe_with_confidence"):
                    text, confidence = stt.transcribe_with_confidence(audio_bytes)
                    out: dict[str, Any] = {"text": text}
                    if confidence is not None:
                        out["confidence"] = confidence
                    return out
                text = stt.transcribe(audio_bytes)
                return {"text": text}
            except Exception as e:
                logger.exception("STT transcribe failed: %s", e)
                return self._error_response(
                    status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", str(e)
                )

        @self._app.post("/stt/start")
        async def stt_start() -> dict[str, Any]:
            """Start STT engine."""
            try:
                if r := self._require_service(self._components):
                    return r
                self._components.stt.start()
                return {"success": True}
            except Exception as e:
                logger.exception("STT start failed: %s", e)
                return self._error_response(
                    status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", str(e)
                )

        @self._app.post("/stt/stop")
        async def stt_stop() -> dict[str, Any]:
            """Stop STT engine."""
            try:
                if r := self._require_service(self._components):
                    return r
                self._components.stt.stop()
                return {"success": True}
            except Exception as e:
                logger.exception("STT stop failed: %s", e)
                return self._error_response(
                    status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", str(e)
                )

        @self._app.post("/tts/speak")
        async def tts_speak(request: Request) -> dict[str, Any]:
            """Speak text."""
            try:
                if r := self._require_service(self._components):
                    return r
                data = await request.json()
                text = data.get("text", "")
                if text:
                    self._components.tts.speak(text)
                return {"success": True}
            except Exception as e:
                logger.exception("TTS speak failed: %s", e)
                return self._error_response(
                    status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", str(e)
                )

        @self._app.post("/tts/stop")
        async def tts_stop() -> dict[str, Any]:
            """Stop TTS."""
            try:
                if r := self._require_service(self._components):
                    return r
                self._components.tts.stop()
                return {"success": True}
            except Exception as e:
                logger.exception("TTS stop failed: %s", e)
                return self._error_response(
                    status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", str(e)
                )

        @self._app.post("/speaker_filter/accept")
        async def speaker_filter_accept(request: Request) -> dict[str, Any]:
            """Check if transcription should be accepted."""
            try:
                if r := self._require_service(self._components):
                    return r
                data = await request.json()
                transcription = data.get("transcription", "")
                audio_base64 = data.get("audio_base64")
                audio_bytes = None
                if audio_base64:
                    audio_bytes = base64.b64decode(audio_base64)
                accept = self._components.speaker_filter.accept(
                    transcription, audio_bytes
                )
                reason = None
                if not accept and hasattr(
                    self._components.speaker_filter, "get_last_reject_reason"
                ):
                    reason = self._components.speaker_filter.get_last_reject_reason()
                return {"accept": accept, "reason": reason}
            except Exception as e:
                logger.exception("Speaker filter accept failed: %s", e)
                return self._error_response(
                    status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", str(e)
                )

        @self._app.get("/calibration/steps")
        async def calibration_steps() -> dict[str, Any]:
            """Return ordered calibration steps (voice enrollment, sensitivity)."""
            try:
                from modules.speech.calibration import CALIBRATION_STEPS

                return {"steps": CALIBRATION_STEPS}
            except Exception as e:
                logger.debug("Calibration steps failed: %s", e)
                return {"steps": []}

        @self._app.post("/calibration/voice_enroll")
        async def calibration_voice_enroll(request: Request) -> dict[str, Any]:
            """Enroll user voice from base64 audio."""
            try:
                if self._settings_repo is None:
                    return self._error_response(
                        status.HTTP_503_SERVICE_UNAVAILABLE,
                        "settings_unavailable",
                        "Settings repository not configured",
                    )
                from modules.speech.calibration.voice_profile import enroll_user_voice

                data = await request.json()
                audio_base64 = data.get("audio_base64", "")
                sample_rate = int(data.get("sample_rate", 16000))
                if not audio_base64:
                    return self._error_response(
                        status.HTTP_400_BAD_REQUEST,
                        "invalid_request",
                        "audio_base64 required",
                    )
                audio_bytes = base64.b64decode(audio_base64)
                success, message = enroll_user_voice(
                    audio_bytes, sample_rate, self._settings_repo
                )
                if success:
                    return {"success": True, "message": message}
                return self._error_response(
                    status.HTTP_400_BAD_REQUEST, "invalid_request", message
                )
            except Exception as e:
                logger.exception("Voice enroll failed: %s", e)
                return self._error_response(
                    status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", str(e)
                )

        @self._app.post("/calibration/voice_clear")
        async def calibration_voice_clear() -> dict[str, Any]:
            """Clear enrolled voice profile."""
            try:
                if self._settings_repo is None:
                    return {"success": True}
                from modules.speech.calibration.voice_profile import clear_voice_profile

                clear_voice_profile(self._settings_repo)
                return {"success": True}
            except Exception as e:
                logger.exception("Voice clear failed: %s", e)
                return self._error_response(
                    status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", str(e)
                )

    async def startup(self) -> None:
        """Initialize speech components on startup. Speaker filter uses voice profile when configured."""
        await super().startup()
        try:
            self._components = self._factory.create_components()
            self._components.stt.start()
            self.set_ready(True)
            logger.info(
                "Speech module initialized and ready (speaker filter: only calibrated speaker when profile enrolled)"
            )
        except Exception as e:
            logger.exception("Failed to initialize speech module: %s", e)
            self.set_ready(False)

    async def shutdown(self) -> None:
        """Cleanup on shutdown."""
        try:
            if self._components is not None:
                self._components.capture.stop()
                self._components.stt.stop()
                self._components.tts.stop()
        except Exception as e:
            logger.warning("Error during speech module shutdown: %s", e)
        await super().shutdown()

    def get_config_dict(self) -> dict[str, Any]:
        """Get current configuration."""
        return self._config

    def update_config_dict(self, config: dict[str, Any]) -> None:
        """Update configuration (recreate components)."""
        self._config.update(config)
        # Recreate factory and components
        self._factory = SpeechFactory(self._config, self._settings_repo)
        if self._components is not None:
            # Stop old components
            try:
                self._components.capture.stop()
                self._components.stt.stop()
            except Exception:
                pass
        # Create new components
        self._components = self._factory.create_components()
        self._components.stt.start()


def main() -> None:
    """CLI entry point for speech module server."""
    parser = argparse.ArgumentParser(description="Speech module HTTP server")
    parser.add_argument("--host", default="localhost", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8001, help="Port to bind to")
    parser.add_argument("--api-key", help="Optional API key for authentication")
    parser.add_argument(
        "--config", help="Path to config file (default: load from standard location)"
    )
    args = parser.parse_args()

    # Load config
    from config import load_config

    config = load_config()

    # Load settings repo if available
    settings_repo = None
    try:
        from persistence.database import get_connection
        from persistence.settings_repo import SettingsRepo

        db_path = config.get("persistence", {}).get("db_path", "data/talkie-core.db")

        def conn_factory():
            return get_connection(str(db_path))

        settings_repo = SettingsRepo(conn_factory)
    except Exception as e:
        logger.warning("Settings repo not available: %s", e)

    # Create and run server
    server = SpeechModuleServer(
        config=config,
        settings_repo=settings_repo,
        host=args.host,
        port=args.port,
        api_key=args.api_key,
    )
    server.run()


if __name__ == "__main__":
    main()
