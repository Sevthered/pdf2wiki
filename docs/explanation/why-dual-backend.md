# Why a dual-backend pipeline

pdf2wiki runs a PDF through **two** MinerU backends and merges the results. This page explains why —
the problem a single backend cannot solve.

## Neither backend wins alone

MinerU can extract a PDF two ways, and each is good at exactly what the other is bad at.

- **`pipeline -m txt`** reads the PDF's embedded text layer. Code and prose come out **byte-perfect**.
  But it reconstructs tables from a flat text stream, so numeric and wrapped-cell tables garble; it
  strips Python indentation; it produces no diagrams; and it mistags code-fence languages.
- **`hybrid-engine --effort high`** runs a vision-language model. It reconstructs **table grids**
  correctly, transcribes diagrams to **Mermaid**, and handles LaTeX. But a VLM re-reading code
  **hallucinates tokens** — on a real Java book we saw `.findFirst()` become `.Alzheimer()`,
  `@PostConstruct` become `@postsConstruct`, `orElseThrow` become garbage. It also markdown-escapes
  punctuation inside code (`$` → `\$`).

So there is no single backend that gives you correct code **and** correct tables **and** diagrams. If
you pick pipeline you lose tables and diagrams; if you pick hybrid you lose code fidelity, which for a
technical book is the thing that matters most.

## The resolution: use both, graft the good parts

pdf2wiki treats the **pipeline** pass as the authoritative skeleton — its code and text are trusted —
and grafts in **only** the parts the hybrid pass does better: table grids, Mermaid diagrams, cleaner
LaTeX, and chart data. Code is reconciled by comparing the two token-for-token and keeping the pipeline
version whenever they differ. See [how the merge works](how-the-merge-works.md).

## Per-page routing keeps it affordable

The expensive VLM pass does not run on the whole book. Only *rich* pages — those whose pipeline output
contains a table, image, code block, equation, or chart — go through hybrid, grouped into contiguous
runs. Plain text pages are served entirely by the cheap pipeline pass. This keeps VRAM bounded and the
run fast while still covering every page that needs the VLM.

## What still needs cleanup

The VLM's Mermaid and language tags are imperfect, and its markdown escaping leaks into code. Those are
not conversion problems — they are fixed deterministically afterward by the
[phase 5 chain](../reference/phase5-steps.md) (Mermaid repair, language re-tagging, code unescaping).
The division of labour is deliberate: MinerU extracts, the merge arbitrates fidelity, phase 5 polishes.
