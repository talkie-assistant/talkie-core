"""Tests for curation __main__: main() with --export and without; FileNotFoundError exits 1."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Import after path is set (tests run from project root)
import curation.__main__ as curation_main  # noqa: E402


def test_curation_main_file_not_found_exits() -> None:
    with patch(
        "curation.__main__.load_config", side_effect=FileNotFoundError("config missing")
    ):
        with patch.object(sys, "argv", ["curation"]):
            with pytest.raises(SystemExit) as exc_info:
                curation_main.main()
    assert exc_info.value.code == 1


def test_curation_main_export_calls_export_for_finetuning(tmp_path: Path) -> None:
    export_path = tmp_path / "out.jsonl"
    config = {
        "persistence": {"db_path": str(tmp_path / "talkie.db")},
        "llm": {"system_prompt": "You are helpful."},
    }
    with patch("curation.__main__.load_config", return_value=config):
        with patch("curation.__main__.export_for_finetuning") as mock_export:
            mock_export.return_value = 3
            with patch.object(sys, "argv", ["curation", "--export", str(export_path)]):
                curation_main.main()
    mock_export.assert_called_once()
    call_args = mock_export.call_args[0]
    call_kw = mock_export.call_args[1]
    assert call_args[1] == str(export_path)
    assert call_kw["limit"] == 5000
    assert call_kw["system_instruction"] == "You are helpful."


def test_curation_main_export_with_limit(tmp_path: Path) -> None:
    export_path = tmp_path / "out.jsonl"
    config = {"persistence": {"db_path": str(tmp_path / "talkie-core.db")}}
    with patch("curation.__main__.load_config", return_value=config):
        with patch("curation.__main__.export_for_finetuning") as mock_export:
            mock_export.return_value = 0
            with patch.object(
                sys,
                "argv",
                ["curation", "--export", str(export_path), "--limit", "100"],
            ):
                curation_main.main()
    mock_export.assert_called_once()
    assert mock_export.call_args[1]["limit"] == 100


def test_curation_main_no_export_calls_run_curation_from_config(tmp_path: Path) -> None:
    db_path = str(tmp_path / "talkie-core.db")
    config = {"persistence": {"db_path": db_path}, "curation": {"min_weight": 0.0}}
    with patch("curation.__main__.load_config", return_value=config):
        with patch("curation.__main__.run_curation_from_config") as mock_run:
            mock_run.return_value = {"weights_updated": 2, "excluded": 0, "deleted": 0}
            with patch.object(sys, "argv", ["curation"]):
                curation_main.main()
    mock_run.assert_called_once()
    assert mock_run.call_args[0][0] == db_path
    assert mock_run.call_args[0][1] == {"min_weight": 0.0}
