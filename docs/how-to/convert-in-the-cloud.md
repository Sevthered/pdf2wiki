# Convert in the cloud (no GPU, no MinerU)

> **Experimental — mind the code fidelity.** An A/B test (2026-07-22) showed the cloud **`vlm`** model
> **corrupts code** (the Qwen2-VL model drifts into Chinese tokens on ambiguous code OCR, e.g.
> `orElseThrow` → `response二等奖Throw`, `findFirst` → `找到了`). The **`pipeline`** model (default) uses
> the text layer and keeps code byte-clean, but **flattens indentation**. Neither cloud model matches the
> local dual-pass converter (clean code *and* indentation). Prefer the local converter for code-heavy
> books; use this for no-GPU one-offs.

`--mineru-cloud` converts a PDF with **zero local setup** — no GPU, no MinerU install, no server. It
uploads the PDF to the fully-managed [mineru.net](https://mineru.net) Precision API, waits for the
result, and lays it out exactly like the local converter (`<out>/<slug>/<slug>.md` + `images/`), so
`phase5` consumes it unchanged.

> **⚠ Data egress.** This sends your PDF to a third-party cloud (OpenDataLab, CN-hosted). Do **not** use
> it for material you cannot send offsite. The command logs the upload loudly every run.

## Requirements

- The `cloud` extra: `pip install 'pdf2wiki[cloud]'` (adds `requests`).
- A mineru.net API token from <https://mineru.net/apiManage/token>. Provide it **without committing it**:
  - env: `export MINERU_API_TOKEN=...`, or
  - `[mineru_cloud].token_file = "~/.mineru_net_token"` (a file you keep out of version control), or
  - `[mineru_cloud].token` in a local (gitignored) config.

## Convert

```bash
export MINERU_API_TOKEN=...        # or use token_file / config
pdf2wiki convert book.pdf --name my-book --mineru-cloud
```

Pick the parsing model with `--cloud-model` (default `pipeline`):

```bash
pdf2wiki convert book.pdf --name my-book --mineru-cloud --cloud-model vlm
```

- **`pipeline`** (default) — text-layer extraction. **Byte-clean code**, but **flat** indentation.
- **`vlm`** — MinerU2.5 VLM. Preserves indentation + adds tables/Mermaid, but **corrupts code** (Chinese-
  token drift — see the warning above). Use only for figure/table-heavy PDFs where code fidelity is moot.

`--mineru-cloud` is mutually exclusive with `--remote` and `--hybrid-server-url` (it runs the *whole*
conversion in the cloud) — passing them together exits with an error.

## Config

```toml
[mineru_cloud]
token_file = "~/.mineru_net_token"   # keep the token out of VCS
model_version = "pipeline"           # pipeline (code-safe) | vlm (corrupts code) | MinerU-HTML
language = "en"                      # mineru.net defaults to "ch"
extra_formats = ["latex"]            # optional; e.g. LaTeX for formula-heavy books
```

## Limits & behaviour

- **≤ 200 pages per file** (mineru.net Precision limit). Larger books must be split first — the command
  fails fast with a clear message rather than silently truncating. **1000 pages/day** at top priority.
- **Fail fast, loud.** Any API error (bad token, oversized file, parse failure, unreachable) aborts
  naming the cause; there is no silent fallback to a local converter.
- The token is read from config/env/file and is **never logged or written to disk** by pdf2wiki.

## When to prefer the local converter

The local dual-pass converter ([convert a book](convert-a-book.md)) keeps PDFs on-prem, has no page cap
or daily quota, and its code/table fidelity is production-validated. Reach for `--mineru-cloud` only when
you have no GPU and the material is safe to send to the cloud.
