"""Tests for history_cmd: _resolve_db_path, _item_at_index, cmd_clear/list/view/edit, main."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from persistence.database import init_database
from persistence.history_repo import HistoryRepo

# Import after path is set (tests run from project root)
import history_cmd  # noqa: E402


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "talkie.db"
    init_database(str(path))
    yield path
    path.unlink(missing_ok=True)


@pytest.fixture
def repo(db_path: Path) -> HistoryRepo:
    def conn_factory():
        return sqlite3.connect(str(db_path))

    return HistoryRepo(conn_factory)


def test_resolve_db_path_uses_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("persistence:\n  db_path: data/talkie-core.db\n")
    db_full = tmp_path / "data" / "talkie-core.db"
    with patch(
        "history_cmd.load_config",
        return_value={"persistence": {"db_path": "data/talkie-core.db"}},
    ):
        with patch.object(Path, "cwd", return_value=tmp_path):
            path = history_cmd._resolve_db_path()
    assert path == db_full
    assert path.is_absolute()


def test_resolve_db_path_absolute(tmp_path: Path) -> None:
    db_abs = tmp_path / "abs.db"
    with patch(
        "history_cmd.load_config",
        return_value={"persistence": {"db_path": str(db_abs)}},
    ):
        path = history_cmd._resolve_db_path()
    assert path == db_abs
    assert path.is_absolute()


def test_resolve_db_path_default_when_no_persistence(tmp_path: Path) -> None:
    with patch("history_cmd.load_config", return_value={}):
        with patch.object(Path, "cwd", return_value=tmp_path):
            path = history_cmd._resolve_db_path()
    assert path == tmp_path / "data/talkie.db"


def test_resolve_db_path_file_not_found_exits() -> None:
    with patch(
        "history_cmd.load_config", side_effect=FileNotFoundError("config missing")
    ):
        with pytest.raises(SystemExit) as exc_info:
            history_cmd._resolve_db_path()
    assert exc_info.value.code == 1


def test_item_at_index_returns_record_and_id(repo: HistoryRepo) -> None:
    repo.insert_interaction("hello", "Hi there.")
    repo.insert_interaction("bye", "Goodbye.")
    out = history_cmd._item_at_index(repo, 1)
    assert out is not None
    rec, iid = out
    assert rec["original_transcription"] == "bye"
    assert rec["llm_response"] == "Goodbye."
    assert iid == rec["id"]
    out2 = history_cmd._item_at_index(repo, 2)
    assert out2 is not None
    rec2, _ = out2
    assert rec2["original_transcription"] == "hello"


def test_item_at_index_out_of_range_returns_none(repo: HistoryRepo) -> None:
    repo.insert_interaction("a", "A")
    assert history_cmd._item_at_index(repo, 0) is None
    assert history_cmd._item_at_index(repo, 2) is None
    assert history_cmd._item_at_index(repo, 10) is None


def test_item_at_index_empty_repo_returns_none(repo: HistoryRepo) -> None:
    assert history_cmd._item_at_index(repo, 1) is None


def test_cmd_clear_empties_repo_and_prints(
    repo: HistoryRepo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.insert_interaction("x", "X")
    repo.insert_interaction("y", "Y")
    history_cmd.cmd_clear(repo)
    out, err = capsys.readouterr()
    assert "Cleared 2" in out
    assert repo.list_recent(limit=10) == []


def test_cmd_list_prints_numbered_newest_first(
    repo: HistoryRepo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.insert_interaction("first", "First response.")
    repo.insert_interaction("second", "Second response.")
    history_cmd.cmd_list(repo, limit=10)
    out, err = capsys.readouterr()
    assert "1 " in out
    assert "2 " in out
    assert "second" in out
    assert "first" in out
    assert "Second response" in out
    assert "First response" in out


def test_cmd_view_prints_full_record(
    repo: HistoryRepo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.insert_interaction("trans", "Response.")
    history_cmd.cmd_view(repo, 1)
    out, err = capsys.readouterr()
    assert "id:" in out
    assert "created_at:" in out
    assert "original_transcription:" in out
    assert "trans" in out
    assert "llm_response:" in out
    assert "Response." in out
    assert "corrected_response:" in out


def test_cmd_view_out_of_range_exits(repo: HistoryRepo) -> None:
    with pytest.raises(SystemExit) as exc_info:
        history_cmd.cmd_view(repo, 1)
    assert exc_info.value.code == 1


def test_cmd_edit_calls_update_correction_with_edited_content(
    repo: HistoryRepo, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.insert_interaction("orig", "LLM said this.")
    rec = repo.list_recent(limit=1)[0]
    interaction_id = rec["id"]
    edit_file = tmp_path / "edit.txt"
    edited_content = "User corrected this."

    class MockTempFile:
        def __enter__(self):
            self.f = type(
                "F",
                (),
                {
                    "name": str(edit_file),
                    "write": lambda self, s: edit_file.write_text(s),
                },
            )()
            return self.f

        def __exit__(self, *args):
            pass

    def open_mock(path, mode="r", encoding=None, **kwargs):
        if path == str(edit_file) and "r" in mode:
            return type(
                "F",
                (),
                {
                    "read": lambda self: edited_content,
                    "__enter__": lambda self: self,
                    "__exit__": lambda self, *a: None,
                },
            )()
        return open(path, mode, encoding=encoding or "utf-8", **kwargs)

    with patch("history_cmd._item_at_index", return_value=(rec, interaction_id)):
        with patch("history_cmd.subprocess.run"):
            with patch(
                "history_cmd.tempfile.NamedTemporaryFile", return_value=MockTempFile()
            ):
                with patch("builtins.open", side_effect=open_mock):
                    with patch("os.unlink"):
                        history_cmd.cmd_edit(repo, 1)
    rows = repo.list_recent(limit=1)
    assert len(rows) == 1
    assert rows[0].get("corrected_response") == edited_content
    out, _ = capsys.readouterr()
    assert "Updated correction" in out


def test_main_no_args_exits_with_usage() -> None:
    with patch.object(sys, "argv", ["history_cmd.py"]):
        with pytest.raises(SystemExit) as exc_info:
            history_cmd.main()
    assert exc_info.value.code == 1


def test_main_unknown_subcommand_exits() -> None:
    with patch.object(sys, "argv", ["history_cmd.py", "unknown"]):
        with patch("history_cmd._resolve_db_path", return_value=Path("/tmp/talkie.db")):
            with patch("history_cmd._repo"):
                with pytest.raises(SystemExit) as exc_info:
                    history_cmd.main()
    assert exc_info.value.code == 1


def test_main_clear_calls_cmd_clear(tmp_path: Path) -> None:
    db_path = tmp_path / "talkie.db"
    init_database(str(db_path))
    repo = HistoryRepo(lambda: sqlite3.connect(str(db_path)))
    repo.insert_interaction("a", "A")
    repo.insert_interaction("b", "B")

    with patch.object(sys, "argv", ["history_cmd.py", "clear"]):
        with patch("history_cmd._resolve_db_path", return_value=db_path):
            with patch("history_cmd._repo", return_value=repo):
                history_cmd.main()
    assert repo.list_recent(limit=10) == []


def test_main_view_without_n_exits() -> None:
    with patch.object(sys, "argv", ["history_cmd.py", "view"]):
        with patch("history_cmd._resolve_db_path"):
            with patch("history_cmd._repo"):
                with pytest.raises(SystemExit) as exc_info:
                    history_cmd.main()
    assert exc_info.value.code == 1


def test_main_view_invalid_n_exits() -> None:
    with patch.object(sys, "argv", ["history_cmd.py", "view", "x"]):
        with patch("history_cmd._resolve_db_path"):
            with patch("history_cmd._repo"):
                with pytest.raises(SystemExit) as exc_info:
                    history_cmd.main()
    assert exc_info.value.code == 1
