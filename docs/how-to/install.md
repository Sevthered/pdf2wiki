# Install pdf2wiki

## Prerequisites

- **Python ≥ 3.11** (always).

The rest depends on **how you convert**. Local conversion needs a GPU + MinerU; the offload and cloud
paths need neither:

| Convert mode | GPU | Local MinerU | Extra requirement |
|---|---|---|---|
| local (default), `--remote` | yes (host side) | yes | `build-essential` (below) |
| `--hybrid-server-url` | no (client) | yes (pipeline runs on CPU) | a reachable MinerU server |
| `--mineru-cloud` (incl. `--cloud-model merge`) | **no** | **no** | the `cloud` extra + a mineru.net token |

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

For the **cloud** converter (`--mineru-cloud`), install the `cloud` extra (adds `requests`):

```bash
pip install 'pdf2wiki[cloud]'      # or: uv tool install 'pdf2wiki[cloud]'
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
