# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Write `<slug>-index.md`, the entry page of a split book.

The page has the book-level metadata in its frontmatter, a line with the authors, the publisher,
the year and the ISBN, and a table with one row per chapter file: its number, a link to the file,
and its PDF pages when they are known.

The links are CommonMark relative links, `[Title](01-chapter.md)`. Obsidian, GitHub and static
site generators all follow them. A chapter file name comes from `chapter_split.slugify`, so it has
no space or other character that a link destination must escape. A title is text inside a table
cell and inside link text, so its ASCII punctuation is escaped with a backslash. CommonMark lets
any ASCII punctuation take a backslash, so an escape is never wrong. Without one, `|` ends the
cell, `]` ends the link text, and `<T>` is read as an HTML tag and disappears.

The file is named `<slug>-index.md`, for example `50-algorithms-index.md`, and sits beside the
chapter files. The name is unique in a vault that holds many books. A plain `index.md` in every
book folder would make a vault's existing `[[index]]` links ambiguous. A plain `<slug>.md` would
collide with the `wiki/sources/<slug>.md` page that an ingest writes for the book.
"""

from __future__ import annotations

import os
import re

from ..bookmeta import BookMeta, PageRange
from .chapter_split import PlannedFile, book_fields, slugify, yaml_str

INDEX_SUFFIX = "-index.md"


def index_name(book: str) -> str:
    """The file name of the index for book slug `book`."""
    return slugify(book) + INDEX_SUFFIX


# Markdown punctuation that can change how a title renders in a table cell or a link text: emphasis,
# code, links, HTML, the cell bar, a heading, Obsidian's $math$, ~~strike~~ and ==highlight==, an
# image's "!", and "&" before an entity name.
_MD_PUNCT = re.compile(r"([\\`*_\[\]<>|#$~=&!])")


def escape(text: str) -> str:
    return _MD_PUNCT.sub(r"\\\1", text)


def render(
    book: str,
    source: str,
    meta: BookMeta | None,
    entries: list[tuple[int, str, str, PageRange | None]],
) -> str:
    """The text of the index page. `entries` holds (number, title, file name, PDF pages) per file."""
    meta = meta or BookMeta()
    title = meta.title or book
    fm = ["---", f"title: {yaml_str(title)}", f"book: {yaml_str(book)}"]
    fm += book_fields(meta, with_title=False)  # the same lines as in every chapter file
    if meta.page_count:
        fm.append(f"pdf_page_count: {meta.page_count}")
    fm += [f"source: {yaml_str(source)}", "tags: [book-index]", "---"]

    out = ["\n".join(fm), "", f"# {escape(title)}", ""]
    facts = []
    if meta.authors:
        facts.append("By " + ", ".join(escape(a) for a in meta.authors))
    if meta.publisher:
        facts.append(escape(meta.publisher))
    if meta.year:
        facts.append(str(meta.year))
    if meta.isbn:
        facts.append(f"ISBN {meta.isbn}")
    if facts:
        out += [" · ".join(facts), ""]
    out += ["| # | Chapter | PDF pages |", "|---|---|---|"]
    for number, chapter, name, pages in entries:
        span = f"{pages[0]}–{pages[1]}" if pages else ""
        out.append(f"| {number} | [{escape(chapter)}]({name}) | {span} |")
    return "\n".join(out) + "\n"


def build(
    files: list[PlannedFile], book: str, source: str, meta: BookMeta | None
) -> tuple[str, str] | None:
    """(path, text) of the index page for the files that `chapter_split.plan` planned, or None
    when it planned none. The rows come from the plan itself, so they cannot drift from the files.
    None too when a planned chapter file already has the index name: the index never overwrites a
    chapter."""
    if not files:
        return None
    entries = [(f.order, f.title, os.path.basename(f.path), f.pages) for f in files]
    index_path = os.path.join(os.path.dirname(files[0].path), index_name(book))
    if any(f.path == index_path for f in files):
        return None
    return index_path, render(book, source, meta, entries)
