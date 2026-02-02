#!/usr/bin/env python3
"""
CLI for interaction history: clear, list (numbered), view #, edit #.
Usage: pipenv run python history_cmd.py clear | list | view <N> | edit <N>
Uses TALKIE_CONFIG or config.yaml for db_path. List is newest-first (1 = most recent).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Project root on path
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config import load_config  # noqa: E402
from persistence.database import get_connection, init_database  # noqa: E402
from persistence.history_repo import HistoryRepo  # noqa: E402

LIST_DEFAULT_LIMIT = 2000
LIST_PREVIEW_LEN = 60


def _resolve_db_path() -> Path:
    try:
        raw = load_config()
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    db_path = Path(raw.get("persistence", {}).get("db_path", "data/talkie-core.db"))
    if not db_path.is_absolute():
        db_path = Path.cwd() / db_path
    return db_path


def _repo(db_path: Path) -> HistoryRepo:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    init_database(str(db_path))

    def conn_factory():
        return get_connection(str(db_path))

    return HistoryRepo(conn_factory)


def _item_at_index(repo: HistoryRepo, one_based_index: int) -> tuple[dict, int] | None:
    """Return (InteractionRecord, db_id) for 1-based index, or None if out of range."""
    if one_based_index < 1:
        return None
    limit = max(one_based_index, 1)
    items = repo.list_recent(limit=limit)
    if one_based_index > len(items):
        return None
    rec = items[one_based_index - 1]
    return (rec, rec["id"])


def cmd_clear(repo: HistoryRepo) -> None:
    n = repo.delete_all()
    print(f"Cleared {n} interaction(s).")


def cmd_list(repo: HistoryRepo, limit: int = LIST_DEFAULT_LIMIT) -> None:
    items = repo.list_recent(limit=limit)
    for i, r in enumerate(items, start=1):
        created = (r.get("created_at") or "")[:19]
        orig = (r.get("original_transcription") or "").strip()
        resp = (r.get("llm_response") or "").strip()
        if len(orig) > LIST_PREVIEW_LEN:
            orig = orig[: LIST_PREVIEW_LEN - 1] + "\u2026"
        if len(resp) > LIST_PREVIEW_LEN:
            resp = resp[: LIST_PREVIEW_LEN - 1] + "\u2026"
        print(f"{i:5}  {created}  {orig}")
        print(f"       {resp}")


def cmd_view(repo: HistoryRepo, one_based_index: int) -> None:
    out = _item_at_index(repo, one_based_index)
    if out is None:
        print(f"No history item at index {one_based_index}.", file=sys.stderr)
        sys.exit(1)
    rec, _ = out
    print("id:", rec.get("id"))
    print("created_at:", rec.get("created_at"))
    print("original_transcription:", rec.get("original_transcription") or "")
    print("llm_response:", rec.get("llm_response") or "")
    print("corrected_response:", rec.get("corrected_response") or "(none)")
    print("exclude_from_profile:", rec.get("exclude_from_profile", 0))


def cmd_edit(repo: HistoryRepo, one_based_index: int) -> None:
    out = _item_at_index(repo, one_based_index)
    if out is None:
        print(f"No history item at index {one_based_index}.", file=sys.stderr)
        sys.exit(1)
    rec, interaction_id = out
    current = (rec.get("corrected_response") or rec.get("llm_response") or "").strip()
    editor = os.environ.get("EDITOR", "vi")
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
        f.write(current)
        tmp_path = f.name
    try:
        subprocess.run([editor, tmp_path], check=True)
        with open(tmp_path, encoding="utf-8") as f:
            new_content = f.read().strip()
        repo.update_correction(interaction_id, new_content)
        print(f"Updated correction for interaction id={interaction_id}.")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "Usage: history_cmd.py clear | list | view <N> | edit <N>",
            file=sys.stderr,
        )
        sys.exit(1)
    subcommand = sys.argv[1].lower()
    db_path = _resolve_db_path()
    repo = _repo(db_path)

    if subcommand == "clear":
        cmd_clear(repo)
        return
    if subcommand == "list":
        cmd_list(repo)
        return
    if subcommand == "view":
        if len(sys.argv) < 3:
            print("Usage: history_cmd.py view <N>", file=sys.stderr)
            sys.exit(1)
        try:
            n = int(sys.argv[2])
        except ValueError:
            print("N must be an integer.", file=sys.stderr)
            sys.exit(1)
        cmd_view(repo, n)
        return
    if subcommand == "edit":
        if len(sys.argv) < 3:
            print("Usage: history_cmd.py edit <N>", file=sys.stderr)
            sys.exit(1)
        try:
            n = int(sys.argv[2])
        except ValueError:
            print("N must be an integer.", file=sys.stderr)
            sys.exit(1)
        cmd_edit(repo, n)
        return

    print(
        f"Unknown subcommand: {subcommand}. Use clear, list, view, or edit.",
        file=sys.stderr,
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
