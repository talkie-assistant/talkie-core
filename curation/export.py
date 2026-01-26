"""
Export interactions to JSONL for external fine-tuning (e.g. Ollama create, or Unsloth/LLaMA-Factory).
High-weight and corrected pairs are preferred for training data.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from llm.prompts import DEFAULT_EXPORT_INSTRUCTION
from persistence.database import get_connection, init_database
from persistence.history_repo import HistoryRepo

logger = logging.getLogger(__name__)

# Format expected by many instruction-tuning tools: instruction, input, output
def _row_to_instruction_json(
    original_transcription: str,
    llm_response: str,
    corrected_response: str | None,
    system_base: str,
) -> dict:
    """One record: instruction + input (optional) + output (prefer corrected)."""
    output = (corrected_response or llm_response or "").strip()
    return {
        "instruction": system_base,
        "input": (original_transcription or "").strip(),
        "output": output,
    }


def export_for_finetuning(
    db_path: str,
    out_path: str,
    *,
    limit: int = 5000,
    prefer_corrected: bool = True,
    min_weight: float | None = None,
    system_instruction: str | None = None,
) -> int:
    """
    Export interactions to a JSONL file for fine-tuning. Each line is a JSON object
    with instruction, input, output. Returns number of lines written.
    """
    init_database(db_path)
    connector = lambda: get_connection(db_path)
    repo = HistoryRepo(connector)
    rows = repo.list_for_curation(limit=limit)
    # Prefer higher weight and corrected; sort so best examples first
    def sort_key(r: dict) -> tuple:
        w = r.get("weight") or 0
        has_corr = 1 if (r.get("corrected_response") or "").strip() else 0
        return (-has_corr, -w, r.get("created_at") or "")

    rows.sort(key=sort_key)
    if min_weight is not None:
        rows = [r for r in rows if (r.get("weight") or 0) >= min_weight]
    system_base = system_instruction or DEFAULT_EXPORT_INSTRUCTION
    written = 0
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        for r in rows:
            out_text = (r.get("corrected_response") or r.get("llm_response") or "").strip()
            if not out_text:
                continue
            rec = _row_to_instruction_json(
                r.get("original_transcription") or "",
                r.get("llm_response") or "",
                r.get("corrected_response"),
                system_base,
            )
            if not rec["output"]:
                continue
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            written += 1
    logger.info("Exported %d records to %s", written, out_path)
    return written
