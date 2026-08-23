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

``U+F0A1`` and ``U+F077`` are list *markers*, not characters -- restoring either as a bullet glyph
would leave the list structure lost, so a line that starts with one becomes a real markdown list
item. ``U+F0A1`` prints a small filled square (*Deep Learning with Python* p197, ``Wingdings2``;
*Advanced Algorithms* opens 786 lines with it, every one ``Wingdings2``), and ``U+F077`` a small
filled diamond (*Advanced Algorithms* p494, ``Wingdings``, "◆ Each reducer will compute the center
of mass of its cluster"). ⚠ Both slots are also Greek letters in Adobe Symbol encoding (``0x77`` is
*omega*, ``0xA1`` is *Upsilon1*), and the corpus's largest PUA source emits Symbol-font text from
exactly that block, so two guards apply. A marker is read as a bullet only where what follows reads
as TEXT -- a marker followed by an operator is a display formula whose first letter is Greek, and
it is left in place and counted. And only ``U+F0A1`` may be DELETED mid-line: that reading has a
rendered page behind it (*Deep Learning with Python*, where MinerU leaves the marker inside a
sentence), ``U+F077`` has none, so mid-line it is kept and counted as ``marker_no_reading``.
Two further shapes need care, both confirmed against rendered pages:

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
from enum import Enum

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
BULLET = "\uf0a1"  # Deep Learning with Python p197 / p399 / p71, Wingdings2; Advanced Algorithms
DIAMOND = "\uf077"  # Advanced Algorithms p494, Wingdings

#: Every marker the structural passes read. A string, because :func:`_fix_line` tests membership
#: one character at a time.
BULLETS = BULLET + DIAMOND

#: The markers :func:`_fix_line` may DELETE when one survives mid-line. Being a list marker at the
#: start of a line says nothing about the same codepoint in the middle of one, and each marker slot
#: is a Greek letter in Adobe Symbol encoding. Only :data:`BULLET` has a rendered page behind the
#: mid-line reading; every other marker is left in place there and counted as ``marker_no_reading``.
STRIPPABLE = BULLET

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

#: CommonMark reads four columns of indent as an indented code block, so a marker that deep cannot
#: open a list item. Three columns is the last indent a list item accepts.
_INDENT_LIMIT = 3

#: CommonMark advances a tab to the next multiple of four columns.
_TAB_STOP = 4

#: A left context that is nothing but indent, with at most one emphasis opener ADJACENT to the
#: marker. MinerU misplaces such an opener ahead of a bullet, and ``*<PUA> Dense layer with relu
#: activation`` is a shape from a rendered page (*Deep Learning with Python* p71). The opener must
#: TOUCH the marker: ``* <PUA> item`` is a real Markdown bullet followed by a stray marker, which is
#: a different line and reads as :data:`Pos.SEPARATOR`.
_OPEN_LEFT = re.compile(r"^([ \t]*)\*?$")

#: A left context of a heading's hashes, where MinerU promoted a list item to a heading.
_HEAD_LEFT = re.compile(r"^([ \t]*)(#{1,6})[ \t]*$")

#: Characters that cannot begin the text of a list item, and CAN begin the right-hand side of a
#: display formula. A marker opening a line is read as a bullet only when what follows reads as
#: text: every marker slot is also a Greek letter in Adobe Symbol encoding, and a book that sets
#: ``ω = ...`` on its own line would otherwise have the letter deleted and the formula turned into a
#: list item -- reported as a repair. Refusing here costs a real bullet nothing: the line is left
#: alone and counted instead.
#:
#: **Priced against the corpus, not chosen from a keyboard.** ``<`` and ``>`` were in this set and
#: had to come out: they cost **6 real list items** in *Microservices Patterns*, whose bullets open
#: with an HTML tag MinerU emits (``<PUA> <sub>REST</sub> <sub>client</sub> ...``). And a bullet
#: BEFORE a formula is a real list item in this corpus -- *Advanced Algorithms* p445 prints a square
#: bullet ahead of ``d*(n+k)*log(k) < n*k*d ⇔ ...`` -- so the set holds only characters that cannot
#: open a sentence, never anything that merely looks mathematical. ⚠ ``·`` is NOT in the set: it is
#: what :data:`DOT` becomes, and :func:`_remap_line` runs first, so a bullet followed by a verified
#: inline dot would have been refused as a list item. With this set the marker counts across all
#: 219 converted files are unchanged.
_NOT_LIST_TEXT = frozenset("=≈≠≡±×÷→←↔⇒⇔∇≤≥∈∉∞")


class Pos(Enum):
    """Where a marker sits on its line.

    This module reads one concept -- a marker -- in five position-dependent ways, and the position
    decides the answer in every rule. Those five readings used to live in three anchored regexes and
    two branches of a character walk, so every change to one of them meant five separate decisions.
    Nine fresh-context review rounds found the same shape of defect again and again: a caution added
    where the author was looking, and not where the same constant is read next door.

    The reading is :func:`classify` alone now, and what each reading MEANS is the :data:`_ACTIONS`
    table, so a position is decided in one place.

    ``HEADING``
        After a heading's hashes, inside the indent limit, with a gap ahead of it.
    ``LIST``
        Opening the line inside the indent limit, with a gap ahead of it.
    ``LINE_OPEN``
        Nothing but indent to its left, yet not readable as a list item -- too deeply indented, or
        with no gap after it. Left in place: a deletion is not a list-recognition rule either.
    ``SEPARATOR``
        Real whitespace survives on one side, so removing the marker cannot join two words.
    ``FLUSH``
        Flush between two non-space characters, where a separator and a decoration look the same.
    ``UNREAD``
        Not at a line-opening position, and not a marker in :data:`STRIPPABLE`: verified as a
        bullet at a line start only, so there is no reading for it here, and it may be a Greek
        letter the table should carry rather than a marker at all.
    """

    HEADING = "heading"
    LIST = "list"
    LINE_OPEN = "line_open"
    SEPARATOR = "separator"
    FLUSH = "flush"
    UNREAD = "unread"


#: What each position means: the counter it raises, and whether the marker SURVIVES the pass. The
#: two line-opening classes also rewrite the prefix they sit in, which is the one action a table
#: cannot carry, so :func:`_fix_line` handles that part.
#:
#: The three positions that keep a marker are the module's refusals. They are counted apart from the
#: repairs, and :func:`remap` keeps them out of ``total_changes``, so a refusal to guess never reads
#: as a successful repair.
_ACTIONS: dict[Pos, tuple[str, bool]] = {
    Pos.HEADING: ("heading_markers", False),
    Pos.LIST: ("list_markers", False),
    Pos.LINE_OPEN: ("line_leading_marker_deferred", True),
    Pos.SEPARATOR: ("stray_markers", False),
    Pos.FLUSH: ("stray_unhandled", True),
    Pos.UNREAD: ("marker_no_reading", True),
}


def _columns(indent: str) -> int:
    r"""Return the width of ``indent`` in COLUMNS, the unit CommonMark measures an indent in.

    A tab is ONE character and FOUR columns. The patterns this function replaces counted characters,
    so ``\t<PUA> nested`` was rewritten as a list item although the marker stands at column 4, where
    CommonMark reads an indented code block rather than a list. ``\t- nested`` and ``     nested``
    sit at the same column, and only one of them was rewritten.
    """
    col = 0
    for ch in indent:
        col += _TAB_STOP - (col % _TAB_STOP) if ch == "\t" else 1
    return col


def classify(left: str, right: str, *, opened: bool = False, strippable: bool = True) -> Pos:
    """Return where a marker sits, from the text emitted before it and the text still ahead of it.

    ``strippable`` says the marker may be deleted mid-line (:data:`STRIPPABLE`), and it is the
    marker with a rendered HEADING page behind it. Any other marker is verified as a list item at a
    line start only, so it is read in three ways, all of which keep it: :data:`Pos.LIST` where the
    verified reading applies, :data:`Pos.LINE_OPEN` after hashes or where the list test fails, and
    :data:`Pos.UNREAD` anywhere else. The per-reading evidence rule of :data:`GLYPHS` applies to
    the structural readings too: a list page does not verify a heading reading.

    ⚠ That is also what keeps the chain's SECOND pass from deleting such a marker. The heading
    action leaves ``# <M> `` behind when a second, kept marker follows the gap, and a heading path
    that read the kept marker on the next run would delete what the first run reported as left in
    place.

    ⚠ ``left`` is what the pass has ALREADY EMITTED, not the input to the left of the marker. A
    marker whose neighbour a previous deletion removed stands next to whatever that deletion
    uncovered, and reading the input instead would call ``a <M><M>b`` flush and keep a codepoint the
    step deletes today.

    ⚠ ``opened`` says an earlier marker on this line was already read, **however it was read**. A
    line opens once. The walk this function replaced had the same rule -- its ``line_open`` flag went
    false at the first marker whatever branch took it -- and the anchored patterns it replaced got it
    for free by running a single time. Without the flag a second marker opens the line again: the
    heading action leaves ``# `` behind, which is itself a valid heading prefix, so ``#<M>   <M> ``
    counted TWO promoted headings on one heading and normalised the trailing whitespace twice.

    The order of the tests is load-bearing. The line-opening tests run FIRST, because in column 0
    ``left`` is ``""`` and ``"".isspace()`` is ``False``, so the flush test wins there and reports a
    line-opening marker as a mid-word one -- which sends the operator to look for a word join that
    is not on the line. A line edge is not whitespace to the separator rule.

    ⚠ ``right`` must reach past the gap: the text test reads the first character AFTER the
    whitespace, and ``[ \t]+`` would backtrack to one space and then inspect a space, which is not
    an operator -- the guard passes and the formula becomes a list item. One space hid it.
    """
    if opened:
        pos = Pos.SEPARATOR if left[-1:].isspace() or right[:1].isspace() else Pos.FLUSH
        return pos if strippable else Pos.UNREAD

    gap = right[:1] in (" ", "\t")
    text = right.lstrip(" \t")[:1] not in _NOT_LIST_TEXT  # "" passes: an empty item is still one
    head = _HEAD_LEFT.match(left)
    if head is not None:
        if _columns(head.group(1)) <= _INDENT_LIMIT and gap:
            return Pos.HEADING if text and strippable else Pos.LINE_OPEN
        if not strippable:
            return Pos.LINE_OPEN  # opens the line after hashes, and no reading deletes it there
        # Hashes too deep to be a heading, or no gap after the marker. The line is not a heading, so
        # the marker is read by position alone, below.
    else:
        open_left = _OPEN_LEFT.match(left)
        if open_left is not None:
            if _columns(open_left.group(1)) <= _INDENT_LIMIT and gap and text:
                return Pos.LIST
            return Pos.LINE_OPEN

    if not strippable:
        return Pos.UNREAD
    if left[-1:].isspace() or right[:1].isspace():
        return Pos.SEPARATOR
    return Pos.FLUSH


def _opening_prefix(left: str, pos: Pos) -> str:
    """Return the prefix that REPLACES ``left`` when the marker there opens a heading or a list.

    A heading keeps its level and loses the marker: demoting ``##`` to ``-`` would restructure a
    document whose chapters are already split and whose headings may be link targets. A list item
    keeps its indent, loses the misplaced emphasis opener, and gains a real ``-``. Both normalise
    the gap that follows to a single space.
    """
    if pos is Pos.HEADING:
        return left.rstrip(" \t") + " "  # keep the indent and the hashes, normalise the gap
    return left.rstrip("*") + "- "  # keep the indent, drop the emphasis opener MinerU misplaced


def _fix_line(ln: str, stats: Counter[str]) -> str:
    r"""Act on every bullet marker in one line, once per position, through the :data:`_ACTIONS` table.

    Removing a marker must NEVER join two words. An earlier version matched ``<marker>[ \t]*`` and
    ate the marker together with the only whitespace between two real words -- ``"word<PUA> next"``
    became ``"wordnext"``, and it was reported as a successful fix. That is the silent-corruption
    class this module exists to remove, so a marker is deleted only where :func:`classify` reads a
    separator, which needs real whitespace to survive on one side of it.

    Where whitespace already survives on the LEFT, one space is dropped on the right as well, so
    removing an isolated marker cannot leave a double space behind.
    """
    if not any(b in ln for b in BULLETS):
        return ln
    out: list[str] = []
    i = 0
    opened = False  # a line opens once, however the marker that opened it was read
    while i < len(ln):
        ch = ln[i]
        if ch not in BULLETS:
            out.append(ch)
            i += 1
            continue

        # Rebuilt per marker, so a line with k markers costs O(k*n). That is deliberate: the
        # opening rules read the WHOLE prefix, and narrowing this to the last character
        # would be exact only while `opened` is set -- a second reading of the same
        # invariant, which is what this refactor exists to remove. Measured: 132
        # marker-opened lines, the largest shape the corpus suggests, take 0.56 ms, and
        # 300 markers on ONE line take 1.15 ms. The cost is real and out of reach.
        left = "".join(out)
        right = ln[i + 1 :]  # the text test reads past the gap, so the whole rest of the line
        pos = classify(left, right, opened=opened, strippable=ch in STRIPPABLE)
        opened = True
        counter, survives = _ACTIONS[pos]
        stats[counter] += 1
        i += 1

        if survives:
            out.append(ch)
        elif pos is Pos.SEPARATOR:
            if right[:1] == " " and left[-1:].isspace():
                i += 1
        else:  # HEADING or LIST: the marker opens the line, so it rewrites the prefix it sits in
            out[:] = list(_opening_prefix(left, pos))
            while i < len(ln) and ln[i] in " \t":
                i += 1
    return "".join(out)


def _remap_line(ln: str, stats: Counter[str]) -> str:
    """Substitute the verified glyphs in one line, with two exceptions the table cannot express.

    ``SPACE`` at a line edge is **dropped rather than spaced**: two of them at end of line would
    render as a CommonMark hard break, which is structure the printed page does not have. That hard
    break is the whole reason. ⚠ Dropping does not *guarantee* the line escapes one, and the claim
    that it does was measured false: real trailing whitespace already on the line survives, so
    ``"x  <SPACE>"`` still ends in two spaces afterwards. The step only declines to ADD to it. That
    shortfall is older than this rule and is filed, not fixed here. ⚠ Dropping does not prevent a paragraph split, and it does not leave
    the rendering unchanged either. ``U+F020`` is not whitespace to CommonMark, so a line that holds
    one and nothing else is a paragraph **continuation** line before this step and a **blank** line
    after it, whichever way the space is handled. Measured with a CommonMark parser:
    ``para one`` / ``<SPACE>`` / ``para two`` renders as one paragraph before the step and two after
    it, both when the space is deleted and when it is substituted. The split is a consequence of an
    edit to that line, not of the choice between the two edits.

    A line-opening ``DOT`` is left in place and counted; see :data:`DOT` for why guessing there is
    the one rewrite this module must not make. ⚠ Its indent is UNBOUNDED, unlike a bullet's: both
    :data:`Pos.LIST` and :data:`Pos.LINE_OPEN` defer it, and only the two together cover every
    indent. This is a refusal, not a list-recognition rule, so the CommonMark limit does not apply
    to it -- an earlier bound made the deferral quietly stop applying to a nested list item, and
    ``    <DOT> Chunked transfer encoding`` was rewritten to a middle dot and reported as a repair.

    ``SPACE`` is handled **before** the ``DOT`` split, and the order is load-bearing in both
    directions. Splitting first made the space that follows a deferred dot look line-*leading*, so
    ``strip`` deleted it and ``<DOT><SPACE>Text`` came out as ``<DOT>Text`` -- an edit to the very
    line this function promises to leave alone. Handling ``SPACE`` first also lets a ``SPACE``
    *before* the dot reach the deferral at all, which a ``[ \\t]`` indent cannot match, because a
    Symbol-font space is neither a space nor a tab.
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
    at = ln.find(DOT)
    if at != -1 and classify(ln[:at], ln[at + 1 :]) in (Pos.LIST, Pos.LINE_OPEN):
        stats["line_leading_dot_deferred"] += 1  # never guess: bullet or dot, per-book judgment
        head, ln = ln[: at + 1], ln[at + 1 :]

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

    ``_remap_line`` runs **first**: the positional rules all test for real whitespace, and a
    Symbol-font space is not whitespace, so a bullet separated from its text by one would otherwise
    be left in the output as an invisible codepoint and its list item lost.
    """
    return "\n".join(_fix_line(_remap_line(ln, stats), stats) for ln in text.split("\n"))


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
    ``line_leading_marker_deferred``
        A marker in :data:`BULLETS` opening a line, left in place because it could not be read as a
        list item -- too indented, no gap after it, or an operator where the item's text would
        start -- and deleting it would flatten a nested list or a formula. Needs a human, like
        ``unknown``: read the rendered page and decide whether the line is a list item.
    ``marker_no_reading``
        A marker that is not in :data:`STRIPPABLE`, found away from a line-opening position. It is
        verified as a bullet at a line start only, and its slot is a Greek letter in Adobe Symbol
        encoding, so it is kept.
        Needs a human: render the page, and either the line is text with a stray marker in it, or
        the codepoint is a letter :data:`GLYPHS` should carry.
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
            "line_leading_marker_deferred": 0,
            "marker_no_reading": 0,
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

    known = set(GLYPHS) | set(BULLETS)
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
        "line_leading_marker_deferred": 0,
        "marker_no_reading": 0,
        "dropped_f020": 0,
        "skipped_crlf": False,
    }
    report.update(stats)
    report["in_code"] = dict(in_code)
    report["unknown"] = dict(unknown)
    # These four count glyphs deliberately LEFT IN PLACE — not changes. Counting them would make
    # a refusal to guess read as a successful repair.
    deliberate = {
        "stray_unhandled",
        "line_leading_dot_deferred",
        "line_leading_marker_deferred",
        "marker_no_reading",
    }
    report["total_changes"] = sum(v for k, v in stats.items() if k not in deliberate)
    return out, report
