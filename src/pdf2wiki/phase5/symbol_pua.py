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

Idempotent: a second pass is a no-op. ⚠ "No mapped PUA codepoint remains outside code" is NOT part
of that claim. Every refusal leaves a mapped codepoint in place on purpose and counts it. There are
eight: ``stray_unhandled``, ``line_leading_marker_deferred``, ``marker_no_reading``,
``adjacent_markers``, ``line_leading_dot_deferred``, and three for a Symbol space that is the only
thing between a line and a Markdown block: ``head_kept_f020`` at the line start (#94),
``tail_kept_f020`` at the line end and ``inner_kept_f020`` inside the text (#96).

⚠ That claim was FALSE for two ADJACENT markers, and the chain runs this step twice on it. The pair
was read piecewise -- the first refused as flush against a marker, the second deleted because a real
space survived to its right -- and the deletion moved the survivor into a position the second pass
read as a list item or a heading. Ten shapes turned a REFUSAL into a repair that way, and because
`residue_lines` takes the high-water mark of the two passes, the operator was warned that a marker
had been "LEFT IN PLACE" on a line the chain had already rewritten. A marker touching another marker
is now :data:`Pos.ADJACENT`: every reading here was verified against a page printing ONE marker, so
a run of them has no reading, and both are kept and counted (``adjacent_markers``).
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

    This module reads one concept -- a marker -- in six position-dependent ways, and the position
    decides the answer in every rule. Five of them used to live in three anchored regexes and two
    branches of a character walk, so every change to one of them meant five separate decisions.
    Nine fresh-context review rounds found the same shape of defect again and again: a caution added
    where the author was looking, and not where the same constant is read next door. The sixth,
    :data:`Pos.ADJACENT`, came later and from the opposite direction: no rule covered a marker
    beside a marker, so the pair was read piecewise and the module contradicted itself.

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
    ``ADJACENT``
        Touching another marker. Every reading below was verified against a page that prints ONE
        marker, so a marker beside a marker has no reading at all, and both of the pair are kept.
    """

    HEADING = "heading"
    LIST = "list"
    LINE_OPEN = "line_open"
    SEPARATOR = "separator"
    FLUSH = "flush"
    UNREAD = "unread"
    ADJACENT = "adjacent"


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
    Pos.ADJACENT: ("adjacent_markers", True),
}


#: A body this rule will move to column 0. It is a WHITELIST, and that direction is the whole
#: design. Three review rounds each found a shape a blacklist of block openers did not name: a PUA
#: marker behind the space, an emphasis opener in front of one (``*<MARKER>``), promoted hashes
#: (``#<MARKER>``), a Symbol space used as the delimiter itself (``-<SPACE>item``), an HTML block,
#: and the two-hyphen setext underline. Each time the guard tested a narrower string than
#: :func:`classify` and CommonMark actually read. A whitelist cannot fail that way: an unlisted
#: shape is simply not edited, which is the behavior of the release before this rule.
_INERT_BODY = re.compile(r"[A-Za-z]")


def _is_inert(body: str) -> bool:
    """Is ``body`` provably safe to move to column 0?

    Safe means three things at once. It starts with a LETTER, so it opens no list, heading, quote,
    fence, thematic break or setext underline, and it is no HTML block. It holds no marker from
    :data:`BULLETS` and no :data:`DOT`, so moving it cannot change how :func:`classify` reads one --
    the invariant the tail already carries, and the one this rule broke twice. It holds no
    :data:`SPACE`, because the body written out is ``body.replace(SPACE, " ")``, so a Symbol space
    inside it can BECOME the delimiter of an opener that is not visible here.

    ⚠ Deliberately narrow. A digit is excluded although only ``1.`` and ``1)`` open a list, and
    ``**bold**`` is excluded although it opens nothing. Widening this needs a measurement, not an
    argument: every widening this module has taken on an argument has been wrong.

    ⚠ **This tests whether the body OPENS a block. It cannot see that the line sits INSIDE one that
    is already open**, where CommonMark passes leading whitespace through verbatim. The step is
    line-local, so ``<pre>`` / ``<SPACE>    literal`` / ``</pre>`` loses the four spaces ``<pre>``
    would have rendered. The blindness is knowingly accepted rather than guarded, on a measurement:
    over 1,680 converted files the converter emits ``<details>`` 8,604 times, ``<table>`` 3,024
    times, ``<div>`` and ``<script>`` besides -- all whitespace-insensitive -- and ``<pre>`` **zero**
    times, with ``U+F020`` itself absent from the same corpus. 🔑 So the whitelist's promise is
    narrower than it first reads: it constrains the BODY, never the surrounding block.
    """
    return (
        bool(_INERT_BODY.match(body))
        and not any(m in body for m in BULLETS)
        and DOT not in body
        and SPACE not in body
    )


def _opening_dot(line: str) -> int:
    """Return the index of the :data:`DOT` that opens ``line``, or ``-1``. The one deferral test.

    ``runs=False``: this asks only whether the dot OPENS its line. A marker that follows it is a
    different question, and answering that one here rewrote the dot instead of deferring it. Two
    callers read this, :func:`_remap_line` to defer the dot and :func:`_a_marker_opens` to leave
    the head of such a line alone. They must agree, or one pass keeps a head the next one drops.
    """
    at = line.find(DOT)
    if at != -1 and classify(line[:at], line[at + 1 :], runs=False) in (Pos.LIST, Pos.LINE_OPEN):
        return at
    return -1


def _is_text(ch: str) -> bool:
    """Is ``ch`` plainly TEXT, a character that no marker and no block opener is written with?

    A letter, or any character that is not ASCII. CommonMark writes every container marker and
    every opener in ASCII punctuation and digits, so neither can be one. The #94 head rule and
    the #96 lead both ask this, here, so that they cannot come to mean two things by "text".

    The character is judged as it is WRITTEN OUT, because the chain runs this step twice. A
    Symbol-font pi is in the Private Use Area and the ``π`` it becomes is a letter. Both are
    non-ASCII, so both are text and the two passes get one answer. The two glyphs written as
    ASCII parentheses are not text, on either pass.

    Measured, not argued, on the whole rendered HTML and in 210 contexts each: 48,965 letters of
    the Basic Multilingual Plane, the seventeen glyphs written as non-ASCII, and 8,028 other
    non-ASCII characters. A dropped Symbol space in front of one changed the rendering of no
    line, with ONE exception that the measurement found and no argument had: ``U+FEFF``. The
    parser skips a byte order mark at the start of a document, so ``<SPACE><FEFF># x`` there is
    a paragraph and ``<FEFF># x`` is a heading. It is not text.
    """
    written = GLYPHS.get(ch, ch)
    return written.isalpha() or (not written.isascii() and written != "\ufeff")


def _a_marker_opens(line: str) -> bool:
    """Does a marker open ``line``, now or once the marker pass has run over it?

    :func:`_head_may_be_dropped` asks this before a head Symbol space is kept (#94). A marker that
    opens its line is read by position, and the line-opening tests accept real indent only. A
    Symbol space left in front of such a marker turns it into a mid-line one: a list item loses its
    marker, or a deferral becomes a deletion. Review found that class while #77 was fixed, 857
    shapes of it. So the question is put to :func:`classify` itself, with the arguments its real
    callers pass, and not to a pattern that reads a narrower string than they do.

    ``line`` is the line as the drop would write it. ``runs=False`` throughout, because this asks
    where a marker stands and not what to do with a neighbour.

    ⚠ **Every marker in** :data:`BULLETS` **is asked, each with the markers in front of it taken
    out.** The first version asked the first marker only, and that answer does not survive the
    marker pass. In ``<SPACE>    #<BULLET> <DIAMOND> item`` the bullet does not open the line,
    four columns deep, so the head was kept and the bullet deleted as a stray. The diamond then
    stood right behind the hashes, where a marker that cannot be deleted opens the line at any
    depth, and the chain's second pass dropped the head the first one had reported as kept. Review
    found it by fuzzing, 40 of 1.2 million lines. Taking the earlier markers out asks the question
    the second pass will ask. It over-approximates, since not every marker in front is deleted,
    and that errs toward the drop, which is the previous release's output.

    ⚠ This says the marker rules own the line. It does NOT say the drop is harmless there. After
    hashes and a gap the text in front of the marker is itself an ATX opener, so
    ``<SPACE># <DIAMOND> item`` is a paragraph line before the step and a heading after it, with
    the deferred marker still in it. A bare ``<SPACE><BULLET>`` under a paragraph becomes ``-``,
    which is a setext underline. Both are the output of the previous release, and keeping the head
    there is the edit that deleted markers, so they stay as they were and are stated as a limit.
    """
    if _opening_dot(line) != -1:
        return True
    if not any(marker in line for marker in BULLETS):
        return False
    left = ""  # the line up to here, with every marker in front taken out
    for i, ch in enumerate(line):
        if ch not in BULLETS:
            left += ch
        elif classify(left, line[i + 1 :], strippable=ch in STRIPPABLE, runs=False) in (
            Pos.HEADING,
            Pos.LIST,
            Pos.LINE_OPEN,
        ):
            return True
    return False


def _head_may_be_dropped(body: str, line: str, grows: bool) -> bool:
    """May the head Symbol space in front of ``body`` be dropped, as every release before #94 did?

    A WHITELIST, and the direction is the design, as it is for :func:`_is_inert`. An unlisted line
    keeps its Symbol space. ``line`` is the whole line as the drop would write it, which the marker
    test reads. ``grows`` says the drop would turn real spaces behind the Symbol space into indent.

    1. The body starts with an **ASCII letter**. This is the ground #77 already decides: an inert
       body is cut back when the drop reaches four columns, and any other is dropped as before.
    2. A **marker** leads the body, or a marker OPENS the line. The marker rules own that line.
       See :func:`_a_marker_opens` for why, and for what that does not promise.
    3. The body starts with **any other text**, as :func:`_is_text` reads it, and the indent does
       not ``grow``. The first version of this case took letters and table glyphs only, so
       ``<SPACE>“Quoted”`` kept its Symbol space while ``“<SPACE>Quoted`` lost it, and curly
       quotes open a large share of book lines. Measured, not
       argued, and on the whole rendered HTML: 48,965 letters of the Basic Multilingual Plane and
       those seventeen glyphs, in 210 contexts each behind a bare Symbol space, and the drop
       changed the rendering of none of 10.3 million lines. Then through the step itself, behind
       seven heads: none of 2.0 million dropped lines. A glyph in front is the likely real shape,
       a line that starts inside a Symbol-font run, and the release before #94 wrote it clean.

    ⚠ **The glyph is judged by what it is WRITTEN OUT as, and** ``U+F028`` **is not on the list.**
    It becomes ``(``, and ``(`` opens the title of a link reference definition on the line above:
    ``[x]: /u`` / ``<SPACE><F028>see note<F029>`` is a paragraph before the step and nothing at
    all after the drop. The first measurement compared block tags, and a swallowed line leaves
    them equal, so it reported that no glyph could do this. Review found it. ``)`` is excluded with
    it: an ASCII character gets no benefit of the doubt here.

    ⚠ **Case 1 is NOT measured safe, and one context shows it.** Under a bare link label, real
    whitespace between the Symbol space and the letter decides everything: ``[note]:`` /
    ``<SPACE> x`` is a paragraph, because the Symbol space is the destination and `` x`` is no
    title, and after the drop ``x`` is the destination and both lines render as nothing. That is
    the previous release's output and it stays, for the reason below. Case 3 does not have it,
    because that whitespace is growth.

    ⚠ Case 3 needs ``not grows`` and case 1 must not have it. A body in case 3 is never inert, so
    nothing cuts it back, and without the test ``<SPACE>    <PI> radians`` is an indented code
    block again. Two columns are enough to do damage, by moving a paragraph into the list item
    above it, so the test is "any growth" and not "four columns". Case 1 cannot take the same test:
    ``<SPACE>    text<BULLET> tail`` would be kept, the marker pass would delete the stray bullet,
    and the chain's second pass would then find an inert body and cut the head back -- a refusal
    the next pass undoes. That shape stays the previous release's output, and it is one of the
    limits :func:`_remap_line` states.

    ⚠ The marker test reads ``body[0]`` as well as the whole line, and both are needed. A marker
    that leads the body can be DELETED by the marker pass, which leaves a letter in front, and the
    second pass then drops the head this pass reported as kept: ``<NBSP><SPACE>    <BULLET> item``
    did exactly that in the first version of this rule.

    ⚠ Wider than :func:`_is_inert` on purpose, and the two must not be merged. That one licenses a
    NEW edit, the cut-back, so it must be sure. This one licenses the OLD edit, so the worst it
    can do is what the previous release did. ⚠ The two halves of case 3 belong together. A glyph
    is written out as a letter more often than not, so with letters alone ``<SPACE><PI> radians``
    is kept by one pass, becomes ``<SPACE>π radians``, and is dropped by the next. Still narrow:
    ``2024 was``, ``(see note)`` and ``**bold**`` keep their Symbol space although the drop would
    be harmless there.
    """
    first = body[0]
    if _INERT_BODY.match(body) or first in BULLETS or _a_marker_opens(line):
        return True
    return _is_text(first) and not grows


def _indent(text: str) -> int:
    """Return the columns of indent CommonMark reads at the start of ``text``: spaces and tabs only.

    Not ``str.isspace()``. ``U+00A0`` and ``U+2003`` are ``isspace()`` and are content to the
    parser, and so is a Symbol space, so the indent ends at the first of them.
    """
    return _columns(text[: len(text) - len(text.lstrip(" \t"))])


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


def classify(
    left: str, right: str, *, opened: bool = False, strippable: bool = True, runs: bool = True
) -> Pos:
    """Return where a marker sits, from the text emitted before it and the text still ahead of it.

    ``strippable`` says the marker may be deleted mid-line (:data:`STRIPPABLE`), and it is the
    marker with a rendered HEADING page behind it. Any other marker is verified as a list item at a
    line start only, so it is read in four ways, all of which keep it: :data:`Pos.ADJACENT` beside
    another marker, which is tested first, :data:`Pos.LIST` where the verified reading applies,
    :data:`Pos.LINE_OPEN` after hashes or where the list test fails, and :data:`Pos.UNREAD`
    anywhere else. The per-reading evidence rule of :data:`GLYPHS` applies to the structural
    readings too: a list page does not verify a heading reading.

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

    ⚠ The adjacency test runs FIRST, ahead of every reading below, because a marker that touches
    another marker is the one shape none of them was verified against. Testing it later let the
    pair be read PIECEWISE -- the first of the two flush against a marker and refused, the second
    with a real space to its right and deleted as a separator -- and the deletion then moved the
    survivor into a position the chain's SECOND pass read as a list item or a heading. Ten shapes
    turned a first-pass REFUSAL into a second-pass repair that way, which is the one thing
    :data:`_ACTIONS` promises never happens. Refusing the whole run is what makes this function's
    answer independent of how many passes run over it.

    ⚠ ``runs`` says whether a neighbouring marker is part of the question, and :func:`_remap_line`
    is the one caller that passes ``False``. That caller does not ask what to DO with a marker. It
    asks one narrower thing -- does this :data:`DOT` open its line? -- so that it can defer the
    per-book bullet-or-dot judgment. Running the adjacency test for it answered a question it never
    asked: ``<DOT><BULLET> item`` returned :data:`Pos.ADJACENT`, the deferral branch was skipped,
    and the dot was REWRITTEN to a middle dot and counted as a repair, which is the exact rewrite
    :data:`DOT` says this module must never make. 428 shapes lost the deferral that way. Adding
    :data:`Pos.ADJACENT` to that caller's tuple instead would over-fire on ``<BULLET><DOT> item``,
    where the dot does not open the line at all: the position question and the run question are
    two questions, so they take two answers.
    """
    # ⚠ Membership, not slice-in-string: `"" in BULLETS` is True, so `left[-1:] in BULLETS` would
    # refuse EVERY marker in column 0, where `left` is empty. An empty needle finds everything.
    if runs:
        neighbours = {left[-1:], right[:1]} - {""}
        if neighbours & set(BULLETS):
            return Pos.ADJACENT

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


def _ends_in_unescaped_backslash(s: str) -> bool:
    """Is the last character of ``s`` a backslash that CommonMark reads as a hard break?

    CommonMark spec 6.7 gives a line-final backslash the same meaning as two trailing spaces, but
    only when the backslash is not itself escaped. One backslash at the line end breaks the line.
    Two are an escape: they print one literal backslash and break nothing. Three print one and then
    break. So the length of the run at the end decides it, and an odd run is a break.
    """
    return (len(s) - len(s.rstrip("\\"))) % 2 == 1


def _real_tail(body: str, tail: str) -> tuple[str, str]:
    """Return the tail of a line with its Symbol spaces dropped, and the counter that drop raises.

    The tail is cut back where a drop would uncover a hard break. Why, and why only here: see the
    docstring of :func:`_remap_line`. The counter is ``""`` when nothing was cut back. It is
    returned and not raised here, because the caller may still decide to keep the tail (#96), and
    a kept tail is not edited at all.
    """
    if SPACE not in tail:
        return tail, ""
    real_tail = tail.replace(SPACE, "")
    seen = tail[tail.rfind(SPACE) + 1 :]
    if real_tail.endswith("  ") and not seen.endswith("  "):
        # At least one space stays: it is no break, and when the body is a bare marker
        # it is the gap `classify` needs. Review measured 108 shapes flip from a read
        # marker to a deferred one when the cut-back left nothing.
        return seen or " ", "tail_collapsed_f020"
    if not real_tail and _ends_in_unescaped_backslash(body):
        # CommonMark's OTHER hard break, and the same shape with a different trigger
        # character. The tail held Symbol spaces only, so the last character of the line
        # was one of them and the backslash was not line-final. The drop makes it
        # line-final. One real space keeps the rendering the page has and is no break.
        return " ", "tail_backslash_spaced_f020"
    return real_tail, ""


def _lead(text: str) -> str:
    """Return ``text`` up to its first character that is plainly TEXT. All of it if there is none.

    This is where a line decides what it is. Every container marker and every block opener stands
    in front of the first word: ``- > 1. ## Title`` is a heading in a list in a quote in a list,
    and all of that is over at the ``T``. Behind it a line is inline text, and nothing there opens
    a block. The constructs that keep reading behind it announce themselves in the lead, and
    :func:`_tail_may_be_dropped` and :func:`_first_gap_may_be_a_space` name each one.

    What counts as text is :func:`_is_text`. ⚠ The first version stopped at a letter only, and
    that kept the Symbol space behind a glyph the table writes as a sign:
    ``<F0A5><SPACE>TPS results for``, a shape read from a rendered page, came out with the
    invisible codepoint still in it. Review found it.
    """
    for at, ch in enumerate(text):
        if _is_text(ch):
            return text[:at]
    return text


def _tag_end(text: str, start: int) -> int:
    """Return the index of the ``>`` that closes the tag opened at ``text[start]``, or ``-1``.

    Quote-aware, because an attribute value may hold a ``>``: ``<span title="a>b">`` is one tag.
    Both #96 rules ask about a tag in the lead, from two sides, and they ask it here so that they
    cannot come to read it differently. A quote marker is a ``>`` too, and it is outside any tag.
    """
    quote = ""
    for at in range(start + 1, len(text)):
        ch = text[at]
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == ">":
            return at
    return -1


def _is_a_definition(body: str) -> bool:
    """Could ``body`` be a link reference definition, ``[label]: destination "title"``?

    The one construct that is parsed to the END of its line. A Symbol space anywhere in it decides
    whether it is a definition at all, in both directions: ``[x]: /u <SPACE>`` is paragraph text,
    because a Symbol space is no valid title, and ``[x]: /u`` renders as nothing. ``[x]: a<SPACE>b``
    is a definition, and ``[x]: a b`` is a paragraph. So a line that could be one is not edited at
    its tail or inside at all.

    The label opens in the lead, behind nothing but container markers, and its OWN closing
    bracket is followed by a colon. An escaped bracket inside the label, ``[a\\]b]:``, does not
    close it. ⚠ A bracket in the lead is not enough, and neither is a ``]:`` somewhere behind it:
    ``[1] Smith, J.`` and ``[3] Knuth [TAOCP]: vol. 1`` are bibliography lines, and such a book is
    full of them.

    ⚠ **What keeping every gap preserves is the SOURCE's rendering, and that can be nothing.**
    ``[Knuth]: The<SPACE>Art<SPACE>of`` is a definition to the parser, with one long destination,
    and it prints no line at all. The previous release wrote real spaces and the line appeared.
    Which one the page shows is not something this step can know, so it is reported.

    ⚠ A footnote definition, ``[^1]: text``, IS one to CommonMark when a Symbol space joins its
    words, so it is held here and every gap in it stays. A reader with footnotes sees the same
    block either way.
    """
    lead = _lead(body)
    opened = lead.find("[")
    # Nothing but container markers may stand in front of the label: `![x]: a` is an image and
    # `(1) [x]: a` is a sentence, and neither can start a definition.
    if opened == -1 or lead[:opened].strip("> \t-+*0123456789.)"):
        return False
    at = opened + 1
    while at < len(body) and body[at] != "]":
        at += 2 if body[at] == "\\" else 1  # a backslash escapes the bracket behind it
    return body[at + 1 : at + 2] == ":"


def _closes_a_task_marker(text: str) -> bool:
    """Does ``text`` end in a checked task box whose letter is the first text of the line?

    A task marker is the one list marker that holds a letter, so the text test of both #96 rules
    lets it through. ``- [x]<SPACE>done`` is a list item with literal text, and ``- [x] done`` is
    a checked box in GFM and in Obsidian. ``- [x] <SPACE>`` is an item with content, and
    ``- [x] `` is an empty one. An unchecked box, ``[ ]``, holds no text and is refused already.

    ⚠ Exactly a box, and the first version asked for any closing bracket: ``[Smith]<SPACE>wrote``
    and ``[link]<SPACE>`` are a citation and a link, and neither can become a box.
    """
    return text.endswith(("[x]", "[X]")) and _lead(text) == text[:-2]


def _tail_may_be_dropped(body: str) -> bool:
    """May the Symbol space at the END of a line be dropped, as every release before #96 did?

    The drop is dangerous on one kind of line: a WHOLE-LINE construct, text that is a block only
    when nothing but whitespace follows it. ``---<SPACE>`` is paragraph text, and ``---`` alone
    turns the line above it into a heading. A WHITELIST again, in the direction of
    :func:`_is_inert`: the tail is dropped where the body is provably no such construct.

    **A line with text in it is not one.** A setext underline, a thematic break, a table
    delimiter row, an empty heading and an empty list item are made of ASCII punctuation and
    digits, by their productions, at any depth of list or quote. Five constructs do hold text,
    and each one is refused by name:

    - a link reference definition, see :func:`_is_a_definition`
    - an HTML block. ``<div<SPACE>`` is no tag, and ``<div`` at a line end opens one, and
      ``<span>`` alone on its line is a block where ``<span><SPACE>`` is not. A ``<`` in the lead
      says so, and inline HTML behind the first word does not. A tag that is closed and has
      content behind it is let through: ``<table><tr>...`` is most of the HTML a converter
      writes, and it is the same block with or without the tail.
    - a heading with closing hashes, which count only at the very end of the line:
      ``# Title #<SPACE>`` prints the ``#``, and ``# Title #`` does not.
    - a task marker, see :func:`_closes_a_task_marker`
    - **the header row of a pipe table.** ``| a | b |<SPACE>`` has three cells, and
      ``| a | b |`` has two. Whether it is a table at all is decided by the delimiter row on the
      line BELOW, which must have the same number, and this step reads one line. So a line with
      a pipe in it keeps its tail. Review found this one. The measurement could not, because it
      had no line below.

    ⚠ **One line is let through although it holds no text: a code fence.** A run of three or
    more backticks or tildes with a Symbol space behind it does not CLOSE a fence, and without it
    it does, so this drop changes structure on purpose. Inside a quote too, behind its markers. It is the repair the previous release
    made: kept, the fence stays open and the rest of the chapter renders as code.

    ⚠ What the drop still changes on a line this lets through is INLINE, and it is the previous
    release's output: ``_x_<SPACE>`` gains the emphasis its underscores could not close in front
    of a Symbol space.

    ⚠ Narrow where it has to be. ``2024<SPACE>`` and ``(1)<SPACE>`` hold no text and keep their
    Symbol space, although no construct is made of them, and so does ``C#<SPACE>``.
    """
    for fence in "`~":
        stem = body.rstrip(fence)
        # a fence, and nothing in front of it but quote markers: `> ```` closes a block as well
        if len(body) - len(stem) >= 3 and not stem.strip("> \t"):
            return True
    lead = _lead(body)
    if (
        len(lead) == len(body)  # no text anywhere
        or "|" in body
        or body.endswith("#")
        or _is_a_definition(body)
        or _closes_a_task_marker(body)
    ):
        return False
    if "<" not in lead:
        return True
    return 0 <= _tag_end(body, body.index("<")) < len(body) - 1


def _first_gap_may_be_a_space(body: str) -> bool:
    """May the FIRST Symbol space in ``body`` be written as a real space, as before #96?

    Substitution is what this step is for, and nearly every Symbol space inside text is right as a
    real space. One is not: a gap in the LEAD of a line, where real whitespace is what completes
    a block opener. ``#<SPACE>Title`` is paragraph text, and ``# Title`` is a heading.

    A WHITELIST, as everywhere in this module: the substitution is safe when **text stands in
    front of the gap**. Then the lead is over and the line is inline. An ATX prefix is hashes, a
    bullet is one character, an ordered marker is digits and a delimiter, and none of them is
    text. Two constructs do hold text, and each is refused by name:

    - a tag name. ``<div<SPACE>class="a">`` becomes a tag, so the gap must not stand INSIDE a tag
      that opened in the lead. Behind a closed one it is content, which is what lets the cells of
      a ``<table>`` line through.
    - a task marker, see :func:`_closes_a_task_marker`

    ⚠ **Real whitespace in front of the gap does NOT make it safe**, and the first version of this
    rule said it did. ``- <SPACE># x`` is a list item that holds the text ``# x``. The Symbol
    space stands at the start of the item's CONTENT, which is a line start of its own, and
    ``-  # x`` is a heading inside the item. The same holds behind ``>`` and behind ``1.``, to
    any depth. Measured through the step itself, 1,687 lines of 2.2 million, and found there and
    not by argument.

    ⚠ Narrow: ``2024<SPACE>was``, ``1.2<SPACE>Vectors`` and ``- <SPACE>item`` keep their Symbol
    space, although nothing is opened by any of them.
    """
    prefix = body[: body.index(SPACE)]
    lead = _lead(prefix)
    if len(lead) == len(prefix) or _closes_a_task_marker(prefix):
        return False
    if "<" not in lead:
        return True
    return not _ends_inside_a_tag(prefix)


def _ends_inside_a_tag(text: str) -> bool:
    """Is the end of ``text`` inside a tag that has not been closed yet?"""
    at = text.find("<")
    while at != -1:
        end = _tag_end(text, at)
        if end == -1:
            return True
        at = text.find("<", end + 1)
    return False


def _gap_closes_a_heading(body: str, at: int) -> bool:
    """Does the Symbol space at ``at`` stand in front of nothing but hashes?

    The closing sequence of an ATX heading is whitespace and then hashes, at the very end of the
    line. ``# Title<SPACE>#`` prints its last ``#``, and ``# Title #`` does not. So this gap is
    kept wherever it stands, first on the line or not. The tail rule refuses the same construct
    from its other side, with ``body.endswith("#")``.
    """
    rest = body[at + 1 :]
    return bool(rest) and not rest.strip("#")


def _remap_line(ln: str, stats: Counter[str]) -> str:
    """Substitute the verified glyphs in one line, with two exceptions the table cannot express.

    ``SPACE`` at a line edge is **dropped rather than spaced**: two of them at end of line would
    render as a CommonMark hard break, which is structure the printed page does not have. That hard
    break is the whole reason. ⚠ Dropping alone did not guarantee the line escapes one, and the
    claim that it did was measured false: real trailing whitespace already on the line survived, so
    ``"x  <SPACE>"`` still ended in two spaces. Now, when the spaces the drop uncovers would be a
    hard break, the tail is cut back to the whitespace that followed the last Symbol space, which is
    all CommonMark saw before the step -- or to ONE space when nothing followed it, because one
    space is no break and a bare marker needs its gap to be read. A break that was already there
    (``"x<SPACE>  "``) stays, and a tail that was never a break is not touched. Counted as
    ``tail_collapsed_f020``. ⚠ The step is line-local and cannot know whether the line ends a
    paragraph, where CommonMark renders no break anyway; it cuts back there too, which changes
    nothing visible. ⚠ Two trailing spaces are not CommonMark's only hard break. Spec 6.7 gives a
    line-final unescaped backslash the same meaning, so a line that ends in a backslash and then a
    Symbol space has no break before the step and one after it. When the tail holds Symbol spaces
    only, and the body ends in an odd run of backslashes, ONE real space stays. That space keeps
    the rendering the page has, and a backslash in front of a space is no break. Counted as
    ``tail_backslash_spaced_f020``, apart from the space cut-back, because it ADDS a character
    where the cut-back removes them. ⚠ The head is cut back too, by the MIRROR of the tail
    rule: the tail keeps the whitespace that followed the LAST Symbol space, the head keeps the
    whitespace that preceded the FIRST one. That is the indent CommonMark read before the step,
    because ``U+F020`` is not whitespace to it -- every real space behind one is CONTENT, and the
    drop promotes it to indent. ``<SPACE>`` and four real spaces is a paragraph line before the
    step and an indented code block after it. ⚠ **No rendered page was needed after all.** The
    question here is not what the glyph prints, which is why :data:`DOT` refuses; it is which
    indent the parser already saw, and that is measurable. ⚠ The cut-back does NOT apply when the
    whitespace before the first Symbol space is already four columns or more. At the top level that
    line is an indented code block on its own, where the whitespace behind the Symbol space is
    literal content and deleting it would edit the code. ⚠ The guard measures ABSOLUTE columns, and
    "four columns is a code block" holds only at the top level. Inside a list item, code starts four
    columns after the item's content indent, so the same promotion happens there and this rule
    DECLINES rather than repairs it: `-   item` / `    text` / `     <SPACE>    more` keeps nine
    columns. That is the previous release's output, so it is a limit and not a regression, and the
    absolute guard is conservative in the safe direction. Columns, not characters, through :func:`_columns`
    -- a tab is four (spec 2.2). ⚠ It applies only to a body :func:`_is_inert` accepts, which is a
    WHITELIST and not a list of dangerous shapes. Three review rounds each found a shape a
    blacklist did not name, and every one of them read a narrower string than :func:`classify` and
    CommonMark do. An unlisted body is simply not edited. Counted as ``head_collapsed_f020``.

    ⚠ **A head Symbol space is KEPT when the body behind it could open a block (#94).** ``U+F020``
    is not whitespace to CommonMark, so a line that starts with one is paragraph text whatever
    comes next. ``<SPACE># Title`` is a paragraph line before the step. The plain drop wrote
    ``# Title``, a heading, and the same happened for a list, a quote, a thematic break, an HTML
    block, a link reference definition that then renders as nothing, a code fence that then has
    no end, and a ``---`` that turns the line ABOVE into a heading. No page shows which reading is
    right, so the head stays as it is and is counted as ``head_kept_f020``, a refusal and not a
    change, the answer :data:`DOT` gives. What may still be dropped is a whitelist, and
    :func:`_head_may_be_dropped` is the one place that states it.

    ⚠ **What #94 does NOT cover, each one the output of the previous release and each measured.**
    (1) A line the marker rules own is dropped as before. So ``<SPACE>    <BULLET> item`` still
    becomes four columns of indent, ``<SPACE># <DIAMOND> item`` still becomes a heading with the
    deferred marker in it, and a bare ``<SPACE><BULLET>`` under a paragraph still becomes ``-``, a
    setext underline. (2) An ASCII-letter body that #77 does not list is still not cut back.
    (3) Behind an ASCII letter, real spaces that stay BELOW four columns are still promoted to
    indent, and two of them move a paragraph into the list item above it. (4) The head is one of
    three edges. A TAIL drop uncovers an opener too -- ``---<SPACE>`` under a paragraph becomes a
    setext underline -- and so does a substitution INSIDE the body: ``#<SPACE>Title`` becomes
    ``# Title``. Neither is this rule's.
    ⚠ **The line END and the first gap INSIDE the text are kept on the same grounds (#96).** The
    head is one of three edges with one root cause. A drop at the end turns ``---<SPACE>`` into
    ``---``, a setext underline, and the line above into a heading. A real space inside turns
    ``#<SPACE>Title`` into a heading and ``-<SPACE>item`` into a list. Both are refusals now,
    ``tail_kept_f020`` and ``inner_kept_f020``, and :func:`_tail_may_be_dropped` and
    :func:`_first_gap_may_be_a_space` state what may still be edited. Both read the LEAD of the
    line, the text in front of its first letter, because that is where a line decides what it is.
    ⚠ Two limits. They act only on a line with no BULLET MARKER in it: the marker pass deletes
    and rewrites, and a refusal it can undo is what broke the head rule twice in review. And they
    do not see a link reference definition that is still OPEN above this line, one line up or
    two, which reads this line as its destination or title: there a Symbol space still decides
    whether the lines are a definition or a paragraph. Measured through the step on 9.6 million
    generated lines, with a line above and a line below each: with no such label above, it
    changed the block structure of none. ⚠ A line of Symbol spaces and NOTHING else is outside
    all three rules and is still dropped to a blank line, which can split a paragraph: see below.

    ⚠ **And one thing a kept head costs.** An emphasis opener in front of a glyph that is written
    out as punctuation, ``<SPACE>*<F028>x<F029>*``, loses its emphasis: with the head kept, ``*``
    stands between a PUA codepoint and a ``(`` and is no longer left-flanking. The previous
    release dropped the head and kept the emphasis. Mid-line the same substitution already costs
    the same emphasis (``a*<F028>x<F029>*``), so it is the substitution's limit, now reachable at
    a line start. Block structure is not changed by it. The second cost is one shape. Under a
    bare link label, ``[x]:`` / ``<SPACE> <F028>see note<F029>``, the kept Symbol space is a
    destination and the written-out ``(see note)`` is its title, so both lines render as nothing,
    where the previous release dropped the head and left a paragraph. Dropping it instead loses
    the line under ``[x]: /u``. A step that reads one line cannot see the label, so a body that
    the paren glyph leads is exposed either way.

    ⚠ Dropping does not prevent a paragraph split, and it does not leave
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
        head_spaces, tail_spaces = head.count(SPACE), tail.count(SPACE)
        inner_spaces = body.count(SPACE)
        spaced = body.replace(SPACE, " ")
        real_tail, tail_counter = _real_tail(body, tail)
        real_head = head.replace(SPACE, "")
        head_kept = False
        # `body` guards a line that is ONLY whitespace and Symbol spaces: it is a blank line to
        # CommonMark either way, so an edit to its head would report a change that changes no
        # rendering -- the "points an operator at nothing" failure these counters exist to avoid.
        if head_spaces and body:
            seen_head = head[: head.find(SPACE)]
            # ⚠ The head must be CommonMark indentation and nothing else. The edge scan above
            # uses `str.isspace()`, which is wider than the parser: `U+00A0` and `U+2003` are
            # `isspace()` and are NOT indentation to CommonMark, and PDF text is full of them. On
            # `<NBSP><SPACE>    text` the line stands at indent 0 both before and after the drop,
            # so no code block was ever possible, and a cut-back there would delete four real
            # spaces of paragraph CONTENT and report an indent repair. The whitelist covers the
            # head for the same reason it covers the body: an unlisted shape is not edited.
            plain_indent = set(head) <= {" ", "\t", SPACE}
            # Would the drop promote content to an indented code block? The tail twin fires only
            # when a hard break would really appear, and the head mirrors that: below `_TAB_STOP`
            # columns an edit mostly reports a repair that repairs nothing. ⚠ "Mostly", measured:
            # after a list item and a blank line, two real spaces behind the Symbol space are
            # enough to move the paragraph INTO the item (`- outer` / `` / `<SPACE>  text`, 12
            # shapes of the rendering grid). An earlier version of this comment said the indent
            # "changes no rendering" there. It is a limit this rule keeps, not a property it has.
            # ⚠ `grows` is NOT gated on `plain_indent`, and it measures the indent as the parser
            # does. A head of `<SPACE>    <NBSP>` is not plain, and its four real spaces still
            # become indent once the Symbol space in front of them is gone. Review found that the
            # gate switched the guard off for exactly that head. ⚠ It guards case 3 of the
            # whitelist ONLY. An ASCII-letter body behind that head is #77's, the cut-back below
            # is gated on a plain head, and `<SPACE>    <NBSP>text` is still an indented code
            # block, as in the previous release.
            grows = _indent(real_head) > _indent(head)
            if not _head_may_be_dropped(body, real_head + spaced + real_tail, grows):
                # #94. The Symbol space is the only thing that keeps this body a paragraph line,
                # and nothing here proves the drop leaves it one. So the head stays as it is,
                # Symbol spaces and all, and is counted as a refusal.
                stats["head_kept_f020"] += head_spaces
                real_head = head
                head_spaces = 0  # kept, so not dropped
                head_kept = True
            elif (
                plain_indent
                and _columns(real_head) >= _TAB_STOP > _columns(seen_head)
                and _is_inert(body)
            ):
                # #77. The head is cut back for the same reason the tail is, and by the mirror
                # rule: the tail keeps what followed the LAST Symbol space, the head keeps what
                # preceded the FIRST one. See the docstring above.
                stats["head_collapsed_f020"] += 1
                real_head = seen_head
        # #96: the line END and the gaps INSIDE the text, the other two edges of #94.
        # ⚠ Only on a line with no BULLET MARKER in it. The marker pass deletes and rewrites, and
        # a refusal it can undo is what broke the #94 rule twice in review. Without one, a pass
        # changes nothing the next pass reads, so these refusals are stable by construction and
        # no marker result can move.
        # ⚠ A DOT is not such a marker. It is deferred at a line start and written out anywhere
        # else, and it is never deleted. The first version of this guard skipped every line that
        # held one -- the math lines, which are the ones most likely to hold a Symbol space too.
        # ⚠ The guard is WIDER than its reason for one marker: a diamond in the middle of a line
        # is never deleted, and its line is left alone all the same. A limit, stated.
        if body and not any(ch in BULLETS for ch in body):
            keep: set[int] = set()  # the gaps of the body that stay Symbol spaces
            gaps = [at for at, ch in enumerate(body) if ch == SPACE]
            # Behind a kept head the line starts with a Symbol space, so no gap on it can
            # complete an opener, and its gaps are written out as they always were.
            if gaps and not head_kept:
                if _is_a_definition(body):
                    keep.update(gaps)  # parsed to the end of its line: every gap decides
                elif not _first_gap_may_be_a_space(body):
                    keep.add(gaps[0])
                if _gap_closes_a_heading(body, gaps[-1]):
                    keep.add(gaps[-1])
            if keep:
                stats["inner_kept_f020"] += len(keep)
                inner_spaces -= len(keep)  # kept, so not written out
                spaced = "".join(
                    ch if ch != SPACE or at in keep else " " for at, ch in enumerate(body)
                )
            # ⚠ A line with a kept gap keeps its tail too. A kept gap and a dropped tail is a
            # line that neither the source nor the previous release wrote, and under a link
            # label it was a new loss: `-<SPACE>item <SPACE>` became one token, a destination,
            # and both lines rendered as nothing. Kept whole, the line is the source's line.
            # ⚠ A kept head makes the tail safe as well, with ONE exception: a pipe. A table
            # header row is no line-start construct, so a Symbol space in front does not stop it
            # from being one, and its cell count still turns on the tail.
            unsafe = "|" in body if head_kept else not _tail_may_be_dropped(body)
            if tail_spaces and (keep or unsafe):
                stats["tail_kept_f020"] += tail_spaces
                real_tail, tail_counter = tail, ""
                tail_spaces = 0  # kept, so not dropped
        if inner_spaces:
            stats["remap_f020"] += inner_spaces
        if tail_counter:
            stats[tail_counter] += 1
        dropped = head_spaces + tail_spaces
        if dropped:  # at an edge it is deleted, not spaced -- counted apart from a substitution
            stats["dropped_f020"] += dropped
        ln = real_head + spaced + real_tail

    head = ""
    at = _opening_dot(ln)
    if at != -1:
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
    ``tail_collapsed_f020``
        Real trailing spaces that a dropped :data:`SPACE` would have uncovered as a hard break,
        cut back to the whitespace that followed the last Symbol space, so the line renders as it
        did before the step. An edit, counted toward ``total_changes``; one per line.
    ``tail_backslash_spaced_f020``
        A line-final backslash that a dropped :data:`SPACE` would have uncovered as CommonMark's
        other hard break (spec 6.7), kept off the line end by one real space, so the line renders
        as it did before the step. An edit, counted toward ``total_changes``; one per line.
    ``head_collapsed_f020``
        Real LEADING spaces that a dropped :data:`SPACE` would have promoted from content to
        indent, cut back to the whitespace that preceded the first Symbol space, so the line keeps
        the indent CommonMark read before the step. An edit, counted toward ``total_changes``; one
        per line. Counted apart from ``dropped_f020``, which holds every benign drop and so points
        an operator at nothing.
    ``head_kept_f020``
        A :data:`SPACE` at the start of a line, LEFT IN PLACE because the text behind it could open
        a Markdown block there -- a heading, a list, a quote, a code fence, a setext underline --
        and the Symbol space is the only thing that keeps it paragraph text. A refusal, counted per
        Symbol space and kept out of ``total_changes``. Needs a human: render the source page, then
        write the line by hand.
    ``tail_kept_f020``
        A :data:`SPACE` at the END of a line, LEFT IN PLACE because without it the line could be a
        whole-line construct -- a setext underline, a thematic break, a table delimiter row, a
        link reference definition, an HTML tag, a heading with closing hashes. A refusal, counted
        per Symbol space and kept out of ``total_changes``. Needs a human.
    ``inner_kept_f020``
        A :data:`SPACE` INSIDE the text, LEFT IN PLACE because a real space there could complete a
        block opener: the first gap of a line with no letter in front of it (``#<SPACE>Title``,
        ``- <SPACE># x``), or any gap of a link reference definition. A refusal, counted per
        Symbol space and kept out of ``total_changes``. Needs a human.
    ``line_leading_marker_deferred``
        A marker in :data:`BULLETS` opening a line, left in place because it could not be read as a
        list item -- too indented, no gap after it, or an operator where the item's text would
        start -- and deleting it would flatten a nested list or a formula. Needs a human, like
        ``unknown``: read the rendered page and decide whether the line is a list item.
    ``adjacent_markers``
        A marker in :data:`BULLETS` that TOUCHES another one, left in place with its neighbour.
        Every other reading in :func:`classify` was verified against a page that prints ONE marker,
        so a run of them has no reading at all. Needs a human: render the page and write the line
        by hand. Counted once per marker, so a pair raises it by two.
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
            "adjacent_markers": 0,
            "dropped_f020": 0,
            "tail_collapsed_f020": 0,
            "tail_backslash_spaced_f020": 0,
            "head_collapsed_f020": 0,
            "head_kept_f020": 0,
            "tail_kept_f020": 0,
            "inner_kept_f020": 0,
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
        "adjacent_markers": 0,
        "dropped_f020": 0,
        "tail_collapsed_f020": 0,
        "tail_backslash_spaced_f020": 0,
        "head_collapsed_f020": 0,
        "head_kept_f020": 0,
        "tail_kept_f020": 0,
        "inner_kept_f020": 0,
        "skipped_crlf": False,
    }
    report.update(stats)
    report["in_code"] = dict(in_code)
    report["unknown"] = dict(unknown)
    # These count glyphs deliberately LEFT IN PLACE — not changes. Counting them would make
    # a refusal to guess read as a successful repair.
    deliberate = {
        "stray_unhandled",
        "line_leading_dot_deferred",
        "line_leading_marker_deferred",
        "marker_no_reading",
        "adjacent_markers",
        "head_kept_f020",
        "tail_kept_f020",
        "inner_kept_f020",
    }
    report["total_changes"] = sum(v for k, v in stats.items() if k not in deliberate)
    return out, report
