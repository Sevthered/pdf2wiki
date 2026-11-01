# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Link the cross-references of a split book: "figure 6.2", "listing 4.1", "table 1.3",
"section 2.3" and "chapter 5" in the prose become links to their target in its chapter file.

The step reads all chapter files of one book together, because a reference and its target are often
in different files. It finds the targets, links the references, and then adds the anchors.

**Targets.**

- A caption is a line that starts with `Figure`, `Fig.`, `Listing` or `Table` and a number, such as
  `*Figure 6.2 Liveness check*`, `**Listing 3.4** Start Live Coding` or `Figure 2-1. The
  architecture`. Prose can start the same way ("Listing 6.1 shows the class"). So a line is a caption
  only when it is a heading, or when an image, a code fence or a table is within two non-blank lines
  of it. The word after the number must not be a verb such as "shows". A line with no emphasis, and
  no `.`, `:` or dash after the number, must also go on with a capital letter: measured on 24 books,
  "Figure 1.1 The internal representation" is a caption and "Figure 3.6 tries to answer" is prose.
- A section is a heading that starts with a number of two parts or more, such as `## 6.3 Getting
  started`.
- A chapter is a file. Its number comes from its first H1, such as `# Chapter 5 Data` or `# 5 Data`.
  When the H1 has no number, every caption and numbered section in the file must share one first
  number, and there must be two or more of them: a file with Figure 6.1 and `## 6.3` is chapter 6. The
  frontmatter `chapter:` is not used: it counts files, and cover, part and preface pages shift it.

A number that two targets share links nowhere. A wrong link is worse than no link. Numbers compare
without leading zeros, so "Chapter 05" is chapter 5.

**Links.** Every link is a CommonMark relative link that names the target file, also inside one
file: Obsidian resolves a `[[name]]` wikilink by name across the whole vault, and a vault that holds
many books repeats names such as `01-introduction`. The style sets the anchor:

- `obsidian`: a block id at the end of the caption paragraph, `^fig-6-2`, and a link to
  `file.md#^fig-6-2`. A heading target needs no id: the link is `file.md#<heading text>`, with the
  text percent-encoded.
- `markdown`: an `<a id="fig-6-2"></a>` at the start of a caption paragraph, and a link to
  `file.md#fig-6-2`. A heading gets the anchor on its own line above it, followed by an empty line,
  so the heading text does not change. Without the empty line, CommonMark reads the heading as part
  of the HTML block.

An anchor counts only in the style that wrote it. A block id is no target for a `markdown` link, so
a second run in the other style adds its own anchor and links to that. A chapter link names the
file only.

**What is never scanned for references:** the frontmatter, fenced code, display math between `$$`
lines, inline code, existing links, HTML, inline math, headings and caption paragraphs. "Chapter 3
of Kubernetes in Action" names another book, so it is counted as external and left alone. A second
run in the same style finds its own anchors and links, and changes nothing.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from . import fences

STYLES = ("obsidian", "markdown")
KINDS = ("figure", "table", "listing", "section", "chapter")
_PREFIX = {"figure": "fig", "table": "tbl", "listing": "lst", "section": "sec"}

_NUM = r"\d+(?:[.\-]\d+)*"
_HTML_ANCHOR = r'<a id="(?P<html_id>[a-z]+-[0-9-]+)"></a>'
_ANCHOR_LINE = re.compile(rf"^[ \t]*{_HTML_ANCHOR}[ \t]*$")
_CAPTION = re.compile(
    rf"^(?P<lead>[ \t]*)(?:{_HTML_ANCHOR})?(?P<em>[*_]{{0,2}})(?P<kind>Figure|Fig\.|Listing|Table)"
    rf"[ \t]+(?P<num>{_NUM})(?=[\s.:\u2013\u2014*_-]|$)"
)
# After the number, a caption often has punctuation: "Figure 2-1. The", "Figure 3.1 \u2013 The".
_CAPTION_PUNCT = re.compile(r"^(?:[.:\u2013\u2014]|[ \t]+[\u2013\u2014-][ \t])")
_FIRST_WORD = re.compile(r"^[\s*_.:\u2013\u2014-]*(?P<word>[^\s*_]*)")
# The first word after the number of a line that starts like a caption but is prose.
_VERB_WORDS = (
    "shows show illustrates depicts presents lists contains summarizes summarises is are was were "
    "gives describes demonstrates displays compares has have provides uses outlines highlights "
    "captures represents explains defines implements includes adds will can above below also again "
    "then in on and of to from with for"
)
_VERBS = frozenset(_VERB_WORDS.split())
_HEADING = re.compile(r"^(?P<marks>#{1,6})[ \t]+(?P<text>.*?)(?:[ \t]+#+)?[ \t]*$")
_SECTION_NUM = re.compile(r"^(?:Section[ \t]+)?(?P<num>\d+(?:\.\d+)+)\.?[ \t]+\S")
_H1_NUM = re.compile(
    r"^(?:Chapter[ \t]+)?(?P<num>\d+)(?:[.:]|[ \t]*[\u2013\u2014-])?(?:[ \t]|$)", re.I
)
_BLOCK_ID = re.compile(r"[ \t]\^(?P<id>[A-Za-z0-9-]+)[ \t]*$")
_IMAGE = re.compile(r"!\[[^\]]*\]\(|!\[\[")
# A line that ends a paragraph when it follows one (CommonMark): a heading, a fence, a quote, a
# thematic break or setext underline, a list item that may interrupt, an HTML block of types 1-6, or
# a table row (a GFM table; a pipe row after a caption is never read as its continuation here).
_INTERRUPT = re.compile(
    r"^[ \t]{0,3}(?:#{1,6}(?:[ \t]|$)|`{3,}|~{3,}|>|[-*_](?:[ \t]*[-*_]){2,}[ \t]*$|=+[ \t]*$"
    r"|[-+*][ \t]|1[.)][ \t]|\|"
    r"|<(?:/?(?:address|article|aside|blockquote|details|div|dl|figure|footer|form|h[1-6]|header"
    r"|hr|li|nav|ol|p|pre|script|section|style|summary|table|tbody|td|tfoot|th|thead|tr|ul)\b|!--))"
)
# HTML blocks (CommonMark). Markdown inside one is not rendered, so no link or anchor goes there.
# Types 1-5 end at the line that holds their closing text, type 6 at a blank line. Inline HTML at a
# line start, such as <kbd>, is not a block.
_HTML_UNTIL = (
    (
        re.compile(r"^[ \t]{0,3}<(?:pre|script|style|textarea)(?:[ \t>]|$)", re.I),
        re.compile(r"</(?:pre|script|style|textarea)>", re.I),
    ),
    (re.compile(r"^[ \t]{0,3}<!--"), re.compile(r"--!?>")),  # a browser also ends one at --!>
    (re.compile(r"^[ \t]{0,3}<\?"), re.compile(r"\?>")),
    (re.compile(r"^[ \t]{0,3}<![A-Za-z]"), re.compile(r">")),
    (re.compile(r"^[ \t]{0,3}<!\[CDATA\["), re.compile(r"\]\]>")),
)
_HTML_BLOCK = re.compile(
    r"^[ \t]{0,3}</?(?:address|article|aside|blockquote|details|div|dl|figure|footer|form"
    r"|h[1-6]|header|hr|li|nav|ol|p|section|summary|table|tbody|td|tfoot|th|thead|tr|ul)\b",
    re.I,
)
# A number in a reference ends at a word boundary. One letter may follow, for a part of a figure:
# "figure 9.15B" refers to figure 9.15. A number never ends inside a longer number: "figure 6.2x1"
# is not figure 6.
_NUM_END = r"(?![.\-]?\d)(?=[A-Za-z]?\b)"
_REF = re.compile(
    rf"\b(?P<kind>figures?|figs?\.|listings?|tables?|sections?|chapters?)[ \t]+(?P<num>{_NUM})"
    rf"{_NUM_END}(?P<more>(?:[ \t]*(?:,[ \t]*(?:and|or)\b|,|and|or|&)[ \t]*{_NUM}{_NUM_END})*)",
    re.I,
)
_MORE_NUM = re.compile(_NUM)
# An en or em dash, or a hyphen with spaces, after a number: "chapters 2\u20135", "figures 2.1 - 2.3".
_RANGE_DASH = re.compile(r"[ \t]*[\u2013\u2014][ \t]*\d|[ \t]+-[ \t]+\d")
_EXTERNAL = re.compile(
    r"^[ \t]+of[ \t]+(?!(?i:chapter|part|section|appendix|volume)\b)(?:the[ \t]+)?"
    r"(?:[*_]{1,2})?[A-Z\"\u201c\u2018'\[]"
)
# Spans in a line that a reference inside must not be rewritten in.
_PROTECTED = re.compile(
    r"(?P<code>(`+).*?(?<!`)\2(?!`))"
    r"|!?\[[^\]\n]*\]\([^)\n]*\)"
    r"|\[[^\]\n]*\](?:\[[^\]\n]*\])?"  # [text][ref], [text]: a reference link or plain brackets
    r"|\[\[[^\]\n]*\]\]"
    r"|<[^>\n]+>"
    r"|\$\$[^\n]*?\$\$"
    r"|\$(?=\S)[^$\n]*?(?<=\S)\$(?!\d)"
)
_LINK_DEFINITION = re.compile(r"^[ \t]{0,3}\[[^\]\n]+\]:")
# A heading text that the obsidian style does not link to.
_BAD_HEADING = re.compile(r"[\[\]|^]")
# Obsidian decodes a Markdown link with decodeURI, which keeps the escapes of these characters
# (`%3A`, `%2C`, ...), so a heading fragment with one of them does not match. Obsidian ignores
# punctuation when it compares headings, so the fragment drops them. A literal `:` would also make
# Obsidian read the link as external.
_URI_RESERVED = re.compile(r"[;/?:@&=+$,#]")


@dataclass
class _Target:
    kind: str
    key: str
    file: str
    line: int  # the caption or heading line
    heading: str | None  # the heading text, for a heading target
    end: int  # the last line of the caption paragraph, where a block id goes
    block_id: str | None = None  # a block id already at the end of the paragraph
    html_id: str | None = None  # an <a id> already on the caption or above the heading
    dashed: bool = False  # the number uses a dash, as in "Figure 2-1"


def _key(num: str) -> str:
    """A number as a lookup key: "2-1" and "2.1" are one key, and "05" is "5"."""
    return ".".join(str(int(p)) for p in num.replace("-", ".").split("."))


def _kind(word: str) -> str:
    w = word.lower().rstrip(".")
    w = w[:-1] if w.endswith("s") else w
    return "figure" if w == "fig" else w


def _frontmatter_end(lines: list[str]) -> int:
    """Index of the first line after the YAML frontmatter, or 0 when there is none."""
    if lines and lines[0] == "---":
        for i in range(1, len(lines)):
            if lines[i] == "---":
                return i + 1
    return 0


class _File:
    def __init__(self, name: str, text: str) -> None:
        self.name = name
        self.lines = text.split("\n")
        self.start = _frontmatter_end(self.lines)
        self.code = fences.code_lines(self.lines)
        self.math = self._display_math()
        self.opaque = self._opaque()
        self.skip: set[int] = set()  # caption paragraphs: never scanned for references

    def _display_math(self) -> set[int]:
        """The lines of each display-math block that opens with a `$$` line and closes at the next."""
        out: set[int] = set()
        opened: int | None = None
        for i in range(self.start, len(self.lines)):
            if i in self.code:
                continue
            s = self.lines[i].strip()
            if opened is None and s.startswith("$$") and not (len(s) > 2 and s.endswith("$$")):
                opened = i
            elif opened is not None and s.endswith("$$"):
                out.update(range(opened, i + 1))
                opened = None
        return out

    def _opaque(self) -> set[int]:
        """The lines of HTML blocks and of indented code. Markdown there is not rendered."""
        out: set[int] = set()
        until: re.Pattern[str] | None = None  # the closing text of an open HTML block, types 1-5
        html = indented = False
        after_blank = True
        for i in range(self.start, len(self.lines)):
            ln = self.lines[i]
            if until is not None:
                out.add(i)
                if until.search(ln):
                    until = None
                continue
            if not ln.strip():
                html = False  # an HTML block of type 6 ends at a blank line
                after_blank = True
                continue
            # Indented code: 4 columns or more, after a blank line or more such code. An indented
            # paragraph line inside a list item looks the same and is skipped too.
            wide = ln.expandtabs(4)
            indented = len(wide) - len(wide.lstrip()) >= 4 and (after_blank or indented)
            after_blank = False
            if not indented and i not in self.code and i not in self.math:
                for start, end in _HTML_UNTIL:
                    m = start.match(ln)
                    if m:
                        until = None if end.search(ln, m.end()) else end
                        out.add(i)
                        break
                if _HTML_BLOCK.match(ln):
                    html = True
            if html or indented:
                out.add(i)
        return out

    def prose(self) -> range:
        return range(self.start, len(self.lines))

    def is_text(self, i: int) -> bool:
        return i >= self.start and i not in self.code and i not in self.math

    def starts_paragraph(self, i: int) -> bool:
        """Line `i` is the first line of a paragraph, or follows an image (a converter puts a
        caption right under its image) or a markdown-style anchor line."""
        j = i - 1
        if j < self.start or not self.is_text(j) or j in self.opaque:
            return True
        prev = self.lines[j]
        return not prev.strip() or bool(
            _IMAGE.search(prev) or _ANCHOR_LINE.match(prev) or _HEADING.match(prev)
        )

    def near_block(self, i: int) -> bool:
        """An image, a fence or a table within two non-blank lines of line `i`."""
        for step in (-1, 1):
            j, seen = i + step, 0
            while 0 <= j < len(self.lines) and j >= self.start and seen < 2:
                ln = self.lines[j]
                # A markdown-style anchor line above a heading is not content.
                if ln.strip() and not _ANCHOR_LINE.match(ln):
                    seen += 1
                    s = ln.lstrip()
                    if j in self.code or _IMAGE.search(ln) or s.startswith(("<table", "|")):
                        return True
                j += step
        return False

    def paragraph_end(self, i: int) -> int:
        """The last line of the paragraph that line `i` opens. An image on the next line is inline
        content, so it belongs to the paragraph, and a block id must go after it."""
        j = i
        while j + 1 < len(self.lines):
            nxt = self.lines[j + 1]
            if not nxt.strip() or not self.is_text(j + 1) or _INTERRUPT.match(nxt):
                break
            j += 1
        return j


def _is_caption(text: str, m: re.Match[str], heading: bool) -> bool:
    rest = text[m.end() :]
    word = _FIRST_WORD.match(rest).group("word")  # type: ignore[union-attr]  # the regex always matches
    alpha = re.match(r"[A-Za-z']+", word)
    if alpha and alpha.group(0) in _VERBS:  # prose goes on in lower case: "Figure 3.6 shows"
        return False
    if heading or m.group("em") or _CAPTION_PUNCT.match(rest):
        return True
    return word[:1].isupper()


def _targets(f: _File) -> tuple[list[_Target], list[str]]:
    """The caption and section targets of one file, and the numbers of its H1 (at most one)."""
    out: list[_Target] = []
    h1: list[str] = []
    for i in f.prose():
        if not f.is_text(i) or i in f.opaque or i in f.skip:  # skip: a caption paragraph above
            continue
        ln = f.lines[i]
        h = _HEADING.match(ln)
        text = h.group("text") if h else ln
        html_id = None
        if h:
            prev = next(
                (f.lines[j] for j in range(i - 1, f.start - 1, -1) if f.lines[j].strip()), ""
            )
            a = _ANCHOR_LINE.match(prev)
            html_id = a.group("html_id") if a else None
            if len(h.group("marks")) == 1 and not h1:
                n = _H1_NUM.match(re.sub(r"[*_]", "", text))
                h1.append(_key(n.group("num")) if n else "")
        m = _CAPTION.match(text)
        if (
            m
            and _is_caption(text, m, bool(h))
            and (h or (f.near_block(i) and f.starts_paragraph(i)))
        ):
            end = i if h else f.paragraph_end(i)
            b = _BLOCK_ID.search(f.lines[end])
            t = _Target(
                _kind(m.group("kind")),
                _key(m.group("num")),
                f.name,
                i,
                text if h else None,
                end,
                b.group("id") if b and not h else None,
                html_id or m.group("html_id"),
                "-" in m.group("num"),
            )
            out.append(t)
            f.skip.update(range(i, end + 1))  # the whole caption paragraph
            continue
        if h:
            s = _SECTION_NUM.match(re.sub(r"[*_]", "", text))
            if s:
                out.append(
                    _Target("section", _key(s.group("num")), f.name, i, text, i, None, html_id)
                )
    return out, h1


def _chapter_number(targets: list[_Target], h1: list[str]) -> str | None:
    if h1 and h1[0]:
        return h1[0]
    numbered = [t for t in targets if "." in t.key]  # "Figure 1" in a preface numbers nothing
    majors = {t.key.split(".")[0] for t in numbered}
    if len(numbered) >= 2 and len(majors) == 1:
        return majors.pop()
    return None


_CAPTION_KINDS = ("figure", "table", "listing")


def _scope(kind: str, key: str, file: str) -> str:
    """Where a number is unique. "Figure 7" restarts in each chapter of some books, so a one-part
    caption number is found only in the file that refers to it. Every other number is book-wide."""
    return file if kind in _CAPTION_KINDS and "." not in key else ""


def _anchor_id(t: _Target, style: str) -> str:
    own = t.block_id if style == "obsidian" else t.html_id
    return own or f"{_PREFIX[t.kind]}-{t.key.replace('.', '-')}"


def _destination(t: _Target, style: str) -> str | None:
    """The link destination of target `t`, or None when the style cannot reach it."""
    path = quote(t.file)
    if t.kind == "chapter":
        return path
    if style == "obsidian" and t.heading is not None:
        if _BAD_HEADING.search(t.heading):
            return None
        fragment = " ".join(_URI_RESERVED.sub(" ", t.heading).split())
        return f"{path}#{quote(fragment, safe='')}"
    if style == "obsidian":
        return f"{path}#^{_anchor_id(t, style)}"
    return f"{path}#{_anchor_id(t, style)}"


def _add_anchor(f: _File, t: _Target, style: str) -> bool:
    """Put the anchor of `t` into its file. False when the style's anchor is already there, or when
    the style needs none. Call it from the last target of a file to the first: a heading anchor
    inserts two lines."""
    aid = _anchor_id(t, style)
    if style == "obsidian":
        if t.heading is not None or t.block_id:
            return False  # Obsidian links to a heading by its text
        f.lines[t.end] = f.lines[t.end].rstrip() + f" ^{aid}"
        return True
    if t.html_id:
        return False
    if t.heading is not None:
        block = [f'<a id="{aid}"></a>', ""]
        if t.line - 1 >= f.start and f.lines[t.line - 1].strip():
            block.insert(0, "")  # else the anchor line joins the paragraph above
        f.lines[t.line : t.line] = block
        return True
    ln = f.lines[t.line]
    at = len(ln) - len(ln.lstrip())
    f.lines[t.line] = f'{ln[:at]}<a id="{aid}"></a>{ln[at:]}'
    return True


def _protected(line: str) -> list[tuple[int, int]]:
    spans = [m.span() for m in _PROTECTED.finditer(line)]
    b = _BLOCK_ID.search(line)
    if b:
        spans.append(b.span())
    return spans


def link(files: dict[str, str], style: str) -> tuple[dict[str, str], dict[str, Any]]:
    """Link the cross-references across the chapter files of ONE book.

    `files` maps a file name (as a link names it, relative to the other files) to its text, with LF
    line ends, as Python's text mode reads a file. Returns
    the new texts, in the same order, and a report with counts per kind and the changed file names.
    """
    if style not in STYLES:
        raise ValueError(f"unknown link style {style!r}; use one of {', '.join(STYLES)}")
    report: dict[str, Any] = {
        "style": style,
        **{
            k: dict.fromkeys(KINDS, 0)
            for k in ("linked", "not_found", "ambiguous", "external", "unlinkable")
        },
        "anchors_added": 0,
        "chapters": {},
    }
    parsed = {name: _File(name, text) for name, text in files.items()}

    found: dict[tuple[str, str, str], list[_Target]] = {}
    numbers: dict[str, list[str]] = {}
    for f in parsed.values():
        ts, h1 = _targets(f)
        for t in ts:
            found.setdefault((t.kind, t.key, _scope(t.kind, t.key, t.file)), []).append(t)
        n = _chapter_number(ts, h1)
        if n is not None:
            numbers.setdefault(n, []).append(f.name)
            report["chapters"][f.name] = int(n)
    chapter_of = {name: n for n, names in numbers.items() for name in names}
    for n, names in numbers.items():
        for name in names:
            found.setdefault(("chapter", n, ""), []).append(
                _Target("chapter", n, name, -1, None, -1)
            )

    # A dash in a reference is a range ("sections 2-3"), unless the book numbers that kind with a
    # dash ("Figure 2-1").
    dashed = {t.kind for ts in found.values() for t in ts if t.dashed}

    # Links first: they change single lines only, so every line index found above stays valid.
    for f in parsed.values():
        for i in f.prose():
            ln = f.lines[i]
            if (
                not ln.strip()
                or not f.is_text(i)
                or i in f.opaque
                or i in f.skip
                or _HEADING.match(ln)
                or _LINK_DEFINITION.match(ln)
            ):
                continue
            f.lines[i] = _link_line(ln, f.name, found, chapter_of, style, dashed, report)

    # Anchors last, from the bottom of each file up, because a heading anchor inserts lines.
    picked = [_pick(ts, chapter_of) for ts in found.values() if ts[0].kind != "chapter"]
    for t in sorted((t for t in picked if t), key=lambda t: (t.file, -t.line)):
        if _add_anchor(parsed[t.file], t, style):
            report["anchors_added"] += 1

    out = {name: "\n".join(f.lines) for name, f in parsed.items()}
    report["changed"] = [name for name in files if out[name] != files[name]]
    report["files_changed"] = len(report["changed"])
    return out, report


def _link_line(
    ln: str,
    fname: str,
    found: dict[tuple[str, str, str], list[_Target]],
    chapter_of: dict[str, str],
    style: str,
    dashed: set[str],
    report: dict[str, Any],
) -> str:
    spans = _protected(ln)
    pieces: list[str] = []
    cur = 0
    for m in _REF.finditer(ln):
        if any(a < m.end() and m.start() < b for a, b in spans):
            continue
        kind = _kind(m.group("kind"))
        if _EXTERNAL.match(ln[m.end() :]):
            report["external"][kind] += 1
            continue
        nums = [(m.start("num"), m.end("num"))]
        if m.group("kind").lower().rstrip(".").endswith("s"):  # "figures 6.1 and 6.2"
            # Only numbers of the same shape continue the list: "Figures 6.2, 2019 data" is one.
            parts = len(_key(m.group("num")).split("."))
            base = m.start("more")
            for n in _MORE_NUM.finditer(m.group("more")):
                if len(_key(n.group()).split(".")) != parts:
                    break
                nums.append((base + n.start(), base + n.end()))
        links = []
        for a, b in nums:
            if ("-" in ln[a:b] and kind not in dashed) or _RANGE_DASH.match(ln, b):
                continue  # a range, not a number
            dest = _resolve(kind, _key(ln[a:b]), fname, found, chapter_of, style, report)
            if dest is not None:
                links.append((a, b, dest))
        if not links:
            continue
        if len(nums) == 1:
            a, b, dest = links[0]
            pieces += [ln[cur : m.start()], f"[{ln[m.start() : b]}]({dest})"]
            cur = b
        else:
            for a, b, dest in links:
                pieces += [ln[cur:a], f"[{ln[a:b]}]({dest})"]
                cur = b
    pieces.append(ln[cur:])
    return "".join(pieces)


def _pick(ts: list[_Target], chapter_of: dict[str, str]) -> _Target | None:
    """The one target of a number, or None. Of two targets or more, the one in the file of its
    chapter wins: section 2.1 in chapter 2, not in a table of contents set as headings."""
    if len(ts) == 1:
        return ts[0]
    major = ts[0].key.split(".")[0]
    own = [t for t in ts if "." in t.key and chapter_of.get(t.file) == major]
    return own[0] if len(own) == 1 else None


def _resolve(
    kind: str,
    key: str,
    fname: str,
    found: dict[tuple[str, str, str], list[_Target]],
    chapter_of: dict[str, str],
    style: str,
    report: dict[str, Any],
) -> str | None:
    parts = key.split(".")
    if (kind == "section" and len(parts) < 2) or (kind == "chapter" and len(parts) != 1):
        return None
    ts = found.get((kind, key, _scope(kind, key, fname)), [])
    if not ts:
        report["not_found"][kind] += 1
        return None
    t = _pick(ts, chapter_of)
    if t is None:
        report["ambiguous"][kind] += 1
        return None
    dest = _destination(t, style)
    if dest is None:
        report["unlinkable"][kind] += 1
        return None
    report["linked"][kind] += 1
    return dest


_FM_FIELD = re.compile(r"^(?P<key>book|chapter):[ \t]*(?P<value>.*?)[ \t]*$")


def read_book_dir(path: str) -> dict[str, str]:
    """The chapter files of one book in directory `path`, by file name, in name order.

    A chapter file is a `.md` file whose frontmatter has `book:` and `chapter:`, as `phase5` writes
    it. Other files, such as `<slug>-index.md` or notes, are left out and never changed. Raises
    ValueError when the directory holds no chapter file, or chapter files of more than one book:
    a link must never cross from one book into another.
    """
    out: dict[str, str] = {}
    books: set[str] = set()
    for name in sorted(os.listdir(path)):
        full = os.path.join(path, name)
        if not name.endswith(".md") or not os.path.isfile(full):
            continue
        with open(full, "rb") as fh:
            data = fh.read()
        try:
            text = data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        except UnicodeDecodeError as e:
            if b"book:" in data[:2000] and b"chapter:" in data[:2000]:
                raise ValueError(f"{full} is not UTF-8: {e}") from e
            continue  # not a chapter file, which phase5 always writes as UTF-8
        lines = text.split("\n")
        end = _frontmatter_end(lines)  # 0: no frontmatter, so not a chapter file
        fm = {
            m.group("key"): m.group("value").strip("\"'")
            for m in map(_FM_FIELD.match, lines[1 : end - 1] if end else [])
            if m
        }
        if "book" in fm and "chapter" in fm:
            out[name] = text
            books.add(fm["book"])
    if not out:
        raise ValueError(
            f"{path} holds no chapter file (a .md with `book:` and `chapter:` frontmatter)"
        )
    if len(books) > 1:
        raise ValueError(
            f"{path} holds chapter files of more than one book: {', '.join(sorted(books))}"
        )
    return out


def summary_lines(report: dict[str, Any]) -> list[str]:
    """The human-facing lines of a link report."""
    linked = report["linked"]
    out = [
        f"xref ({report['style']}): {sum(linked.values())} links "
        f"({', '.join(f'{k} {v}' for k, v in linked.items() if v) or 'none'}), "
        f"{report['anchors_added']} anchors added, {report['files_changed']} files changed"
    ]
    for key, label in (
        ("not_found", "no target in the book"),
        ("ambiguous", "two targets or more, left alone"),
        ("external", "another book, left alone"),
        ("unlinkable", "heading text a link cannot carry"),
    ):
        counts = {k: v for k, v in report[key].items() if v}
        if counts:
            out.append(f"  {label}: {', '.join(f'{k} {v}' for k, v in counts.items())}")
    return out
