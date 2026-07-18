"""scan_one resilience: a page-level error must yield {file, error}, not abort the dir scan.

Regression: only pymupdf.open was inside the try; d.page_count / d[i].get_text() ran outside it,
so a corrupt page raised out of scan_one and (via scan_dir's bare comprehension) killed scanning
of every remaining PDF.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pymupdf

import pdf2wiki.scan as scan


def test_scan_one_page_error_is_captured(monkeypatch):
    class BadDoc:
        page_count = 3

        def __getitem__(self, i):
            raise ValueError("bad page stream")   # was raised OUTSIDE the try before the fix

    monkeypatch.setattr(pymupdf, "open", lambda p: BadDoc())
    r = scan.scan_one("book.pdf")
    assert r["file"] == "book.pdf"
    assert "bad page stream" in r["error"]
    assert "pages" not in r                        # no partial record


def test_scan_one_open_error_still_captured(monkeypatch):
    def boom(p):
        raise RuntimeError("cannot open")

    monkeypatch.setattr(pymupdf, "open", boom)
    r = scan.scan_one("x.pdf")
    assert r == {"file": "x.pdf", "error": "cannot open"}
