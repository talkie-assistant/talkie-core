"""
System and user prompt builders for the LLM; injects profile context.
Prompt text is configured in config.yaml under llm; these are fallback defaults.
"""

from __future__ import annotations

import json
import re

DEFAULT_SYSTEM_BASE = """You assist a speech-impaired user in conversation. You will receive a partial or fragmented sentence from their speech recognition (e.g. a few words, a phrase, or an incomplete thought). Your job is to turn that into one clear, complete, natural sentence that conveys what they mean. The sentence is the user speaking for themselves: it must always be in first person (e.g. "I want water", "I'm cold", "I need to rest"). It will be shown and spoken to the person they are talking to (e.g. a caregiver or family member), so it should sound like what the user would say in normal conversation—never third person or "the user wants...". Keep it concise. Do not explain or add meta-commentary; output only the completed first-person sentence. Output only the single completed sentence, no preamble or suffix."""

DEFAULT_USER_PROMPT_TEMPLATE = "Current phrase to respond to (output one sentence for this phrase only): {transcription}"

# Regeneration: raw STT output -> single sentence most likely reflecting user intent.
DEFAULT_REGENERATION_SYSTEM = """You interpret raw speech-recognition output from a speech-impaired user. The text is often fragmented, misheard, or contains homophones (e.g. "hockey" for "I'm", "outlook" for "cat out"). Your job is to output exactly one sentence that has the highest probability of being what the user intended, as the user would say it to the person they are talking to (e.g. a caregiver). Use first person for statements about themselves (e.g. "I want water.", "My leg hurts.", "I'm cold."). For requests to the listener—asking them to do something—output the request as the user would say it (e.g. "Pass me the salt.", "Pass me the chicken.", "Could you turn off the light?"), not as first-person past tense ("I passed the salt" is wrong when they mean pass me the salt). If the user doesn't use "I" (or equivalent), or uses "you" or refers to the person they're asking, it's likely a question—output it as the question they would ask (e.g. "Do you have the time?", "Could you help?", "Are you coming?"). Output only that sentence—no preamble, no explanation. If the input is gibberish or unintelligible, output exactly: I didn't catch that."""

# When requesting certainty, we append this to the system prompt so the model returns JSON.
REGENERATION_JSON_SUFFIX = """ Output your reply as a single JSON object with exactly two keys: "sentence" (the sentence as above, or "I didn't catch that." if unintelligible) and "certainty" (0-100, your confidence that this sentence matches the user's intent). No other text, no markdown."""

DEFAULT_REGENERATION_USER_TEMPLATE = "Raw speech recognition: {transcription}"

DEFAULT_EXPORT_INSTRUCTION = "You assist a speech-impaired user. Turn their partial speech into one clear, complete sentence in first person (as the user speaking: I want..., I need...). Output only that sentence."


def build_system_prompt(
    profile_context: str | None,
    system_base: str | None = None,
    retrieved_context: str | None = None,
    conversation_context: str | None = None,
) -> str:
    """
    Build the system prompt from config (system_base). If profile_context is provided,
    append it as guidance for phrasing and style. If retrieved_context is provided
    (e.g. from RAG over the user's publications), append it as relevant background.
    If conversation_context is provided (recent user/assistant turns), append it so
    the model can keep its reply in context.
    """
    base = (system_base or "").strip() or DEFAULT_SYSTEM_BASE
    parts = [base]
    if profile_context and profile_context.strip():
        parts.append(profile_context.strip())
    if conversation_context and conversation_context.strip():
        parts.append(
            "Recent conversation (topic context only; do not echo any of it):\n"
            + conversation_context.strip()
            + '\n\nYou must output one NEW sentence for the CURRENT phrase only. Do not output the same or nearly the same sentence as any "Assistant:" or "User:" line above. Use the conversation only to keep topic and pronouns consistent; your reply must be a new formulation from the current phrase in the user message.'
        )
    if retrieved_context and retrieved_context.strip():
        parts.append(
            "Relevant background (from the user's documents/publications when applicable):\n"
            + retrieved_context.strip()
        )
    if len(parts) == 1:
        return base
    return "\n\n".join(parts)


def build_user_prompt(
    transcription: str,
    user_prompt_template: str | None = None,
) -> str:
    """Build the user prompt from the transcribed (possibly partial) speech."""
    template = (user_prompt_template or "").strip() or DEFAULT_USER_PROMPT_TEMPLATE
    return template.format(transcription=transcription.strip())


def build_regeneration_prompts(
    transcription: str,
    system_prompt: str | None = None,
    user_prompt_template: str | None = None,
    request_certainty: bool = False,
) -> tuple[str, str]:
    """
    Build system and user prompts for the regeneration step: raw STT output
    -> one sentence with high probability of matching user intent (first person).
    If request_certainty is True, appends instruction to output JSON with sentence and certainty (0-100).
    Returns (system_prompt, user_prompt).
    """
    system = (system_prompt or "").strip() or DEFAULT_REGENERATION_SYSTEM
    if request_certainty:
        system = system.rstrip() + "\n\n" + REGENERATION_JSON_SUFFIX.strip()
    template = (
        user_prompt_template or ""
    ).strip() or DEFAULT_REGENERATION_USER_TEMPLATE
    user = template.format(transcription=transcription.strip())
    return system, user


DOCUMENT_QA_SYSTEM_BASE = """Answer the following question using only the provided context from the user's documents. If the context does not contain enough information, say so. Do not make up information. Output only the answer, no preamble."""


def build_document_qa_system_prompt(retrieved_context: str) -> str:
    """Build system prompt for document Q&A: instructions plus retrieved context."""
    parts = [DOCUMENT_QA_SYSTEM_BASE.strip()]
    if retrieved_context and retrieved_context.strip():
        parts.append("Relevant context:\n" + retrieved_context.strip())
    return "\n\n".join(parts)


def build_document_qa_user_prompt(question: str) -> str:
    """Build user prompt for document Q&A: the user's question."""
    return (question or "").strip() or "No question provided."


# Browse intent: user says command word then payload (e.g. "search" then "high speed railway"). Uses DuckDuckGo for search.
BROWSE_INTENT_SYSTEM = """You interpret a spoken browse command. Output a single JSON object.

CRITICAL for search: If the user said "search" or "search for" followed by ANY other words, use action "search" and put EVERYTHING after "search"/"search for" into "query". Use the USER'S exact words for "query", never substitute example words like "cats" or "weather". Never use scroll_up/scroll_down/scroll_left/scroll_right for search requests.

Required: "action" - one of: search, open_url, demo, browse_on, browse_off, store_page, click_link, select_link, go_back, scroll_up, scroll_down, scroll_left, scroll_right, unknown

Optional (only when relevant):
- "query": string - for action "search" ONLY: the exact phrase the user said after "search" (e.g. user says "search high speed railway" -> query "high speed railway")
- "url": string - for "open_url" or "store_page": full URL
- "demo_index": number - for "demo" ONLY: 0-based (demo one=0). Use "demo" only for commands like "run demo one", never for "search something"
- "demo_name": string - for "demo" only when user asks to run a numbered demo by name
- "link_index": number - for "click_link" or "select_link": 1-based position (first=1, second=2, third=3). Extract from "click the third link", "click 3rd link down", "select the first link", "link number 2", etc.
- "link_text": string - for "click_link" or "select_link": the link text the user said. For "click X" or "select X", put X in link_text. Use the user's exact words (e.g. "click trump tariffs today" -> link_text "trump tariffs today").

Rule: "search [anything]" is always action "search" with query = [anything]. Do not use action "demo" when the user is asking to search for something.
Rule for click_link: (1) "click" with NOTHING after (or just "click") -> action "click_link" with NO link_index or link_text (clicks the currently selected link). (2) "click" + position (third link, 3rd link down, link number 2) -> click_link with link_index. (3) "click" + any other words (partial sentence) -> click_link with link_text = those words. Prefer link_text when both could apply.
Rule for select_link: "select" works like "click" but only highlights the link (does not open it): "select the third link" -> select_link + link_index; "select trump tariffs" -> select_link + link_text; "select" alone is invalid (must specify which link).
Examples:
- User said: search high speed railway -> {"action": "search", "query": "high speed railway"}
- User said: search for cheap flights -> {"action": "search", "query": "cheap flights"}
- User said: open example dot com -> {"action": "open_url", "url": "https://example.com"}
- User said: stop browsing -> {"action": "browse_off"}
- User said: go back -> {"action": "go_back"}
- User said: previous page -> {"action": "go_back"}
- User said: run demo one -> {"action": "demo", "demo_index": 0}
- User said: store this page -> {"action": "store_page"}
- User said: click the third link -> {"action": "click_link", "link_index": 3}
- User said: click 3rd link down -> {"action": "click_link", "link_index": 3}
- User said: click the first link -> {"action": "click_link", "link_index": 1}
- User said: click link number 2 -> {"action": "click_link", "link_index": 2}
- User said: click -> {"action": "click_link"}
- User said: click trump tariffs today -> {"action": "click_link", "link_text": "trump tariffs today"}
- User said: click the link that says all about dogs -> {"action": "click_link", "link_text": "all about dogs"}
- User said: select the third link -> {"action": "select_link", "link_index": 3}
- User said: select trump tariffs -> {"action": "select_link", "link_text": "trump tariffs"}
- User said: select the link that says weather -> {"action": "select_link", "link_text": "weather"}
- User said: scroll up -> {"action": "scroll_up"}
- User said: scroll down -> {"action": "scroll_down"}
- User said: scroll left -> {"action": "scroll_left"}
- User said: scroll right -> {"action": "scroll_right"}
- User said: scroll the page up -> {"action": "scroll_up"}
- User said: scroll the page down -> {"action": "scroll_down"}

Rule for scroll: "scroll up/down/left/right" (with or without "the page") -> scroll_up, scroll_down, scroll_left, or scroll_right. No other keys needed.

If the phrase is not a browser command (e.g. "I want water"), use {"action": "unknown"}. Output only the JSON object, no markdown or explanation."""


def build_browse_intent_prompts(utterance: str) -> tuple[str, str]:
    """Build system and user prompts for browse intent extraction. Returns (system_prompt, user_prompt)."""
    user = f"User said: {utterance.strip()}"
    return BROWSE_INTENT_SYSTEM.strip(), user


def parse_browse_intent(raw: str) -> dict:
    """
    Parse LLM response for browse intent. Returns dict with at least "action";
    may include "query", "url", "demo_index", "demo_name". action defaults to "unknown" if parse fails.
    """
    out: dict = {"action": "unknown"}
    if not raw or not raw.strip():
        return out
    text = raw.strip()
    code_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if code_match:
        text = code_match.group(1).strip()
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            return out
        action = (data.get("action") or "").strip().lower()
        if action in (
            "search",
            "open_url",
            "demo",
            "browse_on",
            "browse_off",
            "store_page",
            "click_link",
            "select_link",
            "go_back",
            "scroll_up",
            "scroll_down",
            "scroll_left",
            "scroll_right",
            "unknown",
        ):
            out["action"] = action
        if "query" in data and data["query"] is not None:
            out["query"] = str(data["query"]).strip()
        if "url" in data and data["url"] is not None:
            out["url"] = str(data["url"]).strip()
        if "demo_index" in data and data["demo_index"] is not None:
            try:
                out["demo_index"] = int(data["demo_index"])
            except (TypeError, ValueError):
                pass
        if "demo_name" in data and data["demo_name"] is not None:
            out["demo_name"] = str(data["demo_name"]).strip()
        if "link_index" in data and data["link_index"] is not None:
            try:
                out["link_index"] = int(data["link_index"])
            except (TypeError, ValueError):
                pass
        if "link_text" in data and data["link_text"] is not None:
            out["link_text"] = str(data["link_text"]).strip()
    except json.JSONDecodeError:
        pass
    return out


# Trailing phrases to strip from spoken/display response so certainty is not spoken.
CERTAINTY_STRIP_PATTERNS = [
    re.compile(
        r"\s*[.,;:]?\s*\(?\s*certainty\s*[:\s]?\s*\d+\s*%?\s*\)?\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"\s*[.,;:]?\s*\(?\s*\d+\s*%\s*certainty\s*\)?\s*$",
        re.IGNORECASE,
    ),
]


def strip_certainty_from_response(text: str) -> str:
    """Remove trailing certainty phrases so they are not spoken or shown."""
    if not text or not text.strip():
        return text
    out = text.strip()
    for pat in CERTAINTY_STRIP_PATTERNS:
        out = pat.sub("", out).strip()
    return out.strip() or text.strip()


def parse_regeneration_response(raw: str) -> tuple[str, int | None]:
    """
    Parse the regeneration model output. If it is JSON with "sentence" and "certainty",
    return (sentence, certainty 0-100). Otherwise return (raw.strip(), None).
    """
    if not raw or not raw.strip():
        return ("", None)
    text = raw.strip()
    # Strip markdown code block if present
    code_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if code_match:
        text = code_match.group(1).strip()
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            return (strip_certainty_from_response(raw.strip()), None)
        sentence = data.get("sentence")
        if sentence is None:
            return (strip_certainty_from_response(raw.strip()), None)
        sentence = strip_certainty_from_response(
            str(sentence).strip() or raw.strip()
        )
        certainty = data.get("certainty")
        if certainty is None:
            return (sentence, None)
        try:
            c = int(certainty)
            c = max(0, min(100, c))
            return (sentence, c)
        except (TypeError, ValueError):
            return (sentence, None)
    except json.JSONDecodeError:
        return (strip_certainty_from_response(raw.strip()), None)
