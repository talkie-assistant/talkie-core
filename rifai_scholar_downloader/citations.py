"""Emit .bib and .ris from list of bib dicts (best-effort from Scholar)."""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Chars that need escaping in BibTeX values
_BIBTEX_SPECIAL = re.compile(r"([{}\\\"#])")


def _bibtex_escape(s: str) -> str:
    if not s:
        return "{}"
    return "{" + _BIBTEX_SPECIAL.sub(r"\\\1", s) + "}"


def _sanitize_key(s: str) -> str:
    """Produce a safe citation key (alphanumeric and maybe dash)."""
    s = re.sub(r"[^\w\-]", "", s)
    return s[:64] or "key"


def bib_entry(index: int, bib: dict, title: str) -> str:
    """Format a single BibTeX entry (article)."""
    key = _sanitize_key(f"rifai{index}_{(bib.get('year') or 'nodate')}")
    lines = [f"@article{{{key},"]
    for field, value in (
        ("title", bib.get("title") or title),
        ("author", bib.get("author")),
        ("year", bib.get("year")),
        ("journal", bib.get("journal") or bib.get("venue")),
        ("volume", bib.get("volume")),
        ("number", bib.get("number")),
        ("pages", bib.get("pages")),
        ("publisher", bib.get("publisher")),
        ("abstract", bib.get("abstract")),
    ):
        if value is not None and str(value).strip():
            lines.append(f"  {field} = {_bibtex_escape(str(value).strip())},")
    # Remove trailing comma from last field (BibTeX allows it but some parsers complain)
    if lines[-1].endswith(","):
        lines[-1] = lines[-1][:-1]
    lines.append("}")
    return "\n".join(lines)


def emit_bib(items: list[dict]) -> str:
    """Build citations.bib from list of item dicts (each with 'bib' and 'title')."""
    out = []
    for i, item in enumerate(items):
        bib = item.get("bib") or {}
        title = item.get("title") or bib.get("title") or "Untitled"
        out.append(bib_entry(i + 1, bib, title))
        out.append("")
    return "\n".join(out).strip()


def ris_entry(index: int, bib: dict, title: str) -> str:
    """Format a single RIS line block (TY JOUR ... ER)."""
    fields = [
        ("TY", "JOUR"),
        ("TI", bib.get("title") or title),
        ("AU", bib.get("author") or ""),
        ("PY", bib.get("year") or ""),
        ("JO", bib.get("journal") or bib.get("venue") or ""),
        ("VL", bib.get("volume") or ""),
        ("IS", bib.get("number") or ""),
        ("SP", bib.get("pages") or ""),
        ("PB", bib.get("publisher") or ""),
        ("AB", bib.get("abstract") or ""),
    ]
    lines = []
    for tag, value in fields:
        if value is None:
            value = ""
        value = str(value).strip()
        if not value and tag in ("JO", "PB", "AB", "VL", "IS", "SP"):
            continue
        # RIS: newlines in value become newline + tag for continuation
        for part in value.replace("\r\n", "\n").split("\n"):
            lines.append(f"{tag}  - {part}")
    lines.append("ER  - ")
    return "\n".join(lines)


def emit_ris(items: list[dict]) -> str:
    """Build citations.ris from list of item dicts."""
    out = []
    for i, item in enumerate(items):
        bib = item.get("bib") or {}
        title = item.get("title") or bib.get("title") or "Untitled"
        out.append(ris_entry(i + 1, bib, title))
    return "\n".join(out)
