# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The rendering oracle for `symbol_pua`, against the CommonMark reference implementation.

Every rendering claim this module makes -- #73's tail hard break, #78's line-final backslash, #77's
head indent -- was measured in a throwaway virtual environment and then thrown away. Nothing in CI
held any of them, and the committed truth table is SINGLE-LINE, so it cannot see a class that needs
a paragraph above the line. Three of the four defects found while fixing #77 lived in exactly that
blind spot.

⚠ **cmark decides.** `markdown-it-py` disagrees with it about a hard break after a backslash, and an
earlier measurement that trusted markdown-it reported five regressions that were not real.

🔑 **This file asks the parser, and it does not re-implement CommonMark.** Re-implementing the block
grammar inside a guard is what failed four times over while #77 was fixed: each guard read a
narrower string than the parser did. Four attempts to encode "an honest reading" here ended up
re-deriving the module's own rules, which is circular, so the snapshot states what the step DOES and
a human reviews any diff -- the same contract as the positional truth table next door.

## What this file catches, verified by mutation rather than asserted

Each rule was deleted in turn and the suite re-run. An oracle nobody has tried to fool is a claim,
not a check.

===============================================  ====================================================
mutation                                         caught by
===============================================  ====================================================
the ``_is_inert`` whitelist removed              the head snapshot below
the head cut-back removed (#77 returns)          the head snapshot, and the code-block test below
the tail cut-back removed (#73 returns)          the tail snapshot, and the hard-break test below
the backslash guard removed (#78 returns)        the backslash test below
the ``plain_indent`` guard removed               ⚠ **NOT here.** Dropping it deletes real content
                                                 without moving a block, so a structural oracle is
                                                 blind to it by construction. It is caught by
                                                 ``test_a_head_that_is_not_commonmark_indentation_is_left_alone``
                                                 in ``test_symbol_pua_positions.py``.
===============================================  ====================================================
"""

from __future__ import annotations

import itertools
import re

import cmarkgfm
import pytest

from pdf2wiki.phase5 import symbol_pua

SPACE = symbol_pua.SPACE
BULLET = symbol_pua.BULLET
DIAMOND = symbol_pua.DIAMOND
DOT = symbol_pua.DOT

# The literal must be built from its codepoint. A previous throwaway harness lost it in a heredoc,
# every shape silently became a no-op, and the run read as a pass.
assert chr(0xF020) == SPACE, "the Symbol space literal is wrong"

# cmarkgfm prints `<!-- raw HTML omitted -->` in place of raw HTML, so a regex over tag names alone
# sees a paragraph where the parser built an html_block. That hole hid the HTML-block class from an
# earlier grid, so the placeholder is part of the skeleton.
_BLOCK = re.compile(r"<!-- raw HTML omitted -->|<(?:/?\w+)[^>]*>")


# The axes. Each entry is here because some rule branches on it, or because a review round found a
# defect in it. Do not shrink one without reading `test_the_grid_is_large_enough_...` below.
_HEADS = [
    "",
    SPACE,
    SPACE + " ",
    SPACE + "  ",
    SPACE + "   ",
    SPACE + "    ",
    SPACE + "     ",
    " " + SPACE,
    "  " + SPACE,
    "   " + SPACE,
    "    " + SPACE,
    "  " + SPACE + "  ",
    SPACE + "\t",
    "\t" + SPACE,
    SPACE + SPACE + "    ",
    SPACE + "  " + SPACE + "  ",
    "\u00a0" + SPACE + "    ",  # `isspace()` in Python, and NOT indentation to CommonMark
]
_BODIES = [
    "text",
    "x = 1",
    "**bold**",
    "a - b",
    "1.5 times",
    "#hashtag",
    "-dash",
    "word ends",
    "- item",
    "+ item",
    "* item",
    "1. one",
    "1) one",
    "# head",
    "###### h6",
    "> quote",
    "```",
    "~~~",
    "*** ",
    "___ ",
    "---",
    "--",
    "===",
    "| a | b |",
    BULLET + " item",
    DIAMOND + " item",
    DOT + " item",
    "*" + DIAMOND + " item",
    "#" + BULLET + " item",
    "-" + SPACE + "item",
    "#" + SPACE + "head",
    "1." + SPACE + "one",
    "<table>",
    "<div>",
    "<pre>",
    "<!-- comment -->",
    "<em>x</em>",
    "text" + BULLET + " tail",
    "ends in a backslash\\",
]
_TAILS = [
    "",
    " ",
    "  ",
    SPACE,
    SPACE + SPACE,
    " " + SPACE,
    "  " + SPACE,
    SPACE + "  ",
    "\t" + SPACE,
]
# A line never stands alone in a chapter, and the block ABOVE it decides how it is read. The
# committed positional table has no such axis, which is why it cannot see this class at all.
_ABOVE = ["", "para above\n", "- outer\n", "> quote\n", "prev\n\n", "- outer\n\n", "# head\n"]


def skeleton(md: str) -> list[str]:
    """The sequence of blocks cmark builds. Inline text is deliberately ignored."""
    return _BLOCK.findall(cmarkgfm.github_flavored_markdown_to_html(md))


def _changed(src: str) -> str | None:
    """Return a one-line record when the step changes the BLOCK STRUCTURE of ``src``, else ``None``.

    ⚠ This deliberately does NOT judge whether a change is correct. Four attempts to encode "an
    honest reading" here ended up re-deriving the module's own rules, which is circular, and
    re-implementing CommonMark inside a guard is the exact mistake that produced four regressions
    while #77 was fixed. The snapshot states what the step DOES, and a human reviews any diff --
    the same contract as the positional truth table next door.
    """
    out = symbol_pua.remap(src)[0]
    before, after = skeleton(src), skeleton(out)
    if before == after:
        return None
    return f"{_show(src)!r} -> {_show(out)!r}   {' '.join(before)}  =>  {' '.join(after)}"


def _show(text: str) -> str:
    return (
        text.replace(SPACE, "<SP>")
        .replace(BULLET, "<BULLET>")
        .replace(DIAMOND, "<DIAMOND>")
        .replace(DOT, "<DOT>")
        .replace("\t", "<TAB>")
    )


def test_every_shape_whose_rendering_the_step_changes(snapshot) -> None:
    """The head axis, crossed with a block ABOVE the line.

    The committed positional table is single-line, so it cannot see any class that needs a preceding
    paragraph -- and three of the four defects found while fixing #77 lived exactly there. A change
    to this snapshot is either intended, and regenerated deliberately, or it is a defect.

        uv run pytest tests/test_symbol_pua_rendering.py --snapshot-update
    """
    records = [
        rec
        for above, head, body in itertools.product(_ABOVE, _HEADS, _BODIES)
        if (rec := _changed(above + head + body + "\n")) is not None
    ]
    assert len(records) < len(_ABOVE) * len(_HEADS) * len(_BODIES), "the step changed every shape"
    assert records == snapshot


def test_every_tail_shape_whose_rendering_the_step_changes(snapshot) -> None:
    """The tail axis, where #73 and #78 live."""
    records = [
        rec
        for above, body, tail in itertools.product(_ABOVE, _BODIES, _TAILS)
        if (rec := _changed(above + body + tail + "\n")) is not None
    ]
    assert records == snapshot


@pytest.mark.parametrize(
    ("body", "tail"),
    [("x", "  " + SPACE), ("x", " " + SPACE), ("x", SPACE + SPACE), ("x", SPACE)],
)
def test_a_dropped_tail_symbol_space_adds_no_hard_break(body: str, tail: str) -> None:
    """#73, pinned in CI for the first time.

    Two real spaces at a line end are a CommonMark hard break, and the printed page has no such
    break. The drop must not uncover one that the source did not have.
    """
    src = body + tail + "\nnext\n"
    out = symbol_pua.remap(src)[0]
    assert ("<br" in cmarkgfm.github_flavored_markdown_to_html(out)) == (
        "<br" in cmarkgfm.github_flavored_markdown_to_html(src)
    ), repr(src)


@pytest.mark.parametrize("body", ["x\\", "x\\\\\\", "a b\\"])
def test_a_dropped_tail_symbol_space_uncovers_no_backslash_break(body: str) -> None:
    """#78, pinned in CI for the first time.

    Spec 6.7 gives a line-final unescaped backslash the same meaning as two trailing spaces. A line
    that ends in a backslash and then a Symbol space has no break before the step, because the
    Symbol space is the last character. The drop must not create one.
    """
    src = body + SPACE + "\nnext\n"
    out = symbol_pua.remap(src)[0]
    assert ("<br" in cmarkgfm.github_flavored_markdown_to_html(out)) == (
        "<br" in cmarkgfm.github_flavored_markdown_to_html(src)
    ), repr(src)


@pytest.mark.parametrize(
    "head", [SPACE + "    ", SPACE + "     ", "  " + SPACE + "    ", SPACE + "\t"]
)
def test_a_dropped_head_symbol_space_opens_no_code_block(head: str) -> None:
    """#77, the issue's own repro, pinned in CI.

    `U+F020` is not whitespace to CommonMark, so the real spaces behind one are content. Promoting
    them to indent turns a paragraph line into an indented code block.
    """
    src = head + "text\nnext\n"
    out = symbol_pua.remap(src)[0]
    assert "<pre" not in cmarkgfm.github_flavored_markdown_to_html(out), repr(src)
    assert "<pre" not in cmarkgfm.github_flavored_markdown_to_html(src), (
        "the source was already code"
    )


def test_the_grid_is_large_enough_to_have_found_the_defects_it_was_written_for() -> None:
    """A grid that shrinks silently stops being an oracle.

    Three of the four defects behind this file needed a paragraph ABOVE the line, and one needed a
    marker body under a long head. Both axes must stay crossed, which a bare count does not say, so
    the axes are asserted directly.
    """
    assert len(_ABOVE) >= 7 and "para above\n" in _ABOVE
    assert any(
        SPACE in h and h.replace(SPACE, "").strip(" \t") == "" and len(h) > 4 for h in _HEADS
    )
    assert any(b.startswith(BULLET) or b.startswith(DIAMOND) or b.startswith(DOT) for b in _BODIES)
    assert any(b.startswith("<") for b in _BODIES)
    assert len(_ABOVE) * len(_HEADS) * len(_BODIES) >= 4000
