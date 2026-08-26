# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Phase 5 post-processing chain — fixed order, each step sees the previous step's output:

    illegal_codepoints -> symbol_pua -> caption_unbleed -> lang_retag -> dash_normalize
                       -> mermaid_repair -> code_unescape -> chapter_split

Order matters: illegal_codepoints runs FIRST because a raw NUL makes the file binary to grep-based
tooling and is a byte no fence lexer, language detector or splitter below is written to expect — it
is also the only step scoped to the whole document, code fences included, since MinerU emits these
inside code (see its module docstring); symbol_pua runs next because it repairs characters and
line-level structure that
every later step parses — a Private-Use-Area bullet marker at line start otherwise reaches
chapter_split as a fake heading, and a dropped symbol silently corrupts prose no later step can
detect; caption_unbleed removes caption-only junk fences and lifts leading captions so lang_retag
detects on clean code; lang tags before dash-normalize scopes to code fences; dash/mermaid fixes
must land before the md is split into chapters; code_unescape strips leftover markdown-punct
escapes inside code fences last (both merge paths). Re-run whenever the converter output changes
upstream — do not reuse stale artifacts.
"""

from typing import Any

from . import (
    caption_unbleed,
    chapter_split,
    code_unescape,
    dash_normalize,
    illegal_codepoints,
    lang_retag,
    mermaid_repair,
    symbol_pua,
)


def residue_lines(report: dict[str, Any]) -> list[str]:
    """The human-facing lines for everything `symbol_pua` refused to decide or could not verify.

    This lives with the step rather than in one command, because both entry points need it and only
    one of them had it. `pdf2wiki batch` converts a whole corpus and discarded the report, so every
    refusal and every unverified codepoint was computed and thrown away on exactly the runs that
    produce a vault -- "a counter no command prints reaches no human", one layer up.

    A count of REFUSALS takes the high-water mark of the two `symbol_pua` passes. A codepoint the
    first pass declines to touch can be removed by the second, and reporting the second alone would
    drop the signal precisely because something acted on it. What the document STILL HOLDS
    (`unknown`, `in_code`) comes from the second pass, the only one that read the text this chain
    writes.
    """
    sp, sp2 = report["symbol_pua"], report["symbol_pua_post_caption"]
    out: list[str] = []
    stray = max(sp["stray_unhandled"], sp2["stray_unhandled"])
    if stray:
        out.append(f"⚠ {stray} mid-word marker(s) LEFT IN PLACE — no safe reading; inspect by hand")
    deferred = max(sp["line_leading_dot_deferred"], sp2["line_leading_dot_deferred"])
    if deferred:
        out.append(
            f"⚠ {deferred} line-leading · marker(s) LEFT IN PLACE — that codepoint is a"
            " multiplication dot inline and a list bullet in some books"
        )
        out.append("  Render the source page, then treat it as a dot or as a list marker")
    marker = max(sp["line_leading_marker_deferred"], sp2["line_leading_marker_deferred"])
    if marker:
        out.append(
            f"⚠ {marker} line-opening bullet marker(s) LEFT IN PLACE — too indented, with no space"
            " after, followed by an operator, or a marker with no verified heading reading"
        )
        out.append("  Render the source page, then write the line as a list item by hand")
    unread = max(sp["marker_no_reading"], sp2["marker_no_reading"])
    if unread:
        out.append(
            f"⚠ {unread} list-marker codepoint(s) found AWAY FROM A LINE START and LEFT IN PLACE —"
            " verified as a bullet at a line start only, and a Greek letter in the Symbol font"
        )
        out.append(
            "  Render the source page: a stray marker, or a letter phase5.symbol_pua should carry"
        )
    adjacent = max(sp["adjacent_markers"], sp2["adjacent_markers"])
    if adjacent:
        out.append(
            f"⚠ {adjacent} marker(s) TOUCHING ANOTHER MARKER and LEFT IN PLACE — every reading is"
            " verified against a page printing ONE marker, so a run of them has none"
        )
        out.append("  Render the source page, then write the line by hand")
    if sp2["in_code"]:
        out.append(f"· verified glyphs left inside code fences: {sp2['in_code']}")
    if sp2["unknown"]:
        out.append(f"⚠ UNVERIFIED PUA codepoints left as-is: {sp2['unknown']}")
        out.append(
            "  Render the source page, confirm the character, then add it to phase5.symbol_pua"
        )
    return out


def run_chain(
    md_path: str,
    book: str,
    out_dir: str | None = None,
    source_name: str | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    """Run the full chain on md_path. With apply=False (dry-run), computes and reports every
    step in memory and writes NOTHING (the split step reports planned files only).
    Returns a report dict.

    ⚠ `md_path` is never written. It used to be: with apply=True the repaired text was written
    back over the source so that `chapter_split` could read it from disk, and that rewrote a
    converter's output in place BEFORE the split ran -- a split that refused (no chapter boundary)
    still left the source edited. The CLI's stated convention is that no command modifies an
    existing file in place, and nothing downstream reads the whole-book file after the chain:
    `batch` copies `chapters/`. The repaired text is handed to `chapter_split.split` directly,
    in both modes, so a dry run now plans the split on the text the chain produced rather than on
    the unrepaired file (see bug-phase5-apply-rewrites-the-source-in-place).

    Line endings: the file is read in Python's default universal-newline mode, so any `\\r\\n` or
    bare `\\r` in the source is translated to `\\n` before any step sees the text — every step below
    is LF-only and this is what makes that a safe assumption rather than a silent gap. A CRLF book
    is therefore repaired like any other, and the chapter files carry LF endings — that
    line-ending change is a side effect of the chain running at all, not a separate decision.
    `symbol_pua.remap()` additionally carries its own CRLF guard for callers that hand it text
    directly rather than through this function; that guard cannot fire on anything read via
    `run_chain`, by construction (see bug-pdf2wiki-crlf-guard-unreachable).
    """
    with open(md_path, encoding="utf-8") as f:
        md = f.read()
    report: dict[str, Any] = {}

    md, illegal = illegal_codepoints.strip(md)
    report["illegal_codepoints"] = illegal

    md, pua = symbol_pua.remap(md)
    report["symbol_pua"] = pua

    md, captions = caption_unbleed.unbleed(md)
    report["caption_unbleed"] = {"unwrapped": len(captions), "captions": captions}

    # caption_unbleed UNWRAPS caption-only fences, promoting their text to prose. Any PUA glyph
    # that the first pass correctly left alone as `in_code` is now running prose, and no later step
    # would ever remap it — it would ship as an invisible codepoint in permanent text. Re-run on the
    # unwrapped output. This pass is a no-op when nothing was unwrapped (the step is idempotent).
    md, pua2 = symbol_pua.remap(md)
    report["symbol_pua_post_caption"] = pua2

    md, retags, stats = lang_retag.retag(md)
    report["lang_retag"] = {
        "changes": len(retags),
        "stats": dict(stats),
        "detail": [(o, n, w) for o, n, w, _ in retags],
    }

    md, dashes = dash_normalize.normalize(md)
    report["dash_normalize"] = {"fixes": len(dashes)}

    md, mstats = mermaid_repair.repair(md)
    report["mermaid_repair"] = mstats

    md, unescapes = code_unescape.unescape(md)
    report["code_unescape"] = {"fixes": len(unescapes)}

    written, bounds = chapter_split.split(
        md_path, book, out_dir=out_dir, source_name=source_name, dry_run=not apply, text=md
    )
    report["chapter_split"] = {
        "boundaries": len(bounds),
        "titles": [t for _, t in bounds],
        "files": written,
    }
    report["applied"] = apply
    return report
