# 0002. Reconcile code by token-verification, keeping pipeline truth

- Status: accepted
- Date: 2026-07-23 (recorded retrospectively)
- Deciders: Sevthered (maintainer)

## Context and Problem Statement

Given the two-backend design ([0001](0001-dual-backend-pipeline-and-hybrid.md)), the merge must decide,
per block, which pass to trust. For most block types the hybrid pass is strictly better (tables,
equations, charts, diagrams) and can be grafted in wholesale. **Code is the dangerous case:** the hybrid
pass often has *better indentation* than the flat pipeline output, but it also sometimes *hallucinates
tokens*. Taking hybrid code blindly reintroduces exactly the corruption the dual-backend design exists to
avoid; taking pipeline code blindly loses indentation the hybrid pass recovered correctly.

## Considered Options

1. **Always take hybrid code** (best indentation) — reintroduces hallucinated tokens. Rejected.
2. **Always take pipeline code** (byte-perfect) — loses recovered indentation; flat Python is often
   structurally wrong.
3. **Diff and pick per block by a token-level comparison**, so indentation comes from hybrid only when
   the tokens provably agree.

## Decision Outcome

Chosen: **option 3**. The base is the pipeline skeleton; hybrid *enriches* existing blocks, never adds or
replaces blocks, and is matched to base blocks by **geometry** (highest intersection-over-union above a
threshold, with a containment fallback). For code specifically, both versions are reduced to a
whitespace-insensitive **normal form** (fences, listing numbers, captions, markdown escapes stripped;
long base64/key blobs collapsed) and compared:

- **tokens match** → use the hybrid body for its indentation (`code_verified`); if that indentation fails
  a Python `ast.parse` check, mark `code_indent_flagged`.
- **tokens diverge** → the VLM changed the code → keep the **pipeline tokens**, re-apply hybrid
  indentation where lines align, and emit a visible `code-verify` comment (`code_flagged`).
- **no hybrid match** → keep the pipeline body (`code_pipeline_only`).

A **coverage gate** guards the whole pass: if any page with real text (>50 chars) produced zero blocks,
the converter hard-stops with `CoverageError` rather than ship a book with an invisible hole.

### Consequences

- **Good:** hallucinated code is never emitted silently — divergences are preserved as pipeline truth and
  flagged for review (`qa flags` surfaces them); correct indentation is still recovered when safe; the
  zero-fail coverage gate turns silent drops into loud failures.
- **Bad / trade-off:** the normal-form/geometry logic is subtle and is the hottest code in the project
  (`convert/merge.py`); the `code-verify` markers are extra artifacts a consumer must understand; the
  coverage gate can hard-stop a book that a looser tool would have shipped.

## More Information

[How the merge works](../explanation/how-the-merge-works.md) ·
[output layout: code-verify markers](../reference/output-layout.md) · `src/pdf2wiki/convert/merge.py`.
