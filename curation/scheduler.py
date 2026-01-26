"""
Run the curator on a schedule: in-process (when app is running) or via CLI for cron.
"""
from __future__ import annotations

import logging
import threading
import time

from curation.curator import CuratorConfig, run_curation
from persistence.database import get_connection, init_database
from persistence.history_repo import HistoryRepo

logger = logging.getLogger(__name__)


def _curator_connector(db_path: str):
    def fn():
        return get_connection(db_path)

    return fn


def run_curation_from_config(db_path: str, config_dict: dict | None) -> dict[str, int]:
    """Run one curation pass using config dict (e.g. from config.yaml). Returns counts."""
    init_database(db_path)
    connector = _curator_connector(db_path)
    repo = HistoryRepo(connector)
    cfg = CuratorConfig()
    if config_dict:
        cfg.min_weight = float(config_dict.get("min_weight", cfg.min_weight))
        cfg.max_weight = float(config_dict.get("max_weight", cfg.max_weight))
        cfg.correction_weight_bump = float(
            config_dict.get("correction_weight_bump", cfg.correction_weight_bump)
        )
        cfg.pattern_count_weight_scale = float(
            config_dict.get("pattern_count_weight_scale", cfg.pattern_count_weight_scale)
        )
        cfg.exclude_duplicate_phrase = bool(
            config_dict.get("exclude_duplicate_phrase", cfg.exclude_duplicate_phrase)
        )
        cfg.exclude_empty_transcription = bool(
            config_dict.get("exclude_empty_transcription", cfg.exclude_empty_transcription)
        )
        cfg.delete_older_than_days = config_dict.get("delete_older_than_days")
        cfg.max_interactions_to_curate = int(
            config_dict.get("max_interactions_to_curate", cfg.max_interactions_to_curate)
        )
    return run_curation(repo, config=cfg)


def start_background_scheduler(
    db_path: str,
    config_dict: dict | None,
    interval_hours: float,
) -> threading.Thread | None:
    """
    Start a daemon thread that runs curation every interval_hours.
    Returns the thread (so caller can track it). Returns None if interval_hours <= 0.
    """
    if interval_hours <= 0:
        return None
    interval_sec = max(60.0, interval_hours * 3600)
    first_run_delay_sec = min(60.0, interval_sec)

    def loop() -> None:
        time.sleep(first_run_delay_sec)
        try:
            run_curation_from_config(db_path, config_dict)
        except Exception as e:
            logger.exception("Curation scheduler first run failed: %s", e)
        while True:
            time.sleep(interval_sec)
            try:
                run_curation_from_config(db_path, config_dict)
            except Exception as e:
                logger.exception("Curation scheduler failed: %s", e)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
    logger.info("Curation scheduler started (interval=%.1f h)", interval_hours)
    return t
