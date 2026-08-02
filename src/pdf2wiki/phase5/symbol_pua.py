# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

r"""Remap Private-Use-Area glyphs that publisher PDFs emit for Symbol-font characters.

Several publisher templates (all four affected books in this corpus are Manning) embed a
``SymbolMT`` subset and emit its glyphs as **Private Use Area** codepoints with **no ``ToUnicode``
map**. `pymupdf` returns the PUA codepoint verbatim and MinerU carries it straight into the
markdown, where it is **invisible** -- it has no glyph in any normal font, so a terminal, a diff and
a reader all see nothing:

    ground truth   "if you rotate 360 degrees or 2\N{GREEK SMALL LETTER PI} radians"
    converted      "if you rotate 360 degrees or 2 radians"    # renders as "2 radians"

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

``U+F0A1`` is a list *marker*, not a character -- restoring it as a bullet glyph would leave the
list structure lost, so a line that starts with it becomes a real markdown list item. Two shapes
need care, both confirmed against rendered pages:

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
GLYPHS: dict[str, str] = {
    "": "\N{GREEK SMALL LETTER PI}",  # Math for Programmers p504, "or 2pi radians"
    "": "\N{GREEK CAPITAL LETTER SIGMA}",  # Advanced Algorithms p209, "an alphabet Sigma"
    "": "\N{RIGHTWARDS ARROW}",  # Microservices Patterns p440, "Service -> Source Envoy"
}

#: Handled structurally rather than as a character; see the module docstring.
BULLET = ""  # Deep Learning with Python p197 / p399 / p71

_PUA_CLASS = "[-]"
_PUA = re.compile(_PUA_CLASS)

# A bullet marker opening a line, optionally behind a stray emphasis opener MinerU misplaced.
_LIST_MARKER = re.compile(r"^([ \t]{0,3})\*?" + BULLET + r"[ \t]+")
# The same marker after a heading's hashes, where MinerU promoted a list item to a heading.
_HEADING_MARKER = re.compile(r"^([ \t]{0,3}#{1,6})[ \t]*" + BULLET + r"[ \t]+")


def _strip_stray(ln: str, stats: Counter[str]) -> str:
    """Drop a bullet marker left mid-line, WITHOUT ever joining two words.

    An earlier version matched ``BULLET[ \\t]*`` and so ate the marker together with the only
    whitespace separating two real words -- ``"word<PUA> next"`` became ``"wordnext"``, reported as
    a successful fix. That is precisely the silent-corruption failure class this module exists to
    remove, so the rule is now explicit and conservative:

    * remove the marker only when it already touches whitespace (or a line edge) on some side, so
      the words around it stay separated;
    * when it sits flush between two non-space characters there is no way to know whether it was a
      separator or a decoration -- **leave it alone** and count it as ``stray_unhandled``, the same
      "don't guess" rule the GLYPHS table follows.
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


def _fix_prose(text: str, stats: Counter[str]) -> str:
    """Apply every rewrite to a run of text that is known to be outside a code block."""
    out = []
    for ln in text.split("\n"):
        new = _HEADING_MARKER.sub(r"\1 ", ln)
        if new != ln:
            stats["heading_markers"] += 1
        else:
            new = _LIST_MARKER.sub(r"\1- ", ln)
            if new != ln:
                stats["list_markers"] += 1
        new = _strip_stray(new, stats)
        for pua, real in GLYPHS.items():
            n = new.count(pua)
            if n:
                stats["remap_" + f"{ord(pua):04x}"] += n
                new = new.replace(pua, real)
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
        "skipped_crlf": False,
    }
    report.update(stats)
    report["in_code"] = dict(in_code)
    report["unknown"] = dict(unknown)
    # `stray_unhandled` counts markers deliberately LEFT IN PLACE — not a change.
    report["total_changes"] = sum(v for k, v in stats.items() if k != "stray_unhandled")
    return out, report
