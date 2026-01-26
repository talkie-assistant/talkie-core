"""
System and user prompt builders for the LLM; injects profile context.
Prompt text is configured in config.yaml under llm; these are fallback defaults.
"""
from __future__ import annotations

import json
import re

DEFAULT_SYSTEM_BASE = """You assist a speech-impaired user in conversation. You will receive a partial or fragmented sentence from their speech recognition (e.g. a few words, a phrase, or an incomplete thought). Your job is to turn that into one clear, complete, natural sentence that conveys what they mean. The sentence is the user speaking for themselves: it must always be in first person (e.g. "I want water", "I'm cold", "I need to rest"). It will be shown and spoken to the person they are talking to (e.g. a caregiver or family member), so it should sound like what the user would say in normal conversation—never third person or "the user wants...". Keep it concise. Do not explain or add meta-commentary; output only the completed first-person sentence. Output only the single completed sentence, no preamble or suffix."""

DEFAULT_USER_PROMPT_TEMPLATE = "Partial sentence from speech-impaired user: {transcription}"

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
) -> str:
    """
    Build the system prompt from config (system_base). If profile_context is provided,
    append it as guidance for phrasing and style. If retrieved_context is provided
    (e.g. from RAG over the user's publications), append it as relevant background.
    """
    base = (system_base or "").strip() or DEFAULT_SYSTEM_BASE
    parts = [base]
    if profile_context and profile_context.strip():
        parts.append(profile_context.strip())
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
    template = (user_prompt_template or "").strip() or DEFAULT_REGENERATION_USER_TEMPLATE
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
            return (raw.strip(), None)
        sentence = data.get("sentence")
        if sentence is None:
            return (raw.strip(), None)
        sentence = str(sentence).strip() or raw.strip()
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
        return (raw.strip(), None)
