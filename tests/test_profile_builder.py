"""Tests for profile.builder build_profile_text."""

from __future__ import annotations


from profile.builder import build_profile_text
from profile.constants import ACCEPTED_DISPLAY_CAP, CORRECTION_DISPLAY_CAP


def test_empty() -> None:
    assert build_profile_text(None, [], []) == ""
    assert build_profile_text("", [], []) == ""
    assert build_profile_text(None, [], [], training_facts=[]) == ""


def test_user_context_only() -> None:
    out = build_profile_text("PhD, professor at Brown.", [], [])
    assert "User context" in out
    assert "PhD, professor at Brown" in out
    assert "User phrasing preferences" not in out
    assert "Accepted completions" not in out
    assert "Facts the user" not in out
    assert isinstance(out, str)
    assert len(out) > 0


def test_corrections_only() -> None:
    corrections = [("orig A", "corrected A"), ("", "just this")]
    out = build_profile_text(None, corrections, [])
    assert "User phrasing preferences" in out
    assert 'Prefer: "corrected A" (instead of "orig A")' in out
    assert 'Prefer: "just this"' in out
    assert "orig A" in out
    assert "corrected A" in out
    assert "just this" in out


def test_accepted_only() -> None:
    accepted = [("user said", "accepted response"), ("", "only response")]
    out = build_profile_text(None, [], accepted)
    assert "Accepted completions" in out
    assert 'When user said "user said", this was accepted: "accepted response"' in out
    assert "user said" in out
    assert "accepted response" in out
    assert "only response" in out


def test_training_facts_only() -> None:
    facts = ["Star is my dog.", "Susan is my wife."]
    out = build_profile_text(None, [], [], training_facts=facts)
    assert "Facts the user has told you" in out
    assert "Star is my dog." in out
    assert "Susan is my wife." in out
    assert out.count("- ") >= 2
    assert isinstance(out, str)


def test_all_combined() -> None:
    out = build_profile_text(
        "Context.",
        [("a", "b")],
        [("x", "y")],
        training_facts=["Star is my dog."],
    )
    assert "User context" in out
    assert "Context." in out
    assert "Facts the user has told you" in out
    assert "Star is my dog." in out
    assert "User phrasing preferences" in out
    assert "Accepted completions" in out
    assert out.index("User context") < out.index("Facts the user")
    assert out.index("Facts the user") < out.index("User phrasing")
    assert out.index("User phrasing") < out.index("Accepted completions")
    assert "\n\n" in out


def test_build_profile_text_training_facts_none_default() -> None:
    out = build_profile_text("Context.", [], [], training_facts=None)
    assert "User context" in out
    assert "Context." in out
    assert "Facts the user has told you" not in out


def test_long_lists_capped() -> None:
    corrections = [(f"o{i}", f"c{i}") for i in range(100)]
    out = build_profile_text(None, corrections, [])
    assert "Prefer:" in out
    assert "c0" in out
    assert "c49" in out
    assert "c50" not in out  # cap at 50
    assert CORRECTION_DISPLAY_CAP == 50
    assert out.count("Prefer:") <= CORRECTION_DISPLAY_CAP


def test_none_empty_defensive() -> None:
    assert build_profile_text(None, None, None) == ""
    out = build_profile_text("", [("x", "")], [("a", "")])
    assert "Prefer:" not in out or "instead of" not in out
    assert build_profile_text(None, None, None, training_facts=None) == ""


def test_accepted_display_cap_constant() -> None:
    assert ACCEPTED_DISPLAY_CAP == 30
    assert isinstance(ACCEPTED_DISPLAY_CAP, int)


def test_correction_display_cap_constant() -> None:
    assert CORRECTION_DISPLAY_CAP == 50
    assert isinstance(CORRECTION_DISPLAY_CAP, int)


def test_custom_caps_applied() -> None:
    corrections = [(f"o{i}", f"c{i}") for i in range(100)]
    out = build_profile_text(None, corrections, [], correction_display_cap=3)
    assert "c0" in out
    assert "c2" in out
    assert "c3" not in out
    accepted = [(f"u{i}", f"r{i}") for i in range(50)]
    out2 = build_profile_text(None, [], accepted, accepted_display_cap=5)
    assert "r0" in out2
    assert "r4" in out2
    assert "r5" not in out2


def test_empty_correction_skipped() -> None:
    out = build_profile_text(None, [("a", ""), ("b", "keep")], [])
    assert "keep" in out
    assert "Prefer:" in out
    assert "instead of" in out


def test_whitespace_user_context_stripped() -> None:
    out = build_profile_text("  trim me  ", [], [])
    assert "trim me" in out
    assert "  trim" not in out or out.strip().startswith("User context")


def test_preferred_name_only() -> None:
    out = build_profile_text(None, [], [], preferred_name="Lou")
    assert "Preferred name" in out
    assert "Lou" in out
    assert "User context" not in out


def test_preferred_name_empty_none_omitted() -> None:
    assert build_profile_text(None, [], [], preferred_name="") == ""
    assert build_profile_text(None, [], [], preferred_name=None) == ""


def test_pronouns_only() -> None:
    out = build_profile_text(None, [], [], pronouns="she/her")
    assert "Pronouns" in out
    assert "she/her" in out


def test_pronouns_empty_none_omitted() -> None:
    assert build_profile_text(None, [], [], pronouns="") == ""
    assert build_profile_text(None, [], [], pronouns=None) == ""


def test_response_style_only() -> None:
    out = build_profile_text(None, [], [], response_style="casual")
    assert "Response style" in out
    assert "casual" in out or "conversational" in out
    out_formal = build_profile_text(None, [], [], response_style="formal")
    assert "formal" in out_formal or "professional" in out_formal


def test_response_style_unknown_omitted() -> None:
    out = build_profile_text(None, [], [], response_style="custom")
    assert "Response style" not in out
    out = build_profile_text(None, [], [], response_style="typo")
    assert "Response style" not in out


def test_response_length_only() -> None:
    out = build_profile_text(None, [], [], response_length="brief")
    assert "Response length" in out
    assert "one sentence" in out
    out_det = build_profile_text(None, [], [], response_length="detailed")
    assert "paragraph" in out_det or "detailed" in out_det.lower()


def test_response_length_unknown_omitted() -> None:
    out = build_profile_text(None, [], [], response_length="long")
    assert "Response length" not in out


def test_topic_hints_only() -> None:
    out = build_profile_text(None, [], [], topic_hints="health, family")
    assert "Topics the user" in out
    assert "health, family" in out


def test_topic_hints_empty_none_omitted() -> None:
    assert build_profile_text(None, [], [], topic_hints="") == ""
    assert build_profile_text(None, [], [], topic_hints=None) == ""


def test_personalization_combined_with_user_context() -> None:
    out = build_profile_text(
        "PhD at Brown.",
        [],
        [],
        preferred_name="Lou",
        pronouns="they/them",
        response_style="neutral",
        response_length="standard",
        topic_hints="health, daily care",
    )
    assert "User context" in out
    assert "PhD at Brown" in out
    assert "Preferred name" in out
    assert "Lou" in out
    assert "Pronouns" in out
    assert "they/them" in out
    assert "Response style" in out
    assert "Response length" in out
    assert "Topics the user" in out
    assert "health, daily care" in out
    assert out.index("User context") < out.index("Preferred name")
    assert out.index("Preferred name") < out.index("Pronouns")


def test_build_profile_text_backward_compat_no_new_args() -> None:
    out = build_profile_text("ctx", [], [])
    assert "User context" in out
    assert "ctx" in out
    assert "Preferred name" not in out
    assert "Pronouns" not in out
    assert "Response style" not in out
    assert "Response length" not in out
    assert "Topics the user" not in out
