# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

r"""Remove codepoints that are illegal in interchange text: NUL and the Unicode noncharacters.

A raw ``U+0000`` in a markdown page makes the file **binary** to most tooling. `grep` stops matching
inside it and reports nothing, so the page becomes invisible to the dead-link, orphan and content
lints that guard the vault -- a silent hole in every downstream check, not a cosmetic defect.

Provenance (see wiki ``bug-converter-maps-uffff-to-nul``): *Modern C++ Tutorial* p55 prints

    throw std::out_of_range(" .");

where the two glyphs are **blank**. The PDF's own text layer holds them as ``U+FFFF`` -- a Unicode
**noncharacter**, permanently unassigned and never legal in interchange -- almost certainly a CJK
word (the book is a translation) that the font subset failed to encode. **MinerU** then writes each
one out as a raw NUL: verified in MinerU's own raw chunk output
(``base_40_79/modern-cpp-tutorial/txt/modern-cpp-tutorial.md``, ``NUL=2``), i.e. upstream of every
line of our merge code, so this cannot be fixed at our extraction boundary.

Two consequences shape this step:

* **Whole-document scope, code fences included.** The p55 occurrence is inside a ```` ```cpp ````
  block. :mod:`~pdf2wiki.phase5.symbol_pua` is deliberately scoped *outside* code, so it can never
  reach this, and widening it would break the invariant that makes its verified-glyph table safe.
* **It runs FIRST in the chain**, before any fence-parsing step. A NUL reaching a lexer, a language
  detector or a chapter splitter is a byte no downstream step is written to expect.

**Drop, do not substitute.** The characters print as *nothing* on the page, so removing them
reproduces what the reader sees, and a ``U+FFFD`` planted inside a C++ string literal would be a
character the source never had. The underlying text is already unrecoverable in the PDF -- do not
"repair" it by guessing the original word.

**Private Use Area codepoints are NOT touched here.** They are a different problem with a different
answer: PUA glyphs carry real characters (π, Σ, →) and are remapped by
:mod:`~pdf2wiki.phase5.symbol_pua` from a table where every entry was confirmed against a rendered
page. A blanket sanitizer that swept them up would destroy that content before it could be restored.

**Word joins are reported, never hidden.** Removing a codepoint that sat between two alphanumerics
merges two words (``"2<U+FFFF>3"`` -> ``"23"``). That is still the correct action for an illegal
codepoint, but it is exactly the silent-corruption shape this project has been bitten by before, so
each occurrence is counted under ``word_joins`` and surfaced by the CLI.

Fence-agnostic and encoding-agnostic: it parses no structure, so unlike ``symbol_pua`` it has no
LF-only dependency and handles CRLF input unchanged. Idempotent -- after one pass no illegal
codepoint remains, so a second pass is a no-op.
"""

from collections import Counter

#: Unicode noncharacters: the U+FDD0-U+FDEF block plus the last two codepoints of every plane.
#: Permanently reserved, never legal in interchange text (Unicode 16.0 sec. 23.7).
NONCHARACTERS: frozenset[int] = frozenset(
    set(range(0xFDD0, 0xFDF0))
    | {plane << 16 | low for plane in range(0x11) for low in (0xFFFE, 0xFFFF)}
)

#: Everything this step removes. NUL is the form the noncharacters actually arrive in, because
#: MinerU rewrites them upstream; both are stripped so either route is covered.
ILLEGAL: frozenset[int] = NONCHARACTERS | {0x0000}


def strip(md: str) -> tuple[str, dict[str, object]]:
    """Return ``(new_md, stats)`` with every illegal codepoint removed.

    ``stats`` carries:

    ``removed``
        Total codepoints deleted.
    ``counts``
        Per-codepoint tally keyed by lowercase hex (``{"0000": 2}``), so a new source of illegal
        bytes is identifiable rather than lumped into one number.
    ``word_joins``
        Runs deleted from between two alphanumeric characters -- the only shape in which this step
        can change how the surrounding text reads. A run counts once, not per codepoint.
    """
    counts: Counter[str] = Counter()
    word_joins = 0
    out: list[str] = []
    i = 0
    n = len(md)
    while i < n:
        if ord(md[i]) not in ILLEGAL:
            out.append(md[i])
            i += 1
            continue
        run_start = i
        while i < n and ord(md[i]) in ILLEGAL:
            counts[f"{ord(md[i]):04x}"] += 1
            i += 1
        # Look at the ORIGINAL string on both sides of the whole run: a run of illegal codepoints is
        # one deletion, and only alphanumeric neighbours can be silently welded into one word.
        before = md[run_start - 1] if run_start else ""
        after = md[i] if i < n else ""
        if before.isalnum() and after.isalnum():
            word_joins += 1

    stats: dict[str, object] = {
        "removed": sum(counts.values()),
        "counts": dict(counts),
        "word_joins": word_joins,
    }
    return "".join(out), stats
