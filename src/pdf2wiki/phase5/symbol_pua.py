# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

r"""Remap Private-Use-Area glyphs that publisher PDFs emit for Symbol-font characters.

Several publisher templates embed a ``SymbolMT`` subset (the Manning books in this corpus all do,
and two slots come from the Wingdings family instead) and emit its glyphs as **Private Use Area**
codepoints with **no ``ToUnicode`` map**. `pymupdf` returns the PUA codepoint verbatim and MinerU
carries it straight into the markdown, where it is **invisible** -- it has no glyph in any normal
font, so a terminal, a diff and a reader all see nothing:

    ground truth   "if you rotate 360 degrees or 2\N{GREEK SMALL LETTER PI} radians"
    converted      "if you rotate 360 degrees or 2\uf070 radians"    # renders as "2 radians"

``2\N{GREEK SMALL LETTER PI} radians`` reading as ``2 radians`` is grammatical, plausible, and false
-- no coverage gate, lint or token-verify can see it. Both converter backends produce it, because
both read the same embedded text layer for running prose, so no backend choice avoids it.

That the codepoint **survives** is what makes this step possible: the information was never lost, so
the repair is a deterministic remap rather than a re-conversion.

**The table is ground truth, not the font spec.** Every entry below was verified by rendering the
source page and reading the printed character. That distinction is not academic: ``U+F0E5`` occupies
Adobe Symbol's *summation* slot (U+2211), but the book that uses it prints a capital Sigma ("given
an alphabet \N{GREEK CAPITAL LETTER SIGMA} with |\N{GREEK CAPITAL LETTER SIGMA}|=k symbols",
*Advanced Algorithms and Data Structures* p209). Deriving the mapping from the encoding table alone
would have written the wrong character. **Do not add an entry here without rendering the page it
came from.**

Unrecognised PUA codepoints are deliberately **left untouched** and reported, so the next book's
glyphs get verified rather than guessed.

Two consequences of "render it, don't derive it" that the table makes visible:

- **Distinct codepoints can print the same character.** ``U+F0B7`` (4 pt, between vectors) and
  ``U+F0D7`` (10 pt, inside a radical) both print a centered multiplication dot in *Math for
  Programmers*, so both map to ``MIDDLE DOT``. ``U+F053`` and ``U+F0E5`` likewise both print a
  capital Sigma, in two different books.
- **Not every entry is a letter.** ``U+F020`` is a Symbol-font *space*, ``U+F028``/``U+F029`` are
  Symbol-font parentheses inside a formula, and ``U+F0FC`` is the check mark a terminal transcript
  prints. Restoring them as the characters they print is what keeps the sentence readable; leaving
  them is what turns ``sqrt(4^2 + 3^2)`` into ``sqrt4^2 + 3^2``.

Where Unicode offers a glyph variant, the entry follows the corpus rather than the typeface: the
phi printed by ``U+F066`` is the straight variant (``U+03D5``), but it maps to ``U+03C6``, the phi
the rest of the converted vault already carries, so one search finds both.

.. warning::

   **The table is keyed by codepoint alone, and the corpus already spans more than one embedded
   font.** Seventeen entries come from a ``SymbolMT`` subset and two from ``Symbol``, and two slots
   are Wingdings-family: ``U+F0FC`` (check mark, *Mastering Blockchain* p511,
   ``Wingdings-Regular``) and ``U+F0A1`` (the list marker, *Deep Learning with Python*,
   ``Wingdings2``). PUA codepoints are only meaningful relative to the font that emitted them, so a
   book embedding a *different* font that reuses one of these slots would be rewritten with the
   wrong character.

   **That collision exists in this corpus, and MinerU absorbs it.** A sweep of all 80 corpus PDFs
   found ``U+F020`` emitted by ``BookAntiqua`` in *Developing IoT Projects with ESP32* p89, where
   the page prints an **ohm sign**, not a space -- and ``U+F0B7`` emitted by ``Symbol`` in *C data
   structures and algorithms*, 132 times, every one of them opening a bulleted line.

   **The ohm case was measured and does not reach this step**: a conversion of those ESP32 pages
   yields **no PUA codepoint at all and a real ohm sign**, because MinerU resolves a fully embedded
   font through its own encoding. What leaks is the ``SymbolMT`` *subset* with no ``ToUnicode``
   map. ⚠ **Nothing is claimed about the C book, which has never been converted.** Its 132 dots are
   a PDF-level reading. If that book is converted and they survive, they arrive as line-opening
   ``U+F0B7`` and this step defers and counts every one of them, which is the outcome :data:`DOT`
   describes. **Measure the converted markdown, not the PDF: this step reads MinerU's output, and a
   PDF-level scan overstates what it ever sees.**

   Every entry is annotated with the book, the page and now the font it was read from, precisely so
   that collision stays traceable. The durable fix is to key on the embedded font name, which needs
   font information MinerU does not currently carry into the markdown.

``U+F0A1`` is a list *marker*, not a character -- restoring it as a bullet glyph would leave the
list structure lost, so a line that starts with it becomes a real markdown list item. It prints a
small filled square (*Deep Learning with Python* p197, ``Wingdings2``). ⚠ *Advanced Algorithms*
p494 uses a **second** marker, ``U+F077`` in ``Wingdings``, which this step does not read: that slot
is *omega* in Adobe Symbol encoding, so reading it as a bullet needs guards this step does not
carry, and it is reported under ``unknown`` instead. See the branch
``feat/phase5-second-list-marker``. Two shapes need care, both confirmed against rendered pages:

- ``*<PUA> Dense layer with relu activation: ...`` -- MinerU emitted the emphasis opener *before*
  the bullet (*Deep Learning with Python* p71 prints a bulleted, italicised lead-in). The stray,
  unclosed ``*`` is dropped along with the marker.
- ``## <PUA> With temperature=0.2`` -- MinerU promoted a bullet to a heading (*Deep Learning with
  Python* p399 prints it as a list item under "Here are some cherrypicked examples"). This step
  **only strips the glyph and keeps the heading level**; demoting ``##`` to ``-`` would restructure
  a document whose chapters are already split and whose headings may be link targets. The count is
  reported as ``heading_markers`` so the residue stays visible rather than silently accepted.

Everything this step does is scoped **outside fenced code blocks**. A marker at the start of a line
of console output must not become a markdown list item, and a PUA codepoint inside a code block is
content we must not silently rewrite -- it is reported under ``unknown`` instead.

Idempotent: after a pass no mapped PUA codepoint remains outside code, so a second pass is a no-op.
"""

import re
from collections import Counter

from . import fences

#: PUA codepoint -> replacement. EVERY entry verified against a rendered source page.
#: See the module docstring before adding one.
#:
#: Keys are written as ``\uXXXX`` escapes rather than as the literal characters: a literal is
#: invisible in an editor, a diff and a review, which is the very property that makes this defect
#: class hard to see. **Page numbers are 1-based PDF pages, not the page label the book prints** --
#: `math.pdf` p87 carries the printed label "55". Open the PDF at that page to re-verify an entry.
#: The name in brackets is **the font that emitted the codepoint**, measured on that page. A PUA
#: codepoint means nothing without it: the same slot in another font is another character, so a
#: future collision is traceable only if every row says which font it was read from.
GLYPHS: dict[str, str] = {
    "\uf020": " ",  # Math for Programmers p677, index line "<pi> (pi) symbol 56" -- a Symbol space  [SymbolMT]
    "\uf028": "(",  # Math for Programmers p118, "sqrt(4^2 + 3^2)" -- a Symbol-font paren  [SymbolMT]
    "\uf029": ")",  # Math for Programmers p118, the closer of the same pair  [SymbolMT]
    "\uf053": "\N{GREEK CAPITAL LETTER SIGMA}",  # Math p314, "the summation symbol Sigma"  [SymbolMT]
    "\uf061": "\N{GREEK SMALL LETTER ALPHA}",  # Math p480, "where a (the Greek letter alpha)"  [SymbolMT]
    "\uf066": "\N{GREEK SMALL LETTER PHI}",  # Math p120, "with the Greek letter f (phi)"  [SymbolMT]
    "\uf06c": "\N{GREEK SMALL LETTER LAMDA}",  # Math p654, "the Greek letter l, written lambda"  [SymbolMT]
    "\uf070": "\N{GREEK SMALL LETTER PI}",  # Math for Programmers p504, "or 2pi radians"  [SymbolMT]
    "\uf071": "\N{GREEK SMALL LETTER THETA}",  # Math p87, "an angle q (the Greek letter theta)"  [SymbolMT]
    "\uf0a5": "\N{INFINITY}",  # Mastering Blockchain p699, footnote marker "oo TPS results for"  [SymbolMT]
    "\uf0ae": "\N{RIGHTWARDS ARROW}",  # Microservices Patterns p440, "Service -> Source Envoy"  [Symbol]
    "\uf0b4": "\N{MULTIPLICATION SIGN}",  # Math p211, "a 3x3 matrix or a 3x1 matrix"  [SymbolMT]
    "\uf0b7": "\N{MIDDLE DOT}",  # Math p80, "points where r.u + s.v could end up"  [SymbolMT]
    "\uf0b9": "\N{NOT EQUAL TO}",  # Math p182, "T(0) != 0, where 0 represents ..."  [SymbolMT]
    "\uf0ba": "\N{IDENTICAL TO}",  # Math p444, "I use the = sign to indicate ... equivalent"  [SymbolMT]
    "\uf0bb": "\N{ALMOST EQUAL TO}",  # Math p86, "tan(37 deg) ~= 3/4"  [SymbolMT]
    "\uf0d1": "\N{NABLA}",  # Math p446, "its gradient and written grad-U"  [SymbolMT]
    "\uf0d7": "\N{MIDDLE DOT}",  # Math p133, "its length is sqrt(a.a + b.b + ...)"  [SymbolMT]
    "\uf0e5": "\N{GREEK CAPITAL LETTER SIGMA}",  # Advanced Algorithms p209, "an alphabet Sigma"  [Symbol]
    "\uf0fc": "\N{CHECK MARK}",  # Mastering Blockchain p511, terminal log "ok Preparing to down"  [Wingdings-Regular]
}

#: List markers, handled structurally rather than as characters; see the module docstring. Each was
#: read from a rendered page, and the font is part of the reading: the same slot in another font is
#: another character. Written as a string because the regexes below use it as a character class.
BULLET = "\uf0a1"  # Deep Learning with Python p197 / p399 / p71, Wingdings2

#: A Symbol-font *space*. It is in :data:`GLYPHS`, but it is also whitespace, and the structural
#: passes below test for real whitespace -- ``"\uf020".isspace()`` is ``False``. It is therefore
#: substituted before them, so a bullet separated from its text by one of these is still seen as a
#: bullet rather than left in place as an invisible codepoint.
SPACE = "\uf020"

#: Every reading of this codepoint verified so far is an inline multiplication dot (*Math for
#: Programmers* p80, set at 4 pt between two vectors). At the START of a line the same glyph is what
#: a publisher template uses for a list bullet, and no rendered page in the corpus shows that case --
#: so it is **left alone and counted**, never rewritten. Restoring it as a middle dot there would
#: flatten a list into paragraphs, and reported as a successful change; that is the exact silent
#: rewrite this module refuses to make for :data:`BULLET` on the same grounds.
#:
#: ⚠ One book *does* print a bullet in this slot: *C data structures and algorithms* opens 132 lines
#: with this codepoint in the ``Symbol`` font. That book is not converted, the reading is per-book
#: rather than per-codepoint, and settling it is a judgment this step will not make on its own -- so
#: the count is **reported** as ``line_leading_dot_deferred`` and the line is left alone.
DOT = "\uf0b7"

_PUA_CLASS = "[\ue000-\uf8ff]"
_PUA = re.compile(_PUA_CLASS)

# A line-opening DOT, which this module deliberately does not interpret; see :data:`DOT`.
# ⚠ The indent is UNBOUNDED here, unlike `_LIST_MARKER`'s CommonMark three-space limit. This is a
# refusal, not a list-recognition rule: a `{0,3}` bound made the deferral quietly stop applying to a
# nested list item, so `    <DOT> Chunked transfer encoding` was rewritten to a middle dot and
# reported as a repair -- the one rewrite :data:`DOT` says this module must never make.
_LEADING_DOT = re.compile(r"^[ \t]*\*?" + DOT)

# A bullet marker opening a line, optionally behind a stray emphasis opener MinerU misplaced.
_LIST_MARKER = re.compile(r"^([ \t]{0,3})\*?" + BULLET + r"[ \t]+")
# The same marker after a heading's hashes, where MinerU promoted a list item to a heading.
_HEADING_MARKER = re.compile(r"^([ \t]{0,3}#{1,6})[ \t]*" + BULLET + r"[ \t]+")


def _strip_stray(ln: str, stats: Counter[str]) -> str:
    """Drop a bullet marker left mid-line, WITHOUT ever joining two words.

    An earlier version matched ``<marker>[ \\t]*`` and so ate the marker together with the only
    whitespace separating two real words -- ``"word<PUA> next"`` became ``"wordnext"``, reported as
    a successful fix. That is precisely the silent-corruption failure class this module exists to
    remove, so the rule is now explicit and conservative:

    * remove the marker only when it already touches whitespace (or a line edge) on some side, so
      the words around it stay separated;
    * when it sits flush between two non-space characters there is no way to know whether it was a
      separator or a decoration -- **leave it alone** and count it as ``stray_unhandled``, the same
      "don't guess" rule the GLYPHS table follows;
    """
    if BULLET not in ln:
        return ln
    out: list[str] = []
    i = 0
    while i < len(ln):
        if ln[i] != BULLET:
            out.append(ln[i])
            i += 1
            continue
        before = out[-1] if out else ""
        after = ln[i + 1] if i + 1 < len(ln) else ""
        if not (before.isspace() or after.isspace()):
            stats["stray_unhandled"] += 1  # never guess: no safe reading
            out.append(ln[i])
            i += 1
            continue
        stats["stray_markers"] += 1
        i += 1
        # If whitespace already survives on the left, drop one space on the right so removing an
        # isolated marker cannot leave a double space behind.
        if after == " " and before.isspace():
            i += 1
    return "".join(out)


def _remap_line(ln: str, stats: Counter[str]) -> str:
    """Substitute the verified glyphs in one line, with two exceptions the table cannot express.

    ``SPACE`` at a line edge is **dropped rather than spaced**: two of them at end of line would
    render as a CommonMark hard break, which is structure the printed page does not have. ⚠ It does
    NOT save a paragraph from splitting -- a line holding one Symbol space and nothing else is blank
    to CommonMark whether the space is deleted or substituted, so that half of the original
    reasoning was wrong. Dropping keeps the line honest rather than changing how it renders.

    A line-opening ``DOT`` is left in place and counted; see :data:`DOT` for why guessing there is
    the one rewrite this module must not make.

    ``SPACE`` is handled **before** the ``DOT`` split, and the order is load-bearing in both
    directions. Splitting first made the space that follows a deferred dot look line-*leading*, so
    ``strip`` deleted it and ``<DOT><SPACE>Text`` came out as ``<DOT>Text`` -- an edit to the very
    line this function promises to leave alone. Handling ``SPACE`` first also lets a ``SPACE``
    *before* the dot reach the deferral at all, which ``_LEADING_DOT`` cannot match, because a
    Symbol-font space is not ``[ \\t]``.
    """
    if SPACE in ln:
        # The edge runs are found through REAL whitespace as well: a Symbol space sitting behind an
        # ordinary one is still at the edge of the line, and substituting it there produces the two
        # structures this drop exists to prevent -- "x<SPACE> " becomes two trailing spaces, which
        # CommonMark reads as a hard break.
        start, stop = 0, len(ln)
        while start < stop and (ln[start].isspace() or ln[start] == SPACE):
            start += 1
        while stop > start and (ln[stop - 1].isspace() or ln[stop - 1] == SPACE):
            stop -= 1
        head, body, tail = ln[:start], ln[start:stop], ln[stop:]
        dropped = head.count(SPACE) + tail.count(SPACE)
        if dropped:  # at an edge it is deleted, not spaced -- counted apart from a substitution
            stats["dropped_f020"] += dropped
        if SPACE in body:
            stats["remap_f020"] += body.count(SPACE)
        ln = head.replace(SPACE, "") + body.replace(SPACE, " ") + tail.replace(SPACE, "")

    head = ""
    m = _LEADING_DOT.match(ln)
    if m:
        stats["line_leading_dot_deferred"] += 1  # never guess: bullet or dot, per-book judgment
        head, ln = ln[: m.end()], ln[m.end() :]

    for pua, real in GLYPHS.items():
        if pua == SPACE:
            continue  # already handled, edge-aware, above
        n = ln.count(pua)
        if n:
            stats["remap_" + f"{ord(pua):04x}"] += n
            ln = ln.replace(pua, real)
    return head + ln


def _fix_prose(text: str, stats: Counter[str]) -> str:
    """Apply every rewrite to a run of text that is known to be outside a code block.

    ``_remap_line`` runs **first**: the structural passes below all test for real whitespace, and a
    Symbol-font space is not whitespace, so a bullet separated from its text by one would otherwise
    be left in the output as an invisible codepoint and its list item lost.
    """
    out = []
    for ln in text.split("\n"):
        remapped = _remap_line(ln, stats)
        new = _HEADING_MARKER.sub(r"\1 ", remapped)
        if new != remapped:
            stats["heading_markers"] += 1
        else:
            new = _LIST_MARKER.sub(r"\1- ", remapped)
            if new != remapped:
                stats["list_markers"] += 1
        new = _strip_stray(new, stats)
        out.append(new)
    return "\n".join(out)


def remap(md: str) -> tuple[str, dict[str, object]]:
    """Return ``(new_md, stats)``.

    ``stats`` carries the per-codepoint replacement counts, the structural marker counts, and two
    distinct residues -- conflating them would hide a real signal behind a benign one:

    ``in_code``
        A codepoint that IS in :data:`GLYPHS`, left alone only because it sits inside a fenced code
        block. Benign and expected (MinerU sometimes sweeps a bulleted list into a fence). Nothing
        to verify; the open question is whether to rewrite code content at all, which is a caller's
        decision, not this step's.
    ``unknown``
        A codepoint this module has never seen. **This is the one that needs a human**: render the
        source page, confirm what it prints, then extend :data:`GLYPHS`.
    ``dropped_f020``
        A :data:`SPACE` at a line edge, **deleted** rather than substituted, because two of them at
        a line end are a CommonMark hard break. It is an edit, so
        it counts toward ``total_changes`` -- but not as ``remap_f020``, which would say the step
        put a space where the page prints one.
    ``line_leading_dot_deferred``
        A :data:`DOT` opening a line, left in place because whether it is a bullet or a dot there is
        a per-book reading this step will not guess: it is verified as an inline dot in one book and
        printed as a bullet in another. Also needs a human, for the same reason ``unknown`` does; it
        is counted separately only because the codepoint itself IS verified inline.
    """
    stats: Counter[str] = Counter()

    # `fences.blocks()` is LF-only: its `_CLOSE` pattern allows no trailing `\r`, so a CRLF
    # document yields ZERO blocks and every code block would be treated as prose — this step would
    # then rewrite bullets and glyphs *inside* code. Since this is the first step whose edits are
    # scoped to prose — `illegal_codepoints` runs before it, but is fence-agnostic and so has no
    # LF dependency — refuse rather than corrupt. MinerU emits LF, so this is a guard, not a path.
    if "\r\n" in md:
        return md, {
            "list_markers": 0,
            "heading_markers": 0,
            "stray_markers": 0,
            "stray_unhandled": 0,
            "line_leading_dot_deferred": 0,
            "dropped_f020": 0,
            "in_code": {},
            "unknown": {},
            "total_changes": 0,
            "skipped_crlf": True,
        }

    pieces: list[str] = []
    cur = 0
    code_spans: list[tuple[int, int]] = []
    for blk in fences.blocks(md):
        pieces.append(_fix_prose(md[cur : blk.offset], stats))
        pieces.append(blk.raw)  # code blocks copied byte-for-byte
        code_spans.append((blk.offset, blk.offset + len(blk.raw)))
        cur = blk.offset + len(blk.raw)
    pieces.append(_fix_prose(md[cur:], stats))
    out = "".join(pieces)

    known = set(GLYPHS) | {BULLET}
    in_code: Counter[str] = Counter()
    unknown: Counter[str] = Counter()
    for m in _PUA.finditer(md):
        ch = m.group()
        inside = any(s <= m.start() < e for s, e in code_spans)
        if ch in known and inside:
            in_code[f"{ord(ch):04x}"] += 1
        elif ch not in known:
            unknown[f"{ord(ch):04x}"] += 1

    # Structural keys are always present so callers can read them without a KeyError guard.
    report: dict[str, object] = {
        "list_markers": 0,
        "heading_markers": 0,
        "stray_markers": 0,
        "stray_unhandled": 0,
        "line_leading_dot_deferred": 0,
        "dropped_f020": 0,
        "skipped_crlf": False,
    }
    report.update(stats)
    report["in_code"] = dict(in_code)
    report["unknown"] = dict(unknown)
    # `stray_unhandled` and `line_leading_dot_deferred` count glyphs deliberately LEFT IN PLACE —
    # not changes. Counting them would make a refusal to guess read as a successful repair.
    deliberate = {"stray_unhandled", "line_leading_dot_deferred"}
    report["total_changes"] = sum(v for k, v in stats.items() if k not in deliberate)
    return out, report
