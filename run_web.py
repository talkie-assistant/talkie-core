#!/usr/bin/env python3
"""
Talkie web UI entry point: FastAPI server, WebSocket for audio + events, static HTML.
Run: pipenv run python run_web.py
Open: http://localhost:8765
"""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
import os
import sys
from pathlib import Path

# Ensure project root is on path
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config import AppConfig, get_modules_enabled  # noqa: E402
from run import bootstrap_config_and_db  # noqa: E402
from starlette.requests import Request  # noqa: E402 module-level so FastAPI can resolve request: Request in route handlers

logger = logging.getLogger(__name__)

# Default host/port for web UI
WEB_HOST = os.environ.get("TALKIE_WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.environ.get("TALKIE_WEB_PORT", "8765"))


def _create_pipeline_and_app(
    config: AppConfig, db_path: Path, web_capture, connections_ref
):
    """Build pipeline with web capture and UI callbacks that broadcast to WebSocket connections."""
    from persistence.database import get_connection
    from persistence.history_repo import HistoryRepo
    from persistence.settings_repo import SettingsRepo
    from persistence.training_repo import TrainingRepo
    from app.pipeline import create_pipeline

    def conn_factory():
        return get_connection(str(db_path))

    history_repo = HistoryRepo(conn_factory)
    settings_repo = SettingsRepo(
        conn_factory,
        user_context_max_chars=config.get_user_context_max_chars(),
    )
    training_repo = TrainingRepo(conn_factory)

    def broadcast(msg: dict) -> None:
        """Send JSON to all connected clients (call from pipeline thread)."""
        conns = connections_ref.get("connections") or set()
        loop = connections_ref.get("loop")
        if not conns or loop is None:
            return
        payload = json.dumps(msg)

        async def send_all():
            for ws in list(conns):
                try:
                    await ws.send_text(payload)
                except Exception:
                    pass

        try:
            asyncio.run_coroutine_threadsafe(send_all(), loop)
        except Exception as e:
            logger.debug("Broadcast failed: %s", e)

    context = {
        "config": config,
        "settings_repo": settings_repo,
        "history_repo": history_repo,
        "training_repo": training_repo,
        "conn_factory": conn_factory,
        "broadcast": broadcast,
        "web_capture": web_capture,
    }
    modules_root = _ROOT / "modules"
    try:
        from modules.discovery import discover_modules

        discovered = discover_modules(modules_root)
    except Exception:
        discovered = []

    for _name, config_path in discovered:
        module_dir = config_path.parent.name
        try:
            mod = importlib.import_module(f"modules.{module_dir}")
            if hasattr(mod, "register"):
                mod.register(context)
        except Exception as e:
            logger.debug("Module %s register (phase 1) skipped: %s", module_dir, e)

    speech_comps = context.get("speech_components")
    from modules.speech.tts.noop_engine import NoOpTTSEngine

    pipeline = create_pipeline(
        config,
        history_repo,
        settings_repo,
        training_repo,
        capture=web_capture,
        stt=speech_comps.stt if speech_comps else None,
        tts=NoOpTTSEngine(),
        speaker_filter=speech_comps.speaker_filter if speech_comps else None,
        auto_sensitivity=speech_comps.auto_sensitivity if speech_comps else None,
    )
    context["pipeline"] = pipeline

    for _name, config_path in discovered:
        module_dir = config_path.parent.name
        try:
            mod = importlib.import_module(f"modules.{module_dir}")
            if hasattr(mod, "register"):
                mod.register(context)
        except Exception as e:
            logger.debug("Module %s register (phase 2) skipped: %s", module_dir, e)

    rag_service = context.get("rag_service")

    pipeline.set_ui_callbacks(
        on_status=lambda s: broadcast(
            {"type": "status", "value": s, "web_mode": pipeline.get_web_mode()}
        ),
        on_response=lambda text, iid: broadcast(
            {"type": "response", "text": text, "interaction_id": iid}
        ),
        on_error=lambda m: broadcast({"type": "error", "message": m}),
        on_debug=lambda m: broadcast({"type": "debug", "message": m}),
        on_volume=lambda v: broadcast({"type": "volume", "value": v}),
        on_sensitivity_adjusted=lambda v: broadcast(
            {"type": "sensitivity", "value": v}
        ),
    )
    # So browse (search) opens the table URL in the user's browser; never the raw search page.
    pipeline.set_on_open_url(lambda url: broadcast({"type": "open_url", "url": url}))

    def _quit_confirmed() -> None:
        broadcast({"type": "quit"})
        sys.exit(0)

    pipeline.set_on_quit_confirmed(_quit_confirmed)
    pipeline.set_on_close_quit_modal(lambda: broadcast({"type": "close_quit_modal"}))

    def _on_training_transcription(text: str) -> None:
        try:
            training_repo.add(text)
            broadcast({"type": "training_fact_added"})
        except Exception as e:
            logger.exception("Training add failed: %s", e)

    return {
        "pipeline": pipeline,
        "history_repo": history_repo,
        "settings_repo": settings_repo,
        "training_repo": training_repo,
        "rag_service": rag_service,
        "on_training_transcription": _on_training_transcription,
        "conn_factory": conn_factory,
        "broadcast": broadcast,
        "quit_callback": _quit_confirmed,
    }


def main() -> None:
    config, db_path = bootstrap_config_and_db(_ROOT)

    curation_cfg = config.get_curation_config()
    interval_hours = float(curation_cfg.get("interval_hours", 0))
    if interval_hours > 0:
        from curation.scheduler import start_background_scheduler

        start_background_scheduler(str(db_path), curation_cfg, interval_hours)

    audio_cfg = config.get("audio") or {}
    sample_rate = int(audio_cfg.get("sample_rate", 16000))
    chunk_sec = float(audio_cfg.get("chunk_duration_sec", 5.0))
    chunk_size = int(chunk_sec * sample_rate * 2)  # int16 = 2 bytes per sample
    sens = float(audio_cfg.get("sensitivity", 1.0))

    from app.web_capture import WebSocketAudioCapture

    web_capture = WebSocketAudioCapture(
        chunk_size_bytes=chunk_size, sample_rate=sample_rate
    )
    web_capture.set_sensitivity(sens)

    connections_ref = {"connections": set(), "loop": None}
    app = create_app(config, db_path, web_capture, connections_ref)
    import uvicorn

    logger.info("Talkie web UI: http://%s:%s", WEB_HOST, WEB_PORT)
    uvicorn.run(app, host=WEB_HOST, port=WEB_PORT)


def create_app(
    config: AppConfig,
    db_path: Path,
    web_capture,
    connections_ref: dict,
    root: Path | None = None,
):
    """Build the FastAPI app (for running or testing). root defaults to project root."""
    app_root = root or _ROOT
    web_dir = app_root / "web"

    deps = _create_pipeline_and_app(config, db_path, web_capture, connections_ref)
    pipeline = deps["pipeline"]
    history_repo = deps["history_repo"]
    # Production mode: no modules/ on disk; config.modules.enabled is source of truth for /api/modules
    try:
        from modules.discovery import get_modules_info
        _discovered_infos = get_modules_info(app_root / "modules")
    except Exception:
        _discovered_infos = []
    _production_mode = (
        os.environ.get("TALKIE_PRODUCTION") == "1"
        or (len(_discovered_infos) == 0 and bool(get_modules_enabled(config._raw)))
    )
    settings_repo = deps["settings_repo"]
    training_repo = deps["training_repo"]
    rag_service = deps["rag_service"]
    on_training_transcription = deps["on_training_transcription"]
    conn_factory = deps.get("conn_factory")

    from fastapi import (
        FastAPI,
        File,
        UploadFile,
        WebSocket,
        WebSocketDisconnect,
    )
    from fastapi.exceptions import RequestValidationError
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, JSONResponse
    import tempfile

    app = FastAPI(title="Talkie Web")

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request: Request, exc: RequestValidationError
    ):
        """Convert 422 validation errors to 400 with a single error message for the client."""
        errors = getattr(exc, "errors", lambda: [])()
        msg = "; ".join(e.get("msg", str(e)) for e in errors) if errors else str(exc)
        logger.debug("Request validation failed: %s (details: %s)", msg, errors)
        return JSONResponse(
            status_code=400,
            content={"error": f"Request validation: {msg}"},
        )

    # Ref set after websocket_endpoint is defined; middleware uses it to handle /ws (avoids router 403).
    _ws_handler_ref = [None]

    class WebSocketHandleMiddleware:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope.get("type") == "websocket" and scope.get("path") in (
                "/ws",
                "/ws/",
            ):
                handler = _ws_handler_ref[0]
                if handler:
                    from starlette.websockets import WebSocket

                    ws = WebSocket(scope, receive=receive, send=send)
                    await handler(ws)
                else:
                    await self.app(scope, receive, send)
            else:
                if scope.get("type") == "websocket" and scope.get("path") == "/ws/":
                    scope = dict(scope)
                    scope["path"] = "/ws"
                await self.app(scope, receive, send)

    # Log request type and path for debugging (e.g. WebSocket 403)
    class RequestLogMiddleware:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope.get("type") in ("http", "websocket"):
                logger.info(
                    "Request type=%s path=%r", scope.get("type"), scope.get("path")
                )
            await self.app(scope, receive, send)

    app.add_middleware(WebSocketHandleMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLogMiddleware)

    @app.get("/")
    async def index():
        index_file = web_dir / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return {"message": "Talkie web UI", "static": "Put web/index.html in place"}

    @app.get("/audio-worklet.js", include_in_schema=False)
    async def audio_worklet():
        worklet_file = web_dir / "audio-worklet.js"
        if worklet_file.exists():
            from starlette.responses import Response

            return Response(
                content=worklet_file.read_text(),
                media_type="application/javascript",
            )
        from starlette.responses import PlainTextResponse

        return PlainTextResponse("/* worklet not found */", status_code=404)

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        from fastapi.responses import Response

        return Response(status_code=204)

    @app.get("/browse-results", include_in_schema=False)
    async def browse_results(request: Request):
        """Serve table HTML from browser module (run_id or legacy data=)."""
        from modules.browser.browse_results_http import handle_browse_results

        return handle_browse_results(request, conn_factory)

    # --- REST API ---
    profile_cfg = config.get_profile_config()
    history_list_limit = int(profile_cfg.get("history_list_limit", 100))

    @app.post("/api/quit")
    async def api_quit():
        """Quit Talkie (called when user confirms quit in the modal)."""
        deps["quit_callback"]()

    @app.post("/api/quit-cancel")
    async def api_quit_cancel():
        """Cancel quit modal (called when user clicks No)."""
        pipeline.set_quit_modal_pending(False)
        deps["broadcast"]({"type": "close_quit_modal"})
        return {"ok": True}

    @app.get("/api/history")
    async def api_history_list():
        records = history_repo.list_recent(limit=history_list_limit)
        return {
            "items": [
                {
                    "id": r["id"],
                    "created_at": r["created_at"],
                    "original_transcription": r["original_transcription"],
                    "llm_response": r["llm_response"],
                    "corrected_response": r.get("corrected_response"),
                    "exclude_from_profile": bool(r.get("exclude_from_profile", 0)),
                }
                for r in records
            ]
        }

    @app.patch("/api/history/{interaction_id:int}")
    async def api_history_patch(interaction_id: int, request: Request):
        body = await request.json()
        if "corrected_response" in body:
            history_repo.update_correction(
                interaction_id, str(body["corrected_response"])
            )
        if "exclude_from_profile" in body:
            history_repo.update_exclude_from_profile(
                interaction_id, bool(body["exclude_from_profile"])
            )
        # Invalidate profile cache so the next LLM request uses updated training data.
        deps["pipeline"].invalidate_profile_cache()
        return {"ok": True}

    @app.get("/api/settings")
    async def api_settings_get():
        keys = [
            "user_context",
            "tts_voice",
            "tts_voice_filter",
            "calibration_sensitivity",
            "calibration_chunk_duration_sec",
            "calibration_min_transcription_length",
            "voice_profile_threshold",
            "preferred_name",
            "pronouns",
            "response_style",
            "response_length",
            "topic_hints",
            "tts_rate",
        ]
        out = settings_repo.get_many(keys)
        try:
            from modules.speech.calibration.voice_profile import (
                is_voice_profile_available,
            )

            out["voice_profile_enrolled"] = (
                "true" if is_voice_profile_available(settings_repo) else "false"
            )
        except Exception:
            out["voice_profile_enrolled"] = "false"
        return out

    @app.put("/api/settings")
    async def api_settings_put(request: Request):
        body = await request.json()
        allowed = (
            "user_context",
            "tts_voice",
            "tts_voice_filter",
            "calibration_sensitivity",
            "calibration_chunk_duration_sec",
            "calibration_min_transcription_length",
            "voice_profile_threshold",
            "preferred_name",
            "pronouns",
            "response_style",
            "response_length",
            "topic_hints",
            "tts_rate",
        )
        for k, v in body.items():
            if k in allowed and v is not None:
                settings_repo.set(k, str(v))
        deps["pipeline"].invalidate_profile_cache()
        return {"ok": True}

    @app.get("/api/calibration/steps")
    async def api_calibration_steps():
        """Return ordered calibration steps (voice enrollment, then sensitivity/pause)."""
        try:
            from modules.speech.calibration import CALIBRATION_STEPS

            return {"steps": CALIBRATION_STEPS}
        except Exception as e:
            logger.debug("Calibration steps failed: %s", e)
            return {"steps": []}

    @app.post("/api/calibration/voice_enroll")
    async def api_calibration_voice_enroll(request: Request):
        """Enroll user voice from base64 audio. Uses raw body to avoid validation and support large payloads."""
        try:
            import json as json_mod

            try:
                raw = await request.body()
                body = json_mod.loads(raw) if raw else None
            except Exception as e:
                logger.warning("Voice enroll body parse failed: %s", e)
                return JSONResponse(
                    status_code=400,
                    content={"error": f"Invalid JSON body: {e}"},
                )
            if not body or not isinstance(body, dict):
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "Request body must be a JSON object with audio_base64 and sample_rate"
                    },
                )
            try:
                from modules.speech.calibration.voice_profile import enroll_user_voice
                import base64 as b64
            except ImportError as e:
                return JSONResponse(status_code=503, content={"error": str(e)})
            audio_base64 = (
                (body.get("audio_base64") or "").strip()
                if isinstance(body.get("audio_base64"), str)
                else ""
            )
            try:
                sample_rate = max(8000, min(48000, int(body.get("sample_rate", 16000))))
            except (TypeError, ValueError):
                sample_rate = 16000
            if not audio_base64:
                return JSONResponse(
                    status_code=400, content={"error": "audio_base64 required"}
                )
            try:
                audio_bytes = b64.b64decode(audio_base64)
            except Exception as e:
                return JSONResponse(
                    status_code=400, content={"error": f"Invalid audio_base64: {e}"}
                )
            success, message = enroll_user_voice(
                audio_bytes, sample_rate, settings_repo
            )
            if success:
                return {"ok": True, "message": message}
            return JSONResponse(status_code=400, content={"error": message})
        except Exception as e:
            logger.exception("Voice enrollment failed: %s", e)
            logger.info("Voice enrollment 500: %s", e)
            return JSONResponse(status_code=500, content={"error": str(e)})

    @app.post("/api/calibration/voice_clear")
    async def api_calibration_voice_clear():
        """Clear enrolled voice profile so the app accepts all speakers again."""
        try:
            from modules.speech.calibration.voice_profile import clear_voice_profile

            clear_voice_profile(settings_repo)
            return {"ok": True}
        except Exception as e:
            logger.exception("Voice clear failed: %s", e)
            return JSONResponse(status_code=500, content={"error": str(e)})

    @app.get("/api/settings/voices")
    async def api_settings_voices():
        try:
            from modules.speech.tts.say_engine import get_available_voices_with_gender

            voices = get_available_voices_with_gender()
            if not voices:
                return {
                    "voices": [
                        {"name": "Daniel", "gender": "male"},
                        {"name": "Alex", "gender": "male"},
                        {"name": "Fred", "gender": "male"},
                        {"name": "Samantha", "gender": "female"},
                        {"name": "Karen", "gender": "female"},
                        {"name": "Victoria", "gender": "female"},
                    ]
                }
            return {"voices": voices}
        except Exception:
            return {
                "voices": [
                    {"name": "Daniel", "gender": "male"},
                    {"name": "Alex", "gender": "male"},
                    {"name": "Fred", "gender": "male"},
                    {"name": "Samantha", "gender": "female"},
                    {"name": "Karen", "gender": "female"},
                    {"name": "Victoria", "gender": "female"},
                ]
            }

    @app.get("/api/training")
    async def api_training_list():
        rows = training_repo.list_all()
        return {"items": [{"id": r[0], "text": r[1], "created_at": r[2]} for r in rows]}

    @app.post("/api/training")
    async def api_training_add(request: Request):
        body = await request.json()
        text = (body.get("text") or "").strip()
        if not text:
            return JSONResponse(status_code=400, content={"error": "text required"})
        training_repo.add(text)
        return {"ok": True}

    @app.delete("/api/training/{fact_id:int}")
    async def api_training_delete(fact_id: int):
        training_repo.delete(fact_id)
        return {"ok": True}

    @app.get("/api/modules")
    async def api_modules_list():
        """List discovered modules with name, version, description, ui_id for UI."""
        try:
            from modules.discovery import get_modules_info

            infos = get_modules_info(app_root / "modules")
            return {
                "modules": [
                    {
                        "id": m["id"],
                        "name": m["name"],
                        "version": m["version"],
                        "description": m["description"],
                        "ui_id": m.get("ui_id"),
                    }
                    for m in infos
                ]
            }
        except Exception as e:
            logger.debug("Modules list failed: %s", e)
            return {"modules": []}

    @app.get("/api/modules/{module_id}/help")
    async def api_module_help(module_id: str):
        """Return help content for a module (id = dir name or ui_id). Renders markdown to HTML."""
        try:
            from modules.discovery import resolve_module_help_path

            help_path = resolve_module_help_path(module_id, app_root / "modules")
            if help_path is None or not help_path.is_file():
                return JSONResponse(
                    status_code=404, content={"error": "Module or help entry not found"}
                )
            raw = help_path.read_text(encoding="utf-8", errors="replace")
            try:
                import markdown

                html = markdown.markdown(
                    raw,
                    extensions=["tables", "fenced_code", "nl2br"],
                )
            except Exception:
                import html as html_module

                html = "<pre>" + html_module.escape(raw) + "</pre>"
            return {"content": html, "format": "html"}
        except Exception as e:
            logger.debug("Module help failed: %s", e)
            return JSONResponse(status_code=500, content={"error": str(e)})

    # Marketplace: list org module repos and install as submodules
    _marketplace_org = os.environ.get("TALKIE_MARKETPLACE_ORG", "talkie-assistant")
    _install_attempts: list[
        tuple[float, str]
    ] = []  # (monotonic_time, client_host) for rate limit

    @app.get("/api/marketplace/git-available")
    async def api_marketplace_git_available():
        """Return whether the app root is a git repo (install only works in a clone)."""
        try:
            from marketplace import git_available

            return {"git_available": git_available(app_root)}
        except Exception as e:
            logger.debug("git_available check failed: %s", e)
            return {"git_available": False}

    @app.get("/api/marketplace/modules")
    async def api_marketplace_modules():
        """List modules from org (talkie-module-*) merged with installed; cached briefly."""
        try:
            from marketplace import list_marketplace_modules

            modules = list_marketplace_modules(app_root, _marketplace_org)
            return {"modules": modules}
        except Exception as e:
            logger.warning("Marketplace list failed: %s", e)
            return {"modules": [], "error": "Could not load marketplace"}

    @app.post("/api/marketplace/install")
    async def api_marketplace_install(request: Request):
        """Install a module repo as git submodule. Body: { \"repo_name\": \"talkie-module-<name>\" }."""
        import time as time_module

        client_host = request.client.host if request.client else "unknown"
        now = time_module.monotonic()
        # Rate limit: 5 installs per IP per 60 seconds
        _install_attempts[:] = [(t, h) for t, h in _install_attempts if now - t < 60]
        if sum(1 for _, h in _install_attempts if h == client_host) >= 5:
            return JSONResponse(
                status_code=429,
                content={"error": "Too many installs; try again in a minute"},
            )
        _install_attempts.append((now, client_host))

        try:
            body = await request.json()
        except Exception:
            return JSONResponse(status_code=400, content={"error": "Invalid JSON body"})
        if not isinstance(body, dict):
            return JSONResponse(
                status_code=400, content={"error": "repo_name required"}
            )

        repo_name = body.get("repo_name")
        if not repo_name or not isinstance(repo_name, str):
            return JSONResponse(
                status_code=400,
                content={"error": "repo_name required"},
            )
        repo_name = repo_name.strip()
        if not repo_name:
            return JSONResponse(
                status_code=400,
                content={"error": "repo_name required"},
            )
        try:
            from marketplace import install_module

            loop = asyncio.get_event_loop()
            ok, message, status_code = await loop.run_in_executor(
                None,
                lambda: install_module(app_root, _marketplace_org, repo_name),
            )
            if ok:
                return {
                    "ok": True,
                    "path": message,
                    "message": "Module added. Restart the app (or reload the page and reconnect) to load it.",
                }
            if status_code == 409:
                return JSONResponse(
                    status_code=409, content={"error": "already installed"}
                )
            return JSONResponse(status_code=status_code, content={"error": message})
        except Exception as e:
            logger.exception("Marketplace install failed: %s", e)
            return JSONResponse(status_code=500, content={"error": str(e)})

    @app.get("/api/documents")
    async def api_documents_list():
        if rag_service is None:
            return {"sources": []}
        return {"sources": rag_service.list_indexed_sources()}

    @app.post("/api/documents/upload")
    async def api_documents_upload(files: list[UploadFile] = File(...)):  # noqa: B008
        if rag_service is None:
            return JSONResponse(status_code=503, content={"error": "RAG not available"})
        paths = []
        try:
            with tempfile.TemporaryDirectory() as tmp:
                for f in files:
                    if not f.filename:
                        continue
                    path = Path(tmp) / (f.filename or "upload")
                    content = await f.read()
                    path.write_bytes(content)
                    paths.append(path)
                if paths:
                    rag_service.ingest(paths)
            return {"ok": True, "ingested": len(paths)}
        except Exception as e:
            logger.exception("Documents upload failed: %s", e)
            return JSONResponse(status_code=500, content={"error": str(e)})

    @app.delete("/api/documents/{source:path}")
    async def api_documents_remove(source: str):
        if rag_service is None:
            return JSONResponse(status_code=503, content={"error": "RAG not available"})
        rag_service.remove_from_index(source)
        return {"ok": True}

    async def websocket_endpoint(websocket: WebSocket):
        try:
            await websocket.accept()
        except Exception as e:
            logger.exception("WebSocket accept failed: %s", e)
            raise
        connections_ref["connections"].add(websocket)
        connections_ref["loop"] = asyncio.get_running_loop()
        try:
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "status",
                        "value": "Stopped",
                        "web_mode": pipeline.get_web_mode(),
                    }
                )
            )
            while True:
                try:
                    raw_msg = await websocket.receive()
                except WebSocketDisconnect:
                    break
                except RuntimeError as e:
                    if "disconnect" in str(e).lower():
                        break
                    raise
                if raw_msg.get("type") == "websocket.disconnect":
                    break
                if "text" in raw_msg:
                    try:
                        data = json.loads(raw_msg["text"])
                        action = data.get("action")
                        if action == "start":
                            sample_rate = int(data.get("sample_rate", 16000))
                            module = (data.get("module") or "speech").lower()
                            pipeline.set_web_mode(module == "web")
                            web_capture.set_client_sample_rate(sample_rate)
                            web_capture.start()
                            pipeline.start()
                        elif action == "stop":
                            pipeline.stop()
                            web_capture.stop()
                        elif action == "training_mode":
                            on = data.get("on", False)
                            pipeline.set_training_mode(on)
                            pipeline.set_on_training_transcription(
                                on_training_transcription if on else None
                            )
                    except Exception as e:
                        logger.debug("WS message error: %s", e)
                elif "bytes" in raw_msg:
                    web_capture.put_chunk(bytes(raw_msg["bytes"]))
        finally:
            connections_ref["connections"].discard(websocket)
            # Stop capture first so pipeline read_chunk() returns and the run loop can exit.
            web_capture.stop()
            pipeline.stop()

    _ws_handler_ref[0] = websocket_endpoint

    return app


if __name__ == "__main__":
    main()
