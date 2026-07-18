"""Tests for qa.sample page-window math on short books (no GPU/MinerU needed).

Regression: `random.sample(range(lo, hi), n)` raised `ValueError: Sample larger than
population` on any book whose 5..95% window was smaller than the requested sample size.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pymupdf  # runtime dependency

from pdf2wiki.qa.sample import sample_pages


def _make_pdf(path, pages):
    d = pymupdf.open()
    for _ in range(pages):
        d.new_page(width=200, height=200)
    d.save(path)
    d.close()


def test_sample_short_book_clamps_instead_of_crashing(tmp_path):
    pdf = str(tmp_path / "short.pdf")
    _make_pdf(pdf, 5)                                   # window 0..4 < default n=20
    r = sample_pages(pdf, "short", str(tmp_path / "qa"), n=20)
    assert 0 < len(r["pages"]) <= 4                     # clamped to the window, no ValueError
    assert len(set(r["pages"])) == len(r["pages"])      # still distinct


def test_sample_single_page_book(tmp_path):
    pdf = str(tmp_path / "one.pdf")
    _make_pdf(pdf, 1)                                   # 5..95% window empty -> falls back to whole book
    r = sample_pages(pdf, "one", str(tmp_path / "qa"), n=20)
    assert r["pages"] == [0]


def test_sample_normal_book_unchanged(tmp_path):
    pdf = str(tmp_path / "big.pdf")
    _make_pdf(pdf, 100)                                 # window 5..95 holds 90 pages
    r = sample_pages(pdf, "big", str(tmp_path / "qa"), n=20)
    assert len(r["pages"]) == 20
    assert all(5 <= p < 95 for p in r["pages"])
