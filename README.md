# pdf2wiki

Convert heavily technical books (native-text PDFs) into clean, chapter-split, **LLM-ready
Markdown** — code byte-perfect, tables intact, diagrams transcribed to Mermaid — suitable for an
Obsidian vault or any Markdown-native knowledge base.

Built on [MinerU](https://github.com/opendatalab/MinerU) with a dual-pass strategy validated on
real technical books:

- **pipeline pass** (`-m txt`): uses the PDF's embedded text layer → byte-perfect code listings.
  A VLM re-OCR of native text *hallucinates* tokens inside code (`.findFirst()` → `.Alzheimer()`);
  the text layer never does.
- **hybrid/VLM pass** (`--effort high`): reconstructs table grids correctly (the text stream
  can't recover grid geometry) and transcribes vector diagrams to Mermaid.
- **base-driven merge**: the pipeline output is authoritative; table grids, Mermaid blocks,
  equations and chart data are grafted in from the hybrid pass by bbox-IoU matching. Code blocks
  are token-verified against the pipeline text layer and flagged when the VLM diverged.

Then a five-step post-processing chain (**phase5**) polishes the result:

1. `caption_unbleed` — unwrap figure/listing captions MinerU trapped in code fences
2. `lang_retag` — fix unreliable code-fence language tags (precision-first heuristics)
3. `dash_normalize` — fix typographic dashes inside code (`–dev` → `--dev`)
4. `mermaid_repair` — sanitize VLM-transcribed Mermaid so it parses
5. `chapter_split` — split into per-chapter files with YAML frontmatter

## Status

**Alpha.** The phase5 chain, QA tooling, scan, and batch driver are functional. The dual-pass
converter module is landing next (being reconciled from its production deployment); until then,
`pdf2wiki convert` raises `NotImplementedError` — run phase5 on existing MinerU output.

## Requirements

- Linux (native or WSL2) with an NVIDIA GPU, **≥ 8 GB VRAM** (hybrid pass peaks ~9 GB on a
  12 GB card), CUDA driver installed
- Python ≥ 3.11
- [MinerU](https://github.com/opendatalab/MinerU) ≥ 3.4 installed and on `PATH` (or configured)
- vllm's Triton JIT needs a C compiler: `sudo apt install build-essential python3-dev`

Only the conversion needs the GPU — phase5/qa/scan run anywhere Python runs.

## Install

```bash
uv tool install pdf2wiki        # or: pip install pdf2wiki
```

## Usage

```bash
# convert one book (GPU machine)
pdf2wiki convert book.pdf --name my-book

# post-process converter output (dry-run first, then apply)
pdf2wiki phase5 out/my-book/my-book.md --book my-book
pdf2wiki phase5 out/my-book/my-book.md --book my-book --apply

# QA: sample 20 reproducible random pages to PNGs for manual back-checks
pdf2wiki qa sample book.pdf my-book

# scan a directory of PDFs -> title/year guesses (JSON)
pdf2wiki scan ~/books/

# batch: manifest-driven, resumable, sequential (single GPU)
pdf2wiki batch books.toml --vault ~/Obsidian/MyVault
```

### Remote mode

Have the GPU in another machine? Run the conversion over SSH and pull artifacts back:

```bash
pdf2wiki convert book.pdf --name my-book --remote user@gpu-host
pdf2wiki batch books.toml --remote user@gpu-host
```

Requirements: key-based SSH auth, pdf2wiki + MinerU installed on the remote host, and
`[remote].books_dir` set in the config (PDF paths in the manifest resolve against it).

### books.toml (batch manifest)

```toml
[[book]]
pdf = "Some_Technical_Book.pdf"
slug = "some-technical-book"
domain = "distributed-systems"   # optional subfolder in the vault
```

### Configuration

`./pdf2wiki.toml` (project) or `~/.config/pdf2wiki/config.toml` (user):

```toml
[mineru]
binary = ""                  # empty = discover on PATH
effort = "high"              # hybrid/VLM pass effort

[convert]
out_root = "~/pdf2wiki/out"
gap = 3                      # merge nearby rich pages into one hybrid run
seg = 40                     # pipeline segment size (pages)
maxrun = 25                  # cap a single hybrid run (pages)

[qa]
dpi = 140
seed = 42

[remote]
host = ""                    # ssh alias or user@host; empty = local
books_dir = ""               # remote directory holding the PDFs

[output]
vault = ""                   # optional final placement root
```

## Output layout

```
<out_root>/<slug>/
├── <slug>.md        merged markdown (input to phase5)
├── images/          extracted figures (relative refs from the md)
├── blocks.json      per-block records (for `qa review`)
└── chapters/        phase5 output: 00-front-matter.md, 01-….md, …, images/
```

Code blocks where the VLM diverged from the text layer carry
`<!-- ⚠ code-verify: … -->` HTML comments (invisible in rendered Markdown) so downstream
tooling can reconcile against the embedded pipeline-verbatim tokens.

## Design notes / gotchas encoded

- MinerU subprocesses run from a **clean working directory** — a helper script named after a
  Python stdlib module (`profile.py`, `inspect.py`, …) in MinerU's cwd gets imported by
  torch/vllm and breaks it cryptically.
- MinerU stderr is **never suppressed** — it is logged per pass so real tracebacks are readable.
- Batch mode checks connectivity **once up front** in remote mode — otherwise a dead SSH session
  fails every remaining book in minutes with misleading statuses.
- Batch is sequential by design: one GPU cannot run concurrent VLM passes.
- All md-mutating commands are dry-run by default; `--apply` writes. All fixers are idempotent.

## License

AGPL-3.0-or-later. This tool drives the MinerU CLI (AGPL-3.0) as an external process.
