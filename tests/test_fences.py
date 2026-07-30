# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

r"""Tests for the shared fence lexer and the phase-5 bugs it fixes.

Regression anchor: the old per-step ``^(```)([a-zA-Z]*)\n(.*?)^```` regex could not match a fence
whose info string was not letters-only, and instead of skipping it, paired that block's CLOSING
fence with the NEXT block's opener -- so intervening PROSE was rewritten as a code body. Also
covers the `_san_inner` label-truncation bug found while verifying this fix.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pdf2wiki.phase5 import (
    caption_unbleed,
    chapter_split,
    code_unescape,
    dash_normalize,
    fences,
    lang_retag,
    mermaid_repair,
)

# ---- lexer ----


def test_blocks_roundtrip_raw_matches_source() -> None:
    md = "a\n\n```python\nx = 1\n```\n\nb\n\n```c++\nint y;\n```\n"
    blks = list(fences.blocks(md))
    assert [b.lang for b in blks] == ["python", "c++"]
    for b in blks:
        assert md[b.offset : b.offset + len(b.raw)] == b.raw
        assert b.rebuild() == b.raw  # no-arg rebuild is byte-identical


def test_transform_identity_is_byte_identical() -> None:
    md = "p\n```java\nint x;\n```\ntail\n"
    assert fences.transform(md, lambda blk: None) == md
    assert fences.transform(md, lambda blk: blk.rebuild()) == md


def test_lang_is_first_token_lowercased() -> None:
    md = "```JAVA {highlight=2}\nint x;\n```\n"
    (blk,) = fences.blocks(md)
    assert blk.lang == "java" and blk.info == "JAVA {highlight=2}"


def test_longer_fence_run_is_lexed() -> None:
    md = "````text\n```inner\n````\n"
    assert [b.lang for b in fences.blocks(md)] == ["text"]
    assert next(iter(fences.blocks(md))).body == "```inner\n"  # inner 3-run is body, not a closer


def test_tilde_fences_are_not_recognised() -> None:
    # Backtick-only, deliberately: MinerU emits only backtick fences, and a PAIR of tilde divider
    # rows in prose used to lex as a real block, so code_unescape/dash_normalize rewrote the prose
    # between them and chapter_split dropped any chapter boundary inside (see
    # test_paired_tilde_rows_in_prose_are_left_alone below). A tilde line is just prose text now.
    assert list(fences.blocks("~~~~yaml\na: 1\n~~~~\n")) == []


def test_paired_tilde_rows_in_prose_are_left_alone() -> None:
    prose = "Console output pasted as prose, with a \\_literal\\_ escape and an —option flag.\n"
    md = (
        "# Chapter One\n\nIntro.\n\n~~~~~~~~~~~~~~~~\n"
        + prose
        + "~~~~~~~~~~~~~~~~\n\n# Chapter Two\n\nMore.\n"
    )
    assert list(fences.blocks(md)) == []
    assert fences.transform(md, lambda blk: blk.rebuild(body="MUTATED\n")) == md


def test_backtick_in_backtick_info_string_is_not_an_opener() -> None:
    assert list(fences.blocks("```py`x\nnot a block\n")) == []


def test_unclosed_opener_is_not_a_block() -> None:
    # CommonMark would render the tail as code, but these callers REWRITE what they match: letting a
    # stray opener claim the tail made code_unescape strip escapes out of prose.
    assert list(fences.blocks("```python\nx = 1\nmore prose\n")) == []


def test_stray_opener_leaves_the_prose_tail_untouched() -> None:
    md = (
        "```java\nint a = 1;\n```\n\n```\n\n"
        "Prose with a \\_literal\\_ underscore and an em—dash —option.\n\n"
        "## A heading\n\nMore \\*prose\\*.\n"
    )
    assert code_unescape.unescape(md) == (md, [])
    assert dash_normalize.normalize(md) == (md, [])
    out, _c, _s = lang_retag.retag(md)
    assert out == md  # the closed java block is already canonically tagged


def test_scanning_resumes_after_an_opener_that_never_closes() -> None:
    # an opener with no closing line anywhere later in the document does not prevent an EARLIER
    # well-formed block from being found.
    md = "```python\nx = 1\n```\n\nprose\n\n```go\ny := 1\nno closer here\n"
    assert [b.lang for b in fences.blocks(md)] == ["python"]


def test_a_stray_opener_pairs_with_the_next_BARE_fence_line() -> None:
    # Documented residual, and it matches how CommonMark/Obsidian actually render this input: an
    # info-string line ("```python") is body content, not a closer, so the block spans to the next
    # bare fence. What the fix removes is the pathological case — an opener with NO closer anywhere,
    # which used to claim the whole document tail.
    md = "```\n\nprose\n\n```python\nx = 1\n```\n"
    (blk,) = fences.blocks(md)
    assert blk.lang == "" and "prose" in blk.body and blk.rebuild() == blk.raw


def test_code_lines_covers_fence_lines() -> None:
    lines = ["a", "```cmake", "# not a heading", "```", "b"]
    assert fences.code_lines(lines) == {1, 2, 3}


# ---- the actual bug: a non-letter info string must not swallow the following prose ----

_CPP_DOC = (
    "```c++\nauto p = \\*ptr;\nint w = a \u2212 b;\n```\n\n"
    "Prose with a \\_literal\\_ underscore.\n\n"
    "```python\nx = 1\n```\n"
)


def test_code_unescape_fixes_cpp_block_and_leaves_prose_alone() -> None:
    out, changes = code_unescape.unescape(_CPP_DOC)
    assert "auto p = *ptr;" in out  # the c++ body IS processed now
    assert "\\_literal\\_" in out  # ...and the prose escape is NOT touched
    assert all("literal" not in old for _tag, old, _new in changes)


def test_dash_normalize_reaches_a_cpp_block() -> None:
    out, changes = dash_normalize.normalize(_CPP_DOC)
    assert "int w = a - b;" in out and changes


def test_lang_retag_does_not_weld_a_tag_onto_a_closing_fence() -> None:
    out, changes, _stats = lang_retag.retag(_CPP_DOC)
    assert "```text" not in out
    assert out.startswith("```cpp\n")  # c++ canonicalized, structure intact
    assert changes == [("c++", "cpp", "kept", "auto p = \\*ptr;")]  # retag ran on the raw doc
    assert out.count("```") == _CPP_DOC.count("```")


def test_non_letter_tags_are_kept_not_downgraded_to_text() -> None:
    for tag, want in [("c#", "csharp"), ("objective-c", "objectivec"), ("c++", "cpp")]:
        out, _c, _s = lang_retag.retag(f"```{tag}\nsome_call(x);\n```\n")
        assert out.startswith(f"```{want}\n"), (tag, out)


def test_real_world_tags_survive_instead_of_downgrading_to_text() -> None:
    # Corpus evidence (1674 vault pages): these tags are emitted correctly by books/authors but the
    # keyword heuristic cannot detect them, so an unknown-tag fallthrough rewrote them to `text`.
    for tag in ["pseudocode", "cmake", "makefile", "hcl", "qml", "vhdl", "gherkin", "graphql"]:
        out, _c, _s = lang_retag.retag(f"```{tag}\nsome content here\n```\n")
        assert out.startswith(f"```{tag}\n"), (tag, out)
    for tag, want in [("js", "javascript"), ("ts", "typescript"), ("proto", "protobuf")]:
        out, _c, _s = lang_retag.retag(f"```{tag}\nsome content here\n```\n")
        assert out.startswith(f"```{want}\n"), (tag, out)


def test_mineru_known_wrong_tags_are_still_re_detected() -> None:
    # The distrust of MinerU's guesses is load-bearing: Java arrives tagged swift/erlang.
    out, _c, _s = lang_retag.retag("```swift\npublic class Foo implements Bar {\n```\n")
    assert out.startswith("```java\n")


def test_indented_fence_is_treated_as_code() -> None:
    md = "- item:\n\n   ```\n   x = 1\n   ```\n"
    out, _c, _s = lang_retag.retag(md)
    assert "   ```text\n" in out  # indent preserved, fence no longer invisible


def test_retag_preserves_an_info_string_remainder() -> None:
    out, _c, _s = lang_retag.retag("```c++ {highlight=1}\nint x;\n```\n")
    assert out.startswith("```cpp {highlight=1}\n")


def test_mermaid_guard_is_case_insensitive() -> None:
    md = '```MERMAID\nA["a \\* b"] --> B\n```\n'
    assert code_unescape.unescape(md) == (md, [])
    assert dash_normalize.normalize(md) == (md, [])
    out, _c, _s = lang_retag.retag(md)
    assert out == md


def test_mermaid_repair_handles_uppercase_fences() -> None:
    out, stats = mermaid_repair.repair('```MERMAID\nA["a&quot;b"] --> B\n```\n')
    assert stats["blocks_changed"] == 1 and out.startswith("```MERMAID\n")
    assert out.endswith("```\n") and "&quot;" not in out


def test_caption_unbleed_unwraps_a_non_letter_tagged_fence() -> None:
    md = "```c++\nListing 2.1 main.cpp: entry point\n```\n"
    out, changes = caption_unbleed.unbleed(md)
    # fence dropped entirely (caption-only); the document's own trailing newline survives
    assert out == "**Listing 2.1** main.cpp: entry point\n\n" and changes == ["Listing 2.1"]


def test_tilde_divider_row_in_prose_does_not_eat_chapter_boundaries() -> None:
    # A single tilde row was already inert under the old multi-fence-type lexer (unclosed opener).
    # Now tildes aren't fence characters at all, so this holds unconditionally.
    lines = ["# Chapter One", "some prose", "~~~~~~~~~~~~~~", "# Chapter Two", "more"]
    assert chapter_split.find_boundaries(lines) == [(0, "Chapter One"), (3, "Chapter Two")]


def test_paired_tilde_divider_rows_do_not_eat_a_chapter_boundary() -> None:
    # The actual regression: with tildes recognised as fence characters, a PAIR of tilde rows lexed
    # as one real block spanning the H1 between them, and chapter_split silently dropped that
    # boundary. Confirmed on the real merged code before this fix (0 boundaries found for "Chapter
    # Two" with the old lexer); backtick-only removes the failure mode outright.
    lines = [
        "# Chapter One",
        "prose",
        "~~~~~~~~",
        "drawing",
        "# Chapter Two",
        "body",
        "~~~~~~~~",
        "tail",
    ]
    assert chapter_split.find_boundaries(lines) == [(0, "Chapter One"), (4, "Chapter Two")]


def test_attribute_syntax_info_string_is_left_alone() -> None:
    md = "```{.python .numberLines}\ndef f():\n    return 1\n```\n"
    out, changes, _stats = lang_retag.retag(md)
    assert out == md and changes == []  # rewriting the first token would orphan the `}`


def test_extension_aliases_resolve_from_one_table() -> None:
    # CANON no longer duplicates EXT; detect() falls back to EXT so both paths share it.
    for tag, want in [("rs", "rust"), ("kt", "kotlin"), ("cxx", "cpp"), ("cs", "csharp")]:
        out, _c, _s = lang_retag.retag(f"```{tag}\nsome content here\n```\n")
        assert out.startswith(f"```{want}\n"), (tag, out)


def test_caption_unbleed_keeps_the_fence_indent() -> None:
    md = (
        "1. Do this:\n\n   ```text\n   Listing 2.1 App.java: the entry point\n   ```\n\n"
        "   ```java\n   class App {}\n   ```\n"
    )
    out, changes = caption_unbleed.unbleed(md)
    assert "   **Listing 2.1** App.java: the entry point\n" in out  # still inside the list item
    assert "\n**Listing" not in out and changes == ["Listing 2.1"]


def test_chapter_split_boundaries_ignore_non_letter_fences() -> None:
    lines = [
        "# Chapter One",
        "```c++",
        "# include guard comment",
        "```",
        "# Chapter Two",
        "```cmake",
        "# not a heading",
        "```",
    ]
    assert chapter_split.find_boundaries(lines) == [(0, "Chapter One"), (4, "Chapter Two")]


# ---- mermaid label truncation (found while verifying the fence fix) ----


def test_san_inner_keeps_trailing_letters_of_a_label() -> None:
    # str.strip("<br> ") was a CHARACTER set: it ate a label's final b/r/</>/space run.
    for label in ["Load Balancer", "Web", "Broker", "API Server", "Job Runner"]:
        assert mermaid_repair._san_inner(label) == label


def test_san_inner_still_strips_edge_br_tokens() -> None:
    assert mermaid_repair._san_inner("<br>Cache<br>") == "Cache"
    assert mermaid_repair._san_inner("a<br>b") == "a<br>b"  # inner <br> survives


def test_repair_does_not_truncate_node_labels() -> None:
    md = '```mermaid\ngraph TD\n  A["Load Balancer"] --> B["API Server"]\n```\n'
    out, _stats = mermaid_repair.repair(md)
    assert "Load Balancer" in out and "API Server" in out
