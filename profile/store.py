"""
Language profile: load user context, corrections, and accepted pairs; build context for the LLM.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from profile.builder import build_profile_text
from profile.constants import ACCEPTED_DISPLAY_CAP, ACCEPTED_PROFILE_LIMIT, CORRECTION_DISPLAY_CAP, CORRECTION_PROFILE_LIMIT

if TYPE_CHECKING:
    from persistence.history_repo import HistoryRepo
    from persistence.settings_repo import SettingsRepo
    from persistence.training_repo import TrainingRepo

logger = logging.getLogger(__name__)

PROFILE_CONTEXT_CACHE_TTL_SEC = 30.0


class LanguageProfile:
    """
    Provides context for the LLM from user context (settings), corrections, and accepted responses.
    get_context_for_llm() returns text to append to the system prompt. On error, returns empty string.
    Caches the result for a short TTL; call invalidate_cache() when history changes.
    """

    def __init__(
        self,
        history_repo: HistoryRepo,
        settings_repo: SettingsRepo | None = None,
        training_repo: TrainingRepo | None = None,
        correction_limit: int = CORRECTION_PROFILE_LIMIT,
        accepted_limit: int = ACCEPTED_PROFILE_LIMIT,
        correction_display_cap: int | None = None,
        accepted_display_cap: int | None = None,
    ) -> None:
        self._history_repo = history_repo
        self._settings_repo = settings_repo
        self._training_repo = training_repo
        self._correction_limit = correction_limit
        self._accepted_limit = accepted_limit
        self._correction_display_cap = correction_display_cap if correction_display_cap is not None else CORRECTION_DISPLAY_CAP
        self._accepted_display_cap = accepted_display_cap if accepted_display_cap is not None else ACCEPTED_DISPLAY_CAP
        self._context_cache: str | None = None
        self._context_cache_time: float = 0.0

    def invalidate_cache(self) -> None:
        """Invalidate cached profile context (e.g. after a new interaction is saved)."""
        self._context_cache = None

    def get_context_for_llm(self) -> str:
        """
        Fetch user_context, corrections, and accepted pairs; build profile text.
        On exception, log and return empty string so the LLM still gets base prompt only.
        Uses a short TTL cache; call invalidate_cache() when history changes.
        """
        now = time.monotonic()
        if (
            self._context_cache is not None
            and (now - self._context_cache_time) < PROFILE_CONTEXT_CACHE_TTL_SEC
        ):
            return self._context_cache
        try:
            user_context = None
            if self._settings_repo is not None:
                user_context = self._settings_repo.get("user_context")
            training_facts = []
            if self._training_repo is not None:
                training_facts = self._training_repo.get_for_profile()
            corrections = self._history_repo.get_corrections_for_profile(
                limit=self._correction_limit
            )
            accepted = self._history_repo.get_accepted_for_profile(
                limit=self._accepted_limit
            )
            self._context_cache = build_profile_text(
                user_context,
                corrections,
                accepted,
                training_facts=training_facts,
                correction_display_cap=self._correction_display_cap,
                accepted_display_cap=self._accepted_display_cap,
            )
            self._context_cache_time = now
            return self._context_cache
        except Exception as e:
            logger.exception("LanguageProfile.get_context_for_llm failed: %s", e)
            return ""
