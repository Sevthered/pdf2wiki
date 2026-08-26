# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The positional truth table for `symbol_pua`, snapshotted.

WHY THIS FILE EXISTS. `symbol_pua` reads one concept -- a marker -- in six position-dependent ways:
after a heading's hashes, opening a line inside CommonMark's indent limit, opening a line outside
it, separating two words, flush between two of them, and touching another marker. Five of those
USED TO live in three anchored regexes and two branches of a character walk, so every change meant
five decisions. Nine fresh-context review rounds found the same shape of defect again and again: a
caution applied where the author was looking and not where the same constant is read next door.

The sixth reading, adjacency, was added last and for the opposite reason: not because one rule was
written five times, but because NO rule covered the shape at all, so the pair was read piecewise
and the module contradicted itself across the two passes the chain runs (#74).

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
from itertools import product

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
        # two adjacent markers: the #74 shape. It needed two passes to settle, and the second
        # pass turned the first pass's refusal into a repair. Refused as a run now.
        out.append(f"word{marker}{marker} next")

    # TWO markers on one line. A line opens ONCE, and what the first marker's action emits is what
    # the second one reads. The heading action leaves `# ` behind, which is itself a valid heading
    # prefix, so `#<M>   <M> ` counted TWO promoted headings on one heading and normalised the
    # trailing whitespace a second time. Nothing above reaches that: every shape there carries a
    # single marker.
    #
    # ⚠ The pair is drawn from the MARKERS TWICE OVER, not from one marker used twice. It used to
    # be `f"{left}{marker}{mid}{marker}{right}"` -- the same marker on both sides -- so no shape in
    # 46,668 ever put a `DOT` next to a `BULLET`. The adjacency fix for #74 then broke the `DOT`
    # deferral (`<DOT><BULLET> item` was rewritten to `· item` and counted as a repair), and the
    # whole table, the group counts AND the sha256 digest reproduced without a murmur. Review found
    # it; the oracle could not. A pair axis that cannot hold two DIFFERENT markers cannot see a
    # rule that fires on the difference.
    for first, second in product((BULLET, DIAMOND, DOT), repeat=2):
        for left in ("", " ", "   ", "\t", "#", "###", "*", "a", "a "):
            for mid in ("", " ", "   ", "\t"):
                for right in ("", " ", "  ", "b"):
                    out.append(f"{left}{first}{mid}{second}{right}")
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

    This asserted **15** unstable shapes for two releases, pinned rather than tolerated. Every one
    was the filed defect (#74): TWO ADJACENT markers, read PIECEWISE. Pass one refused the first of
    the pair -- flush against another marker, which has no safe reading -- and DELETED the second,
    because a real space survived to its right and that reads as a separator. The deletion then
    moved the survivor into a position pass two read as a list item or a heading.

    ⛔ The damage was not the extra pass. It was that **ten of the fifteen turned a first-pass
    REFUSAL into a second-pass REPAIR** -- `line_leading_marker_deferred` became `list_markers`,
    `stray_unhandled` became `heading_markers` -- which is the one thing `_ACTIONS` promises never
    happens. And because `residue_lines` takes the high-water mark of the two passes, the operator
    was told a marker had been "LEFT IN PLACE" on a line the chain had already rewritten, and sent
    to render a page and write by hand a list item the chain had invented on its own. Measured on
    the real chain before the fix: two warnings claiming two markers left in place, and a chapter
    file holding **zero**.

    The fix reads adjacency FIRST, in `classify`, and refuses the whole run: every reading in that
    function was verified against a page printing ONE marker, so a run of them has no reading at
    all. Both are kept, both are counted as `adjacent_markers`, and neither counts as a change.

    ⚠ The count is now **0**, and it is asserted as 0 rather than deleted. An unstable shape of any
    family is a defect from here, so a new one fails here instead of joining an allow-list that
    grows quietly. History for the next reader: 17 shapes before the position refactor, 15 after
    it, 0 now.
    """
    unstable = [
        line
        for line in _shapes()
        if symbol_pua.remap(symbol_pua.remap(line + "\n")[0])[0] != symbol_pua.remap(line + "\n")[0]
    ]

    assert unstable == [], (
        "a shape that changes again on the second pass -- which the chain WILL run. Every such "
        f"shape was the adjacent-marker pair, and that is fixed, so this is a new defect: {unstable}"
    )


def test_adjacent_markers_are_refused_rather_than_read_piecewise():
    """A marker touching another marker is kept, counted, and never counted as a change.

    This is the invariant behind #74, stated directly rather than only as a by-product of the
    idempotence sweep. Reading one of a pair while the other is deleted is what let a refusal
    become a repair, so the property that matters is that BOTH survive and NEITHER is a change.
    """
    for line in (
        f"word{BULLET}{BULLET} next",  # mid-word: the shape the issue was filed on
        f"{BULLET}{BULLET} an item",  # line-opening: pass two used to write `- an item`
        f"#{BULLET}{BULLET} a heading",  # after hashes: pass two used to write `# a heading`
        f"{BULLET}{BULLET}{BULLET} three",  # a run longer than two
        f"{BULLET}{DIAMOND} mixed",  # the pair need not be the same marker
    ):
        out, rep = symbol_pua.remap(line + "\n")
        assert out == line + "\n", f"text changed for {line!r}: {out!r}"
        assert rep["total_changes"] == 0, f"a refusal counted as a change for {line!r}"
        assert rep["adjacent_markers"] >= 2, f"both of the pair must be counted for {line!r}"


def test_a_marker_after_a_line_leading_dot_never_cancels_the_dot_deferral():
    """A `DOT` that opens its line is deferred, whatever follows it.

    ⛔ The first version of the adjacency fix broke this. `_remap_line` asks `classify` one narrow
    question -- does this `DOT` open its line? -- and the adjacency test answered a wider one, so
    `<DOT><BULLET> item` came back `Pos.ADJACENT`, the deferral branch was skipped, and the dot was
    REWRITTEN to a middle dot. That flattens a list to a paragraph, counts as a repair, and drops
    the operator warning: the exact rewrite the `DOT` docstring says the module must never make.
    428 shapes lost the deferral, and the truth table could not see one of them, because its pair
    axis used the same marker on both sides. `_remap_line` passes `runs=False` now.

    ⚠ The second case is the over-fire guard. Putting `Pos.ADJACENT` in the caller's tuple would
    have fixed the first case and broken this one, where the dot does NOT open the line and must
    still be substituted.
    """
    for line, want_deferred in (
        (f"{DOT}{BULLET} item", True),
        (f"  {DOT}{BULLET} nested", True),
        (f"{DOT}{DIAMOND} item", True),
        (f"{DOT} item", True),
        (f"{BULLET}{DOT} item", False),  # the dot does not open the line: substitute it
        (f"word{DOT} next", False),
    ):
        _, rep = symbol_pua.remap(line + "\n")
        deferred = bool(rep["line_leading_dot_deferred"])
        assert deferred is want_deferred, (
            f"{line!r}: line_leading_dot_deferred={rep['line_leading_dot_deferred']}, "
            f"remap_f0b7={rep.get('remap_f0b7', 0)}"
        )


_MARKER_COUNTERS = (
    "list_markers",
    "heading_markers",
    "stray_markers",
    "stray_unhandled",
    "line_leading_marker_deferred",
    "marker_no_reading",
    "line_leading_dot_deferred",
    "adjacent_markers",
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
