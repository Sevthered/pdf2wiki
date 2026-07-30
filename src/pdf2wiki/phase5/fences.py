# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

r"""Shared fenced-code-block lexer for the phase-5 steps.

Every phase-5 step that edits code blocks used to carry its own copy of
``^(```)([a-zA-Z]*)\n(.*?)^```` . That pattern cannot match a fence whose info string is not
letters-only (```` ```c++ ````, ```` ```c# ````, ```` ```objective-c ````, ```` ```java {hl} ````),
and the failure is NOT a benign skip: the opener fails to match, so the engine starts matching at
that block's CLOSING fence and pairs it with the NEXT block's opener. Everything in between --
prose included -- is then treated as a code body. Verified consequences: `code_unescape` stripped
markdown escapes out of prose (which its docstring forbids), and `lang_retag` welded a language tag
onto a closing fence, breaking the document structure.

This module replaces those regexes with a line scanner that follows CommonMark's fenced-code rules
closely enough for converter output:

- **opener**: up to 3 spaces/tabs of indent, then >= 3 backticks, then a free-form info string (a
  backtick fence's info string may not contain a backtick, per CommonMark). Backtick-only,
  deliberately narrower than CommonMark: MinerU emits only backtick fences
  (`convert/merge.py`'s `FENCE_LINE` is backtick-only for the same reason — "a `~~~` run is real
  content in console output / ASCII art"), and a **pair** of `~~~~` divider rows in prose used to
  lex as a real block, so `code_unescape`/`dash_normalize` rewrote the prose between them and
  `chapter_split` dropped any chapter boundary inside. A single stray tilde row was already handled
  by the "no matching closer" rule below; a pair was not.
- **closer**: same fence character, at least as long as the opener, nothing but whitespace after.
- an opener with **no matching closer is not a block at all**. CommonMark would render it as code to
  the end of the document, but these callers *rewrite* what they match: letting one stray opener
  claim the document tail made `code_unescape` strip escapes out of prose and `chapter_split`
  swallow every later chapter boundary. Malformed input is left byte-for-byte alone instead. The old
  "pair it with the next fence line" behaviour is gone either way.
- `lang` is the first whitespace-separated token of the info string, lowercased, so a mermaid guard
  is case-insensitive and survives an attribute suffix. Attribute-syntax info strings (`{.python}`)
  keep their braces here -- callers that rewrite the tag must skip them rather than guess.

Blocks come out in document order; :func:`transform` rebuilds the document with every byte outside
a block copied verbatim.
"""

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass

_OPEN = re.compile(r"^([ \t]{0,3})(`{3,})([^\n]*)$")
_CLOSE = re.compile(r"^[ \t]{0,3}(`{3,})[ \t]*$")


def _closes(line: str, fence: str) -> bool:
    """True if `line` is a closing fence for an opener made of `fence`."""
    m = _CLOSE.match(line)
    if m is None:
        return False
    return len(m.group(1)) >= len(fence)


@dataclass(frozen=True)
class Block:
    """One fenced code block found in a markdown document. Always closed.

    `raw` is the block's exact source text (opener line through closing fence, no trailing
    newline), so `md[offset:offset + len(raw)] == raw`. `body` is the text between the fences and
    ends with a newline unless the block is empty -- the shape the phase-5 line transforms expect.
    """

    indent: str
    fence: str
    info: str
    body: str
    closer: str  # closing fence line verbatim
    raw: str
    offset: int  # character offset of the opener in the source document
    start: int  # line index of the opener
    end: int  # line index of the closer

    @property
    def lang(self) -> str:
        """First token of the info string, lowercased (`""` when there is none)."""
        tok = self.info.strip().split()
        return tok[0].lower() if tok else ""

    @property
    def is_mermaid(self) -> bool:
        return self.lang == "mermaid"

    def rebuild(self, body: str | None = None, lang: str | None = None) -> str:
        """Re-emit this block, optionally with a new body and/or first info-string token.

        Indent, fence run, and any info-string remainder after the language token are preserved,
        so `rebuild()` with no arguments returns `raw` byte-for-byte.
        """
        info = self.info
        if lang is not None:
            rest = self.info.strip().split(None, 1)
            info = lang + (" " + rest[1] if len(rest) > 1 else "")
        new_body = self.body if body is None else body
        return f"{self.indent}{self.fence}{info}\n{new_body}{self.closer}"


def blocks(md: str) -> Iterator[Block]:
    """Yield every CLOSED fenced code block in `md`, in document order.

    An opener with no matching closer is skipped and scanning resumes on the line after it, so a
    stray fence cannot make the rest of the document look like code.
    """
    lines = md.split("\n")
    offsets: list[int] = []
    pos = 0
    for ln in lines:
        offsets.append(pos)
        pos += len(ln) + 1

    n = len(lines)
    i = 0
    while i < n:
        m = _OPEN.match(lines[i])
        if not m:
            i += 1
            continue
        indent, fence, info = m.groups()
        if "`" in info:  # CommonMark: no backtick in a backtick fence's info string
            i += 1
            continue
        j = i + 1
        while j < n and not _closes(lines[j], fence):
            j += 1
        if j >= n:  # unclosed: not a block. Resume after the opener, never claim the tail.
            i += 1
            continue
        yield Block(
            indent=indent,
            fence=fence,
            info=info,
            body="".join(ln + "\n" for ln in lines[i + 1 : j]),
            closer=lines[j],
            raw="\n".join(lines[i : j + 1]),
            offset=offsets[i],
            start=i,
            end=j,
        )
        i = j + 1


def transform(md: str, fn: Callable[[Block], str | None]) -> str:
    """Rewrite each code block with `fn`; `None` leaves that block byte-identical."""
    pieces: list[str] = []
    cur = 0
    for blk in blocks(md):
        rep = fn(blk)
        if rep is None:
            continue
        pieces.append(md[cur : blk.offset])
        pieces.append(rep)
        cur = blk.offset + len(blk.raw)
    pieces.append(md[cur:])
    return "".join(pieces)


def code_lines(lines: list[str]) -> set[int]:
    """Indices of lines that belong to a fenced code block, fence lines included.

    Line-oriented callers (chapter_split) use this instead of toggling on `^```` , which
    mis-tracks tilde fences, longer fence runs, and any info string it cannot parse.
    """
    out: set[int] = set()
    for blk in blocks("\n".join(lines)):
        out.update(range(blk.start, blk.end + 1))
    return out
