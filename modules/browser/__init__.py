"""
Voice-controlled browser: fetch URLs, open in Chrome, store current page for RAG.
"""

from __future__ import annotations

import logging
import re
from typing import Callable

from sdk import get_browser_section
from modules.browser.base import FetchResult
from modules.browser.service import BrowserService, DEFAULT_DEMO_SCENARIOS

logger = logging.getLogger(__name__)


def _normalize_link_text(rest: str) -> str:
    """Strip 'the link for ' / 'link for ' so we match page text (e.g. 'CNN breaking news')."""
    r = (rest or "").strip()
    rl = r.lower()
    for prefix in ("the link for ", "link for "):
        if rl.startswith(prefix):
            return r[len(prefix) :].strip()
    return r


def _strip_open_utterance_suffix(rest: str) -> str:
    """Strip trailing speech/STT filler so '... in Chrome. Click.' or '... Scroll down.' matches SERP title."""
    r = (rest or "").strip()
    rl = r.lower()
    # Order: longest first so we strip " in chrome. scroll down." before " in chrome."
    suffixes = (
        " in chrome. scroll down.",
        " in chrome. scroll up.",
        " in chrome. scroll.",
        " in chrome, scroll down.",
        " in chrome, scroll up.",
        " in chrome, scroll.",
        " in chrome. click.",
        " in chrome.",
        " scroll down.",
        " scroll up.",
        " scroll.",
        " click.",
        " click",
    )
    for suffix in suffixes:
        if rl.endswith(suffix):
            return r[: -len(suffix)].strip()
    return r


def _normalize_browse_utterance(utterance: str) -> str:
    """
    Return utterance with leading filler stripped so it starts with the browse verb
    (click, select, the link for, link for). Handles "please click...", "I want to select...", etc.
    """
    u = (utterance or "").strip()
    if not u:
        return u
    ul = u.lower()
    # Already starts with a browse verb (including "open the first link" -> treat as click)
    if (
        ul.startswith("click")
        or ul.startswith("select ")
        or ul.startswith("open ")
        or ul.startswith("open the ")
        or ul.startswith("the link for ")
        or ul.startswith("link for ")
    ):
        return u
    # Find " click ", " select ", " open ", " open the ", " the link for ", " link for " and take from there
    for phrase in (
        " the link for ",
        " link for ",
        " click ",
        " clicks ",
        " clicked ",
        " select ",
        " open the ",
        " open ",
    ):
        idx = ul.find(phrase)
        if idx >= 0:
            return u[idx + 1 :].strip()  # +1 to skip leading space of " phrase"
    return u


def _force_click_or_select_intent_if_uttered(utterance: str, intent: dict) -> None:
    """
    If the user said "click", "select", or "the link for X" (at start or after "please" etc.),
    force click_link or select_link so the LLM cannot wrongly return "search".
    Extracts link_text or link_index from the rest of the utterance.
    """
    u = _normalize_browse_utterance(utterance)
    if not u:
        return
    ul = u.lower()
    # "the link for X" (with or without "click" - STT often drops "click") -> click_link with link_text X
    if ul.startswith("the link for ") or ul.startswith("link for "):
        intent["action"] = "click_link"
        intent.pop("query", None)
        intent["link_text"] = _normalize_link_text(u)
        if "link_index" in intent:
            del intent["link_index"]
        logger.info(
            "Browse: forced click_link (the link for) link_text=%r", intent["link_text"]
        )
        return
    # "open [url]" -> open_url (open URL in new tab only). Use "click [title]" to open a link by title from the page index.
    if ul.startswith("open the ") or ul.startswith("open "):
        rest = (
            u[len("open the ") :].strip()
            if ul.startswith("open the ")
            else u[len("open ") :].strip()
        )
        if not rest:
            return
        # Only treat as URL when rest looks like a hostname (no spaces). Open = URL in new tab only.
        if "." in rest and "link" not in rest.lower() and " " not in rest:
            intent["action"] = "open_url"
            intent.pop("query", None)
            intent.pop("link_index", None)
            intent.pop("link_text", None)
            url = rest if "://" in rest else "https://" + rest
            intent["url"] = url
            logger.info("Browse: forced open_url from utterance url=%r", url)
            return
        # "open sir" / "open, sir" -> link_index 1 (common STT mishear for "open 1")
        if re.match(r"^sir\.?$", rest, re.IGNORECASE):
            intent["action"] = "click_link"
            intent.pop("query", None)
            intent["link_index"] = 1
            if "link_text" in intent:
                del intent["link_text"]
            logger.info("Browse: forced click_link from 'open sir' -> link_index=1")
            return
        # "open the first link" etc. -> click_link by ordinal; "open link for X" -> click_link by text.
        ordinal = re.match(
            r"^(?:the\s+)?(?:first|1st|one|second|2nd|two|third|3rd|three|fourth|4th|four|fifth|5th|five)\s*(?:link\s*)?(?:down)?$",
            rest,
            re.IGNORECASE,
        )
        num_match = re.match(
            r"^(?:link\s+number\s+)?(\d+)\s*(?:link\s*)?(?:down)?$", rest, re.IGNORECASE
        )
        if ordinal:
            intent["action"] = "click_link"
            intent.pop("query", None)
            ordinals = {
                "first": 1,
                "1st": 1,
                "one": 1,
                "second": 2,
                "2nd": 2,
                "two": 2,
                "third": 3,
                "3rd": 3,
                "three": 3,
                "fourth": 4,
                "4th": 4,
                "four": 4,
                "fifth": 5,
                "5th": 5,
                "five": 5,
            }
            for k, v in ordinals.items():
                if k in rest.lower():
                    intent["link_index"] = v
                    if "link_text" in intent:
                        del intent["link_text"]
                    logger.info(
                        "Browse: forced click_link from 'open' link_index=%s", v
                    )
                    return
            return
        if num_match:
            intent["action"] = "click_link"
            intent.pop("query", None)
            intent["link_index"] = int(num_match.group(1))
            if "link_text" in intent:
                del intent["link_text"]
            logger.info(
                "Browse: forced click_link from 'open' link_index=%s",
                intent["link_index"],
            )
            return
        if "link" in rest.lower():
            intent["action"] = "click_link"
            intent.pop("query", None)
            intent["link_text"] = _normalize_link_text(rest)
            if "link_index" in intent:
                del intent["link_index"]
            logger.info(
                "Browse: forced click_link from 'open' link_text=%r",
                intent["link_text"],
            )
            return
        # "open [title]" not supported: open = URL only. User should say "click [title]" to open link by title.
        return
    # "click" or "click ..." (or STT variants "clicks", "clicked") -> click_link; "select ..." -> select_link
    if (
        ul in ("click", "clicks", "clicked")
        or ul.startswith("click ")
        or ul.startswith("clicks ")
        or ul.startswith("clicked ")
    ):
        intent["action"] = "click_link"
        intent.pop("query", None)
        # Strip "click ", "clicks ", or "clicked " to get rest
        for prefix in ("clicked ", "clicks ", "click "):
            if ul.startswith(prefix):
                rest = u[len(prefix) :].strip()
                break
        else:
            rest = u[5:].strip() if len(u) > 5 else ""
        if not rest:
            # "click" with nothing after = use selected link
            if "link_index" in intent:
                del intent["link_index"]
            if "link_text" in intent:
                del intent["link_text"]
            logger.info("Browse: forced click_link (no specifier)")
            return
        # Parse "the third link", "3rd link", "link number 2", "first link", etc.
        ordinal = re.match(
            r"^(?:the\s+)?(?:first|1st|one|second|2nd|two|third|3rd|three|fourth|4th|four|fifth|5th|five)\s*(?:link\s*)?(?:down)?$",
            rest,
            re.IGNORECASE,
        )
        num_match = re.match(
            r"^(?:link\s+number\s+)?(\d+)\s*(?:link\s*)?(?:down)?$", rest, re.IGNORECASE
        )
        if ordinal:
            ordinals = {
                "first": 1,
                "1st": 1,
                "one": 1,
                "second": 2,
                "2nd": 2,
                "two": 2,
                "third": 3,
                "3rd": 3,
                "three": 3,
                "fourth": 4,
                "4th": 4,
                "four": 4,
                "fifth": 5,
                "5th": 5,
                "five": 5,
            }
            rest.split()[0].lower() if rest.split() else ""
            for k, v in ordinals.items():
                if k in rest.lower():
                    intent["link_index"] = v
                    if "link_text" in intent:
                        del intent["link_text"]
                    logger.info(
                        "Browse: forced click_link link_index=%s from utterance", v
                    )
                    return
        if num_match:
            intent["link_index"] = int(num_match.group(1))
            if "link_text" in intent:
                del intent["link_text"]
            logger.info(
                "Browse: forced click_link link_index=%s from utterance",
                intent["link_index"],
            )
            return
        # click [title]: resolve link by title from page index (strip trailing filler for matching).
        intent["link_text"] = _strip_open_utterance_suffix(_normalize_link_text(rest))
        if "link_index" in intent:
            del intent["link_index"]
        logger.info(
            "Browse: forced click_link link_text=%r (resolve from page index)",
            intent["link_text"],
        )
        return
    if ul.startswith("select "):
        intent["action"] = "select_link"
        intent.pop("query", None)
        rest = u[7:].strip()
        if not rest:
            return
        ordinal = re.match(
            r"^(?:the\s+)?(?:first|1st|one|second|2nd|two|third|3rd|three|fourth|4th|four|fifth|5th|five)\s*(?:link\s*)?(?:down)?$",
            rest,
            re.IGNORECASE,
        )
        num_match = re.match(
            r"^(?:link\s+number\s+)?(\d+)\s*(?:link\s*)?(?:down)?$", rest, re.IGNORECASE
        )
        if ordinal:
            ordinals = {
                "first": 1,
                "1st": 1,
                "one": 1,
                "second": 2,
                "2nd": 2,
                "two": 2,
                "third": 3,
                "3rd": 3,
                "three": 3,
                "fourth": 4,
                "4th": 4,
                "four": 4,
                "fifth": 5,
                "5th": 5,
                "five": 5,
            }
            for k, v in ordinals.items():
                if k in rest.lower():
                    intent["link_index"] = v
                    if "link_text" in intent:
                        del intent["link_text"]
                    logger.info(
                        "Browse: forced select_link link_index=%s from utterance", v
                    )
                    return
        if num_match:
            intent["link_index"] = int(num_match.group(1))
            if "link_text" in intent:
                del intent["link_text"]
            logger.info(
                "Browse: forced select_link link_index=%s from utterance",
                intent["link_index"],
            )
            return
        intent["link_text"] = _normalize_link_text(rest)
        if "link_index" in intent:
            del intent["link_index"]
        logger.info(
            "Browse: forced select_link link_text=%r from utterance",
            intent["link_text"],
        )


def _force_search_intent_if_uttered(utterance: str, intent: dict) -> None:
    """
    If the user said "search", "searching", or "search for" (anywhere) in the utterance,
    set intent to search and extract the query. Handles STT/regeneration like
    "searching for cats", "I want to search for cats", "search cats".
    """
    u = (utterance or "").strip()
    if not u:
        return
    ul = u.lower()
    # Do not override when user clearly said scroll, click, select, open, or "the link for X" (not search)
    if (
        ul.startswith("scroll ")
        or ul == "scroll"
        or ul.startswith("click")
        or ul.startswith("select ")
        or ul.startswith("open ")
        or ul.startswith("open the ")
        or ul.startswith("the link for ")
        or ul.startswith("link for ")
    ):
        return
    for phrase in ("searching for ", "search for "):
        if phrase in ul:
            idx = ul.find(phrase)
            query = u[idx + len(phrase) :].strip()
            if query:
                intent["action"] = "search"
                intent["query"] = query
                logger.info(
                    "Browse: forced search intent from utterance (query=%r)", query
                )
                return
    for phrase in (" searching ", " search "):
        if phrase in ul:
            idx = ul.find(phrase)
            query = u[idx + len(phrase) :].strip()
            if query:
                intent["action"] = "search"
                intent["query"] = query
                logger.info(
                    "Browse: forced search intent from utterance (query=%r)", query
                )
                return
    if ul.startswith("searching ") and len(u) > len("searching "):
        intent["action"] = "search"
        intent["query"] = u[len("searching ") :].strip()
        logger.info(
            "Browse: forced search intent from utterance (query=%r)", intent["query"]
        )
    elif ul.startswith("search ") and len(u) > len("search "):
        intent["action"] = "search"
        intent["query"] = u[len("search ") :].strip()
        logger.info(
            "Browse: forced search intent from utterance (query=%r)", intent["query"]
        )


def _force_store_intent_if_uttered(utterance: str, intent: dict) -> None:
    """
    If the user said "save page", "store this page", "store page", or "store the page",
    force action store_page so the LLM cannot misparse.
    """
    u = (utterance or "").strip()
    if not u:
        return
    ul = u.lower()
    for phrase in (
        "save page",
        "save the page",
        "store this page",
        "store the page",
        "store page",
        "store this",
    ):
        if phrase in ul or ul.startswith(phrase) or ul == phrase:
            intent["action"] = "store_page"
            intent.pop("query", None)
            logger.info("Browse: forced store_page from utterance")
            return


def _force_scroll_intent_if_uttered(utterance: str, intent: dict) -> None:
    """
    If the user said "scroll up", "scroll down", "scroll left", or "scroll right"
    (with or without "the page"), force the corresponding scroll action so the LLM cannot misparse as search.
    Do not overwrite when the user clearly asked for search (e.g. "search for scroll down" -> search, not scroll).
    """
    u = (utterance or "").strip().lower()
    if not u:
        return
    if (
        "search for " in u
        or "searching for " in u
        or (u.startswith("search ") and len(u) > len("search "))
    ):
        return
    if u == "scroll":
        return
    if not u.startswith("scroll ") and " scroll " not in u:
        return
    # Extract direction: "scroll up" -> up, "scroll the page down" -> down, "scroll down." -> down, etc.
    rest = u.split("scroll", 1)[-1].strip()
    rest = rest.replace("the page", "").strip().rstrip(".,;!?")
    if rest in ("up", "down", "left", "right"):
        intent["action"] = f"scroll_{rest}"
        intent.pop("query", None)
        logger.info(
            "Browse: forced scroll intent from utterance (action=%s)", intent["action"]
        )
        return
    # "scroll up/down/left/right" with possible trailing words or punctuation
    rest_clean = rest.rstrip(".,;!?")
    for direction in ("up", "down", "left", "right"):
        if (
            rest_clean == direction
            or rest_clean.startswith(direction + " ")
            or rest_clean.endswith(" " + direction)
        ):
            intent["action"] = f"scroll_{direction}"
            intent.pop("query", None)
            logger.info(
                "Browse: forced scroll intent from utterance (action=%s)",
                intent["action"],
            )
            return


def _force_go_back_intent_if_uttered(utterance: str, intent: dict) -> None:
    """If the user said "go back", "previous page", or "back", force action go_back."""
    u = (utterance or "").strip().lower()
    if not u:
        return
    for phrase in ("go back", "previous page", "go to previous page", "back"):
        if (
            phrase in u
            or u == phrase
            or u.startswith(phrase + " ")
            or u.endswith(" " + phrase)
        ):
            intent["action"] = "go_back"
            intent.pop("query", None)
            intent.pop("url", None)
            intent.pop("link_index", None)
            intent.pop("link_text", None)
            logger.info("Browse: forced go_back from utterance")
            return


def _force_close_tab_intent_if_uttered(utterance: str, intent: dict) -> None:
    """If the user said "close" or "close tab", force action close_tab."""
    u = (utterance or "").strip().lower()
    if not u:
        return
    for phrase in ("close tab", "close"):
        if u == phrase or u.startswith(phrase + " "):
            intent["action"] = "close_tab"
            intent.pop("query", None)
            intent.pop("url", None)
            intent.pop("link_index", None)
            intent.pop("link_text", None)
            logger.info("Browse: forced close_tab from utterance")
            return


def create_web_handler(
    config: object,
    ollama_client: object,
    rag_ingest_callback: Callable[[str, str], None] | None = None,
    conn_factory: Callable[[], object] | None = None,
    broadcast: Callable[[dict], None] | None = None,
    pipeline: object | None = None,
) -> Callable[[str, Callable[[bool], None]], str | None] | None:
    """
    Build the web handler callable for pipeline.set_web_handler.
    Returns (utterance, set_web_mode) -> message or None.
    If server mode is enabled, returns remote API client handler.
    """
    raw = getattr(config, "_raw", config) if config is not None else {}
    if not isinstance(raw, dict):
        raw = {}
    web_mode_system_prompt = (raw.get("llm") or {}).get("web_mode_system_prompt")

    # Check if server mode is enabled
    from modules.api.config import get_module_server_config, get_module_base_url

    server_config = get_module_server_config(raw, "browser")
    if server_config is not None:
        # Server mode: return remote API client handler
        from modules.api.client import ModuleAPIClient
        from modules.api.browser_client import RemoteBrowserHandler

        base_url = get_module_base_url(server_config)
        client = ModuleAPIClient(
            base_url=base_url,
            timeout_sec=server_config["timeout_sec"],
            retry_max=server_config["retry_max"],
            retry_delay_sec=server_config["retry_delay_sec"],
            circuit_breaker_failure_threshold=server_config[
                "circuit_breaker_failure_threshold"
            ],
            circuit_breaker_recovery_timeout_sec=server_config[
                "circuit_breaker_recovery_timeout_sec"
            ],
            api_key=server_config["api_key"],
            module_name="browser",
            use_service_discovery=server_config.get("use_service_discovery", False),
            consul_host=server_config.get("consul_host"),
            consul_port=server_config.get("consul_port", 8500),
            keydb_host=server_config.get("keydb_host"),
            keydb_port=server_config.get("keydb_port", 6379),
            load_balancing_strategy=server_config.get(
                "load_balancing_strategy", "health_based"
            ),
            health_check_interval_sec=server_config.get(
                "health_check_interval_sec", 30.0
            ),
        )
        remote_handler = RemoteBrowserHandler(client)

        # Wrap to handle intent parsing locally (since LLM is local)
        def handler(
            utterance: str,
            set_web_mode: Callable[[bool], None],
            set_web_selection: Callable[[str | None], None] | None = None,
            on_open_url: Callable[[str], None] | None = None,
        ) -> str | None:
            try:
                from llm.prompts import (
                    build_browse_intent_prompts,
                    build_web_mode_prompts,
                    parse_browse_intent,
                    parse_web_mode_command,
                )

                logger.debug(
                    "Web search (remote): utterance=%r", (utterance or "")[:120]
                )
                if web_mode_system_prompt:
                    browse_system, browse_user = build_web_mode_prompts(
                        utterance, system_prompt=web_mode_system_prompt
                    )
                    raw_intent = ollama_client.generate(browse_user, browse_system)
                    intent = parse_web_mode_command(raw_intent)
                else:
                    browse_system, browse_user = build_browse_intent_prompts(utterance)
                    raw_intent = ollama_client.generate(browse_user, browse_system)
                    intent = parse_browse_intent(raw_intent)
                _force_search_intent_if_uttered(utterance, intent)
                _force_store_intent_if_uttered(utterance, intent)
                _force_go_back_intent_if_uttered(utterance, intent)
                _force_click_or_select_intent_if_uttered(utterance, intent)
                _force_scroll_intent_if_uttered(utterance, intent)
                _force_close_tab_intent_if_uttered(utterance, intent)
                action = (intent.get("action") or "").strip().lower()
                logger.debug("Web search (remote): intent action=%r", action)

                if action == "unknown":
                    return None
                if action == "browse_on":
                    set_web_mode(True)
                    return 'Browse mode is on. Say "search", then your search term.'
                if action == "browse_off":
                    set_web_mode(False)
                    return "Browse mode is off."
                if action == "close_tab":
                    return "Close tab is only available when running Talkie locally."
                # Scroll must run on the client machine (where the user's Chrome is), not the server.
                if action in (
                    "scroll_up",
                    "scroll_down",
                    "scroll_left",
                    "scroll_right",
                ):
                    direction = action.replace("scroll_", "")
                    browser_cfg = get_browser_section(raw)
                    from modules.browser.chrome_opener import ChromeOpener

                    opener = ChromeOpener(
                        browser_cfg.get("chrome_app_name", "Google Chrome")
                    )
                    return opener.scroll(direction)

                response_data = remote_handler.execute_intent(intent)
                if not response_data or not isinstance(response_data, dict):
                    logger.debug(
                        "Web search (remote): execute_intent returned no result"
                    )
                    return None
                result = response_data.get("result")
                logger.debug(
                    "Web search (remote): result=%r",
                    (result or "")[:100] if result else None,
                )
                open_url = response_data.get("open_url")
                if open_url and on_open_url:
                    try:
                        on_open_url(open_url)
                    except Exception as e:
                        logger.debug("on_open_url failed: %s", e)
                if result and set_web_selection:
                    if (result or "").strip().lower().startswith("selected: "):
                        set_web_selection(result.split(":", 1)[1].strip())
                    elif "clicked link:" in (result or "").lower():
                        set_web_selection(None)
                return result
            except Exception as e:
                logger.exception("Web search (remote) failed: %s", e)
                return "Could not complete that action."

        return handler

    # In-process mode: return local handler
    browser_cfg = get_browser_section(raw)
    browser_service = BrowserService(browser_cfg)

    def handler(
        utterance: str,
        set_web_mode: Callable[[bool], None],
        set_web_selection: Callable[[str | None], None] | None = None,
        on_open_url: Callable[[str], None] | None = None,
    ) -> str | None:
        try:
            from llm.prompts import (
                build_browse_intent_prompts,
                build_web_mode_prompts,
                parse_browse_intent,
                parse_web_mode_command,
            )

            logger.debug("Web search (local): utterance=%r", (utterance or "")[:120])
            if web_mode_system_prompt:
                browse_system, browse_user = build_web_mode_prompts(
                    utterance, system_prompt=web_mode_system_prompt
                )
                raw_intent = ollama_client.generate(browse_user, browse_system)
                intent = parse_web_mode_command(raw_intent)
            else:
                browse_system, browse_user = build_browse_intent_prompts(utterance)
                raw_intent = ollama_client.generate(browse_user, browse_system)
                intent = parse_browse_intent(raw_intent)
            _force_search_intent_if_uttered(utterance, intent)
            _force_store_intent_if_uttered(utterance, intent)
            _force_go_back_intent_if_uttered(utterance, intent)
            _force_click_or_select_intent_if_uttered(utterance, intent)
            _force_scroll_intent_if_uttered(utterance, intent)
            _force_close_tab_intent_if_uttered(utterance, intent)
            action = (intent.get("action") or "").strip().lower()
            logger.debug("Web search (local): intent action=%r", action)

            if action == "unknown":
                return None
            if action == "browse_on":
                set_web_mode(True)
                return 'Browse mode is on. Say "search", then your search term.'
            if action == "browse_off":
                set_web_mode(False)
                return "Browse mode is off."
            if action == "close_tab":
                set_quit = (
                    getattr(pipeline, "set_quit_modal_pending", None)
                    if pipeline
                    else None
                )
                return browser_service.close_tab(broadcast, set_quit)

            def _on_save_search_results(
                q: str, search_url: str, links: list
            ) -> str | None:
                if not conn_factory:
                    return None
                from modules.browser.browse_results_repo import save_run

                return save_run(conn_factory, q, search_url, links)

            result = browser_service.execute(
                intent,
                rag_ingest=rag_ingest_callback,
                on_selection_changed=set_web_selection,
                on_open_url=on_open_url,
                on_save_search_results=_on_save_search_results,
            )
            if isinstance(result, tuple):
                result = result[0]
            logger.debug(
                "Web search (local): result=%r",
                (result or "")[:100] if result else None,
            )
            return result
        except Exception as e:
            logger.exception("Web search (local) failed: %s", e)
            return "Could not complete that action."

    return handler


def register(context: dict) -> None:
    """
    Register browser web handler with the pipeline (two-phase).
    Phase 1 (context has no "pipeline"): no-op.
    Phase 2 (context has "pipeline"): if browser enabled, create web handler and pipeline.set_web_handler(handler).
    """
    pipeline = context.get("pipeline")
    if pipeline is None:
        return
    config = context.get("config")
    if config is None:
        return
    raw = getattr(config, "_raw", config) if config is not None else {}
    if not isinstance(raw, dict):
        raw = {}
    browser_cfg = get_browser_section(raw)
    if not browser_cfg.get("enabled"):
        return
    try:
        from llm.client import OllamaClient

        ollama_cfg = raw.get("ollama", {})
        base_url = (
            config.resolve_internal_service_url(
                ollama_cfg.get("base_url", "http://localhost:11434")
            )
            if hasattr(config, "resolve_internal_service_url")
            else ollama_cfg.get("base_url", "http://localhost:11434")
        )
        intent_llm = OllamaClient(
            base_url=base_url,
            model_name=ollama_cfg.get("model_name", "mistral"),
            options=ollama_cfg.get("options"),
        )
        conn_factory = context.get("conn_factory")
        handler = create_web_handler(
            config,
            intent_llm,
            None,
            conn_factory=conn_factory,
            broadcast=context.get("broadcast"),
            pipeline=context.get("pipeline"),
        )
        if handler is not None:
            pipeline.set_web_handler(handler)
    except Exception as e:
        logger.warning("Browser not available: %s", e)
        broadcast = context.get("broadcast")
        if callable(broadcast):
            broadcast(
                {"type": "debug", "message": "[WARN] Browser not available: " + str(e)}
            )


__all__ = [
    "BrowserService",
    "FetchResult",
    "DEFAULT_DEMO_SCENARIOS",
    "create_web_handler",
    "register",
]
