"""Per-book flagged-block report: which code blocks the VLM diverged on — the highest-signal QA
sample. Pure read over a converted book's blocks.json (no converter or schema change). The flags are
set during merge in convert/merge.py: `_code_flag` = the hybrid/VLM code diverged from the byte-clean
text layer (output shows the pipeline tokens); `_indent_flag` = tokens agreed but the hybrid
indentation failed a Python ast sanity check. These are exactly the places worth eyeballing."""

import json
import os
from typing import Any

from ..convert.block import Block


def flagged_report(blocks_path: str, name: str | None = None) -> dict[str, Any]:
    """Summarize the flagged code blocks in one book's blocks.json.

    Returns {name, code_blocks, flagged, diverged, indent_suspect, blocks} where `blocks` is the
    page-sorted list of flagged entries {page, lang, flag, snippet}; `page` is 1-based for display.
    """
    path = os.path.expanduser(blocks_path)
    with open(path, encoding="utf-8") as f:
        blocks = [Block.from_dict(b) for b in json.load(f)]
    name = name or os.path.basename(os.path.dirname(os.path.abspath(path)))

    code_blocks = 0
    flagged: list[dict[str, Any]] = []
    for b in blocks:
        if b.type != "code":
            continue
        code_blocks += 1
        if b.code_flag:
            flag = "diverged"
        elif b.indent_flag:
            flag = "indent"
        else:
            continue
        snippet = next((ln.strip() for ln in b.code_body.splitlines() if ln.strip()), "")[:80]
        flagged.append(
            {
                "page": b.abs_page + 1,
                "lang": b.sub_type,
                "flag": flag,
                "snippet": snippet,
            }
        )

    flagged.sort(key=lambda e: e["page"])
    return {
        "name": name,
        "code_blocks": code_blocks,
        "flagged": len(flagged),
        "diverged": sum(1 for e in flagged if e["flag"] == "diverged"),
        "indent_suspect": sum(1 for e in flagged if e["flag"] == "indent"),
        "blocks": flagged,
    }
