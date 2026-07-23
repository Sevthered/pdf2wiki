# 0001. Convert with two MinerU backends and merge, not one

- Status: accepted
- Date: 2026-07-23 (recorded retrospectively)
- Deciders: Sevthered (maintainer)

## Context and Problem Statement

pdf2wiki targets heavily technical books, where **code fidelity is the thing that matters most** — a
hallucinated token in a code block is worse than useless because a reader (or an LLM) will trust it.
MinerU can extract a PDF two ways, and a smoke test on a real Manning/Packt Java book showed each is
good at exactly what the other is bad at:

- **`pipeline -m txt`** (embedded text layer): code and prose come out **byte-perfect**, but it garbles
  numeric/wrapped tables, strips Python indentation, produces no diagrams, and mistags code-fence
  languages.
- **`hybrid-engine --effort high`** (vision-language model): reconstructs **table grids**, transcribes
  diagrams to **Mermaid**, handles LaTeX — but re-reading code it **hallucinates tokens**
  (`.findFirst()` → `.Alzheimer()`, `@PostConstruct` → `@postsConstruct`, `orElseThrow` → garbage) and
  markdown-escapes punctuation inside code.

There is no single backend that gives correct code **and** tables **and** diagrams.

## Considered Options

1. **Pipeline only** — perfect code, but no usable tables/diagrams; unacceptable for the book domain.
2. **Hybrid only** — good tables/diagrams, but corrupted code; fails the primary requirement.
3. **A third-party OCR/VLM service** (LlamaParse, Mathpix, paid vision OCR) — rejected by the project's
   free/open-source-only constraint.
4. **Run both MinerU backends and merge**, trusting each where it is strong.

## Decision Outcome

Chosen: **option 4** — run the pipeline pass as the authoritative skeleton and graft in only the parts
the hybrid pass does better (table grids, Mermaid, LaTeX, chart data), reconciling code by
token-verification ([0002](0002-code-merge-by-token-verification.md)). The expensive VLM pass runs only
on *rich* pages (those whose pipeline output has a table, image, code, equation, or chart), grouped into
contiguous runs, so VRAM stays bounded.

### Consequences

- **Good:** correct code, correct tables, and diagrams in one document; the VLM never silently rewrites
  code; per-page routing keeps a full-book run affordable on a 12 GB GPU.
- **Bad / trade-off:** two passes cost more time and orchestration than one; the merge is non-trivial
  (geometry matching, token-verify); the VLM's imperfect Mermaid and language tags still need a
  deterministic cleanup pass (phase 5).

## More Information

[Why a dual-backend pipeline](../explanation/why-dual-backend.md) ·
[How the merge works](../explanation/how-the-merge-works.md).
