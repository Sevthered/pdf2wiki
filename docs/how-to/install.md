# Install pdf2wiki

## Prerequisites

- **Python ≥ 3.11** (always).

The rest depends on **how you convert**. Local conversion needs a GPU + MinerU. The offload and cloud
paths need neither:

| Convert mode | GPU | Local MinerU | Extra requirement |
|---|---|---|---|
| local (default), `--remote` | yes (host side) | yes | `build-essential` (below) |
| `--hybrid-server-url` | no (client) | yes (pipeline runs on CPU) | a reachable MinerU server |
| `--mineru-cloud` (incl. `--cloud-model merge`) | **no** | **no** | a mineru.net token |

For **local / `--remote`** conversion you also need:

- **Linux or WSL2** with an **NVIDIA GPU, ≥8 GB VRAM** (only conversion needs the GPU).
- **[MinerU](https://github.com/opendatalab/MinerU) ≥ 3.4** on your `PATH`. pdf2wiki drives the
  `mineru` CLI as a subprocess.
- **`build-essential`** (gcc + `python3-dev`). MinerU's vLLM backend JIT-compiles CUDA kernels at
  startup and needs a C compiler:
  ```bash
  sudo apt install build-essential python3-dev
  ```

`phase5`, `qa`, and `scan` run anywhere Python runs — no GPU or MinerU.

## Install the tool

With [uv](https://docs.astral.sh/uv/):

```bash
uv tool install pdf2wiki
```

Or with pip:

```bash
pip install pdf2wiki
```

That single install includes the cloud converter (`--mineru-cloud`) — no extra needed.

## Build from source

pdf2wiki is a **pure-Python** package built with [hatchling](https://hatch.pypa.io/latest/). The build
compiles nothing and needs no GPU, no MinerU and no C toolchain. (The `build-essential` requirement
above belongs to MinerU's vLLM backend at *conversion* time, not to the pdf2wiki build.)

```bash
git clone https://github.com/Sevthered/pdf2wiki.git
cd pdf2wiki
uv build                    # writes dist/pdf2wiki-<version>-py3-none-any.whl and the .tar.gz sdist
uv pip install dist/pdf2wiki-*.whl
```

`uv build` produces both artifacts and builds the wheel **from the sdist**, so it also proves the sdist is
self-contained. Without `uv`, the equivalent is:

```bash
python -m pip install build
python -m build             # same two artifacts in dist/
python -m pip install dist/pdf2wiki-*.whl
```

To work on the code rather than package it, install the dev environment and run the gate. These are the
same checks CI runs, in the same order (`.github/workflows/ci.yml`):

```bash
uv sync --group dev         # --group dev is uv's default here; plain `uv sync` is equivalent
uv run ruff check .
uv run ruff format --check .
uv run reuse lint           # every file carries SPDX copyright + license info
uv run mypy                 # strict
uv run pytest -q --cov=pdf2wiki --cov-report=term-missing
```

Ask the **installed package** for its version, not the package manager. An editable install's
`dist-info` records the version at install time, and it goes stale as the source moves:

```bash
python -c "import pdf2wiki; print(pdf2wiki.__version__)"
```

Note that `pdf2wiki --version` is not a flag. Use `pdf2wiki --help` instead.

## Verify

```bash
pdf2wiki --help
mineru --version    # must resolve on PATH
```

If `pdf2wiki convert` later reports that `mineru` was not found, either put it on your `PATH` or set
`[mineru] binary` in your [config](../reference/configuration.md).

## Next

- Convert one book end-to-end: the [tutorial](../tutorials/convert-your-first-book.md).
- Convert on a separate GPU box: [configure a remote GPU host](set-up-remote-gpu.md).
