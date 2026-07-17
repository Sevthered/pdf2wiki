# How the merge works

The merge is where the two backend passes become one document. This page explains the model behind it.
For the artifacts it produces, see [pipeline stages](../reference/pipeline-stages.md); for *why* there
are two backends, see [why a dual-backend pipeline](why-dual-backend.md).

## Base is the skeleton

The pipeline pass produces the **base**: the full page-ordered block list with byte-perfect code and
text. The merge walks the base block by block and, for each block, asks whether the hybrid pass has
something better to graft in. Hybrid never adds blocks the base doesn't have and never replaces base
images with its own — it only *enriches* existing blocks. This is what keeps code and structure
trustworthy: the shape of the document is always the pipeline's.

## Grafting by geometry

To decide which hybrid block corresponds to a base block, the merge matches them by page and bounding
box. It takes the hybrid candidate with the highest intersection-over-union above a threshold, falling
back to a containment measure when one box sits inside the other. Matched hybrid content is grafted per
block type:

- **tables** → swap in the hybrid grid (`table_body`);
- **equations** → swap in the hybrid LaTeX;
- **charts** → enrich with hybrid data;
- **images** → attach a hybrid Mermaid transcription if present; drop caption-less tiny images as
  decorative noise;
- **code** → reconcile by token-verify (below).

## Code token-verify

Code is the one place a wrong graft would be silently damaging, so it gets special handling. For each
code block the merge computes a whitespace-insensitive **normal form** of both versions (fences,
listing numbers, captions, and markdown escapes stripped; long base64/key blobs collapsed) and compares:

- **tokens match** → use the hybrid body, because it carries better indentation. Counted `code_verified`.
  If the hybrid indentation still fails a Python `ast.parse` sanity check, the block is marked
  `code_indent_flagged`.
- **tokens diverge** → the VLM changed the code. Keep the **pipeline tokens** (the truth), re-apply the
  hybrid indentation onto them where the lines align, and mark the block with a
  [`code-verify` comment](../reference/output-layout.md#code-verify-markers). Counted `code_flagged`.
- **no hybrid match** → use the pipeline body as-is. Counted `code_pipeline_only`.

The result: you never get hallucinated code silently. Divergences are preserved as pipeline truth and
visibly flagged.

## The coverage gate

Before merging, the converter checks that every page carrying real text (more than 50 characters in the
PDF text layer) produced at least one extracted block. If any page produced text but zero blocks, that
page was silently dropped by extraction — and the converter **hard-stops** with a `CoverageError`
rather than emit a book with an invisible hole. This is a deliberate zero-fail policy: a loud failure
you fix beats a quiet gap you ship. See [troubleshooting](../how-to/troubleshoot.md#coverage-gate-hard-stop).

## Chapter normalization

Finally, the PDF's own level-1 bookmarks (its table of contents) correct chapter boundaries: matching
headings are promoted to H1 with the canonical ToC title, a synthetic H1 is inserted where the heading
was dropped, and — only when there is enough corroborating evidence — spurious H1s are demoted. This is
what lets [`chapter_split`](../reference/phase5-steps.md) cut the book at the right places.
