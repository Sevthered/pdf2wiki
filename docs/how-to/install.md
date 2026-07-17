# Install pdf2wiki

## Prerequisites

- **Linux or WSL2** with an **NVIDIA GPU, ≥8 GB VRAM** (only conversion needs the GPU).
- **Python ≥ 3.11**.
- **[MinerU](https://github.com/opendatalab/MinerU) ≥ 3.4** on your `PATH`. pdf2wiki drives the
  `mineru` CLI as a subprocess.
- **`build-essential`** (gcc + `python3-dev`). MinerU's vLLM backend JIT-compiles CUDA kernels at
  startup and needs a C compiler:
  ```bash
  sudo apt install build-essential python3-dev
  ```

## Install the tool

With [uv](https://docs.astral.sh/uv/):

```bash
uv tool install pdf2wiki
```

Or with pip:

```bash
pip install pdf2wiki
```

## Verify

```bash
pdf2wiki --help
mineru --version    # must resolve on PATH
```

If `pdf2wiki convert` later reports that `mineru` was not found, either put it on your `PATH` or set
`[mineru] binary` in your [config](../reference/configuration.md).

## Next

- Convert one book end-to-end: the [tutorial](../tutorials/convert-your-first-book.md).
- Convert on a separate GPU box: [set up a remote GPU host](set-up-remote-gpu.md).
