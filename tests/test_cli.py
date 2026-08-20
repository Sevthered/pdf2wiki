# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the CLI command bodies — argument wiring and the operator-facing report.

The step modules are unit-tested elsewhere; what was unproven is the layer the operator actually
uses. Two things are load-bearing here and neither is cosmetic:

- **dry-run really writes nothing.** Every mutating command is dry-run by default; if `--apply`
  stopped gating the write, the default invocation would silently rewrite a book.
- **the ⚠ lines fire.** Phase 5 leaves residue no automated check can judge (unverified PUA
  codepoints, words joined by a removed codepoint, a CRLF document it refused to touch). Those
  warnings are the ONLY signal a human ever gets; a report that prints clean while the residue is
  there is worse than no report.

Fixtures are real files — a real PDF, a real markdown — so the assertions land on real artifacts.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pdf2wiki.cli as cli
from pdf2wiki.phase5 import symbol_pua

PI = next(k for k, v in symbol_pua.GLYPHS.items() if v == "\N{GREEK SMALL LETTER PI}")
UNKNOWN_PUA = "\uf0ff"  # inside the PUA class, deliberately absent from the verified table


def _md(tmp_path, body):
    p = tmp_path / "book.md"
    p.write_text(body, encoding="utf-8")
    return str(p)


def _pdf(tmp_path, name="book.pdf", pages=12):
    import pymupdf

    doc = pymupdf.open()
    for i in range(pages):
        doc.new_page().insert_text((72, 100), f"Practical Widget Engineering page {i} body text.")
    p = tmp_path / name
    doc.save(str(p))
    return str(p)


BOOK = f"""Front matter.

# Chapter 1. Rotation

You rotate 2{PI} radians, or {UNKNOWN_PUA} of a turn.

# Chapter 2. Strings

A joined\x00word appears here.
"""


DOT = symbol_pua.DOT  # U+F0B7: a multiplication dot inline, a list bullet in some books
OTHER_UNKNOWN_PUA = "\uf0fe"  # a second unverified codepoint, for the second-pass residue test

REFUSED_MARKER_BOOK = f"""# Chapter 1. Notation

{symbol_pua.BULLETS[1]} = 2{PI}f is the angular frequency

Prose after.
"""

DEFERRED_DOT_BOOK = f"""# Chapter 1. Transports

{DOT} Chunked transfer encoding
{DOT} Server-sent events
"""

UNBLED_GLYPH_BOOK = f"""# Chapter 1. Rotation

Prose before.

```
Listing 1.1 A caption holding 2{PI} radians
```

Prose after.
"""

# `caption_unbleed` unwraps a caption-only fence, which promotes whatever was inside it into prose;
# the second `symbol_pua` pass is what sees the codepoint that the first one correctly skipped.
SECOND_PASS_BOOK = f"""# Chapter 1. Rotation

A turn of {UNKNOWN_PUA} radians.

```
Listing 1.1 A caption MinerU trapped in a fence, holding {OTHER_UNKNOWN_PUA}
```
"""


def test_phase5_apply_writes_chapters_and_reports_residue(tmp_path, capsys):
    md = _md(tmp_path, BOOK)

    rc = cli.main(["phase5", md, "--book", "widgets", "--source-name", "orig.pdf", "--apply"])

    out = capsys.readouterr().out
    assert rc == 0
    assert "APPLIED — wrote 3 chapter files" in out
    # the two residue warnings a human must act on
    assert "⚠ 1 removal(s) sat between two alphanumerics" in out
    assert "⚠ UNVERIFIED PUA codepoints left as-is" in out
    assert "phase5.symbol_pua" in out  # tells the reader what to do about it
    ch1 = (tmp_path / "chapters" / "01-chapter-1-rotation.md").read_text(encoding="utf-8")
    assert "2\N{GREEK SMALL LETTER PI} radians" in ch1  # the invisible glyph became the character
    assert UNKNOWN_PUA in ch1  # unverified ones are reported, never guessed
    ch2 = (tmp_path / "chapters" / "02-chapter-2-strings.md").read_text(encoding="utf-8")
    assert "\x00" not in ch2 and "joinedword" in ch2


def test_phase5_reports_a_marker_whose_reading_was_refused(tmp_path, capsys):
    """A list marker is verified at line START, and every marker slot is a Greek letter too.

    When the line reads as a formula rather than as list text, the step leaves the codepoint alone.
    Silence there would be the old defect in a new place: an invisible character in the output and
    nothing in the report.
    """
    md = _md(tmp_path, REFUSED_MARKER_BOOK)

    cli.main(["phase5", md, "--book", "widgets"])

    out = capsys.readouterr().out
    assert "⚠ 1 list marker(s) LEFT IN PLACE" in out
    assert "Greek letter in Symbol encoding" in out
    assert "Render the source page" in out
    assert "symbol_pua: 1 changes" in out  # the pi on that line IS still repaired


def test_phase5_reports_a_deferred_line_leading_dot(tmp_path, capsys):
    """The counter exists in the report; a counter no command prints reaches no human.

    `symbol_pua` refuses to read a line-opening U+F0B7 as either a dot or a bullet, because the
    reading is per-book. It counts the refusal, and `total_changes` deliberately excludes it -- so
    without this line a document made ONLY of such lines reports zero changes, zero unknown and
    zero warnings while every one of those codepoints is still in the output, invisible.
    """
    md = _md(tmp_path, DEFERRED_DOT_BOOK)

    rc = cli.main(["phase5", md, "--book", "widgets"])

    out = capsys.readouterr().out
    assert rc == 0
    # 2, not 4: the chain runs `symbol_pua` twice, and both passes see the same two untouched
    # lines. A refusal counted once per pass reports twice what the document holds.
    assert "⚠ 2 line-leading" in out
    assert "a multiplication dot inline and a list bullet in some books" in out
    assert "Render the source page" in out  # tells the reader what to do about it


def test_phase5_says_nothing_about_deferred_dots_when_there_are_none(tmp_path, capsys):
    cli.main(["phase5", _md(tmp_path, BOOK), "--book", "widgets"])

    assert "line-leading" not in capsys.readouterr().out


def test_phase5_reports_the_residue_the_written_document_still_holds(tmp_path, capsys):
    """The report comes from the SECOND `symbol_pua` pass, which read the text the chain writes.

    Both passes read the whole document, so adding them says a book has two of a codepoint it has
    once. Taking the first pass is wrong in the other direction: `caption_unbleed` runs between
    them, and a glyph it lifts out of a fence is repaired by the second pass.
    """
    md = _md(tmp_path, SECOND_PASS_BOOK)

    cli.main(["phase5", md, "--book", "widgets", "--out", str(tmp_path / "ch"), "--apply"])

    out = capsys.readouterr().out
    assert "⚠ UNVERIFIED PUA codepoints left as-is" in out
    assert "'f0ff': 1" in out and "'f0fe': 1" in out  # once each, and both of them
    # ...and the report matches what the chain actually wrote.
    written = "".join(f.read_text(encoding="utf-8") for f in sorted((tmp_path / "ch").glob("*.md")))
    assert written.count(UNKNOWN_PUA) == 1
    assert written.count(OTHER_UNKNOWN_PUA) == 1


def test_phase5_does_not_report_a_glyph_that_the_second_pass_repaired(tmp_path, capsys):
    """`in_code` shrinks across the passes, so it comes from the last one rather than a merge.

    The first pass correctly skips a glyph inside a fence and reports it as `in_code`. Then
    `caption_unbleed` unwraps that caption-only fence, the glyph lands in prose, and the second pass
    repairs it. Combining the two passes with `max` — right for `unknown`, which only grows — would
    tell the operator a glyph is still stuck in a code fence after it was fixed.
    """
    md = _md(tmp_path, UNBLED_GLYPH_BOOK)

    cli.main(["phase5", md, "--book", "widgets"])

    out = capsys.readouterr().out
    assert "caption_unbleed: 1 unwrapped" in out
    assert "left inside code fences" not in out  # it is not in a fence any more
    assert "symbol_pua: 1 changes" in out  # the second pass repaired it


def test_phase5_dry_run_writes_nothing(tmp_path, capsys):
    md = _md(tmp_path, BOOK)
    before = (tmp_path / "book.md").read_text(encoding="utf-8")

    rc = cli.main(["phase5", md, "--book", "widgets"])

    out = capsys.readouterr().out
    assert rc == 0
    assert "(dry-run — would write 3 chapter files; pass --apply)" in out
    assert not (tmp_path / "chapters").exists()
    assert (tmp_path / "book.md").read_text(encoding="utf-8") == before  # source untouched


def test_phase5_normalizes_a_crlf_book_instead_of_skipping_it(tmp_path, capsys):
    """A CRLF source is repaired, not refused — and `--apply` rewrites it with LF endings.

    `symbol_pua` carries a CRLF guard that returns `skipped_crlf` rather than risk mis-lexing
    fences. Through `run_chain` that guard never fires: the chain reads the markdown in universal-
    newline mode, so the step only ever sees LF, and the CLI's "SKIPPED — CRLF" branch is
    unreachable. Lexing is correct either way, so this pins the behaviour that actually ships:
    the glyph IS repaired, and the whole document's line endings change as a side effect.
    """
    md = _md(tmp_path, BOOK.replace("\n", "\r\n"))

    rc = cli.main(["phase5", md, "--book", "widgets", "--apply"])

    out = capsys.readouterr().out
    assert rc == 0
    assert "⚠ SKIPPED" not in out  # the guard is not reachable from here
    ch1 = (tmp_path / "chapters" / "01-chapter-1-rotation.md").read_bytes()
    assert "2\N{GREEK SMALL LETTER PI} radians".encode() in ch1  # repaired despite CRLF source
    assert b"\r\n" not in ch1


def test_phase5_lists_the_chapter_titles_it_found(tmp_path, capsys):
    md = _md(tmp_path, BOOK)

    cli.main(["phase5", md, "--book", "widgets"])

    out = capsys.readouterr().out
    assert "chapter_split: 2 boundaries" in out
    assert "1. Chapter 1. Rotation" in out and "2. Chapter 2. Strings" in out


def test_scan_prints_parseable_json(tmp_path, capsys):
    _pdf(tmp_path, "practical-widgets.pdf")

    rc = cli.main(["scan", str(tmp_path)])

    assert rc == 0
    records = json.loads(capsys.readouterr().out)  # stdout must stay machine-readable
    assert len(records) == 1 and records[0]["pages"] == 12
    assert records[0]["file"] == "practical-widgets.pdf"


def test_qa_sample_then_review_round_trip(tmp_path, capsys):
    pdf = _pdf(tmp_path, pages=40)
    qa_root = str(tmp_path / "qa")

    rc = cli.main(["qa", "sample", pdf, "widgets", "-n", "3", "--seed", "7", "--qa-root", qa_root])
    out = capsys.readouterr().out
    assert rc == 0
    assert "widgets: sampled 3 pages (seed 7)" in out
    qa_dir = os.path.join(qa_root, "widgets")
    assert len(os.listdir(os.path.join(qa_dir, "pages"))) == 3

    # review aligns converted blocks with the sampled pages; sample index, not original page
    blocks = tmp_path / "blocks.json"
    blocks.write_text(json.dumps([{"type": "text", "text": "hello", "abs_page": 0}]))
    rc = cli.main(["qa", "review", qa_dir, "widgets", "--blocks", str(blocks)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "pages with content: 1/3" in out
    assert "hello" in (tmp_path / "qa" / "widgets" / "review.txt").read_text(encoding="utf-8")


def test_qa_flags_ranks_books_and_details_a_single_one(tmp_path, capsys):
    def _blocks(path, flagged):
        entries = [{"type": "code", "code_body": "print(1)", "sub_type": "python", "abs_page": 3}]
        if flagged:
            entries[0]["_code_flag"] = True
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entries))
        return str(path)

    one = _blocks(tmp_path / "book-a" / "blocks.json", True)
    two = _blocks(tmp_path / "book-b" / "blocks.json", False)

    rc = cli.main(["qa", "flags", one])
    out = capsys.readouterr().out
    assert rc == 0
    assert "book-a" in out
    assert "p4" in out and "[python] diverged: print(1)" in out  # 1-based page for the reader

    rc = cli.main(["qa", "flags", two, one])  # multi-book: ranked table, no per-block detail
    out = capsys.readouterr().out
    assert rc == 0
    assert out.index("book-a") < out.index("book-b")  # most flagged first
    assert "print(1)" not in out


def test_convert_remote_checks_the_host_and_prints_the_remote_log(monkeypatch, capsys):
    # remote conversion streams nothing live — the fetched log is the operator's only view of it.
    import pdf2wiki.executor as executor_mod

    seen = {}

    class FakeSSH:
        def __init__(self, host, *a):
            seen["host"] = host

        def check(self):
            seen["checked"] = True

        def convert(self, pdf, name, out_root):
            seen["convert"] = (pdf, name, out_root)
            return True, "remote log tail"

    monkeypatch.setattr(executor_mod, "SSHExecutor", FakeSSH)

    rc = cli.main(["convert", "b.pdf", "--name", "slug", "--remote", "gpu-box", "--out", "~/o"])

    assert rc == 0
    assert seen["checked"] is True  # fail fast before starting a multi-hour conversion
    assert seen["host"] == "gpu-box" and seen["convert"] == ("b.pdf", "slug", "~/o")
    assert "remote log tail" in capsys.readouterr().out


def test_convert_remote_failure_exits_nonzero(monkeypatch):
    import pdf2wiki.executor as executor_mod

    class FakeSSH:
        def __init__(self, *a):
            pass

        def check(self):
            pass

        def convert(self, *a):
            return False, "EXIT=124"

    monkeypatch.setattr(executor_mod, "SSHExecutor", FakeSSH)

    assert cli.main(["convert", "b.pdf", "--name", "slug", "--remote", "gpu-box"]) == 1
