# Convert in the cloud (no GPU, no MinerU)

> **Code fidelity — use `--cloud-model merge`.** An A/B test showed the single cloud **`vlm`** model
> **corrupts code** (Qwen2-VL drifts into Chinese tokens on ambiguous code OCR, e.g. `orElseThrow` →
> `response二等奖Throw`, `findFirst` → `找到了`). The **`pipeline`** model keeps code byte-clean but
> **flattens indentation**. The **`merge`** model runs *both* cloud passes and splices them locally with
> pdf2wiki's own base-driven merge — **byte-clean code AND correct indentation/tables/Mermaid**, matching
> the local dual-pass converter, still GPU-less. Prefer `merge` for code-heavy books.

`--mineru-cloud` converts a PDF with **zero local setup** — no GPU, no MinerU install, no server. It
uploads the PDF to the fully-managed [mineru.net](https://mineru.net) Precision API, waits for the
result, and lays it out exactly like the local converter (`<out>/<slug>/<slug>.md` + `images/`), so
`phase5` consumes it unchanged.

> **⚠ Data egress.** This sends your PDF to a third-party cloud (OpenDataLab, CN-hosted). Do **not** use
> it for material you cannot send offsite. The command logs the upload loudly every run.

## Data usage & privacy — read before uploading

Using `--mineru-cloud` uploads your **entire source PDF** to servers operated by **OpenDataLab** (a
[Shanghai AI Laboratory](https://opendatalab.com) project; infrastructure is China-hosted). pdf2wiki is
an unaffiliated client — it does not control, and cannot speak for, what mineru.net does with your files.

**What we could verify (as of 2026-07, from the official site/docs):**

- mineru.net publishes a **User Service Agreement (用户服务协议)** and a **Privacy Policy (隐私政策)**,
  linked in the footer of <https://mineru.net> — but **only in Chinese**, and their machine-readable text
  is not publicly indexed. **You are responsible for reading them before uploading anything.**
- The API docs state only operational facts: an upload link is valid for **24 hours**, and there are
  per-file/size and daily quotas (see below). We found **no public English statement** about **how long
  uploaded files are retained, whether they are deleted after parsing, or whether they may be used to
  train models.** **Do not assume** uploads are deleted or excluded from training — the policy is silent
  where we can read it.
- For specifics beyond the published policy, OpenDataLab's listed contact is `OpenDataLab@pjlab.org.cn`.

**Practical guidance:**

- **Copyrighted books, licensed material, confidential or personal documents → do not use this path.**
  Uploading may breach the material's license or your obligations, independent of mineru.net's own terms.
  Use the [local converter](convert-a-book.md), a [remote GPU host](set-up-remote-gpu.md), or
  [offload only the hybrid pass](offload-hybrid-to-a-server.md) to a server you control — all keep the PDF
  on hardware you own.
- Reserve `--mineru-cloud` for **public or self-owned, non-sensitive PDFs** where sending a copy offsite
  is acceptable to you.
- This is a **per-book, explicit** decision. Never wire `--mineru-cloud` into an unattended batch over a
  corpus you have not individually cleared for egress.

*This section summarizes what pdf2wiki's maintainers could independently confirm; it is not legal advice
and is not a statement on OpenDataLab's behalf. Their published policy is the authority — verify it
yourself, as terms may have changed since this was written.*

## Requirements

- pdf2wiki itself (`pip install pdf2wiki`) — the cloud converter ships with the base package, no extra.
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
pdf2wiki convert book.pdf --name my-book --mineru-cloud --cloud-model merge   # best fidelity
```

- **`merge`** — **recommended.** Runs *both* `pipeline` and `vlm` in the cloud (two API calls) and
  splices them with pdf2wiki's local base-driven merge: pipeline supplies byte-clean code tokens, vlm
  supplies indentation + tables + Mermaid. Matches the local dual-pass converter, GPU-less. Costs **2×**
  the daily page quota and 2× egress.
- **`pipeline`** (default) — one pass, text-layer extraction. **Byte-clean code**, but **flat** indentation.
- **`vlm`** — one pass, MinerU2.5 VLM. Preserves indentation + adds tables/Mermaid, but **corrupts code**
  (Chinese-token drift — see the warning above). Use only for figure/table-heavy PDFs where code is moot.

`--mineru-cloud` is mutually exclusive with `--remote` and `--hybrid-server-url` (it runs the *whole*
conversion in the cloud) — passing them together exits with an error.

### How `merge` works

`merge` submits the PDF twice (`model_version=pipeline` and `model_version=vlm`), pulls back each pass's
`content_list.json`, and feeds both into the same base-driven merge the local converter uses — blocks are
matched by page + bbox-IoU, code takes pipeline tokens (re-indented from vlm), tables/diagrams take the
vlm grid/Mermaid. The PDF's own ToC still drives chapter normalization (read locally). Output is identical
in shape to every other path (`<slug>.md` + `blocks.json` + `images/`), phase5-ready.

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
- **`merge` costs 2×** — it submits the PDF twice (`pipeline` + `vlm`), so it burns 2× the daily page
  quota and doubles egress. Budget accordingly on large books.
- **Cloud output is not byte-identical to the local converter.** mineru.net runs its own (evolving)
  MinerU version, so block boundaries and a few merge decisions differ from an on-box run. `merge` keeps
  code *clean* (pipeline tokens win), which is what matters, but don't expect a bit-for-bit match.
- **Math not yet validated on this path.** The `equation` LaTeX field has not been fidelity-checked
  through the cloud; for formula-heavy books try `extra_formats = ["latex"]` and **verify the output**.
- **No automatic chunking.** Books over the per-file page cap must be split by hand before uploading.

## When to prefer the local converter

The local dual-pass converter ([convert a book](convert-a-book.md)) keeps PDFs on-prem, has no page cap
or daily quota, and its code/table fidelity is production-validated. Reach for `--mineru-cloud` only when
you have no GPU and the material is safe to send to the cloud.
