# Pipeline stages reference

The end-to-end path a book takes, stage by stage, with the inputs and on-disk artifacts of each.
`convert` and `phase5` are separate commands you can run by hand; `batch` chains them for many books.
For the conceptual view see [how the merge works](../explanation/how-the-merge-works.md).

## Stage 1 — convert (`pdf2wiki convert`)

Input: one PDF. Output root: `<out_root>/<slug>/`.

1. **Pipeline base pass** — MinerU `-b pipeline -m txt` over the whole page range, in `seg`-page
   chunks. Byte-perfect code/text from the PDF's embedded text layer. This is the authoritative
   skeleton.
2. **Coverage gate** — any page with real text (>50 chars) but zero extracted blocks is a gap. A gap
   is a hard stop ([`CoverageError`](../explanation/how-the-merge-works.md#the-coverage-gate)), not a
   silent drop.
3. **Hybrid VLM passes** — MinerU `-b hybrid-engine --effort <effort>` on *rich* pages only (pages
   whose base blocks include tables, images, code, equations, or charts), grouped into contiguous runs
   capped at `maxrun` pages.
4. **Merge** — base-driven graft by page + bounding-box overlap (see
   [how the merge works](../explanation/how-the-merge-works.md)).
5. **Chapter normalize** — the PDF's level-1 bookmarks (ToC) correct chapter boundaries.
6. **Render + write** — one `.md`, an `images/` folder, and `blocks.json`.

Artifacts under `<out_root>/<slug>/`:

| Artifact | What it is |
|----------|------------|
| `<slug>.md` | The merged Markdown. |
| `images/` | Extracted figures; referenced as `images/<name>` from the Markdown. |
| `blocks.json` | The full merged block list (every block with type, page, bbox, provenance). |
| `base_<a>_<b>/`, `hy_<a>_<b>/` | Per-pass MinerU output dirs, each with a `.log` and a `.done` cache sentinel. |

The `.done` sentinels make convert resumable: a completed pass is reused, so a fixed re-run continues
past it instead of restarting. See [output layout](output-layout.md) for the full tree and the
code-verify markers.

## Stage 2 — phase5 (`pdf2wiki phase5`)

Input: the `<slug>.md` from stage 1. Runs the [six-step chain](phase5-steps.md) and writes chapter
files to `<md dir>/chapters/` (or `--out`). Dry-run by default; `--apply` writes.

## Stage 3 — batch orchestration (`pdf2wiki batch`)

`batch` runs, per book, `convert → fetch → phase5 (--apply) → optional vault placement`, sequentially
(single GPU). `fetch` is a no-op locally; in remote mode it `scp`s the `.md` and `images/` back. After
phase5, images are linked into `chapters/images/` so relative refs resolve, and — if `--vault` (or
`[output] vault`) is set — the chapters are copied to `<vault>/<domain>/<slug>/`.

### Batch manifest states

`batch` records one status per slug in `<stage>/manifest.json` (written atomically). On re-run, only a
`done` book is skipped; every other state retries.

| Status | Meaning |
|--------|---------|
| `convert_failed` | The conversion returned non-zero (a MinerU pass failed or the coverage gate hard-stopped). |
| `fetch_failed` | The converted `.md` could not be pulled back (remote scp failure). |
| `phase5_failed` | Post-processing raised. |
| `done` | Converted, post-processed, and (if configured) placed. Carries `domain`, `minutes`, and optionally `vault_path`. |

A single book's failure never aborts the run — the batch continues to the next book. See
[run a batch](../how-to/run-a-batch.md).
