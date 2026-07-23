# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""render_block must tolerate explicit JSON-null field values (not just missing keys).

Regression: `.get(k, default)` only defaults MISSING keys; a JSON null returns None, so
`None.strip()`, `"# " + None`, and returning None (breaking review.py's join) all crashed when
the converter emitted an explicit null.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pdf2wiki.convert.block import Block
from pdf2wiki.render import render_block


def rb(d):
    return render_block(Block.from_dict(d))


def test_null_text_and_code_body():
    assert rb({"type": "text", "text": None}) == ""
    assert rb({"type": "text", "text": None, "text_level": 2}) == "## "
    assert rb({"type": "code", "code_body": None, "sub_type": None}) == "```\n\n```"
    assert rb({"type": "equation", "text": None}) == ""


def test_null_content_and_captions():
    # None content -> no crash, no [+DATA]/[+MERMAID] section
    assert rb({"type": "chart", "content": None, "img_path": None}) == "[CHART ]"
    assert rb({"type": "image", "content": None, "img_path": None}) == "[IMAGE ]"
    assert rb({"type": "table", "table_body": None, "table_caption": None}) == ""
    assert rb({"type": "list", "list_items": None}) == ""


def test_normal_values_still_render():
    assert rb({"type": "code", "code_body": "x = 1", "sub_type": "py"}) == "```py\nx = 1\n```"
    out = rb({"type": "image", "content": "mermaid\ngraph TD", "img_path": "i.png"})
    assert "[IMAGE i.png]" in out and "[+MERMAID]" in out
