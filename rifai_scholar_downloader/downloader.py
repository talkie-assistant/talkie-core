"""Orchestration: resumable manifest, jittered sleeps, download loop."""

import logging
import random
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests

from .citations import emit_bib, emit_ris
from .io_utils import (
    atomic_write,
    ensure_dir,
    load_manifest,
    safe_filename,
    save_manifest,
    sha256_file,
)
from .pdf_discovery import find_best_pdf_url
from .scholar_client import fetch_author_publications

logger = logging.getLogger(__name__)

STATUS_NOT_ATTEMPTED = "not_attempted"
STATUS_NO_URL = "no_url"
STATUS_PDF_FOUND = "pdf_found"
STATUS_DOWNLOADED = "downloaded"
STATUS_DOWNLOAD_FAILED = "download_failed"
STATUS_NO_PDF_FOUND = "no_pdf_found"
STATUS_BLOCKED = "blocked"

MANIFEST_VERSION = 1
MIN_PDF_SIZE = 100  # Reject files smaller than this (likely HTML error page)


def _item_key(pub: dict) -> str:
    """Stable key for a publication in the manifest (title + year)."""
    return f"{pub.get('title', '')}|{pub.get('year') or 'unknown'}"


def _find_existing_item(manifest: dict, pub: dict) -> dict | None:
    pub_year = str(pub.get("year") or "unknown").strip()
    pub_title = pub.get("title") or ""
    for it in manifest.get("items") or []:
        if (it.get("title") or "") == pub_title and str(it.get("year") or "unknown").strip() == pub_year:
            return it
    return None


def _sleep_jitter(sleep_min: float, sleep_max: float) -> None:
    if sleep_min <= sleep_max:
        time.sleep(random.uniform(sleep_min, sleep_max))
    else:
        time.sleep(random.uniform(sleep_max, sleep_min))


def run(
    user_id: str,
    outdir: Path,
    *,
    sleep_min: float = 0.3,
    sleep_max: float = 1.0,
    timeout: int = 45,
    max_pubs: int | None = None,
    resume: bool = True,
    create_zip: bool = True,
) -> None:
    """
    Main entry: fetch publications, download open PDFs, update manifest, write citations and ZIP.
    """
    outdir = Path(outdir)
    ensure_dir(outdir)
    manifest_path = outdir / "manifest.json"
    manifest = load_manifest(manifest_path) if resume else {"items": [], "version": MANIFEST_VERSION}
    items: list[dict] = manifest.setdefault("items", [])

    # 1) Enumerate publications
    try:
        pubs = fetch_author_publications(user_id, max_pubs=max_pubs)
    except Exception as e:
        logger.error("Failed to fetch author publications: %s", e)
        raise
    if not pubs:
        logger.warning("No publications returned for user %s", user_id)

    session = requests.Session()
    session.headers.setdefault(
        "User-Agent",
        "Mozilla/5.0 (compatible; ScholarPdfDiscovery/1.0)",
    )

    for idx, pub in enumerate(pubs):
        title = pub.get("title") or "Untitled"
        raw_year = pub.get("year")
        year = str(raw_year).strip() if raw_year is not None and str(raw_year).strip() else "unknown"
        year_dir = "unknown" if year == "unknown" or not year.isdigit() else year
        existing = _find_existing_item(manifest, pub) if resume else None

        if existing:
            status = existing.get("status", STATUS_NOT_ATTEMPTED)
            if status == STATUS_DOWNLOADED:
                rel_path = existing.get("rel_path")
                if rel_path:
                    full = outdir / rel_path
                    if full.is_file() and full.stat().st_size >= MIN_PDF_SIZE:
                        logger.debug("Skip (already downloaded): %s", title[:60])
                        continue
                # File missing or too small, retry
                existing["status"] = STATUS_NOT_ATTEMPTED
            elif status == STATUS_BLOCKED:
                logger.warning("Skipping previously blocked item: %s", title[:60])
                continue

        # Ensure we have an item in manifest
        item = existing or next(
            (i for i in items if (i.get("title") or "") == title and str(i.get("year") or "unknown").strip() == year),
            None,
        )
        if not item:
            item = {
                "title": title,
                "year": year,
                "status": STATUS_NOT_ATTEMPTED,
                "pdf_url": None,
                "rel_path": None,
                "sha256": None,
                "ts": None,
            }
            items.append(item)

        eprint_url = pub.get("eprint_url")
        pub_url = pub.get("pub_url")
        if not eprint_url and not pub_url:
            item["status"] = STATUS_NO_URL
            item["ts"] = datetime.now(timezone.utc).isoformat()
            save_manifest(manifest_path, manifest)
            logger.info("No URL: %s", title[:60])
            _sleep_jitter(sleep_min, sleep_max)
            continue

        # Find PDF URL
        try:
            pdf_url = find_best_pdf_url(
                eprint_url,
                pub_url,
                timeout=timeout,
                session=session,
            )
        except Exception as e:
            logger.debug("find_best_pdf_url failed for %s: %s", title[:40], e)
            pdf_url = None
        _sleep_jitter(sleep_min, sleep_max)

        if not pdf_url:
            item["status"] = STATUS_NO_PDF_FOUND
            item["ts"] = datetime.now(timezone.utc).isoformat()
            save_manifest(manifest_path, manifest)
            logger.info("No PDF found: %s", title[:60])
            continue

        item["pdf_url"] = pdf_url
        item["status"] = STATUS_PDF_FOUND

        # Download
        safe_name = safe_filename(title, year if year != "unknown" else None, ".pdf")
        rel_path = f"{year_dir}/{safe_name}"
        dest = outdir / rel_path
        ensure_dir(dest.parent)
        try:
            r = session.get(pdf_url, timeout=timeout, allow_redirects=True, stream=True)
            r.raise_for_status()
            data = b"".join(r.iter_content(chunk_size=65536))
            r.close()
            ct = r.headers.get("Content-Type", "")
            if not data.startswith(b"%PDF"):
                logger.warning("Response not PDF (magic): %s", title[:50])
                item["status"] = STATUS_DOWNLOAD_FAILED
                item["ts"] = datetime.now(timezone.utc).isoformat()
                save_manifest(manifest_path, manifest)
                continue
            if len(data) < MIN_PDF_SIZE:
                logger.warning("Download too small (likely HTML): %s", title[:50])
                item["status"] = STATUS_DOWNLOAD_FAILED
                item["ts"] = datetime.now(timezone.utc).isoformat()
                save_manifest(manifest_path, manifest)
                continue
            if not data.startswith(b"%PDF"):
                logger.warning("Download not PDF (magic): %s", title[:50])
                item["status"] = STATUS_DOWNLOAD_FAILED
                item["ts"] = datetime.now(timezone.utc).isoformat()
                save_manifest(manifest_path, manifest)
                continue
            atomic_write(dest, data)
            sh = sha256_file(dest)
            item["status"] = STATUS_DOWNLOADED
            item["rel_path"] = rel_path
            item["sha256"] = sh
            item["ts"] = datetime.now(timezone.utc).isoformat()
            save_manifest(manifest_path, manifest)
            logger.info("Downloaded: %s -> %s", title[:50], rel_path)
        except Exception as e:
            logger.warning("Download failed for %s: %s", title[:50], e)
            item["status"] = STATUS_DOWNLOAD_FAILED
            item["ts"] = datetime.now(timezone.utc).isoformat()
            save_manifest(manifest_path, manifest)

        _sleep_jitter(sleep_min, sleep_max)

    # Attach bib from pubs to items for citations
    for pub in pubs:
        pt = pub.get("title") or ""
        py = str(pub.get("year") or "unknown").strip()
        for it in items:
            if (it.get("title") or "") == pt and str(it.get("year") or "unknown").strip() == py:
                it["bib"] = pub.get("bib", {})
                break

    # Write citations.bib and citations.ris (all items with bib)
    try:
        bib_content = emit_bib(items)
        atomic_write(outdir / "citations.bib", bib_content.encode("utf-8"))
    except Exception as e:
        logger.warning("Could not write citations.bib: %s", e)
    try:
        ris_content = emit_ris(items)
        atomic_write(outdir / "citations.ris", ris_content.encode("utf-8"))
    except Exception as e:
        logger.warning("Could not write citations.ris: %s", e)

    if create_zip:
        zip_path = outdir.parent / f"{outdir.name}.zip"
        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in outdir.rglob("*"):
                    if f.is_file():
                        arcname = f.relative_to(outdir.parent)
                        zf.write(f, arcname)
            logger.info("Created %s", zip_path)
        except Exception as e:
            logger.warning("Could not create ZIP: %s", e)
