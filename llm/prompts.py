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
DEFAULT_REGENERATION_SYSTEM = """You complete a speech-impaired user's partial utterance into exactly one natural sentence they meant to say. The input is often fragmented or misheard (e.g. "hockey" for "I'm"). Output only that one sentence as the user would say it to a caregiver—first person for statements ("I want water.", "My leg hurts."), direct requests ("Pass me the salt."), or the question they are asking ("Do you have the time?"). No explanation, no preamble, no description of the task. If the input is already a clear, complete sentence (e.g. "Test sentence.", "I want water.", "Hello."), output that same sentence with high certainty. Only if the input is truly unintelligible noise or gibberish, output exactly: I didn't catch that. Never use "I didn't catch that" for test phrases, greetings, or clear words."""

# When requesting certainty, we append this to the system prompt so the model returns JSON.
REGENERATION_JSON_SUFFIX = """ Output your reply as a single JSON object with exactly two keys: "sentence" (the one sentence as above, or "I didn't catch that." if unintelligible) and "certainty" (0-100). No other text, no markdown."""

# User prompt must clearly ask to complete the phrase, not describe "raw speech recognition" (which triggers meta-explanations).
DEFAULT_REGENERATION_USER_TEMPLATE = (
    "Complete this phrase into one sentence the user meant to say: {transcription}"
)

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

Required: "action" - one of: search, open_url, demo, browse_on, browse_off, store_page, click_link, select_link, go_back, scroll_up, scroll_down, scroll_left, scroll_right, close_tab, unknown

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
- User said: close -> {"action": "close_tab"}
- User said: close tab -> {"action": "close_tab"}

Rule for scroll: "scroll up/down/left/right" (with or without "the page") -> scroll_up, scroll_down, scroll_left, or scroll_right. No other keys needed.

If the phrase is not a browser command (e.g. "I want water"), use {"action": "unknown"}. Output only the JSON object, no markdown or explanation."""


def normalize_browse_utterance(utterance: str) -> str:
    """
    Normalize common STT mishears for browse commands before intent parsing.
    E.g. "open sir" / "Open, sir" -> "open 1" so "open 1" is recognized correctly.
    """
    if not utterance or not utterance.strip():
        return utterance
    u = utterance.strip()
    # "open sir" / "open, sir" / "open sir." -> "open 1" (STT often hears "open 1" as "open sir")
    m = re.match(r"^(\s*open)\s*,?\s*sir\.?\s*", u, re.I)
    if m:
        prefix = m.group(1)
        rest = u[m.end() :].strip()
        u = f"{prefix} 1" + (f" {rest}" if rest else "")
    return u


def build_browse_intent_prompts(utterance: str) -> tuple[str, str]:
    """Build system and user prompts for browse intent extraction. Returns (system_prompt, user_prompt)."""
    user = f"User said: {normalize_browse_utterance(utterance).strip()}"
    return BROWSE_INTENT_SYSTEM.strip(), user


def build_web_mode_prompts(
    utterance: str, system_prompt: str | None = None
) -> tuple[str, str]:
    """
    Build system and user prompts for web (browse) mode when using the
    normalized-command system prompt (config llm.web_mode_system_prompt).
    Returns (system_prompt, user_prompt). If system_prompt is None, falls back
    to BROWSE_INTENT_SYSTEM (JSON output).
    """
    system = (system_prompt or "").strip() or BROWSE_INTENT_SYSTEM.strip()
    user = f"User said: {normalize_browse_utterance(utterance or '').strip()}"
    return system, user


def parse_web_mode_command(raw: str) -> dict:
    """
    Parse a single-line normalized web-mode command into the same intent dict
    used by parse_browse_intent. Used when llm.web_mode_system_prompt is set.
    Command format: "browse on", "search <query>", "save page", "back",
    "open <target>", "scroll up", "scroll down", "no_command".
    """
    out: dict = {"action": "unknown"}
    if not raw or not raw.strip():
        return out
    line = raw.strip().split("\n")[0].strip()
    if not line:
        return out
    lower = line.lower()
    if lower == "no_command":
        return out
    if lower == "browse on":
        out["action"] = "browse_on"
        return out
    if lower == "browse off":
        out["action"] = "browse_off"
        return out
    if lower == "save page":
        out["action"] = "store_page"
        return out
    if lower == "back":
        out["action"] = "go_back"
        return out
    if lower == "scroll up":
        out["action"] = "scroll_up"
        return out
    if lower == "scroll down":
        out["action"] = "scroll_down"
        return out
    if lower == "close" or lower == "close tab":
        out["action"] = "close_tab"
        return out
    if lower.startswith("search "):
        out["action"] = "search"
        out["query"] = line[7:].strip()
        return out
    if lower.startswith("open "):
        target = line[5:].strip()
        if target:
            out["action"] = "click_link"
            out["link_text"] = target
            # "sir" is a common STT mishear for "1"; treat as link_index 1
            if re.match(r"^sir\.?$", target, re.I):
                out["link_index"] = 1
                out.pop("link_text", None)
                return out
            # Optional: "result 3" or "result three" -> link_index
            result_match = re.match(
                r"result\s+(one|two|three|four|five|\d+)\s*$", target, re.I
            )
            if result_match:
                word = result_match.group(1).lower()
                ordinals = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
                if word in ordinals:
                    out["link_index"] = ordinals[word]
                    out.pop("link_text", None)
                elif word.isdigit():
                    out["link_index"] = int(word)
                    out.pop("link_text", None)
            # Bare digit or "one"/"two"/... -> link_index
            elif re.match(r"^\d+$", target):
                out["link_index"] = int(target)
                out.pop("link_text", None)
            else:
                ordinals = {
                    "one": 1,
                    "two": 2,
                    "three": 3,
                    "four": 4,
                    "five": 5,
                    "six": 6,
                    "seven": 7,
                    "eight": 8,
                    "nine": 9,
                    "ten": 10,
                }
                if target.lower() in ordinals:
                    out["link_index"] = ordinals[target.lower()]
                    out.pop("link_text", None)
        return out
    return out


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
            "close_tab",
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
    return (sentence, certainty 0-100). Otherwise return (sentence_from_raw, None).
    When JSON is missing, if raw contains "Sentence: X" (model echoing field name),
    use X as the sentence so we don't speak "I didn't catch that" plus the real sentence.
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
            return (_fallback_sentence_from_raw(raw), None)
        sentence = data.get("sentence")
        if sentence is None:
            return (_fallback_sentence_from_raw(raw), None)
        sentence = strip_certainty_from_response(str(sentence).strip() or raw.strip())
        sentence = _strip_meta_commentary_from_sentence(sentence)
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
        return (_fallback_sentence_from_raw(raw), None)


# Model sometimes echoes system-prompt rules; strip so we never speak "Never use... Output your reply as: ...".
_OUTPUT_REPLY_AS_PATTERN = re.compile(
    r"\s*Output your reply as:\s*[\"']([^\"']+)[\"']\s*\.?\s*$",
    re.IGNORECASE | re.DOTALL,
)

# Model sometimes returns meta-commentary like "Yes, I can complete this phrase into a single sentence that the user meant to say: \"Ready, want water?\"".
# Extract only the quoted sentence so we display/speak one sentence.
_META_MEANT_TO_SAY_PATTERN = re.compile(
    r"(?:that the user meant to say|into a single sentence[^:]*):\s*[\"']([^\"']+)[\"']\s*\.?\s*$",
    re.IGNORECASE | re.DOTALL,
)


def _strip_meta_commentary_from_sentence(text: str) -> str:
    """If the sentence is meta-commentary (e.g. 'Yes, I can complete... that the user meant to say: \"X\"'), return only X."""
    if not text or not text.strip():
        return text
    t = text.strip()
    m = _META_MEANT_TO_SAY_PATTERN.search(t)
    if m:
        return m.group(1).strip()
    return t


def _fallback_sentence_from_raw(raw: str) -> str:
    """When regeneration returns non-JSON, extract sentence; prefer text after 'Sentence: ' or 'Output your reply as: \"X\"'."""
    text = strip_certainty_from_response(raw.strip())
    if not text:
        return text
    # Model sometimes echoes "Output your reply as: \"Test 123.\"" (meta-instruction); use the quoted sentence.
    out_match = _OUTPUT_REPLY_AS_PATTERN.search(text)
    if out_match:
        return out_match.group(1).strip()
    # Model sometimes echoes "Sentence: X" in plain text; use X so we don't speak "I didn't catch that. Sentence: X".
    match = re.search(r"\bSentence:\s*(.+)$", text, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    # If the reply is "I didn't catch that." followed by meta-instruction, strip the meta part so we don't speak it.
    if re.match(r"^I didn't catch that\.?\s*", text, re.IGNORECASE):
        rest = re.sub(
            r"^I didn't catch that\.?\s*", "", text, flags=re.IGNORECASE
        ).strip()
        if "never use" in rest.lower() or "output your reply as" in rest.lower():
            return "I didn't catch that."
    return _strip_meta_commentary_from_sentence(text)
