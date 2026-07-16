"""Unit tests for the converter's pure functions (no MinerU / GPU needed)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pdf2wiki.convert.merge import (cap_runs, detect_watermarks, group_runs, indent_suspect,
                                    iou, merge, norm_code, overlap_coef, render,
                                    strip_callouts, transplant_indent)


# ---------- code normal form ----------

def test_norm_code_ignores_fences_captions_callouts():
    a = "```java\nListing 3.1 Foo.java\npublic class Foo {①\n}\n```"
    b = "public class Foo {\n}"
    assert norm_code(a) == norm_code(b)


def test_norm_code_collapses_long_blobs():
    a = "token = 'eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9abcdef'"
    b = "token = 'eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9abcdEf'"  # OCR confusion inside blob
    assert norm_code(a) == norm_code(b)


def test_norm_code_flags_dot_for_underscore_hallucination():
    a = "serialization.load_pem_private_key(data)"
    b = "serialization.load.pem.private.key(data)"   # classic VLM `_`->`.` hallucination
    assert norm_code(a) != norm_code(b)


def test_strip_callouts():
    assert strip_callouts("int x = 1;①") == "int x = 1;"
    assert strip_callouts("foo() B") == "foo()"


# ---------- indent checks ----------

def test_indent_suspect_broken_python():
    # needs a PY_MARK keyword (def/class/import/...) to be treated as confidently-Python
    assert indent_suspect("def g():\ntry:\nf()\nexcept ValueError:\npass\n") is True


def test_indent_suspect_ignores_non_python():
    # no Python keyword marker -> check not meaningful -> never flags
    assert indent_suspect("try:\nf()\nexcept ValueError:\npass\n") is False


def test_indent_suspect_valid_python():
    assert indent_suspect("def f():\n    return 1\n") is False


def test_indent_suspect_skips_ruby_and_placeholders():
    assert indent_suspect("params[:id] => x\n.each do |y|\ndef f\n") is False
    assert indent_suspect("def g():\n[...]\n") is False


def test_transplant_indent_1to1():
    disp, reindented = transplant_indent("  a = 1\n    b = 2\n", "a = 1①\nb = 2❷\n")
    assert reindented is True
    assert disp == "  a = 1\n    b = 2"


def test_transplant_indent_fallback():
    disp, reindented = transplant_indent("  a = 1\n", "a = 1\nb = 2\n")
    assert reindented is False
    assert "b = 2" in disp


# ---------- geometry / runs ----------

def test_iou_and_overlap():
    assert iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1.0
    assert iou([0, 0, 2, 2], [5, 5, 6, 6]) == 0.0
    # contained smaller box: full containment -> overlap_coef 1.0 even at low IoU
    assert overlap_coef([0, 0, 100, 10], [0, 0, 20, 10]) == 1.0
    assert iou([0, 0, 100, 10], [0, 0, 20, 10]) < 0.3


def test_group_and_cap_runs():
    assert group_runs([1, 2, 3, 9, 10, 30], 3) == [(1, 3), (9, 10), (30, 30)]
    assert cap_runs([(0, 100)], 25) == [(0, 24), (25, 49), (50, 74), (75, 99), (100, 100)]


# ---------- watermarks ----------

def test_detect_watermarks():
    base = []
    for pg in range(20):
        base.append({"type": "text", "text": "LICENSED TO user@example.com", "page_idx": pg})
        base.append({"type": "text", "text": f"unique content {pg}", "page_idx": pg})
    wm = detect_watermarks(base, 20)
    assert wm == {"LICENSED TO user@example.com"}


# ---------- merge ----------

def _base():
    return [
        {"type": "header", "text": "hdr", "abs_page": 1, "bbox": [0, 0, 10, 5], "_imgdir": "/x"},
        {"type": "table", "table_body": "<table>bad</table>", "abs_page": 1,
         "bbox": [0, 30, 100, 80], "_imgdir": "/x"},
        {"type": "code", "code_body": "def f():\n    return 1\n", "abs_page": 2,
         "bbox": [0, 0, 100, 50], "_imgdir": "/x"},
        {"type": "code", "code_body": "x = private_key\n", "abs_page": 3,
         "bbox": [0, 0, 100, 50], "_imgdir": "/x"},
        {"type": "image", "image_caption": [], "img_path": "tiny.jpg", "abs_page": 3,
         "bbox": [0, 0, 10, 10], "_imgdir": "/x"},
        {"type": "text", "text": "WM LINE", "abs_page": 5, "bbox": [0, 90, 100, 99], "_imgdir": "/x"},
    ]


HYBRID = [
    {"type": "table", "table_body": "<table>good</table>", "abs_page": 1, "bbox": [0, 30, 100, 80]},
    {"type": "code", "code_body": "def f():\n    return 1\n", "abs_page": 2, "bbox": [0, 0, 95, 50]},
    {"type": "code", "code_body": "x = private.key\n", "abs_page": 3, "bbox": [0, 0, 95, 50]},
]


def test_merge_grafts_and_flags():
    final, st = merge(_base(), [dict(h) for h in HYBRID], {"WM LINE"}, tiny_px2=2500)
    assert st["table_swapped"] == 1
    assert st["code_verified"] == 1
    assert st["code_flagged"] == 1                     # `_`->`.` divergence caught
    assert st["noise_dropped"] == 2                    # watermark line + tiny caption-less image
    types = [b["type"] for b in final]
    assert "header" not in types                       # DROP list applied
    flagged = [b for b in final if b.get("_code_flag")]
    assert flagged and "private_key" in flagged[0]["code_body"]   # pipeline tokens won


def test_render_emits_code_verify_flag():
    final, _ = merge(_base(), [dict(h) for h in HYBRID], set(), tiny_px2=2500)
    flagged = next(b for b in final if b.get("_code_flag"))
    out = render(flagged)
    assert out.startswith("<!-- code-verify:")
    assert "private_key" in out
