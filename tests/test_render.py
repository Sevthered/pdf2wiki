"""render_block must tolerate explicit JSON-null field values (not just missing keys).

Regression: `.get(k, default)` only defaults MISSING keys; a JSON null returns None, so
`None.strip()`, `"# " + None`, and returning None (breaking review.py's join) all crashed when
the converter emitted an explicit null.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pdf2wiki.render import render_block


def test_null_text_and_code_body():
    assert render_block({"type": "text", "text": None}) == ""
    assert render_block({"type": "text", "text": None, "text_level": 2}) == "## "
    assert render_block({"type": "code", "code_body": None, "sub_type": None}) == "```\n\n```"
    assert render_block({"type": "equation", "text": None}) == ""


def test_null_content_and_captions():
    # None content -> no crash, no [+DATA]/[+MERMAID] section
    assert render_block({"type": "chart", "content": None, "img_path": None}) == "[CHART ]"
    assert render_block({"type": "image", "content": None, "img_path": None}) == "[IMAGE ]"
    assert render_block({"type": "table", "table_body": None, "table_caption": None}) == ""
    assert render_block({"type": "list", "list_items": None}) == ""


def test_normal_values_still_render():
    assert render_block({"type": "code", "code_body": "x = 1", "sub_type": "py"}) == "```py\nx = 1\n```"
    out = render_block({"type": "image", "content": "mermaid\ngraph TD", "img_path": "i.png"})
    assert "[IMAGE i.png]" in out and "[+MERMAID]" in out
