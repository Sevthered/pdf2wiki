# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Golden snapshot of the merge → blocks.json + rendered-markdown output.

This is a behavior-lock: a representative base(pipeline) + hybrid(vlm) block pair is run through the
real `merge()`, and both the serialized block list (what becomes `blocks.json`) and the rendered
markdown are snapshotted. Any change to the merge/render output — intended or not — shows up as a
snapshot diff. It exists so a refactor (e.g. typing the block schema) can prove it changed nothing.

Regenerate deliberately with:  uv run pytest tests/test_golden.py --snapshot-update
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pdf2wiki.convert.block import Block
from pdf2wiki.convert.merge import merge, render

# A small fixture that exercises the paths that matter: code that MATCHES (take hybrid indentation),
# code that DIVERGES (VLM hallucinated → keep pipeline tokens + flag), a table swap, an image whose
# hybrid pass carries a Mermaid transcription, a plain heading + prose, and a per-page watermark drop.
BASE = [
    {"type": "text", "abs_page": 0, "bbox": [0, 0, 500, 20], "text": "Chapter 1", "text_level": 1},
    {
        "type": "code",
        "sub_type": "python",
        "abs_page": 0,
        "bbox": [0, 30, 500, 80],
        "code_body": "def f():\nreturn 1",
    },  # flat pipeline tokens
    {
        "type": "code",
        "sub_type": "python",
        "abs_page": 0,
        "bbox": [0, 90, 500, 140],
        "code_body": "x = load_key()",
    },  # pipeline truth
    {
        "type": "table",
        "abs_page": 1,
        "bbox": [0, 0, 500, 60],
        "table_body": "<table><tr><td>4.39.5</td></tr></table>",
    },  # garbled flat-text grid
    {
        "type": "image",
        "abs_page": 1,
        "bbox": [0, 70, 500, 200],
        "img_path": "images/fig1.jpg",
        "image_caption": ["Figure 1.1 Architecture"],
    },
    {"type": "text", "abs_page": 1, "bbox": [0, 210, 500, 230], "text": "Some prose."},
    {"type": "text", "abs_page": 2, "bbox": [0, 0, 500, 20], "text": "CONFIDENTIAL"},  # watermark
]

HYBRID = [
    {
        "type": "code",
        "sub_type": "python",
        "abs_page": 0,
        "bbox": [0, 30, 500, 80],
        "code_body": "def f():\n    return 1",
    },  # same tokens, correct indentation
    {
        "type": "code",
        "sub_type": "python",
        "abs_page": 0,
        "bbox": [0, 90, 500, 140],
        "code_body": "x = load.key()",
    },  # VLM dot-for-underscore hallucination
    {
        "type": "table",
        "abs_page": 1,
        "bbox": [0, 0, 500, 60],
        "table_body": "<table>\n<tr><td>4.3</td><td>9.5</td></tr>\n</table>",
    },  # correct grid
    {
        "type": "image",
        "abs_page": 1,
        "bbox": [0, 70, 500, 200],
        "content": "```mermaid\nflowchart LR\n  A --> B\n```",
    },  # diagram transcription
]

WATERMARKS = ["CONFIDENTIAL"]


def test_merge_golden(snapshot):
    final, stats = merge([dict(b) for b in BASE], [dict(b) for b in HYBRID], WATERMARKS)
    blocks_json = json.dumps(final, indent=1, default=str, ensure_ascii=False)
    rendered_md = "\n\n".join(render(Block.from_dict(b)) for b in final)

    assert stats == snapshot(name="graft_stats")
    assert blocks_json == snapshot(name="blocks_json")
    assert rendered_md == snapshot(name="rendered_md")
