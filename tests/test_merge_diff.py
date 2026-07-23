"""Differential harness for the merge() typed-Block migration (Stage 6b-ii).

`merge_legacy` is a FROZEN, dict-based copy of merge() as it was before the typed-Block migration.
The property test generates arbitrary base/hybrid block pairs (sharing page+bbox so the graft paths
actually fire) and asserts `merge(...) == merge_legacy(...)` — output AND stats identical. This is far
stronger than the single golden fixture for the code that decides fidelity: while merge() migrates onto
Block, any behavioural divergence on any generated input fails here.

Delete this file (and merge_legacy) once merge() is migrated + proven; the golden snapshot remains the
permanent regression test.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hypothesis import given, settings
from hypothesis import strategies as st

from pdf2wiki.convert.merge import (
    DROP,
    bbox,
    indent_suspect,
    iou,
    merge,
    norm_code,
    overlap_coef,
    strip_callouts,
    strip_listing_numbers,
    transplant_indent,
)


def merge_legacy(base, hybrid, wm, tiny_px2=2500):
    hy = {"table": {}, "image": {}, "equation": {}, "chart": {}, "code": {}}
    for h in hybrid:
        t = h.get("type")
        if t == "table":
            hy["table"].setdefault(h["abs_page"], []).append(h)
        elif t == "image" and "mermaid" in str(h.get("content", "")):
            hy["image"].setdefault(h["abs_page"], []).append(h)
        elif t == "equation" and h.get("text"):
            hy["equation"].setdefault(h["abs_page"], []).append(h)
        elif t == "chart" and str(h.get("content", "")).strip():
            hy["chart"].setdefault(h["abs_page"], []).append(h)
        elif t == "code" and h.get("code_body"):
            hy["code"].setdefault(h["abs_page"], []).append(h)

    def best(cands, b, contain_ok=False):
        m = max(cands, key=lambda h: iou(bbox(b), bbox(h)), default=None)
        if m and iou(bbox(b), bbox(m)) > 0.3:
            return m
        if contain_ok and cands:
            m2 = max(cands, key=lambda h: overlap_coef(bbox(b), bbox(h)), default=None)
            if m2 and overlap_coef(bbox(b), bbox(m2)) > 0.8:
                return m2
        return None

    final = []
    st_ = dict(
        table_swapped=0,
        table_kept=0,
        mermaid_attached=0,
        images=0,
        eq_swapped=0,
        eq_kept=0,
        chart_enriched=0,
        charts=0,
        noise_dropped=0,
        code_verified=0,
        code_flagged=0,
        code_pipeline_only=0,
        code_indent_flagged=0,
    )
    for b in base:
        t = b.get("type")
        if t in DROP:
            continue
        if isinstance(b.get("text"), str) and b["text"].strip() in wm:
            st_["noise_dropped"] += 1
            continue
        b = dict(b)
        b["_src"] = "base"
        if t == "table":
            m = best(hy["table"].get(b["abs_page"], []), b)
            if m:
                b["table_body"] = m.get("table_body", b.get("table_body"))
                st_["table_swapped"] += 1
            else:
                st_["table_kept"] += 1
        elif t == "equation":
            m = best(hy["equation"].get(b["abs_page"], []), b)
            if m:
                b["text"] = m["text"]
                st_["eq_swapped"] += 1
            else:
                st_["eq_kept"] += 1
        elif t == "code":
            m = best(hy["code"].get(b["abs_page"], []), b, contain_ok=True)
            if m:
                hy_body = m.get("code_body", "")
                pi_body = b.get("code_body", "")
                b["sub_type"] = m.get("sub_type", b.get("sub_type"))
                if norm_code(pi_body) == norm_code(hy_body):
                    b["code_body"] = hy_body
                    b["_code_path"] = "verified"
                    if indent_suspect(hy_body):
                        b["_indent_flag"] = True
                        st_["code_indent_flagged"] += 1
                    st_["code_verified"] += 1
                else:
                    disp, reindented = transplant_indent(hy_body, pi_body)
                    b["code_body"] = disp
                    b["_code_flag"] = True
                    b["_reindented"] = reindented
                    b["_code_path"] = "flagged"
                    st_["code_flagged"] += 1
            else:
                b["code_body"] = strip_callouts(strip_listing_numbers(b.get("code_body", "")))
                b["_code_path"] = "pipeline_only"
                st_["code_pipeline_only"] += 1
        elif t == "chart":
            m = best(hy["chart"].get(b["abs_page"], []), b)
            if m:
                b["content"] = m.get("content", "")
                st_["chart_enriched"] += 1
            st_["charts"] += 1
        elif t == "image":
            bb = bbox(b)
            area = (bb[2] - bb[0]) * (bb[3] - bb[1]) if bb else 0
            cap = b.get("image_caption") or []
            if not any(cap) and area < tiny_px2:
                st_["noise_dropped"] += 1
                continue
            m = best(hy["image"].get(b["abs_page"], []), b)
            if m:
                b["content"] = m.get("content", "")
                st_["mermaid_attached"] += 1
            st_["images"] += 1
        final.append(b)
    return final, st_


# ---- generators: base/hybrid pairs that share page+bbox so matches actually fire ----
_TYPE = st.sampled_from(["code", "table", "text", "image", "equation", "chart", "header", "footer"])
_BODY = st.text(alphabet="abcXYZ012 =()_.\n", max_size=24)
_CONTENT = st.sampled_from(["", "```mermaid\nA-->B\n```", "chartdata"])
_SUB = st.sampled_from(["python", "java", ""])


@st.composite
def _pair(draw):
    page = draw(st.integers(0, 3))
    lo = draw(st.integers(0, 40))
    hi = draw(st.integers(41, 100))
    box = [lo, lo, hi, hi]  # non-degenerate; base+hybrid share it -> IoU 1.0
    base = {
        "type": draw(_TYPE),
        "abs_page": page,
        "bbox": box,
        "sub_type": draw(_SUB),
        "code_body": draw(_BODY),
        "text": draw(_BODY),
        "table_body": draw(_BODY),
        "content": draw(_CONTENT),
        "image_caption": draw(st.lists(_BODY, max_size=1)),
    }
    hyb = None
    if draw(st.booleans()):
        hyb = {
            "type": draw(_TYPE),
            "abs_page": page,
            "bbox": box,
            "sub_type": draw(_SUB),
            "code_body": draw(_BODY),
            "text": draw(_BODY),
            "table_body": draw(_BODY),
            "content": draw(_CONTENT),
        }
    return base, hyb


@settings(max_examples=300)
@given(st.lists(_pair(), max_size=6), st.sets(st.text(max_size=4), max_size=2))
def test_merge_equals_legacy(pairs, wm):
    base = [b for b, _ in pairs]
    hybrid = [h for _, h in pairs if h]
    got = merge([dict(b) for b in base], [dict(h) for h in hybrid], set(wm))
    ref = merge_legacy([dict(b) for b in base], [dict(h) for h in hybrid], set(wm))
    assert got == ref
