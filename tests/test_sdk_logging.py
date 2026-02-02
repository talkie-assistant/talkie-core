"""Tests for sdk.logging: get_logger."""

from __future__ import annotations

import logging

from sdk import get_logger


def test_get_logger_returns_logger() -> None:
    logger = get_logger("speech")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "talkie.modules.speech"


def test_get_logger_name_prefix() -> None:
    logger = get_logger("rag")
    assert logger.name == "talkie.modules.rag"
    assert "talkie.modules" in logger.name
    assert "rag" in logger.name


def test_get_logger_empty_strips_to_module() -> None:
    logger = get_logger("")
    assert "talkie.modules" in logger.name
    assert logger.name == "talkie.modules.module"


def test_get_logger_whitespace_strips() -> None:
    logger = get_logger("  browser  ")
    assert logger.name == "talkie.modules.browser"
