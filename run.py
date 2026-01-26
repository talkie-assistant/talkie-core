#!/usr/bin/env python3
"""
Talkie entry point: load config, initialize database, start UI and pipeline.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from config import AppConfig, load_config

# Ensure project root is on path
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def validate_config(config: dict) -> None:
    """Validate required config values. Raises ValueError with a clear message if invalid."""
    if not config:
        raise ValueError("Config is empty")
    audio = config.get("audio") or {}
    sr = audio.get("sample_rate", 16000)
    try:
        sr = int(sr)
    except (TypeError, ValueError):
        raise ValueError("config.audio.sample_rate must be a positive integer") from None
    if sr <= 0:
        raise ValueError("config.audio.sample_rate must be positive")
    chunk = audio.get("chunk_duration_sec", 5.0)
    try:
        chunk = float(chunk)
    except (TypeError, ValueError):
        raise ValueError("config.audio.chunk_duration_sec must be a positive number") from None
    if chunk <= 0:
        raise ValueError("config.audio.chunk_duration_sec must be positive")
    sens = audio.get("sensitivity", 2.5)
    try:
        sens = float(sens)
    except (TypeError, ValueError):
        raise ValueError("config.audio.sensitivity must be a number") from None
    if not (0.1 <= sens <= 10.0):
        raise ValueError("config.audio.sensitivity must be between 0.1 and 10.0")
    ollama = config.get("ollama") or {}
    model = ollama.get("model_name", "mistral")
    if not model or not str(model).strip():
        raise ValueError("config.ollama.model_name must be non-empty")


def create_and_show_app(config: AppConfig, db_path: Path):
    """
    Create QApplication, pipeline, main window; wire callbacks and show window.
    Returns the QApplication instance (caller typically runs app.exec()).
    """
    from PyQt6.QtWidgets import QApplication

    from app.pipeline import create_pipeline
    from persistence.database import get_connection
    from persistence.history_repo import HistoryRepo
    from persistence.settings_repo import SettingsRepo
    from persistence.training_repo import TrainingRepo
    from ui.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    ui_config = config.get("ui", {})
    font_size = int(ui_config.get("font_size", 24))
    if ui_config.get("high_contrast", True):
        from ui.styles import get_high_contrast_stylesheet
        app.setStyleSheet(get_high_contrast_stylesheet(font_size))
    conn_factory = lambda: get_connection(str(db_path))
    history_repo = HistoryRepo(conn_factory)
    settings_repo = SettingsRepo(
        conn_factory,
        user_context_max_chars=config.get_user_context_max_chars(),
    )
    training_repo = TrainingRepo(conn_factory)
    pipeline = create_pipeline(config, history_repo, settings_repo, training_repo)
    rag_service = None
    try:
        from rag import RAGService
        rag_config = config.get_rag_config()
        rag_service = RAGService(rag_config)

        def rag_retriever(query: str, top_k: int | None = None) -> str:
            return rag_service.retrieve(query, top_k=top_k)

        pipeline.set_rag_retriever(rag_retriever)
        pipeline.set_rag_has_documents(rag_service.has_documents)
        pipeline.set_document_qa_top_k(rag_service.get_document_qa_top_k())
    except Exception as e:
        logging.getLogger(__name__).warning("RAG not available: %s", e)
    debug_log_path = _ROOT / "talkie_debug.log"
    window = MainWindow(
        config,
        pipeline,
        history_repo,
        settings_repo,
        training_repo,
        rag_service=rag_service,
        debug_log_path=debug_log_path,
    )
    pipeline.set_ui_callbacks(
        on_status=window.on_pipeline_status,
        on_response=window.on_pipeline_response,
        on_error=window.on_pipeline_error,
        on_debug=window.append_debug,
        on_volume=window.on_pipeline_volume,
        on_sensitivity_adjusted=window.on_pipeline_sensitivity_adjusted,
    )
    window.show()
    return app


def main() -> None:
    config_path = os.environ.get("TALKIE_CONFIG", str(_ROOT / "config.yaml"))
    raw = load_config()
    validate_config(raw)
    config = AppConfig(raw)
    log_level = config.get_log_level()
    logging.basicConfig(level=getattr(logging, log_level.upper()))
    logger = logging.getLogger(__name__)
    logger.info("Config path: %s", config_path)

    from persistence.database import init_database

    db_path = Path(config.get_db_path())
    db_path.parent.mkdir(parents=True, exist_ok=True)
    init_database(str(db_path))
    logger.info("Database initialized at %s", db_path)

    curation_cfg = config.get_curation_config()
    interval_hours = float(curation_cfg.get("interval_hours", 0))
    if interval_hours > 0:
        from curation.scheduler import start_background_scheduler

        start_background_scheduler(str(db_path), curation_cfg, interval_hours)

    app = create_and_show_app(config, db_path)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
