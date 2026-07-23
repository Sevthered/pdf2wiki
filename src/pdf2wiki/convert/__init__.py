"""Dual-pass converter (MinerU pipeline + hybrid merge).

Base-driven merge: the pipeline `-m txt` pass gives a byte-perfect skeleton from the PDF's
embedded text layer; the hybrid/VLM pass is grafted in for table grids, Mermaid diagram
transcriptions, LaTeX equations and chart data, matched by page + bbox-IoU. Code blocks are
token-verified between the passes and flagged on divergence. A coverage gate hard-stops if any
text-bearing page produced no blocks (zero-fail scrape); all MinerU passes are cached with
`.done` sentinels for safe resume.

Output layout (consumed by phase5, qa.review, batch):
    <out_root>/<slug>/<slug>.md     merged markdown
    <out_root>/<slug>/images/       extracted figure images (relative refs from the md)
    <out_root>/<slug>/blocks.json   per-block records with abs_page (for QA review)
    <out_root>/<slug>/*.log         per-pass MinerU logs (never suppressed)
"""
from .cloud import convert_book_cloud
from .merge import convert_book

__all__ = ["convert_book", "convert_book_cloud"]
