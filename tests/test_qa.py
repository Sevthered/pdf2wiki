# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

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
    _make_pdf(pdf, 5)  # window 0..4 < default n=20
    r = sample_pages(pdf, "short", str(tmp_path / "qa"), n=20)
    assert 0 < len(r["pages"]) <= 4  # clamped to the window, no ValueError
    assert len(set(r["pages"])) == len(r["pages"])  # still distinct


def test_sample_single_page_book(tmp_path):
    pdf = str(tmp_path / "one.pdf")
    _make_pdf(pdf, 1)  # 5..95% window empty -> falls back to whole book
    r = sample_pages(pdf, "one", str(tmp_path / "qa"), n=20)
    assert r["pages"] == [0]


def test_sample_normal_book_unchanged(tmp_path):
    pdf = str(tmp_path / "big.pdf")
    _make_pdf(pdf, 100)  # window 5..95 holds 90 pages
    r = sample_pages(pdf, "big", str(tmp_path / "qa"), n=20)
    assert len(r["pages"]) == 20
    assert all(5 <= p < 95 for p in r["pages"])


# ---------- qa.flagged: per-book flagged-block report (T3) ----------
import json

import pdf2wiki.cli as cli
from pdf2wiki.qa.flagged import flagged_report


def _write_blocks(dirpath, specs):
    """specs: list of (type, flag) where flag in {None, '_code_flag', '_indent_flag'}."""
    os.makedirs(dirpath, exist_ok=True)
    blocks = []
    for i, (t, flag) in enumerate(specs):
        b = {"type": t, "abs_page": i, "sub_type": "python", "code_body": f"line_{i} = {i}\nmore"}
        if flag:
            b[flag] = True
        blocks.append(b)
    p = os.path.join(dirpath, "blocks.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(blocks, f)
    return p


def test_flagged_report_counts(tmp_path):
    p = _write_blocks(
        str(tmp_path / "mybook"),
        [
            ("code", None),
            ("code", "_code_flag"),
            ("code", "_indent_flag"),
            ("code", "_code_flag"),
            ("text", None),
        ],
    )
    r = flagged_report(p)
    assert r["name"] == "mybook"
    assert r["code_blocks"] == 4  # 4 code blocks, the text block ignored
    assert r["diverged"] == 2 and r["indent_suspect"] == 1 and r["flagged"] == 3
    assert [e["flag"] for e in r["blocks"]] == ["diverged", "indent", "diverged"]  # page-sorted
    assert r["blocks"][0]["page"] == 2 and r["blocks"][0]["lang"] == "python"  # abs_page 1 -> pg 2
    assert r["blocks"][0]["snippet"].startswith("line_1")


def test_flagged_report_empty(tmp_path):
    p = _write_blocks(str(tmp_path / "clean"), [("code", None), ("code", None), ("text", None)])
    r = flagged_report(p)
    assert r["flagged"] == 0 and r["blocks"] == [] and r["code_blocks"] == 2


def test_cmd_qa_flags_ranks_books(tmp_path, capsys):
    a = _write_blocks(str(tmp_path / "alpha"), [("code", "_code_flag"), ("code", None)])  # 1 flag
    b = _write_blocks(
        str(tmp_path / "beta"),
        [("code", "_code_flag"), ("code", "_code_flag"), ("code", "_indent_flag")],
    )  # 3 flags
    assert cli.main(["qa", "flags", a, b]) == 0
    out = capsys.readouterr().out
    assert out.index("beta") < out.index("alpha")  # most-flagged book ranked first


# ---------- qa.review: per-sample-page rendered review (build_review) ----------
from pdf2wiki.qa.review import build_review


def test_build_review_renders_by_sample_page(tmp_path):
    qa = tmp_path / "qa"
    sampledir = qa / "out" / "bk_sample"
    os.makedirs(sampledir)
    blocks = [
        {"type": "text", "abs_page": 0, "text_level": 1, "text": "Title"},
        {"type": "code", "abs_page": 0, "sub_type": "py", "code_body": "x = 1"},
        {"type": "text", "abs_page": 1, "text": "Body"},
    ]
    with open(sampledir / "blocks.json", "w", encoding="utf-8") as f:
        json.dump(blocks, f)
    with open(qa / "mapping.json", "w", encoding="utf-8") as f:
        json.dump([{"sample_idx": 0, "orig_page": 12}, {"sample_idx": 1, "orig_page": 40}], f)

    r = build_review(str(qa), "bk")
    assert r["pages_with_content"] == 2 and r["sampled"] == 2
    with open(r["review"], encoding="utf-8") as f:
        txt = f.read()
    assert "original page 12" in txt and "original page 40" in txt
    assert "# Title" in txt and "```py\nx = 1\n```" in txt and "Body" in txt
