# Offload the hybrid pass to a MinerU server

> **Experimental.** Validated end-to-end (a GPU-less Linux client over an SSH tunnel produced
> byte-identical output to a local run), but not yet broadly exercised. Prefer local mode for
> production until this note is lifted.

pdf2wiki runs two MinerU passes: a **pipeline** pass (the byte-perfect code/text skeleton, CPU-capable)
and a **hybrid** VLM pass (tables, Mermaid, LaTeX, charts — GPU-heavy). `--hybrid-server-url` sends
**only the hybrid pass** to a remote OpenAI-compatible MinerU server; the pipeline pass stays local. A
machine with no usable GPU can convert by offloading just the heavy half.

This is a different mode from [`--remote`](set-up-remote-gpu.md), which runs the **whole** conversion on
a GPU host over SSH. The two are mutually exclusive — passing both exits with an error.

## When to use which

| | `--hybrid-server-url` | `--remote` |
|---|---|---|
| Where the pipeline pass runs | **locally** (CPU ok) | on the GPU host |
| Where the hybrid pass runs | remote server (VLM only) | on the GPU host |
| Client needs MinerU installed | **yes** (for the pipeline pass) | no (thin SSH client) |
| Server it talks to | any OpenAI-compatible MinerU server | a full pdf2wiki+MinerU host |
| PDF location | local | on the remote host |

## Requirements

- **Client:** MinerU on `PATH` for the pipeline pass — the lightweight extra is enough, no local vLLM:
  `uv pip install "mineru[core]"`. Force CPU for the pipeline pass on a GPU-less (or small-GPU) box:
  `export MINERU_DEVICE_MODE=cpu`.
- **Server (BYO):** any OpenAI-compatible endpoint serving a MinerU2.5 VLM. pdf2wiki owns no server
  lifecycle — you start it (see below).
- Network reachability from client to server (see [Security](#security-no-auth) — an SSH tunnel is the
  recommended path).

## Start a server (BYO)

On the GPU host, MinerU ships an OpenAI-compatible server:

```bash
mineru-openai-server            # serves MinerU2.5 on 0.0.0.0:30000 (vLLM under the hood)
```

Or run vLLM directly:

```bash
vllm serve opendatalab/MinerU2.5-2509-1.2B \
  --port 30000 \
  --logits-processors mineru_vl_utils:MinerULogitsProcessor
```

Verify it: `curl http://localhost:30000/v1/models` returns a model list (HTTP 200).

> **Gotcha — FastAPI too new for vLLM.** On vLLM 0.20.2, FastAPI ≥ 0.139 breaks every server route with
> `'_IncludedRouter' object has no attribute 'path'` (all requests 500). Pin a compatible FastAPI in the
> server's environment: `uv pip install "fastapi==0.115.6"`, then restart. This affects only the server;
> the local pipeline pass never imports FastAPI.

## Convert

```bash
export MINERU_DEVICE_MODE=cpu          # GPU-less client: run the pipeline pass on CPU
pdf2wiki convert book.pdf --name my-book --hybrid-server-url http://gpu-host:30000
```

The pipeline pass runs locally; the hybrid pass calls the server (`hybrid-http-client -u <url>`). MinerU
appends the OpenAI path itself — pass the **base** URL (`http://host:30000`), not `/v1/...`. `--effort`
and image analysis are preserved, so Mermaid and chart transcription still work.

You can also set it in [config](../reference/configuration.md) instead of the flag:

```toml
[mineru]
hybrid_server_url = "http://gpu-host:30000"
```

## Security (no auth)

The MVP sends no credentials — MinerU's CLI has no `--api-key`. **Do not expose the server on an
untrusted network.** The recommended pattern is an **SSH tunnel**, so nothing binds on the LAN:

```bash
# on the client: forward localhost:30000 to the server's 30000 over SSH
ssh -fN -L 30000:localhost:30000 gpu-host
pdf2wiki convert book.pdf --name my-book --hybrid-server-url http://localhost:30000
```

Otherwise front the server with a reverse proxy that adds auth, on a trusted network only.

## If the server is unreachable

The hybrid pass **fails fast and loud**, naming the server and page range, and does **not** silently fall
back to local hybrid (which would need the GPU you offloaded) or to pipeline-only (which would drop
tables, diagrams, and Mermaid). Completed passes are cached under the output dir (`.done` sentinels), so
once the server is back, re-run and it resumes straight to the hybrid pass — no pipeline re-run.
