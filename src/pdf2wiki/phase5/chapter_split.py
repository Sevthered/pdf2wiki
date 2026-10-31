# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Split a converted book .md into per-chapter files + inject YAML frontmatter.

Boundaries = fence-aware H1 lines (`# ...`), PLUS an H2 `## Appendix X. ...` line when the
converter mistagged an appendix heading one level down (a real source heading-level inconsistency
seen in the wild, not a converter bug). Fence-aware: a `# file: x.py` code COMMENT inside a fenced
code block must never be read as a chapter boundary.

Image paths are left untouched — MinerU emits `images/<hash>.ext` relative refs; every chapter
file is written into the SAME output directory as the shared `images/` folder, so the relative
path still resolves. No rewrite needed.

Everything before the first boundary becomes `00-front-matter.md` (title page, ToC, preface).
Frontmatter always has title, book, chapter, source and tags. When the caller passes book metadata
(see `pdf2wiki.bookmeta`), it also has book_title, authors, year, isbn and publisher, each one only
when it is known. When the caller passes page ranges, it has pdf_pages: [first, last], 1-based PDF
pages. A field with no value is left out, so a book with no metadata gets the same frontmatter as
before.
"""

import json
import os
import re
from dataclasses import dataclass
from typing import Any

from ..bookmeta import BookMeta, PageRange, chapter_page_ranges
from . import fences

H1 = re.compile(r"^# (.+)$")
# The title of an appendix that the converter set one level down. `bookmeta` reads the same rule to
# find the page of each boundary, so the two can never disagree on what a boundary is.
APPENDIX_TITLE = re.compile(r"Appendix [A-Z]\..+")
APPENDIX_H2 = re.compile(rf"^## ({APPENDIX_TITLE.pattern})$")


def find_boundaries(lines: list[str]) -> list[tuple[int, str]]:
    """Return list of (line_index, heading_text) for chapter-level boundaries, fence-aware."""
    bounds = []
    # shared lexer: the old `^```` toggle mis-tracked tilde fences, longer fence runs, and any
    # info string it could not parse (a `c++` opener flipped the toggle out of step).
    in_code = fences.code_lines(lines)
    for i, ln in enumerate(lines):
        if i in in_code:
            continue
        m = H1.match(ln)
        if m:
            bounds.append((i, m.group(1).strip()))
            continue
        m = APPENDIX_H2.match(ln)
        if m:
            bounds.append((i, m.group(1).strip()))
    return bounds


def slugify(title: str) -> str:
    s = re.sub(r"[^\w\s-]", "", title.lower()).strip()
    s = re.sub(r"[\s_-]+", "-", s)
    return s[:60].strip("-") or "untitled"


def yaml_str(value: str) -> str:
    """A double-quoted YAML scalar that keeps printable characters such as `’`, `é` or an emoji
    as they are.

    `json.dumps` gives `"O\\u2019Reilly"`: valid, but not what a person reading the file expects.
    It also writes a character outside the Basic Multilingual Plane as two `\\u` surrogate
    escapes, which PyYAML does not join, so an emoji loads back as two broken halves. Raw output
    is no answer either: YAML forbids the C1 control characters raw in a stream. So a printable
    character is written raw. Any other character is escaped: a control character, an invisible
    space such as `U+00A0`, and a Private Use Area glyph that `symbol_pua` did not resolve.
    """
    out = ['"']
    for ch in value:
        if ch in '"\\':
            out.append("\\" + ch)
        elif ch.isprintable():
            out.append(ch)
        elif ord(ch) < 0x10000:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(f"\\U{ord(ch):08x}")
    out.append('"')
    return "".join(out)


def yaml_list(values: list[str]) -> str:
    return "[" + ", ".join(yaml_str(v) for v in values) + "]"


def book_fields(meta: BookMeta | None, *, with_title: bool = True) -> list[str]:
    """The frontmatter lines for the book-level metadata that is known, in a fixed order.
    The index page passes `with_title=False`, because there the book title is the page `title`."""
    if meta is None:
        return []
    out = []
    if meta.title and with_title:
        out.append(f"book_title: {yaml_str(meta.title)}")
    if meta.authors:
        out.append(f"authors: {yaml_list(meta.authors)}")
    if meta.year:
        out.append(f"year: {meta.year}")
    if meta.isbn:
        out.append(f"isbn: {json.dumps(meta.isbn)}")  # quoted: a bare ISBN would load as an int
    if meta.publisher:
        out.append(f"publisher: {yaml_str(meta.publisher)}")
    return out


def frontmatter(
    title: str,
    book: str,
    order: int,
    source: str,
    meta: BookMeta | None = None,
    pages: PageRange | None = None,
) -> str:
    # yaml_str -> a valid double-quoted YAML scalar. Python repr()/raw interpolation broke YAML on
    # titles with mixed quotes/backslashes and on source filenames containing `: `, `#`, or a
    # leading flow-indicator char. json.dumps fixed that, but it split a character outside the
    # BMP into two surrogate escapes that PyYAML loads as two broken halves.
    lines = [
        "---",
        f"title: {yaml_str(title)}",
        f"book: {yaml_str(book)}",
        *book_fields(meta),
        f"chapter: {order}",
    ]
    if pages is not None:
        lines.append(f"pdf_pages: [{pages[0]}, {pages[1]}]")
    lines += [f"source: {yaml_str(source)}", "tags: [book]", "---"]
    return "\n".join(lines) + "\n\n"


class NoBoundariesError(RuntimeError):
    pass


@dataclass
class PlannedFile:
    """One file that `plan` decided to write: its path, heading, order, PDF pages and text."""

    path: str
    title: str
    order: int  # 0 = the front matter
    pages: PageRange | None
    content: str


def plan(
    md_path: str,
    book: str,
    out_dir: str | None = None,
    source_name: str | None = None,
    text: str | None = None,
    meta: BookMeta | None = None,
    blocks: list[dict[str, Any]] | None = None,
) -> tuple[list[PlannedFile], list[tuple[int, str]]]:
    """Plan the split of md_path, write nothing. Returns (files, boundaries).

    source_name: value for frontmatter `source:` (pass the original PDF filename so staging
    paths don't leak into permanent frontmatter). Defaults to md_path.
    text: the document to split, when the caller already holds it (`run_chain` passes the
    repaired text). With `text` given, `md_path` is not read; it only names the default output
    directory and the default `source`.
    meta: book-level metadata for every file's frontmatter.
    blocks: the `blocks.json` list of the conversion. With it, each file gets its PDF page range
    (see `bookmeta.chapter_page_ranges`).
    """
    source = source_name or md_path
    if text is None:
        with open(md_path, encoding="utf-8") as f:
            text = f.read()
    lines = text.split("\n")
    bounds = find_boundaries(lines)
    if not bounds:
        raise NoBoundariesError("no chapter boundaries found")

    out = out_dir or os.path.join(os.path.dirname(md_path) or ".", "chapters")
    front_pages: PageRange | None = None
    chapter_pages: list[PageRange | None] = [None] * len(bounds)
    if blocks:
        front_pages, chapter_pages = chapter_page_ranges(blocks, [t for _, t in bounds])

    # front matter: everything before the first boundary
    front = "\n".join(lines[: bounds[0][0]]).strip("\n")
    files: list[PlannedFile] = []
    if front.strip():
        files.append(
            PlannedFile(
                os.path.join(out, "00-front-matter.md"),
                "Front matter",
                0,
                front_pages,
                frontmatter("Front matter", book, 0, source, meta, front_pages) + front + "\n",
            )
        )

    # each chapter: from its boundary to the next (or EOF)
    for idx, (start, title) in enumerate(bounds, start=1):
        end = bounds[idx][0] if idx < len(bounds) else len(lines)
        chapter_lines = list(lines[start:end])
        chapter_lines[0] = f"# {title}"  # heading normalize: boundary heading is always H1 in its
        body = "\n".join(chapter_lines).strip("\n")  # own file, even when the source mistagged it
        pages = chapter_pages[idx - 1]
        files.append(
            PlannedFile(
                os.path.join(out, f"{idx:02d}-{slugify(title)}.md"),
                title,
                idx,
                pages,
                frontmatter(title, book, idx, source, meta, pages) + body + "\n",
            )
        )
    return files, bounds


def write(files: list[PlannedFile]) -> None:
    for f in files:
        os.makedirs(os.path.dirname(f.path) or ".", exist_ok=True)
        with open(f.path, "w", encoding="utf-8") as fh:
            fh.write(f.content)


def split(
    md_path: str,
    book: str,
    out_dir: str | None = None,
    source_name: str | None = None,
    dry_run: bool = False,
    text: str | None = None,
    meta: BookMeta | None = None,
    blocks: list[dict[str, Any]] | None = None,
) -> tuple[list[str], list[tuple[int, str]]]:
    """Split md_path into chapter files. Returns (written_paths, boundaries).

    dry_run: compute boundaries and target paths, write nothing. The other arguments are those of
    `plan`.
    """
    files, bounds = plan(md_path, book, out_dir, source_name, text, meta, blocks)
    if not dry_run:
        write(files)
    return [f.path for f in files], bounds
