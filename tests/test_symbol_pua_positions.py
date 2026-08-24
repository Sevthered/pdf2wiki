# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The positional truth table for `symbol_pua`, snapshotted.

WHY THIS FILE EXISTS. `symbol_pua` reads one concept -- a marker -- in five position-dependent
ways: after a heading's hashes, opening a line inside CommonMark's indent limit, opening a line
outside it, separating two words, and flush between two of them. Those five readings USED TO live in
three anchored regexes and two branches of a character walk, so every change meant five decisions.
Nine fresh-context review rounds found the same shape of defect again and again: a caution applied
where the author was looking and not where the same constant is read next door.

This file was written BEFORE `classify` collapsed those five readings into one, so that the
collapse had an oracle to reproduce rather than an argument. It stays afterwards for the same
reason it was needed: the next change to a positional rule is still five decisions' worth of
behavior, whatever it looks like in the source.

The 219-file converted corpus cannot catch that class. `stray_markers` is **2** across all of it, so
a defect presenting as `stray_markers` hides inside the number used to prove a change is free, and
the corpus holds no formula-after-marker line at all. It can prove a change costs nothing. It cannot
prove the code is right.

So this file enumerates the input SHAPE space instead of sampling real books, and snapshots what the
step does with each shape. Every row is behavior that ships. A diff here is a behavior change:
either it was intended, and the snapshot is regenerated deliberately, or it is a defect the corpus
would never have shown.

    Regenerate deliberately with:  uv run pytest tests/test_symbol_pua_positions.py --snapshot-update

⚠ Every Private Use Area codepoint is built with `chr()` at the destination. A literal is invisible
in an editor, a diff and a review -- the same property that makes this whole defect class hard to
see -- and pasting one through a shell silently mangles it.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pdf2wiki.phase5 import symbol_pua

BULLET = symbol_pua.BULLET  # U+F0A1, a Wingdings2 square used as a list marker
DIAMOND = symbol_pua.DIAMOND  # U+F077, a Wingdings diamond: a list marker, and omega in Symbol
DOT = symbol_pua.DOT  # U+F0B7, a multiplication dot inline and a bullet in other books
SPACE = symbol_pua.SPACE  # U+F020, a Symbol-font space, which is not whitespace to CommonMark

# The axes, each chosen because some rule in the module branches on it.
_INDENTS = [
    "",  # column 0: `before` is "" and "".isspace() is False
    " ",
    "   ",  # the last indent CommonMark accepts for a list item
    "    ",  # four spaces: over the limit, and the shape that used to be DELETED
    "\t",  # one tab is four columns to CommonMark and one character to the regex
    " \t",
]
_STARS = [
    "",
    "*",  # adjacent: an emphasis opener MinerU misplaced ahead of the marker
    "* ",  # NOT adjacent: a real Markdown bullet, then a stray marker
    "**",  # a second opener closes the line again
]
_HEADS = ["", "#", "###"]  # the heading path reads the same marker after the hashes
_GAPS = ["", " ", "  ", "\t", SPACE]  # no gap means the list pattern declines the line
# An operator FIRST is a formula; a letter first is text. A body that ENDS in a backslash is
# the trigger of the second hard-break rule: without one here, no shape in the table reaches
# `tail_backslash_spaced_f020`, and a refactor that deleted that rule would reproduce this
# snapshot and its digest unchanged. Review found the hole; the table did not.
_BODIES = ["item", "= 2x", "x = 2", "", "item\\"]
# Mixed tails: real whitespace BEHIND or AROUND the Symbol space. Every earlier tail was one kind,
# so the table could not see that dropping the Symbol space uncovers the real spaces as a hard break.
_TAILS = [
    "",
    " ",
    "  ",
    SPACE,
    SPACE + SPACE,
    " " + SPACE,
    "  " + SPACE,  # the drop would uncover a hard break
    " " + SPACE + " ",
    SPACE + "  ",  # the hard break was already there, in front of CommonMark: it must stay
]


def _shapes() -> list[str]:
    """Every line shape the positional rules can tell apart, plus a mid-line control for each.

    Concatenating the axes produces collisions -- an empty body with a trailing space is the same
    string as a body of one space -- so the result is deduplicated. Uniqueness of the concatenation
    is not the property that matters; reaching every documented outcome is, and
    `test_the_table_is_not_all_one_answer` asserts that directly.
    """
    out: list[str] = []
    for marker in (BULLET, DIAMOND, DOT):
        for indent in _INDENTS:
            for head in _HEADS:
                for star in _STARS:
                    for gap in _GAPS:
                        for body in _BODIES:
                            for tail in _TAILS:
                                out.append(f"{indent}{head}{star}{marker}{gap}{body}{tail}")
        # mid-line controls: the same marker where no positional rule applies
        for left, right in (("word", "next"), ("word ", " next"), ("word", " next")):
            out.append(f"{left}{marker}{right}")
        # two adjacent markers: the known shape that needs two passes to settle
        out.append(f"word{marker}{marker} next")

    # TWO markers on one line. A line opens ONCE, and what the first marker's action emits is what
    # the second one reads. The heading action leaves `# ` behind, which is itself a valid heading
    # prefix, so `#<M>   <M> ` counted TWO promoted headings on one heading and normalised the
    # trailing whitespace a second time. Nothing above reaches that: every shape there carries a
    # single marker.
    for marker in (BULLET, DIAMOND, DOT):
        for left in ("", " ", "   ", "\t", "#", "###", "*", "a", "a "):
            for mid in ("", " ", "   ", "\t"):
                for right in ("", " ", "  ", "b"):
                    out.append(f"{left}{marker}{mid}{marker}{right}")
    return sorted(set(out))


def _row(line: str) -> str:
    """One readable line of the truth table: what went in, what came out, what was counted."""
    out, rep = symbol_pua.remap(line + "\n")
    counted = {
        k: v
        for k, v in sorted(rep.items())
        if k not in ("in_code", "unknown", "skipped_crlf") and v
    }
    return f"{line!r} -> {out[:-1]!r}  {counted}"


def _summary(shapes: list[str]) -> str:
    """A readable class summary of the table, plus a digest that pins every row of it.

    The full table is thousands of rows, which no reviewer reads and therefore no reviewer checks.
    Grouping the shapes by what the step DID to them collapses it to a page: one line per distinct
    outcome, with how many shapes reach it and the shortest one that does. A behavior change moves
    shapes between groups, which changes a count.

    The sha256 of the full table is snapshotted alongside, so a change that happens to keep every
    group count identical still shows up. Readable for a human, exact for a machine.
    """
    import hashlib
    from collections import defaultdict

    table = "\n".join(_row(s) for s in shapes)
    groups: dict[str, list[str]] = defaultdict(list)
    for line in shapes:
        out, rep = symbol_pua.remap(line + "\n")
        counted = tuple(sorted(k for k, v in rep.items() if v and k not in ("in_code", "unknown")))
        verb = "unchanged" if out == line + "\n" else "rewritten"
        groups[f"{verb}: {', '.join(counted) or 'nothing counted'}"].append(line)

    rows = [f"{len(shapes)} shapes, {len(groups)} distinct outcomes", ""]
    for key in sorted(groups):
        members = sorted(groups[key], key=lambda x: (len(x), x))
        rows.append(f"{len(members):5d}  {key}")
        rows.append(f"         e.g. {_row(members[0])}")
    rows += ["", f"sha256 of the full table: {hashlib.sha256(table.encode()).hexdigest()}"]
    return "\n".join(rows)


def test_marker_position_truth_table(snapshot):
    """Snapshot what every line shape becomes, and what the operator is told about it.

    This is the oracle a refactor of the positional rules has to reproduce. It is deliberately
    exhaustive rather than curated: the defects that reached review were all in shapes nobody
    thought to write down.
    """
    shapes = _shapes()
    assert all(BULLET in s or DIAMOND in s or DOT in s for s in shapes)

    assert _summary(shapes) == snapshot(name="marker_positions")


def test_the_table_is_not_all_one_answer():
    """A truth table where every row agrees would pass a refactor that deleted the rules.

    So assert the shapes actually reach every documented outcome. Without this, a `classify` that
    returned one class for everything could still reproduce a snapshot built from itself.
    """
    seen: set[str] = set()
    for line in _shapes():
        _, rep = symbol_pua.remap(line + "\n")
        seen.update(k for k, v in rep.items() if v and k not in ("in_code", "unknown"))

    for counter in (
        "list_markers",
        "heading_markers",
        "stray_markers",
        "stray_unhandled",
        "line_leading_marker_deferred",
        "line_leading_dot_deferred",
        "marker_no_reading",
        "dropped_f020",
        "remap_f020",
        "tail_collapsed_f020",
        "tail_backslash_spaced_f020",
        "total_changes",
    ):
        assert counter in seen, f"no shape reaches {counter}"


def test_remap_is_idempotent_on_every_shape():
    """The chain runs `symbol_pua` TWICE, so a shape that keeps changing corrupts on the second pass.

    Every unstable shape in the table is the one already filed: TWO ADJACENT markers. Pass one
    refuses the first of the pair (it is flush against another marker, which has no safe reading)
    and deletes the second, and pass two then reads the survivor as a line-opening or a stray marker
    and acts on it. That is pre-existing, it has no corpus instance, and it is filed rather than
    fixed.

    ⚠ It is pinned by SHAPE and by COUNT rather than tolerated, so a second unstable family -- or one
    more instance of this one -- fails here instead of joining an allow-list that grows quietly.
    Measured against the pre-refactor module over this same table: **17** shapes were unstable there
    and **15** are here, the two removed being tab-indented ones the column fix now defers. The
    refactor introduced none.
    """
    unstable = [
        line
        for line in _shapes()
        if symbol_pua.remap(symbol_pua.remap(line + "\n")[0])[0] != symbol_pua.remap(line + "\n")[0]
    ]

    # ...and only `BULLET + BULLET` pairs: `DOT` is a verified glyph, so both of a pair are
    # substituted in the first pass and nothing is left for the second to act on, and a `DIAMOND`
    # is never deleted, so nothing it leaves behind changes on a second read. A first version of the
    # second marker promoted it to a heading; then `#<D> <D> ` kept the second diamond on pass one
    # and pass two read `# <D> ` as a heading again -- 12 shapes, the filed defect in a new family.
    # Withholding the heading reading, which no rendered page verifies anyway, removed them all.
    assert all(BULLET + BULLET in line for line in unstable), (
        "an unstable shape that is NOT two adjacent markers is a new defect, not the filed one: "
        f"{[line for line in unstable if BULLET + BULLET not in line]}"
    )
    assert len(unstable) == 15, (
        "the number of shapes that change again on the second pass -- which the chain WILL run -- "
        f"moved from the measured 15: {unstable}"
    )


_MARKER_COUNTERS = (
    "list_markers",
    "heading_markers",
    "stray_markers",
    "stray_unhandled",
    "line_leading_marker_deferred",
    "marker_no_reading",
    "line_leading_dot_deferred",
)


def test_a_tail_symbol_space_never_decides_how_a_marker_is_read():
    """Strip the Symbol spaces off the end of every shape: the marker counters must not move.

    The tail cut-back for the hard break (`tail_collapsed_f020`) once ate the gap after a bare
    marker, and 108 shapes flipped from a read marker to a deferred one. The snapshot showed the
    category shift and nobody read it. This pins the invariant instead: a Symbol space at the line
    end is about the line end, never about the marker.
    """
    for line in _shapes():
        bare = line.rstrip(SPACE)
        if bare == line:
            continue
        _, with_space = symbol_pua.remap(line + "\n")
        _, without = symbol_pua.remap(bare + "\n")
        got = {k: with_space[k] for k in _MARKER_COUNTERS}
        want = {k: without[k] for k in _MARKER_COUNTERS}
        assert got == want, repr(line)
