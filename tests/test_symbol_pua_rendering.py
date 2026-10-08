# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The rendering oracle for `symbol_pua`, against the CommonMark reference implementation.

Every rendering claim this module makes -- #73's tail hard break, #78's line-final backslash, #77's
head indent -- was measured in a throwaway virtual environment and then thrown away. (#94's block
opener came later, and its claim was pinned here in the same change that made it.) Nothing in CI
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
the #94 keep rule removed (#94 returns)          the head snapshot, and the block-opener test below
its leading-marker test removed                  ``test_every_head_shape_settles_in_one_pass`` ALONE:
                                                 seven shapes become a refusal the second pass undoes
its marker-opens test removed                    the head snapshot, and the positional table
its dot test removed                             the head snapshot, and the positional table
only the FIRST marker asked                      the settle test and the token fuzz in the positional
                                                 file: the first is deleted, the second then opens
its ASCII-letter case removed                    the head snapshot, and six positional tests
its mapped glyphs removed                        the settle test again, and three positional tests:
                                                 one pass keeps the head, writes a letter, the next
                                                 drops it
its indent guard removed, or gated on a plain    the head snapshot, and
head again                                       ``test_the_indent_guard_measures_indent_as_the_parser_does``
a glyph written as ASCII allowed                 the head snapshot, and the paren test below. ⚠ Only
                                                 since ``_ABOVE`` holds a link label: ``(`` is
                                                 swallowed as the title of the definition above, and
                                                 without that context no shape here could show it.
its non-ASCII letters removed                    ⚠ **NOT here.** A harmless drop and a keep build the
                                                 same blocks, so a structural oracle cannot tell them
                                                 apart. ``test_a_head_symbol_space_in_front_of_a_letter_is_still_dropped``
                                                 in ``test_symbol_pua_positions.py`` catches it.
the #96 tail rule removed                        the tail snapshot, and the whole-line test below
the #96 first-gap rule removed                   both snapshots, and the opener test below
its letter test removed                          both snapshots: ``- <SPACE># x`` is a heading again
the #96 rules let loose on a marker line         the head snapshot and the positional table: the
                                                 oldest repair of the step, ``<BULLET><SPACE>item``,
                                                 stops being one
the #96 clauses for a definition, a tag, a       ⚠ **NOT here**, or only in part. Each has a test of
closing hash, a closed tag, a written glyph      its own in ``test_symbol_pua_positions.py``.
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
    SPACE + "    \u00a0",  # the same character BEHIND the real spaces, which are then indent
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
    # The edges of the #94 whitelist. Without these four the grid cannot tell a rule that drops
    # the head in front of a mapped glyph or a non-ASCII letter from one that keeps it, and the
    # first version of that whitelist was widened with every test here still green.
    "\uf070 radians",  # a mapped glyph leads: the likely real shape, a Symbol-font run
    "\u00e9 accent",  # a letter that is not ASCII
    "[ref]: /url",  # a link reference definition: an opener that renders as NOTHING
    # An emphasis opener in front of a glyph that is written out as punctuation. With the head
    # kept, `*` stands between a PUA codepoint and a `(`, so it is no longer left-flanking and
    # the emphasis is lost. The same happens mid-line with no head at all (`a*<F028>x<F029>*`),
    # so it is the substitution's limit and not the keep rule's, and it is recorded here.
    "*\uf028x\uf029* is",
    # Two markers behind hashes. The first is deleted as a stray four columns deep, and the
    # second then opens the line. No shape here had two markers behind a kept head, and the #94
    # rule shipped to review unstable on this one.
    "#" + BULLET + " " + DIAMOND + " item",
    # The paren glyph in front. It is written out as `(`, which a link label above reads as a
    # title: under `[x]: /u` the dropped line vanishes, and under a bare `[x]:` the KEPT Symbol
    # space becomes the destination and the line vanishes the other way. A line-local step cannot
    # see the label, so one of the two is lost whichever way the head goes, and both are recorded.
    "\uf028see note\uf029",
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
# A link label above. It reads the NEXT line as its destination or its title, so it is the one
# block that a line below can vanish into, and two defects of the #94 rule needed it to be seen.
_ABOVE += ["[x]: /u\n", "[x]:\n"]


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


@pytest.mark.parametrize("above", ["", "para above\n", "- outer\n", "> quote\n", "# head\n"])
@pytest.mark.parametrize("head", [SPACE, " " + SPACE, SPACE + SPACE, SPACE + " ", "   " + SPACE])
def test_a_dropped_head_symbol_space_uncovers_no_block_opener(
    above: str, head: str, block_openers: list[str]
) -> None:
    """#94, pinned in CI.

    `U+F020` is not whitespace to CommonMark, so a line that starts with one is paragraph text
    whatever comes next. The drop used to put the text behind it at the start of the line, where
    `# Title` is a heading, `- item` a list, a fence an open code block, and `---` a setext
    underline that turns the line ABOVE into a heading.

    Every body here holds no marker and no Symbol space of its own, so the head is the only thing
    the step can act on, and cmark judges the whole block structure and not one tag.
    """
    for body in block_openers:
        src = above + head + body + "\nnext\n"
        out = symbol_pua.remap(src)[0]
        assert skeleton(out) == skeleton(src), repr(src)


@pytest.mark.parametrize("above", ["", "para above\n", "- outer\n", "> quote\n", "# head\n"])
@pytest.mark.parametrize("tail", [SPACE, SPACE + SPACE, " " + SPACE])
def test_a_dropped_tail_symbol_space_completes_no_whole_line_construct(
    above: str, tail: str
) -> None:
    """#96, the line end, pinned in CI.

    `---<SPACE>` is paragraph text, and `---` alone turns the line ABOVE into a heading. A
    whole-line construct is a block only when nothing but whitespace follows it, and `U+F020` is
    not whitespace, so the drop made one out of every such line. cmark judges the whole structure.
    """
    for body in ("---", "===", "***", "___", "-", "- - -", "#", "1.", "|---|---|", "[ref]: /url "):
        src = above + body + tail + "\nnext\n"
        out = symbol_pua.remap(src)[0]
        assert skeleton(out) == skeleton(src), repr(src)


@pytest.mark.parametrize("above", ["", "para above\n", "- outer\n", "> quote\n", "# head\n"])
def test_a_symbol_space_written_out_completes_no_opener(above: str) -> None:
    """#96, inside the text, pinned in CI.

    `#<SPACE>Title` is paragraph text, and `# Title` is a heading. The first gap of a line is the
    only place where a real space can complete an opener, and only behind text that is one.
    """
    for prefix in ("#", "##", "-", "+", "*", "1.", "1)", "<div", "- ", "> ", "1. ", "- > "):
        # the last four end in real whitespace: the gap is the start of a container's content
        src = above + prefix + SPACE + ("# x" if prefix.endswith(" ") else "item") + "\nnext\n"
        out = symbol_pua.remap(src)[0]
        assert skeleton(out) == skeleton(src), repr(src)


def test_a_dropped_tail_makes_and_unmakes_no_pipe_table() -> None:
    """A table is decided by two lines, and this is the only test here with a line BELOW.

    `| a | b |<SPACE>` over a two-column delimiter row is a paragraph, because the Symbol space is
    a third cell. `| a | b |` over the same row is a table.
    """
    for head in ("| a | b |" + SPACE, "a | b" + SPACE, SPACE + "| a | b |" + SPACE):
        for below in (
            "|---|---|\n| 1 | 2 |\n",
            "--- | ---\n1 | 2\n",
            "|---|---|---|\n| 1 | 2 | 3 |\n",
        ):
            src = head + "\n" + below
            out = symbol_pua.remap(src)[0]
            before = "<table" in cmarkgfm.github_flavored_markdown_to_html(src)
            after = "<table" in cmarkgfm.github_flavored_markdown_to_html(out)
            assert before == after, repr(src)


def test_a_symbol_space_written_out_makes_no_task_box() -> None:
    """`- [x]<SPACE>done` is a list item with literal text, and `- [x] done` is a checked box.

    Review found it: a task marker is the one marker that holds a letter, so the gap rule, which
    asks for a letter in front of the gap, let it through.
    """
    for mark in ("[x]", "[X]", "[ ]"):
        src = "- " + mark + SPACE + "done\n"
        out = symbol_pua.remap(src)[0]
        assert "<input" not in cmarkgfm.github_flavored_markdown_to_html(src), repr(src)
        assert "<input" not in cmarkgfm.github_flavored_markdown_to_html(out), repr(src)


def test_a_paren_glyph_under_a_link_definition_still_renders() -> None:
    """The reason `U+F028` is not in the #94 whitelist, asserted on the rendering and not on a counter.

    `[x]: /u` and then `<SPACE><F028>see note<F029>` is a definition and a paragraph. With the head
    dropped the second line is `(see note)`, a valid title, and it renders as NOTHING. The block
    tags stay equal when that happens, which is why the first measurement missed it.
    """
    src = "[x]: /u\n" + SPACE + "\uf028see note\uf029\nnext\n"
    out = symbol_pua.remap(src)[0]
    assert "see note" in cmarkgfm.github_flavored_markdown_to_html(src)
    assert "see note" in cmarkgfm.github_flavored_markdown_to_html(out)


def test_every_head_shape_settles_in_one_pass() -> None:
    """The chain runs this step twice, and a refusal the second pass undoes is a false report.

    The first version of the #94 rule kept the head of ``<NBSP><SPACE>    <BULLET> item``, the
    marker pass then deleted the bullet as a stray, and the second pass found a letter in front
    and dropped the head. The operator was told a Symbol space had been left in place on a line
    that no longer held it. Seven shapes of this grid caught it, and nothing else did.
    """
    for above, head, body in itertools.product(_ABOVE, _HEADS, _BODIES):
        once = symbol_pua.remap(above + head + body + "\n")[0]
        assert symbol_pua.remap(once)[0] == once, repr(_show(above + head + body))


def test_the_grid_is_large_enough_to_have_found_the_defects_it_was_written_for() -> None:
    """A grid that shrinks silently stops being an oracle.

    Three of the four defects behind this file needed a paragraph ABOVE the line, and one needed a
    marker body under a long head. Both axes must stay crossed, which a bare count does not say, so
    the axes are asserted directly.
    """
    assert len(_ABOVE) >= 9 and "para above\n" in _ABOVE and "[x]:\n" in _ABOVE
    assert any(
        SPACE in h and h.replace(SPACE, "").strip(" \t") == "" and len(h) > 4 for h in _HEADS
    )
    assert any(b.startswith(BULLET) or b.startswith(DIAMOND) or b.startswith(DOT) for b in _BODIES)
    assert any(b.startswith("<") for b in _BODIES)
    assert len(_ABOVE) * len(_HEADS) * len(_BODIES) >= 4000
