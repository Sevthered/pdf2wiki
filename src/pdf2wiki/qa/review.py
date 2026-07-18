"""Split converted blocks by sample page -> per-page markdown, aligned with the rendered PNGs
from qa.sample, for manual side-by-side back-checks."""
import json
import os

from ..render import render_block


def build_review(qa_dir: str, name: str, blocks_path: str | None = None) -> dict:
    qa = os.path.expanduser(qa_dir)
    blocks_path = blocks_path or os.path.join(qa, "out", f"{name}_sample", "blocks.json")
    with open(blocks_path, encoding="utf-8") as f:
        blocks = json.load(f)
    with open(os.path.join(qa, "mapping.json"), encoding="utf-8") as f:
        mapping = {m["sample_idx"]: m["orig_page"] for m in json.load(f)}

    # NOTE: blocks.json here comes from converting the SAMPLE pdf, so abs_page IS the sample
    # index (the sample pdf's pages are 0..N-1). mapping only translates it back to the original
    # book page for display. Do not "fix" this to key by original page.
    bypage: dict[int, list] = {}
    for b in blocks:
        bypage.setdefault(int(b.get("abs_page", 0)), []).append(b)

    out = []
    for si in sorted(mapping):
        md = "\n\n".join(render_block(b) for b in bypage.get(si, []))
        out.append(f"\n\n{'=' * 70}\nSAMPLE {si:02d}  (original page {mapping[si]})\n{'=' * 70}\n{md}")
    review_path = os.path.join(qa, "review.txt")
    with open(review_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    return {"review": review_path, "pages_with_content": len(bypage), "sampled": len(mapping)}
