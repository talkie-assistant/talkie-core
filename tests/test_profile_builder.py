"""Tests for profile.builder build_profile_text."""
from __future__ import annotations

import pytest

from profile.builder import build_profile_text


def test_empty() -> None:
    assert build_profile_text(None, [], []) == ""


def test_user_context_only() -> None:
    out = build_profile_text("PhD, professor at Brown.", [], [])
    assert "User context" in out
    assert "PhD, professor at Brown" in out


def test_corrections_only() -> None:
    corrections = [("orig A", "corrected A"), ("", "just this")]
    out = build_profile_text(None, corrections, [])
    assert "User phrasing preferences" in out
    assert 'Prefer: "corrected A" (instead of "orig A")' in out
    assert 'Prefer: "just this"' in out


def test_accepted_only() -> None:
    accepted = [("user said", "accepted response"), ("", "only response")]
    out = build_profile_text(None, [], accepted)
    assert "Accepted completions" in out
    assert 'When user said "user said", this was accepted: "accepted response"' in out


def test_training_facts_only() -> None:
    facts = ["Star is my dog.", "Susan is my wife."]
    out = build_profile_text(None, [], [], training_facts=facts)
    assert "Facts the user has told you" in out
    assert "Star is my dog." in out
    assert "Susan is my wife." in out


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


def test_long_lists_capped() -> None:
    corrections = [(f"o{i}", f"c{i}") for i in range(100)]
    out = build_profile_text(None, corrections, [])
    assert "Prefer:" in out
    assert "c0" in out
    assert "c49" in out
    assert "c50" not in out  # cap at 50


def test_none_empty_defensive() -> None:
    assert build_profile_text(None, None, None) == ""
    out = build_profile_text("", [("x", "")], [("a", "")])
    assert "Prefer:" not in out or "instead of" not in out
