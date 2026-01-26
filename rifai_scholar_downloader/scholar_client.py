"""Fetch author and publications via scholarly; return normalized metadata dicts."""

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# Lazy import to avoid hard dependency at import time
_scholarly = None


def _get_scholarly():
    global _scholarly
    if _scholarly is None:
        try:
            from scholarly import scholarly as _scholarly  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "scholarly is required. Install with: pip install -r requirements.txt"
            ) from e
    return _scholarly


def _get_attr(obj: Any, key: str, default: Any = None) -> Any:
    """Get key from dict-like or attribute-based object."""
    if obj is None:
        return default
    if hasattr(obj, "get") and callable(getattr(obj, "get")):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _bib_get(bib: Any, key: str, default: str = "") -> str:
    """Extract string from bib dict/object."""
    v = _get_attr(bib, key, default)
    if v is None:
        return default
    if isinstance(v, list):
        return " and ".join(str(x) for x in v) if v else default
    return str(v).strip()


def fetch_author_publications(
    user_id: str,
    *,
    max_pubs: int | None = None,
    sortby: str = "citedby",
    sleep_after_fill: float = 0.5,
) -> list[dict]:
    """
    Fetch author by Google Scholar user id and return list of normalized
    publication dicts. Each dict has: title, year, bib (dict), eprint_url, pub_url,
    author_pub_id (if any). Fills each publication to get eprint_url/pub_url.
    """
    schol = _get_scholarly()
    try:
        author = schol.search_author_id(
            user_id,
            filled=False,
            sortby=sortby,
            publication_limit=0,
        )
    except Exception as e:
        logger.exception("search_author_id failed for %s", user_id)
        _raise_blocked_or_rerais(e)

    if author is None:
        raise ValueError(f"Author not found for user id: {user_id}")

    # Fill author with publications (optionally limited)
    fill_limit = max_pubs if max_pubs is not None and max_pubs > 0 else 0
    try:
        author = schol.fill(
            author,
            sections=["publications"],
            sortby=sortby,
            publication_limit=fill_limit,
        )
    except Exception as e:
        logger.exception("fill(author) failed for %s", user_id)
        _raise_blocked_or_rerais(e)

    publications = _get_attr(author, "publications") or []
    out = []
    for i, pub in enumerate(publications):
        if max_pubs is not None and len(out) >= max_pubs:
            break
        # Fill each publication to get eprint_url and pub_url (detail view)
        try:
            pub = schol.fill(pub)
        except Exception as e:
            logger.debug("fill(pub) failed for pub %s: %s", i, e)
            # Still normalize with whatever we have
        if sleep_after_fill > 0:
            time.sleep(sleep_after_fill)
        norm = _normalize_publication(pub, schol)
        if norm:
            out.append(norm)
    return out


def _normalize_publication(pub: Any, schol: Any) -> dict | None:
    """Turn a scholarly Publication into a flat dict with bib, urls, etc."""
    bib = _get_attr(pub, "bib")
    title = _bib_get(bib, "title") or _bib_get(bib, "citation")
    if not title:
        return None

    year = _bib_get(bib, "pub_year")
    author_list = _get_attr(bib, "author")
    if isinstance(author_list, list):
        authors_str = " and ".join(str(a) for a in author_list)
    else:
        authors_str = str(author_list or "")

    eprint_url = _get_attr(pub, "eprint_url") or ""
    pub_url = _get_attr(pub, "pub_url") or ""
    if eprint_url and isinstance(eprint_url, str):
        eprint_url = eprint_url.strip()
    if pub_url and isinstance(pub_url, str):
        pub_url = pub_url.strip()

    # Build bib dict for citations (best-effort from Scholar)
    bib_dict = {
        "title": title,
        "author": authors_str,
        "year": year or "",
        "journal": _bib_get(bib, "journal"),
        "venue": _bib_get(bib, "venue"),
        "volume": _bib_get(bib, "volume"),
        "number": _bib_get(bib, "number"),
        "pages": _bib_get(bib, "pages"),
        "publisher": _bib_get(bib, "publisher"),
        "abstract": _bib_get(bib, "abstract"),
    }

    return {
        "title": title,
        "year": year or None,
        "bib": bib_dict,
        "eprint_url": eprint_url or None,
        "pub_url": pub_url or None,
        "author_pub_id": _get_attr(pub, "author_pub_id"),
        "pub_object": pub,  # Keep for bibtex() if needed
    }


def _raise_blocked_or_rerais(e: Exception) -> None:
    """If response looks like rate limit/CAPTCHA, raise a clear error."""
    msg = str(e).lower()
    if "captcha" in msg or "blocked" in msg or "rate" in msg or "429" in msg:
        raise RuntimeError(
            "Google Scholar may have rate-limited or shown a CAPTCHA. "
            "Please retry later from the same network. Do not attempt to bypass CAPTCHA."
        ) from e
    raise
