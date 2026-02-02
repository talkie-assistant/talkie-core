"""Unit tests for rifai_scholar_downloader helpers. Not critical; skipped if bs4 is not installed."""

import pytest

pytest.importorskip("bs4")

# Test io_utils
from rifai_scholar_downloader.io_utils import (
    load_manifest,
    safe_filename,
    save_manifest,
    sha256_file,
    atomic_write,
)
from rifai_scholar_downloader.pdf_discovery import (
    is_pdf_content_type,
    is_pdf_url,
)


class TestSafeFilename:
    def test_basic(self):
        assert "abc" in safe_filename("abc", year="2020")
        assert "2020" in safe_filename("abc", year="2020")
        assert safe_filename("abc", year="2020").endswith(".pdf") is False

    def test_unsafe_chars_removed(self):
        out = safe_filename('a/b*c: "x"', year="1999")
        assert "/" not in out and ":" not in out and '"' not in out
        assert "1999" in out

    def test_empty_title_has_fallback(self):
        out = safe_filename("", year="2000")
        assert "untitled" in out.lower() or "2000" in out
        assert out

    def test_deterministic_hash_same_input(self):
        a = safe_filename("Same Title", year="2021", suffix=".pdf")
        b = safe_filename("Same Title", year="2021", suffix=".pdf")
        assert a == b

    def test_different_titles_differ(self):
        a = safe_filename("Title A", year="2020", suffix=".pdf")
        b = safe_filename("Title B", year="2020", suffix=".pdf")
        assert a != b
        assert a.endswith(".pdf") and b.endswith(".pdf")


class TestPdfDiscovery:
    def test_is_pdf_content_type(self):
        assert is_pdf_content_type("application/pdf") is True
        assert is_pdf_content_type("application/pdf; charset=binary") is True
        assert is_pdf_content_type("application/x-pdf") is True
        assert is_pdf_content_type("text/html") is False
        assert is_pdf_content_type(None) is False

    def test_is_pdf_url(self):
        assert is_pdf_url("https://example.com/paper.pdf") is True
        assert is_pdf_url("https://example.com/paper.PDF?q=1") is True
        assert is_pdf_url("https://example.com/page") is False
        assert is_pdf_url("") is False


class TestManifest:
    def test_load_missing_returns_empty(self, tmp_path):
        m = load_manifest(tmp_path / "nonexistent.json")
        assert m.get("items") == []
        assert "version" in m

    def test_save_and_load_roundtrip(self, tmp_path):
        path = tmp_path / "manifest.json"
        manifest = {"version": 1, "items": [{"title": "A", "status": "downloaded"}]}
        save_manifest(path, manifest)
        loaded = load_manifest(path)
        assert loaded["items"] == manifest["items"]
        assert loaded["version"] == 1


class TestSha256File:
    def test_known_content(self, tmp_path):
        f = tmp_path / "f.bin"
        f.write_bytes(b"hello")
        assert (
            sha256_file(f)
            == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
        )


class TestAtomicWrite:
    def test_writes_content(self, tmp_path):
        p = tmp_path / "out.pdf"
        atomic_write(p, b"%PDF-1.4 fake")
        assert p.read_bytes() == b"%PDF-1.4 fake"
