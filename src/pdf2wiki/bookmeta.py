# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Book-level metadata, and the PDF page range of each chapter.

The metadata is the title, the authors, the year, the ISBN and the publisher. It comes from two
sources:

- The PDF (`from_pdf`). The document information dictionary gives the title and the authors. The
  text of the first pages gives the rest. `convert` writes the result to `book.json`, beside
  `blocks.json`, because the PDF is not on the control host after a remote conversion.
- The converted Markdown (`from_text`). The copyright page is in the text, so the ISBN, the year
  and the publisher can be read without the PDF.

Each value records its source in `sources`. A field with no strong source stays empty. A guess is
never written: this metadata goes into permanent frontmatter, where a wrong year is worse than no
year. So the year comes from a copyright line only, never from any four digits on a page, and an
ISBN must pass its checksum.

The chapter page ranges come from `blocks.json`. Each heading block there carries the PDF page it
was found on (`abs_page`, 0-based). The ranges in the output are 1-based, as a PDF viewer counts
pages. They are not the page labels that the book prints.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import unicodedata
from dataclasses import asdict, dataclass, field, fields, replace
from typing import Any

# How far into the converted Markdown `from_text` reads. The copyright page is in the first few
# pages of every book measured (Packt, Manning, O'Reilly). The limit keeps the "other books you may
# enjoy" pages at the back out, because their ISBNs belong to other books.
FRONT_CHARS = 40_000

# How many PDF pages `from_pdf` reads for the same purpose.
FRONT_PAGES = 10


@dataclass
class BookMeta:
    title: str | None = None
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    isbn: str | None = None
    publisher: str | None = None
    page_count: int | None = None
    sources: dict[str, str] = field(default_factory=dict)

    def fill(self, other: BookMeta) -> BookMeta:
        """Return a copy where each empty field takes the value of `other`, with its source."""
        out = replace(self, authors=list(self.authors), sources=dict(self.sources))
        for f in fields(self):
            if f.name == "sources":
                continue
            if not getattr(out, f.name) and getattr(other, f.name):
                value = getattr(other, f.name)
                setattr(out, f.name, list(value) if isinstance(value, list) else value)
                if f.name in other.sources:
                    out.sources[f.name] = other.sources[f.name]
        return out

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> BookMeta:
        """Read a `book.json` dict. A value of the wrong type is dropped, not trusted: the file
        crosses machines and a hand edit can break it."""

        def text(v: Any) -> str | None:
            return v.strip() if isinstance(v, str) and v.strip() else None

        def num(v: Any) -> int | None:
            return v if isinstance(v, int) and not isinstance(v, bool) and v > 0 else None

        authors = d.get("authors")
        sources = d.get("sources")
        return cls(
            title=text(d.get("title")),
            authors=[a.strip() for a in authors if isinstance(a, str) and a.strip()]
            if isinstance(authors, list)
            else [],
            year=num(d.get("year")),
            isbn=text(d.get("isbn")),
            publisher=text(d.get("publisher")),
            page_count=num(d.get("page_count")),
            sources={k: v for k, v in sources.items() if isinstance(v, str)}
            if isinstance(sources, dict)
            else {},
        )


# ---------- ISBN ----------

# "ISBN 978…", "ISBN: …", "ISBN-13 …", "ISBN 13: …", "ISBN 13 978…", "ISBN (ebook): …", "eISBN: …",
# "?isbn=…". A "10" or "13" after the word is a label only with a hyphen before it, a colon or a
# bracket after it, or a 978/979 ISBN-13 after it: in "ISBN 1098108302" the 10 starts an ISBN-10. A PDF text layer often sets the hyphens
# as U+2010 to U+2015, so those count as separators too.
_ISBN_SEP = "\u2010-\u2015"
ISBN_RE = re.compile(
    r"\b(?:e-?)?ISBN(?:-1[03]|\s?1[03](?=\s*[:(])|\s1[03](?=\s+97[89]))?"
    r"(?:\s*\([^)\n]{0,20}\))?\s*[:=#]?\s*"
    rf"([0-9][0-9Xx \-{_ISBN_SEP}]{{8,24}})",
    re.I,
)


def isbn13_ok(s: str) -> bool:
    if len(s) != 13 or not s.isdigit():
        return False
    return sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(s)) % 10 == 0


def isbn10_ok(s: str) -> bool:
    if len(s) != 10 or not s[:9].isdigit() or not (s[9].isdigit() or s[9] in "Xx"):
        return False
    total = sum((10 - i) * int(c) for i, c in enumerate(s[:9]))
    total += 10 if s[9] in "Xx" else int(s[9])
    return total % 11 == 0


def find_isbn(text: str) -> str | None:
    """The first ISBN in `text` that passes its checksum, as digits only (an ISBN-10 keeps a final
    `X`). The candidate after the word ISBN can run into the next number on the line, so the
    13-digit prefix is tried first and then the 10-digit one. A 13-digit prefix counts only when
    it starts with 978 or 979, the two ISBN-13 prefixes: one in ten random 13-digit runs passes the
    checksum, so `ISBN 1491950358 2010` would otherwise give an ISBN-13 that does not exist."""
    for m in ISBN_RE.finditer(text):
        digits = re.sub(rf"[ \-{_ISBN_SEP}]", "", m.group(1))
        if digits[:3] in ("978", "979") and isbn13_ok(digits[:13]):
            return digits[:13]
        if isbn10_ok(digits[:10]):
            return digits[:10].upper()
    return None


# ---------- year ----------

# "Copyright © 2023 Packt", "©2021 by Manning", "Copyright 2019", "Copyright (c) 2020". Not "First
# published: June 2020": that is the first edition, and the copyright line names this one. Not a bare
# "(c)": in a list, "(c) 2048 bytes" is item c. A reprint names a run of years, "© 2015, 2021" or
# "© 2017-2023", and the run is captured whole so that the latest year wins.
YEAR = r"(?:19|20)\d{2}"
# Between the marker and the year: spaces and at most one line break. A PDF text layer often puts
# "Copyright ©" at the end of one line and "2023 Packt" at the start of the next.
_GAP = r"[^\S\n]*\n?[^\S\n]*"
COPYRIGHT_YEAR_RE = re.compile(
    rf"(?:\bcopyright\b{_GAP}(?:©|\(c\))?|©){_GAP}(?:by\s+)?"
    rf"({YEAR}(?:\s*(?:,|-|–|—|and)\s*{YEAR})*)\b",
    re.I,
)
# A license header in a code listing, such as "// Copyright 2025 Google LLC" or "# Copyright 2024
# The Kubernetes Authors", is not the copyright of the book. The Markdown path also skips fences,
# but PDF page text has no fences, so the comment marker is the only signal there. In Markdown a
# "#" opens a heading and a "*" opens emphasis or a list item, so `hash_comments=False` keeps
# "## Copyright © 2020 X" and "**©2021 by Manning**" for that path.
_CODE_COMMENT_RE = re.compile(r"^\s*(?://|/\*|--|;|<!--)")
_HASH_COMMENT_RE = re.compile(r"^\s*[#*]")


# A copyright page puts all its copyright lines close together. Only the matches within this many
# lines of the first one count, so a license header later in chapter 1 cannot win the year.
COPYRIGHT_SPAN = 15


def find_year(text: str, *, hash_comments: bool = True) -> int | None:
    """The latest year of the first copyright statement, outside code comments.

    The copyright page comes before any code, so the first match is the book's. A reprint can put
    a second copyright line a few lines below the first one, so the latest year within
    `COPYRIGHT_SPAN` lines of the first match wins.
    """
    kept = "\n".join(
        ln
        for ln in text.splitlines()
        if not (_CODE_COMMENT_RE.match(ln) or (hash_comments and _HASH_COMMENT_RE.match(ln)))
    )
    first_line: int | None = None
    years: list[int] = []
    for m in COPYRIGHT_YEAR_RE.finditer(kept):
        line = kept.count("\n", 0, m.start())
        if first_line is None:
            first_line = line
        elif line > first_line + COPYRIGHT_SPAN:
            break
        years += [int(y) for y in re.findall(YEAR, m.group(1))]
    return max(years) if years else None


# ---------- publisher ----------

PUBLISHED_BY_RE = re.compile(r"^Published by\s+(.+)$", re.I)
# A line that holds only a company name, such as Manning's "Manning Publications Co.". The
# company suffix is required: without it, a heading such as "Social Media" or "Bench Press" in the
# first chapter reads as a publisher. So "No Starch Press" alone is not found. An empty field is
# the cost, and a wrong one would be worse.
PUBLISHER_LINE_RE = re.compile(
    r"^([A-Z][\w'’&.\- ]{0,40}?\b(?:Publications|Publishing|Press|Media)"
    r",?\s+(?:Co|Inc|Ltd|LLC)\.?)$"
)
COMPANY_SUFFIX_RE = re.compile(r"^(?:Inc|Ltd|LLC|Co|Corp|GmbH|PLC|L\.?P)\.?$", re.I)
MAX_PUBLISHER = 80


def _plain(line: str) -> str:
    """A Markdown line without the heading, quote and emphasis marks around it."""
    return re.sub(r"^[#>*_\s]+", "", line).rstrip().rstrip("*_").strip()


def _published_by(rest: str) -> str | None:
    # "O’Reilly Media, Inc., 1005 Gravenstein Highway North" -> "O’Reilly Media, Inc."
    # "Packt Publishing Ltd. Livery Place" -> "Packt Publishing Ltd."
    parts = rest.split(",")
    name = re.split(r"(?<=\.)\s+(?=[A-Z0-9])", parts[0].strip(), maxsplit=1)[0]
    if name == parts[0].strip():
        for p in parts[1:]:
            if not COMPANY_SUFFIX_RE.match(p.strip()):
                break
            name += ", " + p.strip()
    name = name.strip().rstrip(",;:")
    if not name or len(name) > MAX_PUBLISHER or not any(c.isalpha() for c in name):
        return None
    if re.search(YEAR, name):  # "Published by Google in 2018, BERT …" is prose, not an imprint
        return None
    return name


def find_publisher(text: str) -> tuple[str | None, str]:
    """(publisher, source). The first candidate in the text wins: a "Published by" line or a line
    that is only a company name. The copyright page comes before the prose, so a later "Published
    by" sentence in a preface cannot replace the imprint above it."""
    for orig in text.splitlines():
        ln = _plain(orig)
        m = PUBLISHED_BY_RE.match(ln)
        if m:
            name = _published_by(m.group(1))
            if name:
                return name, "published-by"
            continue
        if orig.lstrip().startswith("#"):
            continue  # a heading names a topic, not the publisher
        m = PUBLISHER_LINE_RE.match(ln)
        if m:
            return m.group(1).strip(), "publisher-line"
    return None, ""


# ---------- title and authors (PDF metadata only) ----------

_JUNK_TITLE_RE = re.compile(
    r"^(?:untitled|microsoft word\b.*|.*\.(?:pdf|indd|docx?|tex|qxd))$", re.I
)
_JUNK_AUTHORS = {"unknown", "administrator", "admin", "user", "author", "owner"}


def clean_title(raw: str | None) -> str | None:
    """A title from the PDF metadata, or None when it names a file or a template."""
    t = " ".join((raw or "").split())
    if len(t) < 3 or _JUNK_TITLE_RE.match(t):
        return None
    return t


def split_authors(raw: str | None) -> list[str]:
    """Authors from the PDF metadata `author` field: separated by `;`, `&` or "and", and by `,`
    only when every part between the commas has two words or more. So "Heather Adkins, Betsy
    Beyer" is two authors, and "Richardson, Chris" or "John Smith, Jr." stays one."""
    out: list[str] = []
    parts: list[str] = []
    for chunk in re.split(r"\s*(?:;|&|\band\b)\s*", raw or ""):
        # "A, B, and C": the chunk before "and" ends in a comma, so drop the empty piece
        pieces = [p.strip() for p in chunk.split(",") if p.strip()]
        chunk = ", ".join(pieces)
        if len(pieces) > 1 and all(len(p.split()) >= 2 for p in pieces):
            parts += pieces
        else:
            parts.append(chunk)
    for part in parts:
        name = " ".join(part.split())
        if len(name) >= 2 and name.lower() not in _JUNK_AUTHORS and name not in out:
            out.append(name)
    return out


# ---------- entry points ----------


def from_text(text: str, *, markdown: bool = True) -> BookMeta:
    """ISBN, year and publisher from the front of a book's text, outside code.

    The first 40,000 characters can reach into chapter 1. A code sample there often opens with a
    license header, such as `// Copyright 2025 Google LLC`, which would win the year. In Markdown
    the fences mark the code, so fenced lines are skipped. PDF page text (`markdown=False`) has no
    fences, so there a line that starts like a code comment, `#` too, gives no year.
    """
    from .phase5 import fences  # lazy: the phase5 package imports this module

    lines = text[:FRONT_CHARS].split("\n")
    code = fences.code_lines(lines) if markdown else set()
    front = "\n".join(ln for i, ln in enumerate(lines) if i not in code)
    meta = BookMeta()
    meta.isbn = find_isbn(front)
    if meta.isbn:
        meta.sources["isbn"] = "text"
    meta.year = find_year(front, hash_comments=not markdown)
    if meta.year:
        meta.sources["year"] = "copyright-line"
    meta.publisher, how = find_publisher(front)
    if meta.publisher:
        meta.sources["publisher"] = how
    return meta


def from_pdf(pdf_path: str) -> BookMeta:
    """All fields: title and authors from the PDF metadata, the rest from its first pages."""
    import pymupdf  # lazy: keep the CLI start fast

    with pymupdf.open(pdf_path) as doc:
        if not doc.is_pdf:  # pymupdf also opens .md, .txt and .epub, and would scrape them
            raise ValueError(f"{pdf_path} is not a PDF")
        info = doc.metadata or {}
        n = doc.page_count
        text = "\n".join(doc[i].get_text() for i in range(min(FRONT_PAGES, n)))
    meta = from_text(text, markdown=False)
    meta.page_count = n
    meta.sources["page_count"] = "pdf"
    meta.title = clean_title(info.get("title"))
    if meta.title:
        meta.sources["title"] = "pdf-metadata"
    meta.authors = split_authors(info.get("author"))
    if meta.authors:
        meta.sources["authors"] = "pdf-metadata"
    return meta


def load(path: str) -> BookMeta | None:
    """Read a `book.json`. None when the file is missing or is not a JSON object."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return BookMeta.from_dict(data) if isinstance(data, dict) else None


def load_blocks(path: str) -> tuple[list[dict[str, Any]] | None, str]:
    """(blocks, state) for the `blocks.json` that `convert` wrote. The state is "ok", "absent",
    "unreadable" (cut off, not JSON, not a list) or "empty" (a list with no block in it). Page
    ranges are an enrichment, so no state stops the chain that writes the chapters."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return None, "absent"
    except (OSError, ValueError):
        return None, "unreadable"
    if not isinstance(data, list):
        return None, "unreadable"
    blocks = [b for b in data if isinstance(b, dict)]
    return (blocks, "ok") if blocks else (None, "empty")


SIDECARS = ("blocks.json", "book.json")


def clear_sidecars(work: str) -> None:
    """Remove the sidecars of an earlier run before a convert writes. Every convert path calls
    this first, so a `blocks.json` or `book.json` beside a new Markdown always comes from the same
    run. The Markdown itself stays until the new one replaces it: a failed convert then leaves the
    old book without its sidecars, which gives no metadata rather than wrong metadata."""
    for name in SIDECARS:
        with contextlib.suppress(FileNotFoundError):
            os.remove(os.path.join(work, name))


def write(meta: BookMeta, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta.to_dict(), f, indent=1, ensure_ascii=False)
        f.write("\n")


def write_for_pdf(pdf_path: str, work: str, say: Any) -> None:
    """`convert` calls this after it writes the book. Metadata never fails a conversion: a PDF
    whose information dictionary pymupdf cannot read still converts, and the step says why it
    wrote no `book.json`."""
    path = os.path.join(work, "book.json")
    try:
        meta = from_pdf(pdf_path)
        write(meta, path)
    except Exception as e:  # metadata is an enrichment, never a reason to fail a book
        with contextlib.suppress(OSError):
            os.remove(path)  # a half-written book.json is worse than none
        say(f"book metadata: not written ({type(e).__name__}: {e})")
        return
    found = [k for k in ("title", "authors", "year", "isbn", "publisher") if getattr(meta, k)]
    say(f"book metadata: {', '.join(found) or 'no fields found'} -> {work}/book.json")


# ---------- chapter page ranges ----------

PageRange = tuple[int, int]


def _norm(s: str) -> str:
    """A title reduced to its ASCII letters and digits, after NFKC. `symbol_pua` turns a PUA glyph
    in a Markdown title into a letter such as π, while the block keeps the glyph. Both are dropped
    here, so the two still match. A title with no ASCII letter at all keeps its Unicode letters,
    so two titles in another script never both normalize to an empty string."""
    s = unicodedata.normalize("NFKC", s).lower()
    if any(c.isascii() and c.isalpha() for c in s):
        return "".join(c for c in s if c.isascii() and c.isalnum())
    return "".join(c for c in s if c.isalnum())  # "Глава 1" must not reduce to "1"


def _page(b: dict[str, Any]) -> int | None:
    """The 0-based PDF page of a block, or None when `abs_page` is not a page number."""
    page = b.get("abs_page")
    return page if isinstance(page, int) and not isinstance(page, bool) and page >= 0 else None


def _heading_pages(blocks: list[dict[str, Any]]) -> list[tuple[str, int]]:
    """(normalized title, 0-based page) for each block that `chapter_split` can make a boundary:
    a level-1 heading, or a level-2 heading that names an appendix."""
    from .phase5.chapter_split import APPENDIX_TITLE  # lazy: chapter_split imports this module

    out: list[tuple[str, int]] = []
    for b in blocks:
        if b.get("type") != "text":
            continue
        level = b.get("text_level")
        first = str(b.get("text") or "").split("\n", 1)[0].strip()
        page = _page(b)
        if page is not None and (level == 1 or (level == 2 and APPENDIX_TITLE.fullmatch(first))):
            out.append((_norm(first), page))
    return out


def chapter_page_ranges(
    blocks: list[dict[str, Any]], titles: list[str]
) -> tuple[PageRange | None, list[PageRange | None]]:
    """1-based PDF page ranges: (front matter, one per chapter title).

    The titles are matched to the heading blocks in order, so a title that occurs twice in a book
    takes the next block each time. A match may not jump over a heading that a later title needs:
    the titles and the blocks then disagree on the order, and the title stays unmatched.

    A chapter starts on the page of its heading and ends on the page before the next chapter
    starts. Its range is None when its own start is unknown, or when the next chapter has no known
    start: an end taken from a later chapter would include a chapter that was not found.

    ⚠ Known limit: a chapter that runs on to the page where the next one starts mid-page loses that
    page. The other rule, "end on the last page that holds a block of the chapter", was measured on
    four converted books and was wrong in 12 of 12 cases: each block on the next chapter's first
    page was that chapter's own material that the converter put before its heading in reading order
    (a big chapter number, an opener image, its first paragraphs). No case of a chapter that runs on
    was found.
    """
    heads = _heading_pages(blocks)
    pages = [p for p in map(_page, blocks) if p is not None]
    if not heads or not pages:
        return None, [None] * len(titles)
    wanted = [_norm(t) for t in titles]
    starts: list[int | None] = []
    j = 0
    for i, want in enumerate(wanted):
        later = set(wanted[i + 1 :])
        hit = None
        for k in range(j, len(heads)):
            if heads[k][0] == want:
                hit, j = heads[k][1], k + 1
                break
            if heads[k][0] in later:
                break  # this match would skip a heading that a later title needs
        starts.append(hit)
    last = max(pages)
    ranges: list[PageRange | None] = []
    for i, s in enumerate(starts):
        nxt = starts[i + 1] if i + 1 < len(starts) else last + 1
        if s is None or nxt is None:
            ranges.append(None)
            continue
        ranges.append((s + 1, max(s, nxt - 1) + 1))
    first_page = min(pages)
    front = None
    if starts and starts[0] is not None and starts[0] > first_page:
        front = (first_page + 1, starts[0])
    return front, ranges
