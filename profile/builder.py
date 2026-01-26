"""
Build profile text from user context, corrections, and accepted pairs for LLM context.
"""
from __future__ import annotations

from profile.constants import ACCEPTED_DISPLAY_CAP, CORRECTION_DISPLAY_CAP


def _section_user_context(uc: str | None) -> str:
    if not (uc and uc.strip()):
        return ""
    return "User context (tailor vocabulary and topic to this person):\n" + uc.strip()


def _section_corrections(
    corrections: list[tuple[str, str]],
    correction_display_cap: int | None = None,
) -> str:
    if not corrections:
        return ""
    cap = correction_display_cap if correction_display_cap is not None else CORRECTION_DISPLAY_CAP
    lines = []
    for orig, corrected in corrections[:cap]:
        orig = (orig or "").strip()
        corrected = (corrected or "").strip()
        if not corrected:
            continue
        if orig:
            lines.append(f'- Prefer: "{corrected}" (instead of "{orig}")')
        else:
            lines.append(f'- Prefer: "{corrected}"')
    if not lines:
        return ""
    return "User phrasing preferences (from corrections; prefer these when relevant):\n" + "\n".join(lines)


def _section_accepted(
    accepted: list[tuple[str, str]],
    accepted_display_cap: int | None = None,
) -> str:
    if not accepted:
        return ""
    cap = accepted_display_cap if accepted_display_cap is not None else ACCEPTED_DISPLAY_CAP
    lines = []
    for transcription, response in accepted[:cap]:
        t = (transcription or "").strip()
        r = (response or "").strip()
        if not r:
            continue
        if t:
            lines.append(f'- When user said "{t}", this was accepted: "{r}"')
        else:
            lines.append(f'- Accepted: "{r}"')
    if not lines:
        return ""
    return "Accepted completions (use similar style when relevant):\n" + "\n".join(lines)


def _section_training_facts(facts: list[str] | None) -> str:
    if not facts:
        return ""
    lines = [f"- {f.strip()}" for f in facts if (f or "").strip()]
    if not lines:
        return ""
    return (
        "Facts the user has told you (use this context when relevant, e.g. names and relationships):\n"
        + "\n".join(lines)
    )


def build_profile_text(
    user_context: str | None,
    corrections: list[tuple[str, str]] | None,
    accepted: list[tuple[str, str]] | None,
    training_facts: list[str] | None = None,
    correction_display_cap: int | None = None,
    accepted_display_cap: int | None = None,
) -> str:
    """
    Build one profile string from user context, corrections, and accepted pairs.
    Defensive: skips invalid entries; returns empty sections for bad input.
    Caps use profile.constants defaults when not provided.
    """
    sections = []
    uc = _section_user_context(user_context)
    if uc:
        sections.append(uc)
    train = _section_training_facts(training_facts)
    if train:
        sections.append(train)
    corr = _section_corrections(
        corrections if corrections else [], correction_display_cap=correction_display_cap
    )
    if corr:
        sections.append(corr)
    acc = _section_accepted(
        accepted if accepted else [], accepted_display_cap=accepted_display_cap
    )
    if acc:
        sections.append(acc)
    return "\n\n".join(sections) if sections else ""
