# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

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
            raise ValueError("bad page stream")  # was raised OUTSIDE the try before the fix

    monkeypatch.setattr(pymupdf, "open", lambda p: BadDoc())
    r = scan.scan_one("book.pdf")
    assert r["file"] == "book.pdf"
    assert "bad page stream" in r["error"]
    assert "pages" not in r  # no partial record


def test_scan_one_open_error_still_captured(monkeypatch):
    def boom(p):
        raise RuntimeError("cannot open")

    monkeypatch.setattr(pymupdf, "open", boom)
    r = scan.scan_one("x.pdf")
    assert r == {"file": "x.pdf", "error": "cannot open"}


# ---------- guess_title ----------


def test_guess_title_from_text_skips_non_title_lines():
    # first two lines pass the length filter but have a <=0.6 letter ratio (digits/punctuation)
    # and must be skipped; the real title line is returned with source "text".
    pages = ["1234567890-\n+++ +++ +++ +++\nClean Architecture in Python"]
    title, conf = scan.guess_title(pages, "whatever.pdf")
    assert title == "Clean Architecture in Python"
    assert conf == "text"


def test_guess_title_rejects_boilerplate_and_falls_back_to_filename():
    # every candidate line is boilerplate (copyright / isbn) -> filename fallback, ISBN stripped.
    pages = ["Copyright 2020 Some Press\nISBN 978-0-000-00000-0"]
    title, conf = scan.guess_title(pages, "/books/9781234567890-my_great-book.pdf")
    assert title == "my great book"
    assert conf == "filename-fallback"


# ---------- guess_year ----------


def test_guess_year_prefers_latest_copyright_line():
    pages = ["Copyright © 2019 First\nReprint Copyright 2021"]
    year, conf = scan.guess_year(pages)
    assert year == 2021
    assert conf == "copyright-line"


def test_guess_year_loose_fallback_when_no_copyright():
    pages = ["Published in 2018 by Nobody"]
    year, conf = scan.guess_year(pages)
    assert year == 2018
    assert conf == "loose-year"


def test_guess_year_none_found():
    year, conf = scan.guess_year(["no dates here", "nor here"])
    assert year is None
    assert conf == "none-found"


# ---------- scan_one / scan_dir success paths ----------


class _Page:
    def __init__(self, text):
        self._text = text

    def get_text(self):
        return self._text


class _GoodDoc:
    page_count = 2

    def __init__(self):
        self._pages = [
            _Page("My Book Title\nCopyright 2020 Some Press"),
            _Page("body text"),
        ]

    def __getitem__(self, i):
        return self._pages[i]


def test_scan_one_success_record(monkeypatch):
    monkeypatch.setattr(pymupdf, "open", lambda p: _GoodDoc())
    r = scan.scan_one("/books/My Book Title.pdf")
    assert r["file"] == "My Book Title.pdf"
    assert r["pages"] == 2
    assert r["title"] == "My Book Title"
    assert r["title_conf"] == "text"
    assert r["year"] == 2020
    assert r["year_conf"] == "copyright-line"
    assert "error" not in r


def test_scan_dir_sorted_records(monkeypatch, tmp_path):
    (tmp_path / "b.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "a.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "notes.txt").write_text("ignored")  # non-pdf must be skipped
    monkeypatch.setattr(pymupdf, "open", lambda p: _GoodDoc())
    records = scan.scan_dir(str(tmp_path))
    assert [r["file"] for r in records] == ["a.pdf", "b.pdf"]  # glob sorted, .txt excluded
    assert all(r["pages"] == 2 for r in records)
