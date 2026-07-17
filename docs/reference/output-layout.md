# Output layout reference

What `convert`, `phase5`, and `batch` write to disk, and how to read the fidelity markers.

## Converted book

```
<out_root>/<slug>/
├── <slug>.md          # merged Markdown (the whole book)
├── images/            # extracted figures, referenced as images/<name>
├── blocks.json        # full merged block list (type, page, bbox, provenance)
├── base_0_39/         # pipeline pass output (one dir per seg-page chunk)
│   ├── ...            # MinerU content_list.json etc.
│   └── (base_0_39.log, base_0_39/.done next to it)
└── hy_40_64/          # hybrid VLM pass output (one dir per rich-page run)
```

`<out_root>` defaults to `~/pdf2wiki/out` (config `[convert] out_root`, or `--out`). The `base_*` and
`hy_*` directories are the MinerU pass caches; their `.done` sentinels drive
[resumability](pipeline-stages.md#stage-1--convert-pdf2wiki-convert).

## After phase5

```
<md dir>/chapters/
├── 00-front-matter.md
├── 01-<slug-of-heading>.md
├── 02-<slug-of-heading>.md
└── ...
```

Each file carries YAML frontmatter (`title`, `book`, `chapter`, `source`, `tags: [book]`) — see
[phase5 steps](phase5-steps.md#chapter-frontmatter). In `batch`, images are also copied to
`chapters/images/` so the chapter files render standalone.

## Code-verify markers

The converter never silently trusts VLM-transcribed code. When a code block's hybrid and pipeline
versions diverge, the block keeps the pipeline tokens (the truth) and carries an HTML comment so a
downstream reader (or human) can reconcile:

```
<!-- ⚠ code-verify: hybrid tokens diverged from pipeline; showing pipeline tokens -->
```

A second marker flags a block whose tokens agreed but whose hybrid indentation failed a Python
`ast.parse` sanity check. These comments are invisible in rendered Markdown. See
[how the merge works](../explanation/how-the-merge-works.md#code-token-verify).

## Stats glossary

`convert` reports merge stats; here is what each counter means.

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
