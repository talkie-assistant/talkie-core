"""Discover PDF links from a URL: HEAD/GET and parse HTML for PDF anchors, etc."""

import logging
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Content-Type that qualify as PDF
PDF_CONTENT_TYPES = ("application/pdf", "application/x-pdf")
# URL path ending that suggests PDF
PDF_PATH_RE = re.compile(r"\.pdf(\?.*)?$", re.I)
# Common link text/rel hints for PDF
PDF_LINK_HINTS = ("pdf", "full text", "fulltext", "download", "article pdf")


def is_pdf_content_type(content_type: str | None) -> bool:
    """Return True if content_type indicates PDF."""
    if not content_type:
        return False
    ct = content_type.split(";")[0].strip().lower()
    return any(ct == t for t in PDF_CONTENT_TYPES) or "pdf" in ct


def is_pdf_url(url: str) -> bool:
    """Return True if URL path looks like a PDF (after optional query)."""
    if not url or not url.strip():
        return False
    return bool(PDF_PATH_RE.search(urlparse(url).path or ""))


def head_pdf(url: str, timeout: int = 45, session: requests.Session | None = None) -> tuple[bool, str | None]:
    """
    HEAD request to check if URL returns PDF. Returns (ok, final_url).
    ok is True only if Content-Type is application/pdf or path ends with .pdf after redirects.
    """
    sess = session or requests.Session()
    try:
        r = sess.head(url, timeout=timeout, allow_redirects=True, stream=True)
        r.close()
        final = r.url
        ct = r.headers.get("Content-Type", "")
        if is_pdf_content_type(ct):
            return True, final
        if is_pdf_url(final):
            return True, final
        return False, final
    except requests.RequestException as e:
        logger.debug("HEAD %s failed: %s", url, e)
        return False, None


def get_pdf_url_from_page(
    landing_url: str,
    timeout: int = 45,
    session: requests.Session | None = None,
) -> list[str]:
    """
    Fetch landing page and collect candidate PDF URLs from:
    - a[href] ending in .pdf or with PDF-like rel/text
    - link[rel='alternate'][type='application/pdf']
    - iframe src ending in .pdf
    Returns list of absolute URLs (may need HEAD check afterward).
    """
    sess = session or requests.Session()
    try:
        r = sess.get(
            landing_url,
            timeout=timeout,
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; ScholarPdfDiscovery/1.0)"},
        )
        r.raise_for_status()
    except requests.RequestException as e:
        logger.debug("GET %s failed: %s", landing_url, e)
        return []

    base = r.url
    html = r.text
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[str] = []

    # link[rel="alternate"][type="application/pdf"]
    for link in soup.find_all("link", rel="alternate", type=re.compile(r"application/pdf", re.I)):
        href = link.get("href")
        if href:
            candidates.append(urljoin(base, href))

    # a[href] with .pdf or pdf-like text/rel
    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href or href.startswith("#") or href.startswith("javascript:"):
            continue
        text = (a.get_text() or "").strip().lower()
        rel = (a.get("rel") or [])
        if isinstance(rel, str):
            rel = [rel]
        rel_str = " ".join(r.lower() for r in rel)
        if is_pdf_url(href):
            candidates.append(urljoin(base, href))
            continue
        if any(h in text for h in PDF_LINK_HINTS) or "pdf" in rel_str:
            candidates.append(urljoin(base, href))

    # iframe src
    for iframe in soup.find_all("iframe", src=True):
        src = iframe.get("src", "").strip()
        if src and is_pdf_url(src):
            candidates.append(urljoin(base, src))

    # Dedupe preserving order
    seen = set()
    out = []
    for u in candidates:
        u = u.split("#")[0].rstrip("/")
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def find_best_pdf_url(
    eprint_url: str | None,
    pub_url: str | None,
    timeout: int = 45,
    session: requests.Session | None = None,
) -> str | None:
    """
    Prefer eprint_url if it is already a PDF; else pub_url if PDF; else discover from pub_url.
    Returns first URL that HEAD-confirms as PDF, or None.
    """
    sess = session or requests.Session()
    for url in (eprint_url, pub_url):
        if not url or not url.strip():
            continue
        url = url.strip()
        if is_pdf_url(url):
            ok, _ = head_pdf(url, timeout=timeout, session=sess)
            if ok:
                return url
        elif head_pdf(url, timeout=timeout, session=sess)[0]:
            return url

    # Discover from landing page (use first of eprint_url, pub_url that looks like landing)
    for url in (eprint_url, pub_url):
        if not url or not url.strip():
            continue
        for candidate in get_pdf_url_from_page(url, timeout=timeout, session=sess):
            ok, final = head_pdf(candidate, timeout=timeout, session=sess)
            if ok:
                return final
    return None
