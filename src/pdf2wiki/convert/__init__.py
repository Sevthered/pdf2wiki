"""Dual-pass converter (MinerU pipeline + hybrid merge).

STATUS: pending import of the validated production converter. The proven implementation
(base-driven merge: pipeline `-m txt` skeleton for byte-perfect code, hybrid/VLM pass grafted in
for table grids / Mermaid diagrams / equations, bbox-IoU matching, coverage gate with
hard-stop-and-resume) is being reconciled from its production deployment before it lands here.

The public contract this module will honor:

    convert_book(pdf_path, slug, out_root, *, start=None, end=None, timeout=None)
        -> (ok: bool, log_text: str)

Output layout (consumed by phase5, qa.review, batch):
    <out_root>/<slug>/<slug>.md     merged markdown
    <out_root>/<slug>/images/       extracted figure images (relative refs from the md)
    <out_root>/<slug>/blocks.json   per-block records with abs_page (for QA review)
    <out_root>/<slug>/*.log         per-pass MinerU logs (never suppressed)
"""


def convert_book(pdf_path: str, slug: str, out_root: str, *,
                 start: int | None = None, end: int | None = None,
                 timeout: int | None = None) -> tuple[bool, str]:
    raise NotImplementedError(
        "the converter module has not landed in this release yet — "
        "see the project README roadmap. Phase 5, qa, and scan commands are fully functional "
        "on existing MinerU/converter output."
    )
