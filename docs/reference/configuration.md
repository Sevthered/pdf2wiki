# Configuration reference

pdf2wiki reads an optional TOML config file. Every field has a built-in default, so a config file is
optional — you only set what you want to change.

## Resolution order

pdf2wiki layers configuration from lowest to highest precedence:

1. Built-in dataclass defaults (documented below).
2. User config: `~/.config/pdf2wiki/config.toml`.
3. Project config: `./pdf2wiki.toml` (current directory) — overrides the user config.
4. `--config PATH` — when given, it is the *only* file read (skips 2 and 3).

Unknown keys are ignored. Missing files are skipped.

## Example

```toml
[mineru]
model_source = "huggingface"
effort = "high"

[convert]
out_root = "~/pdf2wiki/out"
timeout = 7200
seg = 40
maxrun = 25

[qa]
pages = 20
dpi = 140

[remote]
host = "gpu-box"
books_dir = "/mnt/d/Books"

[output]
vault = "~/Obsidian/MyVault"
```

## `[mineru]`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `binary` | string | `""` | Path to the `mineru` executable. Empty means discover `mineru` on `PATH`. |
| `model_source` | string | `"huggingface"` | Sets `MINERU_MODEL_SOURCE` for the MinerU subprocess. |
| `effort` | string | `"high"` | Hybrid/VLM effort. `high` enables image/chart/diagram analysis. |
| `hybrid_server_url` | string | `""` | Offload the hybrid VLM pass to this OpenAI-compatible MinerU server (`hybrid-http-client -u URL`); the pipeline pass stays local. Empty = local hybrid. Set by `--hybrid-server-url`. See [offload the hybrid pass](../how-to/offload-hybrid-to-a-server.md). |

## `[convert]`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `out_root` | string | `"~/pdf2wiki/out"` | Root for converted output; a book lands in `<out_root>/<slug>/`. |
| `workdir` | string | `"~/.pdf2wiki/run"` | Clean working directory for MinerU subprocesses (avoids stdlib-shadow crashes — see [design principles](../explanation/design-principles.md)). |
| `timeout` | int (s) | `7200` | Timeout per MinerU pass in local mode. |
| `gap` | int (pages) | `3` | Merge rich pages into one hybrid run if the gap between them is ≤ this. |
| `seg` | int (pages) | `40` | Pipeline segment size; the base pass runs in chunks of this many pages. |
| `maxrun` | int (pages) | `25` | Cap on the length of a single hybrid run (bounds VRAM). |
| `tiny_px2` | int (px²) | `2500` | Caption-less images smaller than this are dropped as decorative noise. |

## `[qa]`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `root` | string | `"~/pdf2wiki/qa"` | QA output root. |
| `dpi` | int | `140` | Page-render resolution for sample PNGs. |
| `seed` | int | `42` | RNG seed for reproducible page sampling. |
| `pages` | int | `20` | Default number of pages to sample. |

## `[remote]`

Experimental — SSH-driven remote conversion. See [set up a remote GPU host](../how-to/set-up-remote-gpu.md).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `host` | string | `""` | SSH host (e.g. `user@gpu-box` or a `~/.ssh/config` alias). Empty means local execution. |
| `books_dir` | string | `""` | Directory on the remote host that holds the source PDFs. |
| `workdir` | string | `"~/pdf2wiki-remote"` | Remote working directory (holds `logs/`). |
| `connect_timeout` | int (s) | `8` | SSH connect timeout for the one-time connectivity check. |
| `convert_timeout` | int (s) | `7200` | Timeout for a remote conversion. |

## `[mineru_cloud]`

Fully-managed [mineru.net](https://mineru.net) Cloud conversion (`--mineru-cloud`) — no GPU, no local
MinerU. **⚠ Uploads the PDF to a third-party cloud (OpenDataLab, CN-hosted); do not use for material you
cannot send offsite.** Needs the `cloud` extra (`pip install 'pdf2wiki[cloud]'`). See
[convert in the cloud](../how-to/convert-in-the-cloud.md).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `token` | string | `""` | Bearer token. Empty → falls back to env `MINERU_API_TOKEN`, then `token_file`. **Prefer env/file so the token never lands in a committed config.** |
| `token_file` | string | `""` | Path to a file holding the token (e.g. `~/.mineru_net_token`), kept out of VCS. |
| `base_url` | string | `"https://mineru.net/api/v4"` | Precision API base URL. |
| `model_version` | string | `"pipeline"` | Default cloud model when `--cloud-model` is not given: `pipeline` (code-safe, flat indent) · `vlm` (indent/tables, corrupts code) · `MinerU-HTML`. (`merge` is a CLI-only pseudo-model, not a config value.) |
| `language` | string | `"en"` | OCR language hint (mineru.net defaults to `ch`). |
| `extra_formats` | list | `[]` | Extra output formats to request, e.g. `["latex"]` for formula-heavy books. |
| `poll_timeout` | int (s) | `1800` | How long to wait for a cloud task before failing. |
| `max_pages` | int | `200` | Per-file page cap (mineru.net Precision limit); larger PDFs fail fast rather than truncate. |

## `[output]`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `vault` | string | `""` | Optional final placement root (e.g. an Obsidian vault). When set, `batch` copies each book's chapters to `<vault>/<domain>/<slug>/`. |

## Environment

pdf2wiki sets `MINERU_MODEL_SOURCE` (from `[mineru] model_source`) for the MinerU subprocess and
otherwise inherits your environment. There is no environment-variable override layer for the config
fields above — use a config file or CLI flags.

One exception: **`MINERU_API_TOKEN`** is read for `--mineru-cloud` when `[mineru_cloud] token` is empty
(precedence: config `token` → env `MINERU_API_TOKEN` → `token_file`). The token is never logged or written
to disk by pdf2wiki.
