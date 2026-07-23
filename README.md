# pdf2wiki

[![PyPI](https://img.shields.io/pypi/v/pdf2wiki)](https://pypi.org/project/pdf2wiki/)
[![Python](https://img.shields.io/pypi/pyversions/pdf2wiki)](https://pypi.org/project/pdf2wiki/)
[![License: AGPL-3.0](https://img.shields.io/pypi/l/pdf2wiki)](LICENSE)

Convert heavily technical books (native-text PDFs) into clean, chapter-split, **LLM-ready Markdown** —
code byte-perfect, tables intact, diagrams transcribed to Mermaid — suitable for an Obsidian vault or
any Markdown-native knowledge base.

Built on [MinerU](https://github.com/opendatalab/MinerU) with a **dual-pass strategy**: a pipeline pass
(`-m txt`) takes byte-perfect code and text from the PDF's embedded text layer, a hybrid/VLM pass
(`--effort high`) reconstructs table grids and transcribes diagrams to Mermaid, and a base-driven merge
grafts the good parts together — token-verifying code so a hallucinating VLM never corrupts a listing.
A six-step post-processing chain then cleans and splits the result into per-chapter files.

Why two backends instead of one: [why a dual-backend pipeline](docs/explanation/why-dual-backend.md).

## Requirements

- Linux (native or WSL2) with an NVIDIA GPU, **≥ 8 GB VRAM**, CUDA driver installed
- Python ≥ 3.11
- [MinerU](https://github.com/opendatalab/MinerU) ≥ 3.4 on `PATH`
- A C compiler for vLLM's Triton JIT: `sudo apt install build-essential python3-dev`

Only the conversion needs the GPU — `phase5`, `qa`, and `scan` run anywhere Python runs. No GPU at all?
[offload the hybrid pass to a server](docs/how-to/offload-hybrid-to-a-server.md) (pipeline local on CPU,
VLM pass remote), use a [remote GPU](docs/how-to/set-up-remote-gpu.md), or — with no local setup at all —
[convert in the cloud](docs/how-to/convert-in-the-cloud.md) via the managed mineru.net API.

## Install

```bash
uv tool install pdf2wiki        # or: pip install pdf2wiki
```

Full steps: [install pdf2wiki](docs/how-to/install.md). The install includes every converter, cloud
included — no separate extra.

## Quickstart

```bash
# 1. convert one book  ->  out/my-book/my-book.md + images/ + blocks.json
pdf2wiki convert book.pdf --name my-book

# 2. preview the cleanup + chapter split (dry-run)
pdf2wiki phase5 out/my-book/my-book.md --book my-book

# 3. apply it  ->  out/my-book/chapters/00-front-matter.md, 01-….md, …
pdf2wiki phase5 out/my-book/my-book.md --book my-book --source-name book.pdf --apply
```

New here? Follow the guided [tutorial: convert your first book](docs/tutorials/convert-your-first-book.md).

## Query the vault: the `llm-wiki` plugin

pdf2wiki *builds* a knowledge vault; the bundled **`llm-wiki`** Claude Code plugin *reads* one — so
Claude can consult it while you plan, and review your code against it, always citing the exact
`[[Page-Name]]`. It's the "LLM Wiki" pattern (an alternative to RAG/embeddings): plain Markdown read
just-in-time, with coverage discovered from the vault itself. Standalone (works with any vault in the
shape pdf2wiki produces) and **MIT-licensed**.

```bash
claude plugin marketplace add https://github.com/Sevthered/pdf2wiki
claude plugin install llm-wiki@pdf2wiki
```

Query-side (consult + review) ships now; ingest-side is a later release. Details:
[`plugin/`](plugin/) · [llm-wiki documentation](docs/llm-wiki/).

## Documentation

Full docs live in [`docs/`](docs/), organized by intent ([Diátaxis](https://diataxis.fr/)):

- **Tutorials** — [convert your first book](docs/tutorials/convert-your-first-book.md)
- **How-to** — [convert](docs/how-to/convert-a-book.md) · [post-process & split](docs/how-to/post-process-and-split.md) · [batch](docs/how-to/run-a-batch.md) · [QA](docs/how-to/qa-a-conversion.md) · [remote GPU](docs/how-to/set-up-remote-gpu.md) · [offload hybrid to a server](docs/how-to/offload-hybrid-to-a-server.md) · [convert in the cloud](docs/how-to/convert-in-the-cloud.md) · [troubleshoot](docs/how-to/troubleshoot.md)
- **Reference** — [CLI](docs/reference/cli.md) · [configuration](docs/reference/configuration.md) · [pipeline stages](docs/reference/pipeline-stages.md) · [phase 5 steps](docs/reference/phase5-steps.md) · [output layout](docs/reference/output-layout.md)
- **Explanation** — [why dual-backend](docs/explanation/why-dual-backend.md) · [how the merge works](docs/explanation/how-the-merge-works.md) · [design principles](docs/explanation/design-principles.md)
- **Architecture** — [overview with C4 diagrams](docs/architecture/architecture.md)
- **Plugin** — [llm-wiki (query/review a vault)](docs/llm-wiki/)

## Status

**Alpha.** All stages are functional; the converter was ported from a production deployment validated
on several full technical books, and the coverage gate hard-stops rather than silently dropping
content. Remote mode is **experimental** — no full public end-to-end run yet; prefer local mode.

## License

AGPL-3.0-or-later for the converter. This tool drives the MinerU CLI (AGPL-3.0) as an external process.
The bundled `plugin/` (the `llm-wiki` Claude Code plugin) is **MIT**-licensed — see [`plugin/LICENSE`](plugin/LICENSE).
