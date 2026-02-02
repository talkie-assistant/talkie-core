"""Tests for BrowseCommandMatcher: is_browse_command and first_single_command."""

from __future__ import annotations

import pytest

from app.browse_command import BrowseCommandMatcher


@pytest.fixture
def matcher() -> BrowseCommandMatcher:
    return BrowseCommandMatcher()


# ---- is_browse_command: search (including relaxed) ----
@pytest.mark.parametrize(
    "candidate",
    [
        "search airplane engines",
        "search for cheap flights",
        "searching for cats",
        "Search...Saube airplane engine.",
        "Search. topic",
        "I searched for a Sawbearer plane engine.",
        "Oh, good. I searched for a Sawbearer plane engine.",
        "searched for high speed rail",
        " search high speed rail",
    ],
)
def test_is_browse_command_search_and_relaxed(
    matcher: BrowseCommandMatcher, candidate: str
) -> None:
    assert matcher.is_browse_command(candidate) is True


# ---- is_browse_command: scroll, store, go_back, click, mode_toggle ----
@pytest.mark.parametrize(
    "candidate",
    [
        "scroll down",
        "scroll up",
        "Scroll down.",
        "store this page",
        "store the page",
        "save page",
        "save the page",
        "go back",
        "previous page",
        "back",
        "click the third link",
        "select the first link",
        "open the first link",
        "open result three",
        "start browsing",
        "stop browsing",
        "browse on",
        "browse off",
    ],
)
def test_is_browse_command_other_commands(
    matcher: BrowseCommandMatcher, candidate: str
) -> None:
    assert matcher.is_browse_command(candidate) is True


# ---- is_browse_command: negative cases ----
@pytest.mark.parametrize(
    "candidate",
    [
        "Okay",
        "Thank you",
        "Thank you for the hard work.",
        "How are you",
        "I want water.",
        "Airplane engines.",
        # Mishear: "click" in middle must not trigger browse (command must start utterance).
        "one here two click your free feedback",
        # URL then "Click Link" (command not at start)
        "www.slashflashsupport.google.com Click Link",
        # Echo/continuation of TTS: "to open a result... say open 1..."
        "to open a result one here, two click here, three feedback.",
    ],
)
def test_is_browse_command_negative(
    matcher: BrowseCommandMatcher, candidate: str
) -> None:
    assert matcher.is_browse_command(candidate) is False


def test_is_browse_command_empty_returns_false(matcher: BrowseCommandMatcher) -> None:
    assert matcher.is_browse_command("") is False
    assert matcher.is_browse_command("   ") is False


@pytest.mark.parametrize(
    "candidate",
    [
        "close tab",
        "close",
        "scroll",
        "scroll up",
        "link for first result",
        "the link for feedback",
    ],
)
def test_is_browse_command_close_scroll_link(
    matcher: BrowseCommandMatcher, candidate: str
) -> None:
    assert matcher.is_browse_command(candidate) is True


# ---- is_browse_command: any of multiple candidates ----
def test_is_browse_command_any_candidate(matcher: BrowseCommandMatcher) -> None:
    assert matcher.is_browse_command("Okay", "scroll down") is True
    assert matcher.is_browse_command("scroll down", "Okay") is True
    assert matcher.is_browse_command("Okay", "Thank you") is False


# ---- first_single_command ----
def test_first_single_command_scroll_then_search(matcher: BrowseCommandMatcher) -> None:
    result = matcher.first_single_command("Scroll down. Open search for")
    assert result == "Scroll down"


def test_first_single_command_search_and_chrome(matcher: BrowseCommandMatcher) -> None:
    result = matcher.first_single_command("search high speed railway and chrome output")
    assert result == "search high speed railway"


def test_first_single_command_short_unchanged(matcher: BrowseCommandMatcher) -> None:
    result = matcher.first_single_command("search cats")
    assert result == "search cats"


def test_first_single_command_under_max_len_unchanged(
    matcher: BrowseCommandMatcher,
) -> None:
    short = "search airplane engines"
    assert matcher.first_single_command(short, max_len=80) == short


def test_first_single_command_capped(matcher: BrowseCommandMatcher) -> None:
    long_utterance = "search " + ("x" * 100)
    result = matcher.first_single_command(long_utterance, max_len=80)
    assert len(result) == 80
    assert result.startswith("search ")


def test_first_single_command_empty(matcher: BrowseCommandMatcher) -> None:
    assert matcher.first_single_command("") == ""
    assert matcher.first_single_command("   ") == ""


# ---- starts_with_browse_command: web mode "wait for command" ----
@pytest.mark.parametrize(
    "utterance",
    [
        "search miniature golf in California.",
        "open 1",
        "open the first link",
        "click feedback",
        "scroll down",
        "go back",
        "stop browsing",
    ],
)
def test_starts_with_browse_command_positive(
    matcher: BrowseCommandMatcher, utterance: str
) -> None:
    assert matcher.starts_with_browse_command(utterance) is True


@pytest.mark.parametrize(
    "utterance",
    [
        "to open a result one here, two click here, three feedback.",
        "one here two click your free feedback",
        "Yeah.",
    ],
)
def test_starts_with_browse_command_negative(
    matcher: BrowseCommandMatcher, utterance: str
) -> None:
    assert matcher.starts_with_browse_command(utterance) is False


def test_starts_with_browse_command_empty_returns_false(
    matcher: BrowseCommandMatcher,
) -> None:
    assert matcher.starts_with_browse_command("") is False
    assert matcher.starts_with_browse_command("   ") is False


# ---- is_open_number_only: open result by number (cooldown exception) ----
@pytest.mark.parametrize(
    "utterance",
    [
        "open 1",
        "open 6",
        "open 10",
        "Open 6.",
        "open the 3",
        "open one",
        "open six",
        "open ten",
    ],
)
def test_is_open_number_only_positive(
    matcher: BrowseCommandMatcher, utterance: str
) -> None:
    assert matcher.is_open_number_only(utterance) is True


@pytest.mark.parametrize(
    "utterance",
    [
        "open",
        "open 0",
        "open 11",
        "open 12",
        "open the first link",
        "scroll down",
        "open one two",
    ],
)
def test_is_open_number_only_negative(
    matcher: BrowseCommandMatcher, utterance: str
) -> None:
    assert matcher.is_open_number_only(utterance) is False
