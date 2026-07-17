# Phase 5 steps reference

`phase5` runs six post-processors in a fixed order on a converted `.md`. The first five transform the
Markdown string; the sixth splits it into chapter files. Order matters — each step depends on the
previous one's output. See [post-process and split](../how-to/post-process-and-split.md) for how to run
it, and [`phase5` in the CLI reference](cli.md#phase5) for flags.

The chain is a dry-run by default. Every string transformer is idempotent, and all of them except
`mermaid_repair` leave ```mermaid``` fences untouched.

## The chain

| # | Step | Reads | Does | Produces |
|---|------|-------|------|----------|
| 1 | `caption_unbleed` | md | Lifts a `Listing/Figure/Table/Example N.M …` caption that MinerU trapped inside a code fence out to a bold line above the fence, or drops a caption-only fence entirely. | md with captions un-bled from code |
| 2 | `lang_retag` | md | Re-detects each code fence's language by precedence — a `# file: x.ext` hint, then a trusted specific MinerU tag, then a keyword heuristic, else `text` — and rewrites the fence tag. | md with reliable language tags |
| 3 | `dash_normalize` | md | Inside code fences only, converts a typographic en/em-dash used as a long-flag prefix (`–dev`) to `--` and a U+2212 minus to `-`. | md with correct dashes in code |
| 4 | `mermaid_repair` | md | Sanitizes ```mermaid``` node labels so the diagram parses — literal `\n` → `<br>`, inner quotes → `'`, inner brackets → `()`, closes unclosed labels, drops orphan brackets. | md with parseable Mermaid |
| 5 | `code_unescape` | md | Inside code fences only, strips MinerU's markdown-punctuation escapes (`\$ \* \~ \_` `` \` `` `\# \@ \% \& \!`) while preserving real string/regex escapes (`\n \t \d \s \" \\`). | md with clean code fences |
| 6 | `chapter_split` | md file | Splits at fence-aware H1 boundaries (plus mistagged `## Appendix X.` H2s) into per-chapter files with YAML frontmatter. | `00-front-matter.md` + `NN-slug.md` files |

## Chapter frontmatter

`chapter_split` injects this frontmatter into every chapter file:

```yaml
---
title: 'Chapter 3: Advanced Features'
book: <slug>            # from --book
chapter: 3              # integer order; front matter = 0
source: <pdf-filename>  # from --source-name (else the md path)
tags: [book]
---
```

Files are named `00-front-matter.md` (all content before the first boundary) then `NN-slug.md`, where
`NN` is the two-digit order and the slug is the lowercased, hyphenated, 60-char-truncated heading.
Image paths are **not** rewritten — chapter files share the same directory as `images/`, so relative
references keep resolving.

If the Markdown has no detectable boundary, `chapter_split` raises an error rather than emit a single
undivided file — fix the headings and re-run.

## Why this order

`caption_unbleed` first, so `lang_retag` detects language on clean code. `lang_retag` before
`dash_normalize` and `code_unescape`, which scope their edits to code fences. `mermaid_repair` before
the split, so diagrams are fixed while still in one document. `chapter_split` last, because the
other five must land before the Markdown is cut into files.
