# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Wiring tests for `convert_book` — the orchestration entry point no unit test covered.

Every MinerU subprocess is faked, but the **PDF is real**, so the coverage gate is exercised
against an actual text layer rather than a stub that agrees with it. What these prove:

- the gate hard-stops and writes NOTHING rather than leaving a short book on disk;
- a genuinely blank page is not mistaken for a dropped one;
- a failed pass is reported as `(False, log)`, never raised into the batch loop;
- `hybrid_server_url` actually changes the backend argv, and an offloaded failure never
  silently falls back to the local GPU (the whole point of the offload guard);
- the detected watermark is scrubbed from the markdown that is written, not just from blocks.
"""

import json
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pdf2wiki.convert.merge as merge_mod
from pdf2wiki.config import Config
from pdf2wiki.convert.merge import PassFailed, convert_book


def _pdf(tmp_path, pages=3, blank=()):
    """A real PDF: every page carries >50 chars of text unless listed in `blank`."""
    import pymupdf

    doc = pymupdf.open()
    for i in range(pages):
        pg = doc.new_page()
        if i not in blank:
            pg.insert_text((72, 100), f"Page {i} body text with enough characters to count. " * 2)
    p = tmp_path / "book.pdf"
    doc.save(str(p))
    return str(p)


def _cfg(tmp_path, **mineru):
    cfg = Config()
    cfg.mineru.binary = "/bin/true"  # skip PATH discovery; no subprocess is ever run
    cfg.convert.workdir = str(tmp_path / "run")
    for k, v in mineru.items():
        setattr(cfg.mineru, k, v)
    return cfg


def _blk(page, kind="text", **kw):
    b = {
        "type": kind,
        "abs_page": page,
        "page_idx": page,
        "text": f"body text on page {page}",
        "bbox": [0.0, 0.0, 100.0, 100.0],
    }
    b.update(kw)
    return b


def _fake_passes(monkeypatch, base, mineru=None):
    """Patch both MinerU entry points. Returns the list that records every hybrid call."""
    calls = []

    def fake_chunks(mineru_bin, pdf, start, end, work, clean_cwd, env, seg=40, timeout=None):
        calls.append({"pass": "pipeline", "start": start, "end": end, "timeout": timeout})
        return list(base), None

    def fake_mineru(
        mineru_bin, pdf, a, b, backend, extra, outdir, clean_cwd, env, label="", timeout=None
    ):
        calls.append({"pass": "hybrid", "a": a, "b": b, "backend": backend, "extra": list(extra)})
        if mineru is not None:
            return mineru(a, b)
        return [], ""

    monkeypatch.setattr(merge_mod, "run_pipeline_chunks", fake_chunks)
    monkeypatch.setattr(merge_mod, "run_mineru", fake_mineru)
    return calls


def test_convert_book_writes_markdown_and_blocks(tmp_path, monkeypatch):
    pdf = _pdf(tmp_path, pages=3)
    base = [_blk(0), _blk(1, "table", table_body="<table></table>"), _blk(2)]
    calls = _fake_passes(monkeypatch, base)

    ok, log = convert_book(pdf, "slug", str(tmp_path / "out"), cfg=_cfg(tmp_path))

    assert ok is True
    work = tmp_path / "out" / "slug"
    md = (work / "slug.md").read_text(encoding="utf-8")
    assert "body text on page 0" in md and "body text on page 2" in md
    assert len(json.loads((work / "blocks.json").read_text(encoding="utf-8"))) == 3
    assert "coverage: 3/3 pages produced blocks; text-bearing gaps=0" in log
    # the table page is `rich`, so exactly one hybrid run covers it and nothing else
    hybrid = [c for c in calls if c["pass"] == "hybrid"]
    assert len(hybrid) == 1 and (hybrid[0]["a"], hybrid[0]["b"]) == (1, 1)
    assert hybrid[0]["backend"] == "hybrid-engine"


def test_coverage_gap_hard_stops_and_writes_nothing(tmp_path, monkeypatch):
    # a page with real text that produced no blocks was silently dropped by the scrape. Failing
    # here is the point: a short book written to disk looks complete to every downstream step.
    pdf = _pdf(tmp_path, pages=3)
    _fake_passes(monkeypatch, [_blk(0), _blk(2)])

    ok, log = convert_book(pdf, "slug", str(tmp_path / "out"), cfg=_cfg(tmp_path))

    assert ok is False
    assert "FAILED coverage" in log and "[1]" in log  # names the dropped page
    assert not (tmp_path / "out" / "slug" / "slug.md").exists()


def test_blank_page_is_not_a_coverage_gap(tmp_path, monkeypatch):
    # the mirror of the test above: a genuinely empty page produces no blocks and must not fail
    # the book, or every PDF with a section-break page becomes unconvertible.
    pdf = _pdf(tmp_path, pages=3, blank=(1,))
    _fake_passes(monkeypatch, [_blk(0), _blk(2)])

    ok, log = convert_book(pdf, "slug", str(tmp_path / "out"), cfg=_cfg(tmp_path))

    assert ok is True
    assert "text-bearing gaps=0" in log


def test_page_range_is_passed_through(tmp_path, monkeypatch):
    pdf = _pdf(tmp_path, pages=5)
    calls = _fake_passes(monkeypatch, [_blk(1), _blk(2)])

    ok, log = convert_book(
        pdf, "slug", str(tmp_path / "out"), start=1, end=2, timeout=99, cfg=_cfg(tmp_path)
    )

    assert ok is True
    p = calls[0]
    assert (p["start"], p["end"], p["timeout"]) == (1, 2, 99)
    assert "pages 1-2 (2)" in log  # pages outside the range are neither converted nor counted


def test_hybrid_offload_switches_backend_and_keeps_effort(tmp_path, monkeypatch):
    # offloading moves only the VLM inference; --effort (image analysis / Mermaid) must survive,
    # or the offloaded pass quietly stops transcribing diagrams.
    pdf = _pdf(tmp_path, pages=2)
    calls = _fake_passes(monkeypatch, [_blk(0), _blk(1, "chart")])
    cfg = _cfg(tmp_path, hybrid_server_url="http://box:8000/v1")

    ok, log = convert_book(pdf, "slug", str(tmp_path / "out"), cfg=cfg)

    assert ok is True
    hy = next(c for c in calls if c["pass"] == "hybrid")
    assert hy["backend"] == "hybrid-http-client"
    assert "-u" in hy["extra"] and "http://box:8000/v1" in hy["extra"]
    assert hy["extra"][hy["extra"].index("--effort") + 1] == "high"
    assert "offloaded to remote MinerU server: http://box:8000/v1" in log


def test_offloaded_hybrid_failure_never_falls_back_to_local(tmp_path, monkeypatch):
    # falling back would assume the GPU we just offloaded away, or drop to pipeline-only and lose
    # tables/diagrams — either way the book looks converted and is quietly worse.
    pdf = _pdf(tmp_path, pages=2)

    def boom(a, b):
        raise PassFailed(f"hybrid {a}-{b} exited 1")

    calls = _fake_passes(monkeypatch, [_blk(0), _blk(1, "table")], mineru=boom)
    cfg = _cfg(tmp_path, hybrid_server_url="http://box:8000/v1")

    ok, log = convert_book(pdf, "slug", str(tmp_path / "out"), cfg=cfg)

    assert ok is False
    assert "Not falling back" in log and "http://box:8000/v1" in log
    assert len([c for c in calls if c["pass"] == "hybrid"]) == 1  # no second, local, attempt
    assert not (tmp_path / "out" / "slug" / "slug.md").exists()


def test_local_hybrid_failure_is_reported_not_raised(tmp_path, monkeypatch):
    # run_batch relies on this: a raised PassFailed here would abort the whole batch.
    pdf = _pdf(tmp_path, pages=2)

    def boom(a, b):
        raise PassFailed("mineru exited 1; see hy_1_1.log")

    _fake_passes(monkeypatch, [_blk(0), _blk(1, "table")], mineru=boom)

    ok, log = convert_book(pdf, "slug", str(tmp_path / "out"), cfg=_cfg(tmp_path))

    assert ok is False
    assert "FAILED: mineru exited 1" in log
    assert "Not falling back" not in log  # that guard belongs to the offloaded path only


def test_missing_mineru_binary_is_reported_not_raised(tmp_path, monkeypatch):
    pdf = _pdf(tmp_path, pages=1)
    _fake_passes(monkeypatch, [_blk(0)])
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    cfg = _cfg(tmp_path)
    cfg.mineru.binary = ""  # force PATH discovery, which now finds nothing

    ok, log = convert_book(pdf, "slug", str(tmp_path / "out"), cfg=cfg)

    assert ok is False
    assert "mineru CLI not found on PATH" in log


def test_watermark_is_scrubbed_from_the_written_markdown(tmp_path, monkeypatch):
    # a DRM footer merged into a caption survives block-level removal — the scrub has to run
    # against the rendered markdown too, which is only observable through the written file.
    wm = "Licensed to Reader <reader@example.com>"
    pdf = _pdf(tmp_path, pages=5)
    base = []
    for p in range(5):
        base.append(_blk(p))
        base.append(_blk(p, text=wm))
    _fake_passes(monkeypatch, base)

    ok, log = convert_book(pdf, "slug", str(tmp_path / "out"), cfg=_cfg(tmp_path))

    assert ok is True
    assert "watermark(s) auto-detected" in log
    assert wm not in (tmp_path / "out" / "slug" / "slug.md").read_text(encoding="utf-8")
