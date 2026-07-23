# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Hypothesis property tests for the Phase 5 transformers (Stage 7).

These generalize the example-based tests in test_phase5.py: instead of a handful of fixtures, a
generator builds arbitrary converted-book markdown (prose + well-formed fenced blocks with varied
language tags, including mermaid) and asserts the invariants each transformer's docstring PROMISES.
A Hypothesis counterexample here is therefore a real finding (a broken idempotence/fidelity claim),
not a flaky test — triage it (fix the code or soften the documented claim), don't just delete it.

Domain restriction (matches what the converter actually emits, and what the phase5 FENCE regexes
were written for): generated fence bodies never contain a bare ``` line or an embedded newline, and
language tags are letters-only. Malformed/unbalanced fences are out of scope — the converter never
produces them inside a single block.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from pdf2wiki.phase5 import (
    caption_unbleed,
    chapter_split,
    code_unescape,
    dash_normalize,
    lang_retag,
    mermaid_repair,
)

# ---- generators: arbitrary converted-book markdown in the documented domain ----

# Chars that exercise the transforms: escapable markdown punct (code_unescape), dashes/minus
# (dash_normalize), quotes/brackets (mermaid_repair), plus letters/digits/space. No backtick, so a
# bare ``` fence can only ever come from the block assembly below (never from a random line). These
# letters (a,b,c,X,Y,Z) also can't spell Listing/Figure/Table/Example, so a random line is never a
# caption — captions only enter via the explicit _CAPTION_LINE sampler below.
_CHARS = "abcXYZ 012 =:./()[]{}\"'$*~_#@%&!-\\"
_PLAIN = st.text(alphabet=_CHARS, max_size=30)

# non-caption code lines aimed at specific transform paths so examples actually hit the code
_CODE_LINE = st.one_of(
    _PLAIN,
    st.sampled_from(
        [
            "\\$ go run \\*main.go",  # code_unescape
            "uv add –dev pytest",  # dash_normalize (en-dash flag)
            "x = 5 − 3",  # dash_normalize (U+2212 minus)
            'A["{"key": "value"}"] --> B',  # mermaid_repair
            'A["line1\\nline2"] --> B',
            "&quot;hello&quot;",
            "# file: app.py",  # lang_retag ext hint
            "import java.util.List;",  # lang_retag heuristic
            "apiVersion: v1",
            "",
        ]
    ),
)
_CAPTION_LINE = st.sampled_from(
    [
        "Listing 1.2 Foo.java: a widget",
        "Figure 3.4 An architecture diagram",
        "Table 2.1 Comparison",
    ]
)
_TAG = st.sampled_from(
    ["", "text", "code", "python", "java", "bash", "yaml", "ruby", "go", "mermaid"]
)


@st.composite
def _body(draw: st.DrawFn) -> str:
    # Documented domain: at most ONE caption line, and only as the fence's first line (a caption-only
    # fence, or a caption above real code). The converter never stacks captions inside one fence; a
    # generator that did would (correctly) show caption_unbleed lifting only the first per pass — a
    # real but out-of-domain edge, see wiki bug-caption-unbleed-stacked.
    lead = draw(st.one_of(st.none(), _CAPTION_LINE))
    rest = draw(st.lists(_CODE_LINE, max_size=4))
    lines = ([lead] if lead is not None else []) + rest
    return "\n".join(lines)


@st.composite
def _fence(draw: st.DrawFn) -> str:
    return f"```{draw(_TAG)}\n{draw(_body())}\n```"


_PROSE = _PLAIN.filter(lambda s: not s.startswith("# "))


@st.composite
def _doc(draw: st.DrawFn) -> str:
    blocks = draw(st.lists(st.one_of(_fence(), _PROSE), min_size=1, max_size=6))
    return "\n\n".join(blocks)


# ---- idempotence: f(f(x)) == f(x) ----
# Each of these transformers documents that it is re-runnable (idempotent). Applying it to its own
# output must be a no-op, else re-running the phase5 chain on already-processed markdown would drift.


@settings(max_examples=300)
@given(_doc())
def test_unbleed_idempotent(md: str) -> None:
    once, _ = caption_unbleed.unbleed(md)
    twice, changes = caption_unbleed.unbleed(once)
    assert twice == once and changes == []


@settings(max_examples=300)
@given(_doc())
def test_dash_normalize_idempotent(md: str) -> None:
    once, _ = dash_normalize.normalize(md)
    twice, changes = dash_normalize.normalize(once)
    assert twice == once and changes == []


@settings(max_examples=300)
@given(_doc())
def test_code_unescape_idempotent(md: str) -> None:
    once, _ = code_unescape.unescape(md)
    twice, changes = code_unescape.unescape(once)
    assert twice == once and changes == []


@settings(max_examples=300)
@given(_doc())
def test_lang_retag_idempotent(md: str) -> None:
    # not documented "idempotent" but must converge: a specific tag is kept, and the heuristic is a
    # pure function of the (unchanged) body, so a second pass never re-tags.
    once, _, _ = lang_retag.retag(md)
    twice, changes, _ = lang_retag.retag(once)
    assert twice == once and changes == []


# ---- structural: the in-fence transforms only rewrite a fence's tag or body, never its count ----
# retag/dash_normalize/code_unescape rewrite the tag or characters inside a fence; mermaid_repair
# rewrites mermaid labels. None may add, drop, or merge a fence. A body line never contains a bare
# ``` (domain), so every "```" occurrence is a real delimiter -> counting them counts delimiters.
# (caption_unbleed is deliberately excluded: removing a caption-only fence is its whole job.)


def _fences(md: str) -> int:
    return md.count("```")


@settings(max_examples=300)
@given(_doc())
def test_fence_count_preserved(md: str) -> None:
    n = _fences(md)
    assert _fences(dash_normalize.normalize(md)[0]) == n
    assert _fences(code_unescape.unescape(md)[0]) == n
    assert _fences(lang_retag.retag(md)[0]) == n
    assert _fences(mermaid_repair.repair(md)[0]) == n


_PROSE_DOC = st.lists(_PROSE, min_size=1, max_size=6).map("\n\n".join)


@settings(max_examples=200)
@given(_PROSE_DOC)
def test_no_fence_input_is_untouched(prose: str) -> None:
    # dash_normalize/code_unescape/lang_retag act ONLY inside fences (never prose). With no fence in
    # the input, each must return it byte-identical with no recorded changes.
    assert dash_normalize.normalize(prose) == (prose, [])
    assert code_unescape.unescape(prose) == (prose, [])
    out, changes, _ = lang_retag.retag(prose)
    assert out == prose and changes == []


@settings(max_examples=300)
@given(_doc())
def test_mermaid_repair_never_worsens_score(md: str) -> None:
    # repair's validation proxy is a parse-breaker score; sanitizing a label must never raise it.
    _, stats = mermaid_repair.repair(md)
    assert stats["score_after"] <= stats["score_before"]


# ---- chapter_split: fence-aware boundaries + no content dropped ----
# Build a document from labeled elements so the expected boundary count is known: an H1 element is a
# real chapter boundary; a fenced block is not (even when it contains a `# ...` code comment line);
# prose is not. Titles are pre-stripped (alphabet can't spell Appendix, so no accidental H2 boundary).

_TITLE = st.text(alphabet="abcXYZ 012", min_size=1, max_size=15).map(str.strip).filter(bool)
_H1_EL = _TITLE.map(lambda t: ("h1", [f"# {t}"]))
_PROSE_EL = _PLAIN.filter(lambda s: not s.startswith("#")).map(lambda s: ("prose", [s]))
_FENCE_EL = st.builds(
    lambda tag, inner: ("fence", [f"```{tag}", *inner, "```"]),
    _TAG,
    st.lists(st.one_of(_CODE_LINE, _TITLE.map(lambda t: f"# {t}")), max_size=3),
)
_ELEMENTS = st.lists(st.one_of(_H1_EL, _PROSE_EL, _FENCE_EL), max_size=8)


@settings(max_examples=300)
@given(_ELEMENTS)
def test_boundaries_are_exactly_outside_fence_h1s(elements: list) -> None:
    lines: list[str] = []
    expected = 0
    for kind, ls in elements:
        if kind == "h1":
            expected += 1
        lines.extend(ls)
    bounds = chapter_split.find_boundaries(lines)
    assert len(bounds) == expected  # fence-aware: `# ...` lines inside a fence are never boundaries
    for i, _title in bounds:
        assert lines[i].startswith("# ")  # every reported boundary is a real outside-fence H1


@settings(max_examples=150, deadline=None)
@given(_ELEMENTS)
def test_split_preserves_all_nonblank_content(elements: list) -> None:
    lines: list[str] = []
    for _kind, ls in elements:
        lines.extend(ls)
    assume(chapter_split.find_boundaries(lines))  # a boundary-less doc raises (covered by fixtures)
    md = "\n".join(lines)
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "book.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(md)
        written, _ = chapter_split.split(p, "b", out_dir=os.path.join(d, "ch"))
        body_lines: set[str] = set()
        for path in written:
            with open(path, encoding="utf-8") as f:
                content = f.read()
            # drop the injected frontmatter (--- fields --- ) via maxsplit=2 so a body `---` survives
            parts = content.split("---\n", 2)
            body = parts[2] if len(parts) == 3 else content
            body_lines.update(ln for ln in body.split("\n") if ln.strip())
    # every non-blank input line lands in some chapter (boundary H1s are re-emitted verbatim)
    for ln in lines:
        if ln.strip():
            assert ln in body_lines
