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
    # Symbol spaces IN the indent (#77). `U+F020` is not whitespace to CommonMark, so every real
    # space BEHIND one is content, and dropping the Symbol space promotes that content to indent.
    # ⚠ These do NOT let the table reach `head_collapsed_f020`, and an earlier version of this
    # comment claimed they did. Every shape `_shapes()` builds carries a marker, and `_is_inert`
    # rejects a body that holds one, so no row here can fire the rule. Review proved it: stubbing
    # the condition to `if False` reproduces this snapshot AND its digest byte for byte. What
    # these three cover is the must-NOT-fire path, which is most of the rule. The firing path is
    # asserted directly by `test_a_plain_body_is_still_cut_back`.
    SPACE + "    ",  # indent 0 before the step, an indented code block after it
    "  " + SPACE + "  ",  # real whitespace on BOTH sides: 2 columns before, 4 after
    "    " + SPACE,  # already a code block at 4 columns: the cut-back must NOT fire
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

    # ⚠ `head_collapsed_f020` is NOT in this list, and that is a property of the table rather than
    # an omission: every shape it builds carries a marker, and the head rule edits only a body that
    # holds none. `test_a_plain_body_is_still_cut_back` asserts the counter directly, so a refactor
    # that deletes the rule still fails a test.
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
        # Reached through the three indents that hold a Symbol space, wherever the text in front
        # of the marker is a real Markdown opener (`* <M>`) or no opener the marker can use (`**`).
        "head_kept_f020",
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


def test_a_dropped_head_symbol_space_never_promotes_content_to_indent():
    """#77: the head-side twin of #73, and the mirror rule.

    ``U+F020`` is not whitespace to CommonMark, so the indent it read before the step is the real
    whitespace BEFORE the first Symbol space. Everything behind that Symbol space is content. The
    drop used to keep it all, which is how ``<SPACE>`` and four real spaces became an indented code
    block: a paragraph line before the step, a code block after it.

    Measured with cmark-gfm over 400 shapes: 80 changed their indent-derived structure on `main`,
    0 on this rule.

    ⚠ The rule fires only when the drop reaches `_TAB_STOP` columns, which mirrors the tail twin:
    that one fires only when a hard break would really appear. Below four columns the indent
    changes no rendering for a body that opens no block, and an edit there would report a repair
    that repairs nothing.
    """
    cases = [
        (SPACE + "    text", "text"),  # the issue's own repro
        (SPACE + "     text", "text"),
        ("  " + SPACE + "    text", "  text"),  # 2 columns before the step, 4 after
        (SPACE + "\ttext", "text"),  # a tab is four columns, not one character
        (SPACE + "   " + SPACE + " text", "text"),  # two Symbol spaces, one indent
    ]
    for line, want in cases:
        got, rep = symbol_pua.remap(line + "\n")
        assert got == want + "\n", repr(line)
        assert rep["head_collapsed_f020"] == 1, repr(line)


def test_the_head_cut_back_leaves_a_real_indented_code_block_alone():
    """The one shape the rule must NOT touch, and the reason it is a rule and not a strip.

    When four columns of real whitespace already sit in front of the first Symbol space, the line
    is an indented code block on its own, before the step. The whitespace behind the Symbol space
    is then literal code content, and cutting it back would edit the code -- the same class of
    edit `DOT` exists to refuse.
    """
    line = "    " + SPACE + "   text"
    got, rep = symbol_pua.remap(line + "\n")
    assert got == "       text\n"  # 4 columns of indent + 3 literal content spaces
    assert rep["head_collapsed_f020"] == 0
    assert rep["dropped_f020"] == 1


def test_a_head_symbol_space_with_no_real_whitespace_behind_it_is_only_dropped():
    """A drop that uncovers nothing needs no cut-back, and must not claim one.

    `dropped_f020` holds every benign drop, which is why #77 said it points an operator at nothing.
    The new counter has to stay narrow enough to mean something.
    """
    for line in (SPACE + "text", SPACE + SPACE + "text", " " + SPACE + "text"):
        _, rep = symbol_pua.remap(line + "\n")
        assert rep["head_collapsed_f020"] == 0, repr(line)
        assert rep["dropped_f020"] >= 1, repr(line)


def test_the_head_rule_counts_columns_and_not_characters():
    """CommonMark spec 2.2: a tab advances to the next multiple of four.

    Reading a tab as one character is a live bug elsewhere in this module (the ``[ \\t]{0,3}``
    limits), so the head rule must not repeat it. ``<SPACE><TAB>`` is four columns and crosses the
    threshold; ``  <SPACE>\\t`` reaches four columns from two, and crosses it too.
    """
    assert symbol_pua._columns("\t") == 4
    assert symbol_pua._columns("  \t") == 4  # the tab completes the group, it does not add four
    assert symbol_pua._columns("    ") == 4
    assert symbol_pua._columns("   ") == 3
    got, rep = symbol_pua.remap("  " + SPACE + "\ttext\n")
    assert got == "  text\n"
    assert rep["head_collapsed_f020"] == 1


def test_the_head_is_left_alone_unless_the_body_is_provably_inert():
    """The whitelist, and the three review rounds behind it.

    A blacklist of block openers was wrong three times, and each time it tested a narrower string
    than `classify` and CommonMark read: a PUA marker behind the Symbol space, an emphasis opener
    in front of one, promoted hashes, a Symbol space used as the delimiter itself, an HTML block,
    and the two-hyphen setext underline. Every shape below was a measured regression in one of
    those rounds. The rule now edits only a body that starts with a letter and carries no marker
    and no Symbol space, so an unnamed shape is not edited at all.
    """
    for body in (
        "- item",
        "1. one",
        "1) one",
        "# head",
        "> quote",
        "```",
        "~~~",
        "*** ",
        "___ ",
        "===",
        "--",
        "<table>",
        "<div>",
        "<!-- c -->",
        "**bold**",
        BULLET + " item",
        DIAMOND + " item",
        DOT + " item",  # round two
        "*" + DIAMOND + " item",
        "#" + BULLET + " item",  # round three: prefix before a marker
        "-" + SPACE + "item",
        "#" + SPACE + "h",  # round three: SPACE as the delimiter
    ):
        line = "  " + SPACE + "  " + body
        _, rep = symbol_pua.remap(line + "\n")
        assert rep["head_collapsed_f020"] == 0, repr(line)


def test_an_inert_body_still_renders_like_the_source_under_a_paragraph():
    """The property the rule exists for, on the shape that broke the first version."""
    src = "para above\n" + SPACE + "    text\n"
    got, rep = symbol_pua.remap(src)
    assert got == "para above\ntext\n"
    assert rep["head_collapsed_f020"] == 1


def test_a_plain_body_is_still_cut_back():
    """The whitelist must stay wide enough to fix the issue's own repro."""
    for body in ("text", "word two", "a - b"):
        line = SPACE + "    " + body
        got, rep = symbol_pua.remap(line + "\n")
        assert got == body + "\n", repr(line)
        assert rep["head_collapsed_f020"] == 1, repr(line)


def test_a_whitespace_only_line_reports_no_head_cut_back():
    """Both forms are a blank line to CommonMark, so an edit there points an operator at nothing."""
    _, rep = symbol_pua.remap("  " + SPACE + "  \n")
    assert rep["head_collapsed_f020"] == 0


def test_a_head_symbol_space_never_decides_how_a_marker_is_read():
    """The head twin of `test_a_tail_symbol_space_never_decides_how_a_marker_is_read`.

    Review caught both ways this rule broke the invariant on a body that opens with a PUA marker.
    A cut-back moves the marker to column 0, and a DEFERRAL becomes a REPAIR
    (`line_leading_marker_deferred` -> `list_markers`), which `_ACTIONS` promises never happens. A
    refusal keeps the Symbol space in front of the marker, so `classify` stops reading the marker
    as line-leading, it becomes a stray, and a stray is DELETED -- the flattened nested list of
    `bug-symbol-pua-nested-bullet-deleted`, which this project has shipped once already. It also
    left 857 shapes unstable across the chain's two passes, because the same pass deleted the
    marker that justified the refusal.

    Both branches therefore step aside for a marker body, and the counters must match the tree
    that has no head rule at all.
    """
    for marker in (BULLET, DIAMOND, DOT):
        for head in (
            SPACE + "    ",
            "  " + SPACE + "  ",
            SPACE + "\t",
            SPACE + "   " + SPACE + " ",
        ):
            line = head + marker + " item"
            got, rep = symbol_pua.remap(line + "\n")
            assert rep["head_collapsed_f020"] == 0, repr(line)
            assert rep["stray_markers"] == 0, repr(line)  # the marker is never deleted
            # and the line settles: the chain runs this step twice
            assert symbol_pua.remap(got)[0] == got, repr(line)


def test_a_head_that_is_not_commonmark_indentation_is_left_alone():
    """`str.isspace()` is wider than CommonMark indentation, and PDF text is full of the difference.

    ``U+00A0`` and ``U+2003`` are `isspace()` in Python and are not indentation to the parser. A
    line that opens with one stands at indent 0 before AND after the drop, so no indented code
    block was ever possible, and a cut-back would delete real paragraph content while reporting an
    indent repair. Review found this. The whitelist covers the head for the same reason it covers
    the body.
    """
    for pad in ("\u00a0", "\u2003", "\u3000", ""):
        line = pad + SPACE + "    text"
        got, rep = symbol_pua.remap(line + "\n")
        if pad:
            assert rep["head_collapsed_f020"] == 0, repr(line)
            assert got == pad + "    text\n", repr(line)  # the real spaces stay, as on 0.2.10
        else:
            assert rep["head_collapsed_f020"] == 1, repr(line)
            assert got == "text\n", repr(line)


def test_a_head_symbol_space_in_front_of_a_block_opener_is_kept(block_openers):
    """#94: the drop put a block opener at the start of its line, and the opener became structure.

    ``U+F020`` is not whitespace to CommonMark, so a line that starts with one is paragraph text
    whatever comes next. ``<SPACE># Title`` is a paragraph line before the step. The plain drop
    wrote ``# Title``, which is a heading. Nothing shows which of the two the page prints, so the
    step keeps the Symbol space and counts it, the same answer :data:`DOT` gives.

    The count is per Symbol space, like ``dropped_f020``, and it is a refusal: it is not a change,
    and the same space is not counted as dropped as well.
    """
    for head in (SPACE, " " + SPACE, SPACE + SPACE, SPACE + " ", SPACE + "    "):
        for body in block_openers:
            line = head + body
            got, rep = symbol_pua.remap(line + "\n")
            assert got == line + "\n", repr(line)
            assert rep["head_kept_f020"] == head.count(SPACE), repr(line)
            assert rep["dropped_f020"] == 0, repr(line)
            assert rep["head_collapsed_f020"] == 0, repr(line)
            assert rep["total_changes"] == 0, repr(line)
            # and the line settles: the chain runs this step twice
            assert symbol_pua.remap(got)[0] == got, repr(line)


def test_a_kept_head_does_not_stop_the_rest_of_the_line():
    """Only the head is refused. A Symbol space inside the body and one at the tail are still read."""
    got, rep = symbol_pua.remap(SPACE + "# a" + SPACE + "b" + SPACE + "\n")
    assert got == SPACE + "# a b\n"
    assert rep["head_kept_f020"] == 1
    assert rep["remap_f020"] == 1  # the one inside the body became a real space
    assert rep["dropped_f020"] == 1  # the one at the tail was dropped, and only that one


def test_a_head_symbol_space_in_front_of_a_letter_is_still_dropped():
    """The control. A body that starts with a letter opens no block, so the drop is safe.

    "A letter" is `str.isalpha()`, not ASCII. The first version of the rule tested `[A-Za-z]` and
    kept the Symbol space in front of an accented letter, where the previous release wrote a clean
    line. Measured before it was widened: 48,965 letters of the Basic Multilingual Plane, 60
    contexts each, and the drop changed the block structure of no line.
    """
    for line in (
        SPACE + "text",
        SPACE + SPACE + "Text more",
        " " + SPACE + "x = 1",
        SPACE + "\u00e9 accent",
        SPACE + "\u03c0 radians",  # a real Greek letter, not the Symbol glyph
    ):
        got, rep = symbol_pua.remap(line + "\n")
        assert SPACE not in got, repr(line)
        assert rep["head_kept_f020"] == 0, repr(line)
        assert rep["dropped_f020"] >= 1, repr(line)


def test_a_head_symbol_space_in_front_of_a_mapped_glyph_is_still_dropped():
    """The likely real shape: a line that starts inside a Symbol-font run.

    Review found that the first version of the rule kept the Symbol space here, because a PUA
    glyph is not a letter. Seventeen of the nineteen glyphs are written out as a non-ASCII
    character, and the drop in front of one changed the rendering of no measured line, so the line
    is cleaned as it was before #94. The other two are the parentheses, and the next test is why
    they are not here.
    """
    for glyph, real in symbol_pua.GLYPHS.items():
        if glyph == SPACE or real.isascii():
            continue
        got, rep = symbol_pua.remap(SPACE + glyph + " (pi) symbol 56\n")
        if glyph == DOT:  # a line-opening dot is deferred, and the head in front of it still goes
            assert got == DOT + " (pi) symbol 56\n"
        else:
            assert got == real + " (pi) symbol 56\n", repr(glyph)
        assert rep["head_kept_f020"] == 0, repr(glyph)


def test_a_glyph_written_out_as_ascii_does_not_unlock_the_drop():
    """``U+F028`` becomes ``(``, and ``(`` opens the title of a link reference definition.

    ``[x]: /u`` and then ``<SPACE><F028>see note<F029>`` is a definition and a paragraph before the
    step. With the head dropped the second line is ``(see note)``, a valid title, and the whole
    line is swallowed: it renders as nothing. Review found it, and the first measurement could not,
    because it compared block tags and a swallowed line leaves them equal. So a glyph is judged by
    what it is written out as, and an ASCII character gets no benefit of the doubt.
    """
    lparen, rparen = "\uf028", "\uf029"
    assert symbol_pua.GLYPHS[lparen] == "(" and symbol_pua.GLYPHS[rparen] == ")"
    for glyph in (lparen, rparen):
        got, rep = symbol_pua.remap("[x]: /u\n" + SPACE + glyph + "see note" + rparen + "\nnext\n")
        assert got.split("\n")[1].startswith(SPACE), repr(glyph)
        assert rep["head_kept_f020"] == 1, repr(glyph)


def test_no_glyph_is_written_out_as_an_ascii_letter():
    """A property of the table that the #94 whitelist leans on, pinned so a new entry cannot break it.

    A glyph that is written out as a non-ASCII character is judged with the indent guard. An ASCII
    letter is judged without it, because that ground belongs to #77. A glyph that became an ASCII
    letter would be read by the first rule on one pass and, once written out, by the second rule
    on the next: kept, then dropped, with a warning about a Symbol space that is gone. No entry
    does that today. If this fails, read `_head_may_be_dropped` before adding the entry.
    """
    for glyph, written in symbol_pua.GLYPHS.items():
        assert not (written.isascii() and written.isalpha()), repr(glyph)


def test_the_indent_guard_measures_indent_as_the_parser_does():
    """Real spaces behind the Symbol space become indent whatever else the head holds.

    The first version of the guard was switched off for any head that held a character other than
    a space, a tab or a Symbol space. ``<SPACE>    <NBSP>`` is such a head, and its four real spaces
    are indent once the Symbol space in front of them is gone: a paragraph line became an indented
    code block, counted as a harmless drop. ``<NBSP>`` in FRONT is the opposite case. The line
    stands at indent 0 before and after, so nothing grows and the drop is safe.
    """
    pi, nbsp = "\uf070", "\u00a0"
    got, rep = symbol_pua.remap(SPACE + "    " + nbsp + pi + " radians\n")
    assert got.startswith(SPACE) and rep["head_kept_f020"] == 1
    got, rep = symbol_pua.remap(nbsp + SPACE + "    " + pi + " radians\n")
    assert SPACE not in got and rep["head_kept_f020"] == 0


def test_no_short_line_gives_two_passes_two_answers():
    """Every head, in front of every body of up to four tokens: the second pass changes nothing.

    The chain runs this step twice, and a refusal counts as its high-water mark. So a head that
    one pass keeps and the next drops leaves a warning about a Symbol space that is no longer
    there. Two versions of the #94 rule did that, and each time a single test caught it. The
    second time no committed test did: ``<SPACE>    #<BULLET> <DIAMOND> item`` needs TWO markers,
    and no shape in either grid had two behind a kept head. Review found it by fuzzing.

    This is that fuzz, cut down to the tokens the marker rules branch on. Both the text and the
    kept count must agree, because the count is what the operator reads.
    """
    heads = [SPACE, SPACE + "    ", "    " + SPACE, "  " + SPACE + "  ", SPACE + "\t"]
    heads += ["\u00a0" + SPACE + "    ", SPACE + "    \u00a0", SPACE + SPACE]
    tokens = [BULLET, DIAMOND, DOT, "#", "*", "-", " ", "x", "\uf070"]
    for size in range(1, 5):
        for body in map("".join, product(tokens, repeat=size)):
            for head in heads:
                once, rep = symbol_pua.remap(head + body + "\n")
                twice, rep2 = symbol_pua.remap(once)
                assert twice == once, repr(head + body)
                assert rep2["head_kept_f020"] == rep["head_kept_f020"], repr(head + body)


def test_a_head_symbol_space_in_front_of_a_marker_that_opens_the_line_is_still_dropped():
    """Keeping the head there would turn a line-opening marker into a mid-line one.

    Every marker reading is positional, and the line-opening tests accept real indent only. A
    Symbol space left in front of a marker makes it a stray: a list item loses its marker, or a
    deferral becomes a deletion. Review found that class while #77 was fixed, 857 shapes of it. So
    a line that a marker opens is read by :func:`classify` exactly as it was before this rule.
    """
    for marker in (BULLET, DIAMOND):
        for prefix in ("", "*"):  # the emphasis opener MinerU misplaces ahead of a marker
            line = SPACE + prefix + marker + " item"
            got, rep = symbol_pua.remap(line + "\n")
            assert got == "- item\n", repr(line)
            assert rep["list_markers"] == 1 and rep["head_kept_f020"] == 0, repr(line)
    got, rep = symbol_pua.remap(SPACE + "## " + BULLET + " With temperature\n")
    assert got == "## With temperature\n"
    assert rep["heading_markers"] == 1 and rep["head_kept_f020"] == 0
    got, rep = symbol_pua.remap(SPACE + DOT + " item\n")
    assert got == DOT + " item\n"
    assert rep["line_leading_dot_deferred"] == 1 and rep["head_kept_f020"] == 0


def test_a_marker_behind_a_block_opener_does_not_unlock_the_drop():
    """The first marker decides, and only when it OPENS the line.

    ``<SPACE>- <BULLET> item`` has a marker on it, and that marker does not open the line: a real
    Markdown bullet stands in front of it. The opener is the ``-``, so the head stays. The stray
    marker behind it is read as it always was.
    """
    got, rep = symbol_pua.remap(SPACE + "- " + BULLET + " item\n")
    assert got == SPACE + "- item\n"
    assert rep["head_kept_f020"] == 1 and rep["stray_markers"] == 1
    assert rep["list_markers"] == 0
    assert symbol_pua.remap(got)[0] == got


# ---- #96: the other two edges of #94, the line END and the first gap INSIDE the text ----

# Whole-line constructs: text that is a block only when NOTHING but whitespace follows it.
_WHOLE_LINE = ["---", "===", "***", "___", "-", "- - -", "#", "1.", "# Title #", "|---|---|"]


def test_a_tail_symbol_space_behind_a_whole_line_construct_is_kept():
    """#96: the drop at the line END turned paragraph text into a block marker.

    ``U+F020`` is not whitespace to CommonMark, so ``---<SPACE>`` is paragraph text: an underline
    must be alone on its line. The drop wrote ``---``, and the line ABOVE became a heading. The
    same happened for a thematic break, an empty heading, an empty list item, a table delimiter
    row and the closing hashes of a heading. The Symbol space now stays, counted as
    ``tail_kept_f020``, a refusal and not a change.
    """
    for body in _WHOLE_LINE:
        for tail in (SPACE, SPACE + SPACE, " " + SPACE):
            line = body + tail
            got, rep = symbol_pua.remap("para\n" + line + "\n")
            assert got == "para\n" + line + "\n", repr(line)
            assert rep["tail_kept_f020"] == tail.count(SPACE), repr(line)
            assert rep["dropped_f020"] == 0 and rep["total_changes"] == 0, repr(line)
            assert rep["tail_collapsed_f020"] == 0, repr(line)
            assert symbol_pua.remap(got)[0] == got, repr(line)


def test_a_tail_symbol_space_behind_a_definition_or_a_tag_is_kept():
    """The whole-line constructs that DO hold a letter, so the letter test cannot clear them.

    ``[ref]: /url <SPACE>`` is paragraph text, because the Symbol space is no valid title. Without
    it the line is a link reference definition and renders as nothing. ``<div<SPACE>`` is no tag,
    and ``<div`` at a line end opens an HTML block. Closing hashes count only at the very end of
    a heading line. Each is refused by name, and at any depth of list or quote, because a
    container marker stands in the lead of the line like everything else that decides what it is.
    """
    for line in (
        "[ref]: /url " + SPACE,
        "> [ref]: /url " + SPACE,
        "<div" + SPACE,
        "<span>" + SPACE,
        "- <div" + SPACE,
        "# Title #" + SPACE,
        "- # Title #" + SPACE,
    ):
        got, rep = symbol_pua.remap(line + "\nnext\n")
        assert got == line + "\nnext\n", repr(line)
        assert rep["tail_kept_f020"] == 1 and rep["dropped_f020"] == 0, repr(line)


def test_a_tail_symbol_space_behind_a_line_with_a_word_in_it_is_still_dropped():
    """The control, and the whole of the whitelist: a whole-line construct holds no letter.

    A setext underline, a thematic break, a table delimiter row, an empty heading and an empty list
    item are made of punctuation and digits. So a line with a word in it is none of them, whatever
    it starts or ends with, and the drop is as safe as it always was.
    """
    for body in ("text", "## Title", "- item", "1. First step.", "(see note)", "**bold**", "x = 1",
                 "> quote", "[1] Smith, J.", "- # Title", "H<sub>2</sub>O", "\uf070 radians", "é"):  # fmt: skip
        got, rep = symbol_pua.remap(body + SPACE + "\nnext\n")
        assert SPACE not in got, repr(body)
        assert rep["tail_kept_f020"] == 0 and rep["dropped_f020"] == 1, repr(body)


def test_a_symbol_space_that_would_complete_an_opener_is_kept():
    """#96: written as a real space, the first gap INSIDE the text made the line a block.

    ``#<SPACE>Title`` is paragraph text, because a heading needs real whitespace behind its
    hashes. The substitution wrote ``# Title``. A list marker and an HTML tag name are completed
    the same way. The Symbol space stays, counted as ``inner_kept_f020``.
    """
    for prefix in ("#", "##", "######", "-", "+", "*", "1.", "1)", "12.", "<div", "</div"):
        line = prefix + SPACE + "item"
        got, rep = symbol_pua.remap("para\n" + line + "\nnext\n")
        assert got == "para\n" + line + "\nnext\n", repr(line)
        assert rep["inner_kept_f020"] == 1, repr(line)
        assert rep.get("remap_f020", 0) == 0 and rep["total_changes"] == 0, repr(line)
        assert symbol_pua.remap(got)[0] == got, repr(line)


def test_only_the_first_gap_of_a_line_can_complete_an_opener():
    """Every Symbol space behind the first gap is written as a real space, as before."""
    got, rep = symbol_pua.remap("#" + SPACE + "a" + SPACE + "b" + SPACE + "c\n")
    assert got == "#" + SPACE + "a b c\n"
    assert rep["inner_kept_f020"] == 1 and rep["remap_f020"] == 2
    # a word in front of the first Symbol space: the lead of the line is over
    got, rep = symbol_pua.remap("- real" + SPACE + "item\n")
    assert got == "- real item\n"
    assert rep["inner_kept_f020"] == 0 and rep["remap_f020"] == 1


def test_a_symbol_space_at_the_start_of_a_container_is_kept():
    """Real whitespace in front of the gap does NOT make it safe, and the first rule said it did.

    ``- <SPACE># x`` is a list item that holds the text ``# x``. The Symbol space stands at the
    start of the item's CONTENT, which is a line start of its own, and ``-  # x`` is a heading
    inside the item. Measured through the step, 1,687 lines of 2.2 million, before any review.
    The rule asks for a LETTER in front of the gap, and a container marker holds none.
    """
    for lead in ("- ", "> ", "1. ", "- > ", "> - ", "* "):
        for opener in ("# x", "- x", "* x", "> x", "1. x"):
            line = lead + SPACE + opener
            got, rep = symbol_pua.remap(line + "\nnext\n")
            assert got == line + "\nnext\n", repr(line)
            assert rep["inner_kept_f020"] == 1 and rep["total_changes"] == 0, repr(line)


def test_a_link_reference_definition_is_not_edited_inside_at_all():
    """The one construct parsed to the END of its line, so every gap in it decides what it is.

    ``[x]: a<SPACE>b`` is a definition, with the Symbol space in its destination, and it renders
    as nothing. ``[x]: a b`` is a paragraph, because ``b`` is no valid title. So all of its
    Symbol spaces stay, not only the first.
    """
    line = "[x]: a" + SPACE + "b" + SPACE + "c" + SPACE
    got, rep = symbol_pua.remap(line + "\nnext\n")
    assert got == line + "\nnext\n"
    assert rep["inner_kept_f020"] == 2 and rep["tail_kept_f020"] == 1 and rep["total_changes"] == 0
    # ⚠ A bracket alone is no definition. A bibliography is full of lines like this one.
    got, rep = symbol_pua.remap("[1] Smith" + SPACE + "J." + SPACE + "\n")
    assert got == "[1] Smith J.\n"
    assert rep["inner_kept_f020"] == 0 and rep["tail_kept_f020"] == 0


def test_a_closed_tag_in_front_of_the_gap_lets_the_cells_of_a_table_through():
    """``<div<SPACE>class>`` becomes a tag, and a ``<table>`` line is the HTML a converter writes.

    Behind a ``<`` in the lead the gap is safe only when a ``>`` already stands in front of it:
    then the tag that leads the line was complete before the step, and the gap is in its content.
    """
    got, rep = symbol_pua.remap(
        "<table><tr><td>a" + SPACE + "b</td><td>c" + SPACE + "d</td></tr></table>\n"
    )
    assert got == "<table><tr><td>a b</td><td>c d</td></tr></table>\n"
    assert rep["inner_kept_f020"] == 0 and rep["remap_f020"] == 2
    got, rep = symbol_pua.remap("<span" + SPACE + 'class="a">x</span>\n')
    assert got == "<span" + SPACE + 'class="a">x</span>\n' and rep["inner_kept_f020"] == 1


def test_a_symbol_space_inside_ordinary_text_is_still_a_real_space():
    """The control. Substitution is what the step is FOR, so the refusal has to stay narrow.

    The text in front of the first gap holds a letter and is no tag, so it is no opener prefix: an
    ATX prefix is hashes, a bullet is one character, an ordered marker is digits and a delimiter.
    """
    for line, want in (
        ("a" + SPACE + "b", "a b"),
        ("\uf070" + SPACE + "(pi) symbol 56", "\N{GREEK SMALL LETTER PI} (pi) symbol 56"),
        ("(pi)" + SPACE + "symbol 56", "(pi) symbol 56"),
        ("**bold**" + SPACE + "text", "**bold** text"),
        ('"Quoted' + SPACE + 'text"', '"Quoted text"'),
        ("x:" + SPACE + "y", "x: y"),
    ):
        got, rep = symbol_pua.remap(line + "\n")
        assert got == want + "\n", repr(line)
        assert rep["inner_kept_f020"] == 0, repr(line)


def test_the_two_new_refusals_leave_a_line_with_a_marker_alone():
    """A marker on the line, and the tail and the first gap are handled as they always were.

    The marker pass deletes and rewrites, and a refusal it can undo is what broke the #94 rule
    twice in review. So these two rules act on a line with no marker in it, where one pass changes
    nothing the next pass reads. A Symbol space as the gap behind a marker is the oldest shape this
    step repairs, and it must stay repaired.
    """
    got, rep = symbol_pua.remap(BULLET + SPACE + "item" + SPACE + "\n")
    assert got == "- item\n"
    assert rep["list_markers"] == 1 and rep["inner_kept_f020"] == 0 and rep["tail_kept_f020"] == 0
    # the previous release's output, and a stated limit: the bullet in front makes it a list
    got, rep = symbol_pua.remap("-" + SPACE + BULLET + " item\n")
    assert got == "- item\n" and rep["inner_kept_f020"] == 0


def test_a_kept_head_makes_the_rest_of_the_line_safe():
    """Behind a kept head the line starts with a Symbol space, so nothing on it can open a block."""
    got, rep = symbol_pua.remap(SPACE + "#" + SPACE + "Title" + SPACE + "\n")
    assert got == SPACE + "# Title\n"
    assert rep["head_kept_f020"] == 1 and rep["inner_kept_f020"] == 0 and rep["tail_kept_f020"] == 0
    got, rep = symbol_pua.remap("para\n" + SPACE + "---" + SPACE + "\n")
    assert got == "para\n" + SPACE + "---\n"
    assert rep["head_kept_f020"] == 1 and rep["tail_kept_f020"] == 0


def test_a_glyph_is_written_as_ascii_only_where_the_rules_know_it():
    """The #96 whitelists test three ASCII characters, and no glyph may become one of them.

    The tail rule asks if a line is led by ``[`` or ``<`` or closed by ``#``, and it asks the line
    as it stands BEFORE the glyphs are written out. A glyph that became one of those would be read
    one way by this pass and the other way by the next. The parentheses are the only ASCII in the
    table besides the space itself.
    """
    ascii_written = {w for g, w in symbol_pua.GLYPHS.items() if w.isascii()}
    assert ascii_written == {" ", "(", ")"}


def test_no_short_marker_free_line_gives_two_passes_two_answers():
    """The token fuzz again, for the three refusals together and with no marker in the line.

    Every head, body and tail of short tokens: the second pass must change nothing, and each of
    the three kept counts must be the same on both passes, because a count is what the operator
    reads.
    """
    heads = ["", SPACE, "  ", SPACE + "    ", "    " + SPACE]
    tails = ["", SPACE, " " + SPACE, SPACE + SPACE, "  " + SPACE]
    tokens = ["#", "-", "*", "1.", "x", " ", SPACE, "<", "[", "]:", "_", "\uf070", "\uf028", "\\"]
    kept = ("head_kept_f020", "tail_kept_f020", "inner_kept_f020")
    for size in range(1, 4):
        for body in map("".join, product(tokens, repeat=size)):
            if not body.strip(" " + SPACE):
                continue
            for head, tail in product(heads, tails):
                once, rep = symbol_pua.remap(head + body + tail + "\n")
                twice, rep2 = symbol_pua.remap(once)
                assert twice == once, repr(head + body + tail)
                assert [rep2[k] for k in kept] == [rep[k] for k in kept], repr(head + body + tail)


# ---- #96, what the first review round found ----


def test_a_dot_in_the_middle_of_a_line_does_not_switch_the_two_refusals_off():
    """Only a dot that OPENS its line belongs to a marker rule. Any other is a multiplication sign.

    The first version of the guard skipped every line that held a dot anywhere. A dot and a Symbol
    space come from the same font, so those are the lines most likely to hold both, and
    ``#<SPACE>r<DOT>u`` was a heading again.
    """
    got, rep = symbol_pua.remap("#" + SPACE + "r" + DOT + "u\n")
    assert got == "#" + SPACE + "r\N{MIDDLE DOT}u\n"
    assert rep["inner_kept_f020"] == 1
    got, rep = symbol_pua.remap("para\n---" + SPACE + DOT + "\n")  # a letter-free line with a dot
    assert rep["inner_kept_f020"] == 1 and SPACE in got
    # a dot that opens the line is deferred, and it is text: the gaps behind it are written out
    got, rep = symbol_pua.remap(DOT + SPACE + "item" + SPACE + "\n")
    assert got == DOT + " item\n"
    assert rep["line_leading_dot_deferred"] == 1 and rep["inner_kept_f020"] == 0


def test_a_gap_in_front_of_closing_hashes_is_kept():
    """``# Title<SPACE>#`` prints its last hash, and ``# Title #`` does not.

    The tail rule refused the closing sequence from one side and the gap rule let it in from the
    other. The gap is kept wherever it stands, and the gaps in front of it are written out.
    """
    got, rep = symbol_pua.remap("# Title" + SPACE + "#\n")
    assert got == "# Title" + SPACE + "#\n" and rep["inner_kept_f020"] == 1
    got, rep = symbol_pua.remap("## A" + SPACE + "B" + SPACE + "##\n")
    assert got == "## A B" + SPACE + "##\n"
    assert rep["inner_kept_f020"] == 1 and rep["remap_f020"] == 1


def test_a_quote_marker_is_not_the_end_of_a_tag():
    """The ``>`` that lets a gap through must close the LAST tag in front of it."""
    line = "> <div" + SPACE + 'class="a">'
    got, rep = symbol_pua.remap(line + "\n")
    assert got == line + "\n" and rep["inner_kept_f020"] == 1


def test_a_line_with_a_kept_gap_keeps_its_tail_too():
    """A kept gap and a dropped tail is a line neither the source nor the last release wrote.

    Under a link label it was a new loss: ``-<SPACE>item <SPACE>`` became one token, a
    destination, and both lines rendered as nothing. Kept whole, the line is the source's line.
    """
    line = "-" + SPACE + "item " + SPACE
    got, rep = symbol_pua.remap("[x]:\n" + line + "\n")
    assert got == "[x]:\n" + line + "\n"
    assert rep["inner_kept_f020"] == 1 and rep["tail_kept_f020"] == 1 and rep["total_changes"] == 0


def test_a_task_marker_is_not_completed():
    """``- [x]<SPACE>done`` holds a letter, and ``- [x] done`` is a checked box in the vault.

    The whitelist of the gap rule says a letter in front means the lead of the line is over. A
    task marker is the one marker that holds a letter, so a bracket that closes right in front of
    the gap is refused. ``[link](u)`` closes with a parenthesis and is let through.
    """
    for line in ("- [x]" + SPACE + "done", "- [X]" + SPACE + "done", "[12]" + SPACE + "Smith"):
        got, rep = symbol_pua.remap(line + "\n")
        assert got == line + "\n" and rep["inner_kept_f020"] == 1, repr(line)
    got, rep = symbol_pua.remap("[link](u)" + SPACE + "text\n")
    assert got == "[link](u) text\n" and rep["inner_kept_f020"] == 0
    # and at the line end: `- [x] <SPACE>` is an item with content, `- [x] ` is an empty one
    got, rep = symbol_pua.remap("- [x] " + SPACE + "\nnext\n")
    assert got == "- [x] " + SPACE + "\nnext\n" and rep["tail_kept_f020"] == 1


def test_the_tail_behind_a_closed_tag_with_content_is_still_dropped():
    """A ``<table>`` line is the same HTML block with or without its tail, and the commonest one.

    ``<div`` is unfinished and ``<span>`` alone on its line is a block of its own kind, so those
    two keep their tail. A tag that is closed and has content behind it does not.
    """
    got, rep = symbol_pua.remap("<table><tr><td>a</td></tr></table>" + SPACE + "\n")
    assert got == "<table><tr><td>a</td></tr></table>\n"
    assert rep["tail_kept_f020"] == 0 and rep["dropped_f020"] == 1
    for line in ("<div" + SPACE, "<span>" + SPACE, "> <div" + SPACE):
        assert symbol_pua.remap(line + "\n")[1]["tail_kept_f020"] == 1, repr(line)


# ---- #96, what the second review round found ----


def test_a_line_with_a_pipe_in_it_keeps_its_tail():
    """The header row of a pipe table is decided by the line BELOW, which this step cannot see.

    ``| a | b |<SPACE>`` has three cells, and ``| a | b |`` has two. A table needs a delimiter row
    with the same number, so the drop makes one or unmakes one. Review found it. The measurement
    behind the first version could not, because none of its lines had a line below. A kept head
    does not make it safe either: a header row is no line-start construct.
    """
    for line in ("| a | b |" + SPACE, "a | b" + SPACE, "x" + SPACE + "|" + SPACE):
        got, rep = symbol_pua.remap(line + "\n|---|---|\n| 1 | 2 |\n")
        assert got.split("\n")[0].endswith(SPACE), repr(line)
        assert rep["tail_kept_f020"] == 1, repr(line)
    got, rep = symbol_pua.remap(SPACE + "| a | b |" + SPACE + "\n")
    assert got == SPACE + "| a | b |" + SPACE + "\n"
    assert rep["head_kept_f020"] == 1 and rep["tail_kept_f020"] == 1


def test_a_code_fence_still_loses_its_tail():
    """The one line that is dropped although it holds no text, and on purpose.

    A fence with a Symbol space behind it does not CLOSE a code block, and without it it does.
    Kept, the block stays open and the rest of the chapter renders as code, which is what the
    first version of the tail rule did to a document the previous release repaired.
    """
    for fence in ("```", "~~~", "`````"):
        got, rep = symbol_pua.remap("```python\nx = 1\n" + fence + SPACE + "\n\nprose\n")
        assert got == "```python\nx = 1\n" + fence + "\n\nprose\n", repr(fence)
        assert rep["tail_kept_f020"] == 0 and rep["dropped_f020"] == 1, repr(fence)


def test_a_glyph_written_as_a_sign_ends_the_lead_like_a_letter():
    """``<F0A5><SPACE>TPS results for`` is a shape read from a rendered page, and it was kept.

    The first version of the lead stopped at a LETTER, and the table writes this glyph as an
    infinity sign. No marker and no opener is written outside ASCII, so anything that is not
    ASCII is plainly text. Judged as it is written out, so both passes agree.
    """
    for glyph, written in (
        ("\uf0a5", "\N{INFINITY}"),
        ("\uf0d1", "\N{NABLA}"),
        ("\uf0ae", "\N{RIGHTWARDS ARROW}"),
    ):
        got, rep = symbol_pua.remap(glyph + SPACE + "TPS results for" + SPACE + "\n")
        assert got == written + " TPS results for\n", repr(glyph)
        assert rep["inner_kept_f020"] == 0 and rep["tail_kept_f020"] == 0, repr(glyph)
    got, rep = symbol_pua.remap("\u2014" + SPACE + "an em dash leads\n")
    assert got == "\u2014 an em dash leads\n" and rep["inner_kept_f020"] == 0


def test_a_definition_needs_the_colon_right_behind_its_own_label():
    """``[3] Knuth [TAOCP]: vol. 1`` is a bibliography line, and its first bracket closes on a space."""
    got, rep = symbol_pua.remap(
        "[3] Knuth [TAOCP]: vol" + SPACE + "1," + SPACE + "p. 4" + SPACE + "\n"
    )
    assert got == "[3] Knuth [TAOCP]: vol 1, p. 4\n"
    assert rep["inner_kept_f020"] == 0 and rep["tail_kept_f020"] == 0


def test_a_tag_is_read_with_its_quoted_attributes():
    """``<span title="a>b">`` is ONE tag, and the two rules must read it the same way.

    The tail rule took the first ``>`` and saw a closed tag with content behind it. Alone on its
    line that tag is an HTML block, so its tail stays. The gap rule took the last ``>`` and saw a
    closed tag where the gap stood inside one. Both ask one quote-aware scanner now.
    """
    line = '<span title="a>b">' + SPACE
    got, rep = symbol_pua.remap("para\n\n" + line + "\nnext\n")
    assert got == "para\n\n" + line + "\nnext\n" and rep["tail_kept_f020"] == 1
    line = '<span title="a>b"' + SPACE + "class>"
    got, rep = symbol_pua.remap(line + "\n")
    assert got == line + "\n" and rep["inner_kept_f020"] == 1
    # the tag the gap stands in need not be the first one on the line
    line = "<td>x</td><span" + SPACE + "class>"
    got, rep = symbol_pua.remap(line + "\n")
    assert got == line + "\n" and rep["inner_kept_f020"] == 1


def test_a_paren_glyph_does_not_end_the_lead():
    """The two glyphs written as ASCII parentheses are judged as ``(`` and ``)``, on both passes.

    Raw, each is a Private Use Area codepoint, which is not ASCII and would end the lead as text.
    Written out, ``1)`` is an ordered list marker. So ``1<F029><SPACE>one`` keeps its Symbol
    space: ``1) one`` is a list, and the line was a paragraph.
    """
    rparen = chr(0xF029)
    got, rep = symbol_pua.remap("para\n1" + rparen + SPACE + "one\n")
    assert got == "para\n1)" + SPACE + "one\n"
    assert rep["inner_kept_f020"] == 1
    assert symbol_pua.remap(got)[0] == got


# ---- #96, what the third review round found ----


def test_a_closing_fence_inside_a_quote_still_loses_its_tail():
    """The fence exception read a bare fence only, and a quoted code block stayed open."""
    src = "> ```\n> x = 1\n> ```" + SPACE + "\n> after the code\n"
    got, rep = symbol_pua.remap(src)
    assert got == src.replace(SPACE, "") and rep["tail_kept_f020"] == 0


def test_an_escaped_bracket_does_not_close_a_label():
    """``[a\\]b]: /u`` is one label. The first ``]`` behind the bracket is escaped."""
    line = "[a\\]b]: /u " + SPACE
    got, rep = symbol_pua.remap(line + "\nnext\n")
    assert got == line + "\nnext\n" and rep["tail_kept_f020"] == 1


def test_only_a_label_at_the_start_of_the_content_is_a_definition():
    """``![x]: a`` is an image and ``(1) [x]: a`` is a sentence. Neither can start a definition."""
    for line, want in (
        ("![x]: a" + SPACE + "b", "![x]: a b"),
        ("(1) [x]: a" + SPACE + "b", "(1) [x]: a b"),
    ):
        got, rep = symbol_pua.remap(line + "\n")
        assert got == want + "\n" and rep["inner_kept_f020"] == 0, repr(line)


def test_only_a_checked_box_is_a_task_marker():
    """``[Smith]<SPACE>wrote`` is a citation, and the first version of the test held it too."""
    got, rep = symbol_pua.remap("[Smith]" + SPACE + "wrote this\n")
    assert got == "[Smith] wrote this\n" and rep["inner_kept_f020"] == 0
    got, rep = symbol_pua.remap("[link]" + SPACE + "\n")
    assert got == "[link]\n" and rep["tail_kept_f020"] == 0


def test_the_head_rule_and_the_lead_agree_on_what_text_is():
    """A curly quote, a dash and a printed bullet open no block, at the head or anywhere else.

    The #94 head rule took letters and table glyphs, and the #96 lead took anything that is not
    ASCII. So ``<SPACE>“Quoted”`` kept its Symbol space while ``“<SPACE>Quoted`` lost it. Measured
    before the head rule was widened: 8,028 characters of the Basic Multilingual Plane that are
    neither ASCII nor letters, 210 contexts each, and the drop changed the rendering of no line
    but one kind: ``U+FEFF``. The parser skips a byte order mark at the start of a document, so
    behind a Symbol space it is text and without one it is nothing. It is not counted as text.
    """
    for first in ("“Quoted”", "— dash", "• item", "¿Qué?"):
        got, rep = symbol_pua.remap(SPACE + first + "\n")
        assert got == first + "\n", repr(first)
        assert rep["head_kept_f020"] == 0 and rep["dropped_f020"] == 1, repr(first)
    bom = chr(0xFEFF)
    got, rep = symbol_pua.remap(SPACE + bom + "# x\n")
    assert got == SPACE + bom + "# x\n" and rep["head_kept_f020"] == 1
