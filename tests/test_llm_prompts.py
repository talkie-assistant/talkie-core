"""Tests for llm.prompts: build_system_prompt, build_user_prompt, build_regeneration_prompts, parse_*, strip_certainty."""

from __future__ import annotations

import pytest

from llm.prompts import (
    build_browse_intent_prompts,
    build_document_qa_system_prompt,
    build_document_qa_user_prompt,
    build_regeneration_prompts,
    build_system_prompt,
    build_user_prompt,
    build_web_mode_prompts,
    normalize_browse_utterance,
    parse_browse_intent,
    parse_regeneration_response,
    parse_web_mode_command,
    strip_certainty_from_response,
)


# ---- build_system_prompt ----
def test_build_system_prompt_empty_profile_returns_base() -> None:
    out = build_system_prompt(profile_context=None, system_base="Base text.")
    assert out == "Base text."
    assert isinstance(out, str)
    assert "Base text" in out


def test_build_system_prompt_with_profile_appends() -> None:
    out = build_system_prompt(
        profile_context="User prefers short sentences.",
        system_base="Base.",
    )
    assert "Base." in out
    assert "User prefers short sentences" in out
    assert out.count("\n\n") >= 1


def test_build_system_prompt_with_conversation_context() -> None:
    out = build_system_prompt(
        profile_context=None,
        system_base="Base.",
        conversation_context="User: hi\nAssistant: Hello.",
    )
    assert "Base." in out
    assert "Recent conversation" in out
    assert "User: hi" in out
    assert "Assistant: Hello" in out


def test_build_system_prompt_with_retrieved_context() -> None:
    out = build_system_prompt(
        profile_context=None,
        system_base="Base.",
        retrieved_context="Doc excerpt here.",
    )
    assert "Base." in out
    assert "Relevant background" in out or "Doc excerpt" in out
    assert "Doc excerpt here" in out


def test_build_system_prompt_default_base_when_empty() -> None:
    out = build_system_prompt(profile_context=None, system_base="")
    assert len(out) > 0
    assert "speech-impaired" in out or "first person" in out or "sentence" in out


# ---- build_user_prompt ----
def test_build_user_prompt_uses_template() -> None:
    out = build_user_prompt("hello world")
    assert "hello world" in out
    assert isinstance(out, str)
    assert len(out) > 0


def test_build_user_prompt_custom_template() -> None:
    out = build_user_prompt("phrase", user_prompt_template="Input: {transcription}")
    assert out == "Input: phrase"
    assert "phrase" in out


# ---- build_regeneration_prompts ----
def test_build_regeneration_prompts_returns_tuple() -> None:
    sys_p, user_p = build_regeneration_prompts("raw stt")
    assert isinstance(sys_p, str)
    assert isinstance(user_p, str)
    assert "raw stt" in user_p or "Complete" in user_p
    assert len(sys_p) > 0
    assert len(user_p) > 0


def test_build_regeneration_prompts_request_certainty_appends_json() -> None:
    sys_p, _ = build_regeneration_prompts("x", request_certainty=True)
    assert "JSON" in sys_p or "certainty" in sys_p
    assert "sentence" in sys_p.lower()


# ---- build_document_qa_* ----
def test_build_document_qa_system_prompt_empty_context() -> None:
    out = build_document_qa_system_prompt("")
    assert "context" in out.lower() or "documents" in out.lower()
    assert isinstance(out, str)


def test_build_document_qa_system_prompt_with_context() -> None:
    out = build_document_qa_system_prompt("Retrieved paragraph here.")
    assert "Retrieved paragraph here" in out
    assert "Relevant context" in out or "context" in out.lower()


def test_build_document_qa_user_prompt() -> None:
    out = build_document_qa_user_prompt("What is X?")
    assert out == "What is X?"
    assert isinstance(out, str)


def test_build_document_qa_user_prompt_empty_returns_default() -> None:
    out = build_document_qa_user_prompt("")
    assert "No question" in out or len(out) > 0
    assert isinstance(out, str)


# ---- normalize_browse_utterance ----
def test_normalize_browse_utterance_empty_unchanged() -> None:
    assert normalize_browse_utterance("") == ""
    assert normalize_browse_utterance("   ") == "   "


def test_normalize_browse_utterance_open_sir_to_open_1() -> None:
    out = normalize_browse_utterance("open sir")
    assert "open" in out
    assert "1" in out
    assert "sir" not in out or out == "open 1"


def test_normalize_browse_utterance_unchanged_when_no_sir() -> None:
    out = normalize_browse_utterance("search cats")
    assert out.strip() == "search cats"


# ---- build_browse_intent_prompts ----
def test_build_browse_intent_prompts_returns_tuple() -> None:
    sys_p, user_p = build_browse_intent_prompts("search trains")
    assert isinstance(sys_p, str)
    assert isinstance(user_p, str)
    assert "User said" in user_p
    assert "search trains" in user_p
    assert "action" in sys_p or "search" in sys_p


# ---- build_web_mode_prompts ----
def test_build_web_mode_prompts_returns_tuple() -> None:
    sys_p, user_p = build_web_mode_prompts("scroll down")
    assert isinstance(sys_p, str)
    assert isinstance(user_p, str)
    assert "scroll down" in user_p
    assert "User said" in user_p


def test_build_web_mode_prompts_custom_system() -> None:
    sys_p, _ = build_web_mode_prompts("x", system_prompt="Custom system.")
    assert sys_p == "Custom system."


# ---- parse_web_mode_command ----
@pytest.mark.parametrize(
    "raw,expected_action",
    [
        ("", "unknown"),
        ("   ", "unknown"),
        ("browse on", "browse_on"),
        ("browse off", "browse_off"),
        ("save page", "store_page"),
        ("back", "go_back"),
        ("scroll up", "scroll_up"),
        ("scroll down", "scroll_down"),
        ("close", "close_tab"),
        ("close tab", "close_tab"),
        ("search cats", "search"),
        ("open 1", "click_link"),
    ],
)
def test_parse_web_mode_command(raw: str, expected_action: str) -> None:
    out = parse_web_mode_command(raw)
    assert isinstance(out, dict)
    assert "action" in out
    assert out["action"] == expected_action


def test_parse_web_mode_command_search_includes_query() -> None:
    out = parse_web_mode_command("search high speed rail")
    assert out["action"] == "search"
    assert out.get("query") == "high speed rail"
    assert isinstance(out["query"], str)


def test_parse_web_mode_command_open_sir_becomes_link_index_1() -> None:
    out = parse_web_mode_command("open sir")
    assert out["action"] == "click_link"
    assert out.get("link_index") == 1


def test_parse_web_mode_command_open_2_becomes_link_index_2() -> None:
    out = parse_web_mode_command("open 2")
    assert out["action"] == "click_link"
    assert out.get("link_index") == 2


# ---- parse_browse_intent ----
def test_parse_browse_intent_empty_returns_unknown() -> None:
    out = parse_browse_intent("")
    assert out == {"action": "unknown"}
    assert parse_browse_intent("   ")["action"] == "unknown"


def test_parse_browse_intent_valid_json_search() -> None:
    raw = '{"action": "search", "query": "trains"}'
    out = parse_browse_intent(raw)
    assert out["action"] == "search"
    assert out.get("query") == "trains"
    assert isinstance(out, dict)


def test_parse_browse_intent_markdown_code_block_extracted() -> None:
    raw = '```json\n{"action": "go_back"}\n```'
    out = parse_browse_intent(raw)
    assert out["action"] == "go_back"


def test_parse_browse_intent_invalid_json_returns_unknown() -> None:
    out = parse_browse_intent("not json")
    assert out["action"] == "unknown"


def test_parse_browse_intent_link_index() -> None:
    raw = '{"action": "click_link", "link_index": 3}'
    out = parse_browse_intent(raw)
    assert out["action"] == "click_link"
    assert out.get("link_index") == 3


# ---- strip_certainty_from_response ----
def test_strip_certainty_from_response_empty_unchanged() -> None:
    assert strip_certainty_from_response("") == ""
    assert strip_certainty_from_response("   ") == "   "


def test_strip_certainty_from_response_strips_trailing_certainty() -> None:
    out = strip_certainty_from_response("Hello world. (certainty: 85)")
    assert "Hello world" in out
    assert "certainty" not in out or out == "Hello world."


def test_strip_certainty_from_response_no_match_unchanged() -> None:
    text = "Just a sentence."
    assert strip_certainty_from_response(text) == text


# ---- parse_regeneration_response ----
def test_parse_regeneration_response_empty_returns_empty_tuple() -> None:
    sent, cert = parse_regeneration_response("")
    assert sent == ""
    assert cert is None
    sent2, cert2 = parse_regeneration_response("   ")
    assert sent2 == ""
    assert cert2 is None


def test_parse_regeneration_response_valid_json() -> None:
    raw = '{"sentence": "I want water.", "certainty": 90}'
    sent, cert = parse_regeneration_response(raw)
    assert sent == "I want water."
    assert cert == 90
    assert isinstance(sent, str)
    assert isinstance(cert, int)


def test_parse_regeneration_response_certainty_clamped() -> None:
    raw = '{"sentence": "Hi", "certainty": 150}'
    sent, cert = parse_regeneration_response(raw)
    assert cert == 100
    raw2 = '{"sentence": "Hi", "certainty": -10}'
    _, cert2 = parse_regeneration_response(raw2)
    assert cert2 == 0


def test_parse_regeneration_response_no_certainty_returns_none() -> None:
    raw = '{"sentence": "Hello."}'
    sent, cert = parse_regeneration_response(raw)
    assert sent == "Hello."
    assert cert is None


def test_parse_regeneration_response_invalid_json_uses_fallback() -> None:
    raw = "Plain text sentence."
    sent, cert = parse_regeneration_response(raw)
    assert cert is None
    assert isinstance(sent, str)
    assert "sentence" in raw.lower() or len(sent) > 0


def test_parse_regeneration_response_sentence_strips_certainty_phrase() -> None:
    raw = '{"sentence": "I want water. (certainty: 80)", "certainty": 80}'
    sent, cert = parse_regeneration_response(raw)
    assert cert == 80
    assert "I want water" in sent
    assert "certainty" not in sent or sent == "I want water."


# ---- parse_regeneration_response fallback (_fallback_sentence_from_raw) ----
def test_parse_regeneration_response_fallback_sentence_colon() -> None:
    raw = "Sentence: I want water."
    sent, cert = parse_regeneration_response(raw)
    assert cert is None
    assert sent == "I want water."
    assert isinstance(sent, str)


def test_parse_regeneration_response_fallback_output_reply_as() -> None:
    raw = 'Output your reply as: "Hello world."'
    sent, cert = parse_regeneration_response(raw)
    assert cert is None
    assert sent == "Hello world."
    assert "Hello" in sent
    assert "world" in sent


def test_parse_regeneration_response_fallback_ididnt_catch_plus_meta() -> None:
    raw = "I didn't catch that. Never use that phrase for test phrases."
    sent, cert = parse_regeneration_response(raw)
    assert cert is None
    assert sent == "I didn't catch that."
    assert "Never use" not in sent


def test_parse_regeneration_response_fallback_plain_text_returned() -> None:
    raw = "Some random reply without JSON."
    sent, cert = parse_regeneration_response(raw)
    assert cert is None
    assert isinstance(sent, str)
    assert len(sent) > 0
    assert (
        "random" in sent or "reply" in sent or "without" in sent or sent == raw.strip()
    )


def test_parse_regeneration_response_fallback_markdown_block_invalid_json() -> None:
    raw = "```json\nnot valid json\n```"
    sent, cert = parse_regeneration_response(raw)
    assert cert is None
    assert isinstance(sent, str)


def test_parse_regeneration_response_fallback_empty_string() -> None:
    sent, cert = parse_regeneration_response("")
    assert cert is None
    assert sent == ""


def test_parse_regeneration_response_fallback_ididnt_catch_output_reply_as() -> None:
    raw = 'I didn\'t catch that. Output your reply as: "Test."'
    sent, cert = parse_regeneration_response(raw)
    assert cert is None
    assert sent == "Test."
