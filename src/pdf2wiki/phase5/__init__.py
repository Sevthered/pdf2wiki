"""Phase 5 post-processing chain — fixed order, each step sees the previous step's output:

    caption_unbleed -> lang_retag -> dash_normalize -> mermaid_repair -> code_unescape -> chapter_split

Order matters: caption_unbleed removes caption-only junk fences and lifts leading captions so
lang_retag detects on clean code; lang tags before dash-normalize scopes to code fences;
dash/mermaid fixes must land before the md is split into chapters; code_unescape strips leftover
markdown-punct escapes inside code fences last (both merge paths). Re-run whenever the converter
output changes upstream — do not reuse stale artifacts.
"""

from typing import Any

from . import (
    caption_unbleed,
    chapter_split,
    code_unescape,
    dash_normalize,
    lang_retag,
    mermaid_repair,
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

    md, captions = caption_unbleed.unbleed(md)
    report["caption_unbleed"] = {"unwrapped": len(captions), "captions": captions}

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
