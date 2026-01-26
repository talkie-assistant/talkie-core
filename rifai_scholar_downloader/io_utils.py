"""Safe filenames, hashing, atomic writes, and directory creation."""

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path


# Characters unsafe in filenames on common filesystems
_UNSAFE_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
# Collapse runs of spaces/underscores/dashes and strip
_NORMALIZE_RE = re.compile(r"[\s_\-]+")
_MAX_FILENAME_LEN = 180
_HASH_LEN = 8


def safe_filename(base: str, year: str | None = None, suffix: str = "") -> str:
    """
    Produce a filesystem-safe base name from a title (and optional year).
    Collisions are avoided by appending a short hash of the original string.
    """
    if not base or not base.strip():
        base = "untitled"
    raw = f"{base} ({year})" if year else base
    raw = raw.strip()
    # Replace unsafe chars with space, then normalize
    safe = _UNSAFE_FILENAME_RE.sub(" ", raw)
    safe = _NORMALIZE_RE.sub(" ", safe).strip(" ._-")
    if not safe:
        safe = "untitled"
    # Truncate to leave room for " (hash).pdf"
    max_base = _MAX_FILENAME_LEN - _HASH_LEN - len(suffix) - 5  # " ().pdf" or similar
    if len(safe) > max_base:
        safe = safe[:max_base].rstrip(" ._-")
    # Append short hash to reduce collision chance
    h = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[: _HASH_LEN]
    return f"{safe} ({h}){suffix}"


def sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    """Write bytes to path atomically via a temp file in the same directory."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp.", suffix=path.suffix)
    try:
        os.write(fd, data)
        os.close(fd)
        os.replace(tmp, path)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def ensure_dir(path: Path) -> Path:
    """Create directory and parents if needed; return path."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_manifest(path: Path) -> dict:
    """Load manifest.json; return empty dict if missing or invalid."""
    path = Path(path)
    if not path.is_file():
        return {"items": [], "version": 1}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data.get("items"), list):
            data["items"] = []
        return data
    except (json.JSONDecodeError, OSError):
        return {"items": [], "version": 1}


def save_manifest(path: Path, manifest: dict) -> None:
    """Write manifest to path (atomic)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(manifest, indent=2, ensure_ascii=False)
    atomic_write(path, data.encode("utf-8"))
