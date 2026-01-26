"""
Curate the interactions database: pattern recognition, assign weights to sentences/phrases,
and optionally add/remove (exclude or delete) entries. Heavier-weighted patterns are
prioritized in the language profile and can be used for fine-tuning.
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from persistence.history_repo import HistoryRepo

logger = logging.getLogger(__name__)

# Normalize text for grouping similar phrases: lowercase, collapse whitespace, strip
def _normalize_phrase(text: str) -> str:
    if not text or not isinstance(text, str):
        return ""
    t = text.strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t


def _normalize_for_pattern(s: str) -> str:
    """Stricter normalization for pattern key: remove trailing punctuation for grouping."""
    t = _normalize_phrase(s)
    t = re.sub(r"[.,!?;:]+$", "", t)
    return t


class CuratorConfig:
    """Options for curation run."""

    def __init__(
        self,
        *,
        min_weight: float = 0.0,
        max_weight: float = 10.0,
        correction_weight_bump: float = 1.5,
        pattern_count_weight_scale: float = 0.5,
        exclude_duplicate_phrase: bool = True,
        exclude_empty_transcription: bool = True,
        delete_older_than_days: int | None = None,
        max_interactions_to_curate: int = 10_000,
    ) -> None:
        self.min_weight = min_weight
        self.max_weight = max_weight
        self.correction_weight_bump = correction_weight_bump
        self.pattern_count_weight_scale = pattern_count_weight_scale
        self.exclude_duplicate_phrase = exclude_duplicate_phrase
        self.exclude_empty_transcription = exclude_empty_transcription
        self.delete_older_than_days = delete_older_than_days
        self.max_interactions_to_curate = max_interactions_to_curate


def run_curation(
    history_repo: HistoryRepo,
    config: CuratorConfig | None = None,
) -> dict[str, int]:
    """
    Run one curation pass: compute weights from patterns, update DB, optionally exclude/remove.
    Returns counts: weights_updated, excluded, deleted.
    """
    cfg = config or CuratorConfig()
    counts = {"weights_updated": 0, "excluded": 0, "deleted": 0}

    rows = history_repo.list_for_curation(limit=cfg.max_interactions_to_curate)
    if not rows:
        logger.debug("Curator: no interactions to curate")
        return counts

    # Pattern recognition: count occurrences of (normalized) phrases
    # Use the text we care about for the profile: corrected_response when present, else llm_response; and original_transcription
    response_key_count: dict[str, int] = defaultdict(int)
    transcription_key_count: dict[str, int] = defaultdict(int)
    for r in rows:
        resp = (r.get("corrected_response") or r.get("llm_response") or "").strip()
        if resp:
            response_key_count[_normalize_for_pattern(resp)] += 1
        orig = (r.get("original_transcription") or "").strip()
        if orig:
            transcription_key_count[_normalize_for_pattern(orig)] += 1

    # Assign weight per interaction: base 1.0, bump for corrections, bump for recurring phrases
    weight_updates: list[tuple[int, float]] = []
    to_exclude: list[int] = []

    for r in rows:
        iid = r["id"]
        orig = (r.get("original_transcription") or "").strip()
        resp = (r.get("corrected_response") or r.get("llm_response") or "").strip()

        if cfg.exclude_empty_transcription and not orig:
            to_exclude.append(iid)
            continue

        weight = 1.0
        if r.get("corrected_response"):
            weight += cfg.correction_weight_bump
        resp_key = _normalize_for_pattern(resp)
        trans_key = _normalize_for_pattern(orig)
        count_resp = response_key_count.get(resp_key, 0)
        count_trans = transcription_key_count.get(trans_key, 0)
        weight += (count_resp - 1) * cfg.pattern_count_weight_scale
        weight += (count_trans - 1) * cfg.pattern_count_weight_scale
        weight = max(cfg.min_weight, min(cfg.max_weight, weight))

        weight_updates.append((iid, weight))

        if cfg.exclude_duplicate_phrase and (count_resp > 1 or count_trans > 1):
            pass
            # Option: we could exclude duplicates here; currently we only weight them higher
            # and do not auto-exclude. Uncomment to exclude duplicates: to_exclude.append(iid)

    if weight_updates:
        history_repo.update_weights_batch(weight_updates)
        counts["weights_updated"] = len(weight_updates)
    if to_exclude:
        history_repo.set_exclude_batch(to_exclude, exclude=True)
        counts["excluded"] = len(to_exclude)

    if cfg.delete_older_than_days is not None and cfg.delete_older_than_days > 0:
        from datetime import datetime, timezone, timedelta

        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=cfg.delete_older_than_days)
        ).isoformat()
        try:
            old_ids = history_repo.list_ids_older_than(cutoff)
            if old_ids:
                n = history_repo.delete_interactions(old_ids)
                counts["deleted"] = n
                logger.info(
                    "Curator: deleted %d interactions older than %d days",
                    n,
                    cfg.delete_older_than_days,
                )
        except Exception as e:
            logger.exception("Curator: delete older failed: %s", e)

    logger.info(
        "Curator: weights_updated=%d excluded=%d deleted=%d",
        counts["weights_updated"],
        counts["excluded"],
        counts["deleted"],
    )
    return counts
