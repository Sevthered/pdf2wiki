# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""End-to-end tests for the Phase 5 chain runner (`run_chain`): dry-run reports every step and
writes nothing; apply=True rewrites the md and emits chapter files. All fixtures are synthetic."""

import os
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pdf2wiki.phase5 import run_chain

# Two H1 boundaries -> front matter + two chapters. An em-dash and an escaped char inside a code
# fence give the dash_normalize / code_unescape steps something to report on.
_MD = textwrap.dedent("""\
    ---
    title: Sample
    ---

    Intro prose before any chapter — with an em dash.

    # Chapter 1 Hello

    Some text.

    ```python
    print("a\\_b")
    ```

    # Chapter 2 World

    Closing text.
    """)


def _write(tmp_path):
    p = tmp_path / "book.md"
    p.write_text(_MD, encoding="utf-8")
    return str(p)


def test_run_chain_dry_run_reports_without_writing(tmp_path):
    md_path = _write(tmp_path)
    before = Path(md_path).read_text(encoding="utf-8")

    report = run_chain(md_path, book="Sample Book", apply=False)

    # every step reported
    for key in (
        "caption_unbleed",
        "lang_retag",
        "dash_normalize",
        "mermaid_repair",
        "code_unescape",
        "chapter_split",
    ):
        assert key in report
    assert report["applied"] is False
    # two H1 boundaries found; nothing written to disk
    assert report["chapter_split"]["boundaries"] == 2
    assert report["chapter_split"]["titles"] == ["Chapter 1 Hello", "Chapter 2 World"]
    assert Path(md_path).read_text(encoding="utf-8") == before  # source untouched
    assert not (tmp_path / "chapters").exists()  # dry-run wrote no chapter files


def test_run_chain_apply_writes_chapters(tmp_path):
    md_path = _write(tmp_path)
    out_dir = tmp_path / "chapters"

    report = run_chain(
        md_path,
        book="Sample Book",
        out_dir=str(out_dir),
        source_name="original.pdf",
        apply=True,
    )

    assert report["applied"] is True
    written = report["chapter_split"]["files"]
    assert len(written) == 3  # front matter + 2 chapters
    for path in written:
        assert os.path.exists(path)
    # frontmatter carries the source_name, not the staging md path
    front = Path(written[0]).read_text(encoding="utf-8")
    assert "original.pdf" in front


def test_run_chain_strips_nul_before_any_chapter_file_is_written(tmp_path):
    # The modern-cpp-tutorial p55 shape, end to end: a raw NUL that MinerU wrote INSIDE a code
    # fence must not survive into the staged chapter files, because a NUL makes a page binary and
    # therefore invisible to every grep-based vault lint (bug-converter-maps-uffff-to-nul).
    nul = chr(0x0000)
    md = textwrap.dedent(f"""\
        # Chapter 1 Templates

        Prose above the listing.

        ```cpp
        throw std::out_of_range("{nul}{nul}.");
        ```
        """)
    md_path = tmp_path / "book.md"
    md_path.write_text(md, encoding="utf-8")
    out_dir = tmp_path / "chapters"

    report = run_chain(str(md_path), book="Sample Book", out_dir=str(out_dir), apply=True)

    assert report["illegal_codepoints"]["removed"] == 2
    assert report["illegal_codepoints"]["counts"] == {"0000": 2}
    assert nul not in md_path.read_text(encoding="utf-8")
    written = report["chapter_split"]["files"]
    assert written
    for path in written:
        body = Path(path).read_text(encoding="utf-8")
        assert nul not in body
    assert 'throw std::out_of_range(".");' in Path(written[-1]).read_text(encoding="utf-8")


def test_run_chain_reports_illegal_codepoints_step(tmp_path):
    md_path = _write(tmp_path)
    report = run_chain(md_path, book="Sample Book", apply=False)
    assert report["illegal_codepoints"] == {"removed": 0, "counts": {}, "word_joins": 0}
