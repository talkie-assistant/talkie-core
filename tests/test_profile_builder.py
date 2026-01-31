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
