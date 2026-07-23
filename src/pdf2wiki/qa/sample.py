"""Sample N random pages from a book, build a sample PDF, render each to PNG.
Reproducible via seed. Used for manual conversion back-checks against the source pages."""

import json
import os
import random


def sample_pages(
    pdf_path: str, name: str, qa_root: str, n: int = 20, seed: int = 42, dpi: int = 140
) -> dict:
    import pymupdf  # lazy: keep import cost out of CLI startup

    qa = os.path.join(os.path.expanduser(qa_root), name)
    os.makedirs(os.path.join(qa, "pages"), exist_ok=True)
    d = pymupdf.open(pdf_path)
    random.seed(seed)
    # avoid front/back matter: sample from 5%..95% of the book
    lo, hi = int(d.page_count * 0.05), int(d.page_count * 0.95)
    if hi <= lo:  # too short for a 5..95% window -> use the whole book
        lo, hi = 0, d.page_count
    if hi <= lo:  # empty/zero-page PDF
        raise ValueError(f"{name}: PDF has no pages to sample (page_count={d.page_count})")
    n = min(n, hi - lo)  # never ask for more pages than the window holds
    pages = sorted(random.sample(range(lo, hi), n))

    sample = pymupdf.open()
    mapping = []
    for i, pg in enumerate(pages):
        sample.insert_pdf(d, from_page=pg, to_page=pg)
        pix = d[pg].get_pixmap(dpi=dpi)
        pix.save(os.path.join(qa, "pages", f"s{i:02d}_orig{pg}.png"))
        mapping.append({"sample_idx": i, "orig_page": pg})
    sample_pdf = os.path.join(qa, f"{name}_sample.pdf")
    sample.save(sample_pdf)
    with open(os.path.join(qa, "mapping.json"), "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=1)
    return {
        "qa_dir": qa,
        "sample_pdf": sample_pdf,
        "pages": pages,
        "range": (lo, hi),
        "page_count": d.page_count,
        "seed": seed,
    }
