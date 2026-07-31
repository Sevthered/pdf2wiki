# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Phase 5 post-processing chain — fixed order, each step sees the previous step's output:

    symbol_pua -> caption_unbleed -> lang_retag -> dash_normalize -> mermaid_repair
               -> code_unescape -> chapter_split

Order matters: symbol_pua runs FIRST because it repairs characters and line-level structure that
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
    lang_retag,
    mermaid_repair,
    symbol_pua,
)


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
    """
    with open(md_path, encoding="utf-8") as f:
        md = f.read()
    report: dict[str, Any] = {}

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

    if apply:
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md)

    written, bounds = chapter_split.split(
        md_path, book, out_dir=out_dir, source_name=source_name, dry_run=not apply
    )
    report["chapter_split"] = {
        "boundaries": len(bounds),
        "titles": [t for _, t in bounds],
        "files": written,
    }
    report["applied"] = apply
    return report
