# Output layout reference

What `convert`, `phase5`, `batch` and `listings --out` write to disk, and how to read the fidelity
markers.

## Converted book

```
<out_root>/<slug>/
├── <slug>.md          # merged Markdown (the whole book)
├── images/            # extracted figures, referenced as images/<name>
├── blocks.json        # full merged block list (type, page, bbox, provenance)
├── book.json          # book metadata from the PDF (title, authors, year, ISBN, publisher)
├── base_0_39/         # pipeline pass output (one dir per seg-page chunk)
│   ├── ...            # MinerU content_list.json etc.
│   └── (base_0_39.log, base_0_39/.done next to it)
└── hy_40_64/          # hybrid VLM pass output (one dir per rich-page run)
```

`<out_root>` defaults to `~/pdf2wiki/out` (config `[convert] out_root`, or `--out`). The `base_*` and
`hy_*` directories are the MinerU pass caches. Their `.done` sentinels drive
[resumability](pipeline-stages.md#stage-1--convert-pdf2wiki-convert).

## After phase5

```
<md dir>/chapters/
├── <slug>-index.md    # the entry page: book metadata + one row per chapter
├── 00-front-matter.md
├── 01-<slug-of-heading>.md
├── 02-<slug-of-heading>.md
└── ...
```

Each chapter file carries YAML frontmatter (`title`, `book`, `chapter`, `source`, `tags: [book]`).
When they are known, it also carries the book metadata and the chapter's `pdf_pages`. See
[phase5 steps](phase5-steps.md#chapter-frontmatter). `<slug>-index.md` links every chapter file. See
[book index](phase5-steps.md#book-index). In `batch`, images are also copied to
`chapters/images/` so the chapter files render standalone.

## Exported listings

`pdf2wiki listings <dir> --out NEW_DIR` writes this layout:

```
<NEW_DIR>/
├── index.json               # one entry for each code block
├── 07-chapter-4/            # the chapter file name without .md
│   ├── 01.java              # the first code block of the chapter
│   ├── 02-listing-4-1.java  # a block with a "Listing 4.1" caption directly above it
│   └── 03.txt               # a block with no tag, or a tag with no known extension
└── 08-chapter-5/
    └── ...
```

The number is the position of the block in its chapter file, from `01`. A chapter with 100 or more
blocks gets three digits. The extension comes from the language tag, through the alias table of the
`lang_retag` step. Each file holds the text of one block, with LF line ends, also for a chapter
file with CRLF line ends.

A caption is attached when the paragraph directly above the opening fence is a listing caption. Blank
lines and one-line HTML comments, such as a code-verify marker, can be between them. The caption and
paragraph rules are the same as for [`link`](cli.md#link). A caption that is not a heading must have
the fence within two non-blank lines. Prose such as "Listing 4.1 shows the class" is not a caption.

`index.json` is a list with one object for each block, in chapter and block order:

| Key | Value |
|-----|-------|
| `chapter` | The chapter file name, such as `07-chapter-4.md`. |
| `line` | The line of the opening fence in the chapter file, from 1. |
| `lang` | The language tag of the fence. An empty string when the fence has no tag. |
| `caption` | The caption text without Markdown emphasis, or `null`. |
| `path` | The path of the block file, relative to `NEW_DIR`. |
| `check` | Only with `--check`: `{"class": ..., "message": ...}`. See [`listings`](cli.md#listings). |

## Code-verify markers

The converter never silently trusts VLM-transcribed code. When a code block's hybrid and pipeline
versions diverge, the block keeps the pipeline tokens, which are the truth. It also carries an HTML
comment, so that a downstream reader or a human can reconcile the two:

```
<!-- ⚠ code-verify: hybrid tokens diverged from pipeline; showing pipeline tokens -->
```

A second marker flags a block whose tokens agreed but whose hybrid indentation failed a Python
`ast.parse` sanity check. These comments are invisible in rendered Markdown. See
[how the merge works](../explanation/how-the-merge-works.md#code-token-verify).

## Stats glossary

`convert` reports merge stats. Here is what each counter means.

| Stat | Meaning |
|------|---------|
| `code_verified` | Code blocks where hybrid and pipeline tokens matched (hybrid indentation kept). |
| `code_flagged` | Code blocks where they diverged — pipeline tokens win, block marked. |
| `code_pipeline_only` | Code blocks with no hybrid match — pipeline body used as-is. |
| `code_indent_flagged` | Verified blocks whose hybrid indentation looked suspect (marked). |
| `table_swapped` / `table_kept` | Tables where a hybrid grid replaced the base / was kept. |
| `mermaid_attached` | Images that gained a hybrid-transcribed Mermaid diagram. |
| `eq_swapped` / `eq_kept` | Equations where hybrid LaTeX replaced the base / was kept. |
| `chart_enriched` / `charts` | Charts enriched with hybrid data / total charts. |
| `images` | Images kept. |
| `noise_dropped` | Caption-less tiny images and watermark blocks dropped. |
