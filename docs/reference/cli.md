# CLI reference

Every `pdf2wiki` command, flag, default, and exit code. For task-oriented walkthroughs see the
[how-to guides](../how-to/); for the config file see [configuration](configuration.md).

```
pdf2wiki [--config PATH] <command> ...
```

`--config PATH` points at an explicit config TOML. Without it, pdf2wiki reads
`./pdf2wiki.toml` then `~/.config/pdf2wiki/config.toml`, falling back to built-in defaults — see
[configuration](configuration.md).

**Dry-run convention:** mutating commands default to dry-run and require `--apply` to write. The
exceptions are `convert` and `qa`, whose purpose is to produce new artifacts in their own output
directories — they never modify existing files in place.

## `convert`

Convert one PDF into merged Markdown with the [dual-pass pipeline](../explanation/how-the-merge-works.md).

```
pdf2wiki convert <pdf> --name <slug> [--out DIR]
                       [--remote HOST | --hybrid-server-url URL | --mineru-cloud [--cloud-model MODEL]]
```

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `pdf` | yes | — | Path to the source PDF (local mode), or a filename under the remote `books_dir` when `--remote` is used. |
| `--name` | yes | — | Output slug; names the output folder and the `.md` file. |
| `--out` | no | `convert.out_root` (`~/pdf2wiki/out`) | Output root; the book lands in `<out>/<slug>/`. |
| `--remote` | no | `remote.host` from config | SSH host to run the *whole* conversion on (experimental — see [set up a remote GPU host](../how-to/set-up-remote-gpu.md)). |
| `--hybrid-server-url` | no | `mineru.hybrid_server_url` from config | Offload **only** the hybrid VLM pass to a BYO OpenAI-compatible MinerU server; the pipeline pass stays local (runs on CPU). Preserves `--effort` (Mermaid/chart transcription). See [offload the hybrid pass](../how-to/offload-hybrid-to-a-server.md). |
| `--mineru-cloud` | no | off | Convert via the fully-managed [mineru.net](https://mineru.net) Cloud — **no GPU, no local MinerU**, token only. Uploads the PDF to a third-party cloud. Needs the `cloud` extra. See [convert in the cloud](../how-to/convert-in-the-cloud.md). |
| `--cloud-model` | no | `mineru_cloud.model_version` (`pipeline`) | Cloud parse model, only with `--mineru-cloud`: `pipeline` (code-safe, flat indent) · `vlm` (indent/tables but corrupts code) · `MinerU-HTML` · `merge` (runs both `pipeline`+`vlm` in the cloud and splices locally = clean code **and** indent/tables, GPU-less; costs 2× quota). |

`--remote`, `--hybrid-server-url`, and `--mineru-cloud` are **mutually exclusive** convert strategies —
passing more than one exits with code `2` and a message naming the conflict rather than silently choosing.

Writes `<out>/<slug>/<slug>.md`, `images/`, and `blocks.json` — see [output layout](output-layout.md).
Exit code `0` on success, `1` on failure (a MinerU/cloud pass failed, or the [coverage gate](../explanation/how-the-merge-works.md#the-coverage-gate) hard-stopped), `2` on a mutually-exclusive-flag misuse.

## `phase5`

Run the six-step [post-processing chain](phase5-steps.md) on a converted `.md` and split it into
per-chapter files. **Dry-run by default** — pass `--apply` to write.

```
pdf2wiki phase5 <md> --book <slug> [--out DIR] [--source-name PDF] [--apply]
```

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `md` | yes | — | Path to the converted `.md`. |
| `--book` | yes | — | Book slug written into each chapter's frontmatter. |
| `--out` | no | `<md dir>/chapters` | Directory for the split chapter files. |
| `--source-name` | no | the `md` path | Original PDF filename for the frontmatter `source:` field (keeps staging paths out of frontmatter). |
| `--apply` | no | off (dry-run) | Write the transformed `.md` and chapter files. Without it, pdf2wiki reports what it would do and writes nothing. |

Prints a per-step report (unwrapped captions, retag count, dash/mermaid/unescape fixes, chapter
boundaries). Exit code `0`.

## `qa sample`

Sample random pages into a small PDF plus rendered PNGs, so you can convert just the sample and
back-check it. See [QA a conversion](../how-to/qa-a-conversion.md).

```
pdf2wiki qa sample <pdf> <name> [-n PAGES] [--seed SEED] [--dpi DPI] [--qa-root DIR]
```

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `pdf` | yes | — | Source PDF. |
| `name` | yes | — | QA run name (names the QA subfolder). |
| `-n`, `--pages` | no | `qa.pages` (`20`) | Number of pages to sample. |
| `--seed` | no | `qa.seed` (`42`) | RNG seed (reproducible sampling). |
| `--dpi` | no | `qa.dpi` (`140`) | PNG render resolution. |
| `--qa-root` | no | `qa.root` (`~/pdf2wiki/qa`) | QA output root. |

Pages are drawn from the middle 5–95% of the book to skip front/back matter. Writes
`<qa-root>/<name>/<name>_sample.pdf`, `pages/*.png`, and `mapping.json`.

## `qa review`

Build a per-page `review.txt` from a converted sample's `blocks.json`, aligned with the sample PNGs.

```
pdf2wiki qa review <qa_dir> <name> [--blocks PATH]
```

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `qa_dir` | yes | — | The QA run directory (from `qa sample`). |
| `name` | yes | — | QA run name. |
| `--blocks` | no | `<qa_dir>/out/<name>_sample/blocks.json` | Explicit `blocks.json` path. |

Writes `<qa_dir>/review.txt`.

## `scan`

Scan a directory of PDFs and print title/year guesses as JSON — a triage aid, not ground truth.

```
pdf2wiki scan <directory>
```

Prints a JSON array, one record per PDF: `{file, pages, title, title_conf, year, year_conf}`. The
`*_conf` fields report how each guess was derived (e.g. `text`, `filename-fallback`, `copyright-line`,
`loose-year`, `none-found`).

## `batch`

Convert many books from a manifest, resumably. See [run a batch](../how-to/run-a-batch.md).

```
pdf2wiki batch <books.toml> [--stage DIR] [--remote HOST] [--max-books N] [--only SLUG] [--vault DIR]
```

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `books` | yes | — | Books TOML with `[[book]]` entries (`pdf`, `slug`, optional `domain`). |
| `--stage` | no | `~/pdf2wiki/stage` | Staging dir; also holds the resume `manifest.json` and the `STOP` file. |
| `--remote` | no | `remote.host` from config | SSH host to convert on. |
| `--max-books` | no | unlimited | Stop after this many books *attempted* this run. |
| `--only` | no | — | Run only this slug. |
| `--vault` | no | `output.vault` from config | Final placement root; chapters copy to `<vault>/<domain>/<slug>/`. |

Runs `convert → fetch → phase5 → optional vault placement` per book, sequentially. Resumable: only a
book with status `done` is skipped on re-run; any failed book retries. Drop a file named `STOP` in the
stage dir to halt cleanly between books. See [manifest states](pipeline-stages.md#batch-manifest-states).
