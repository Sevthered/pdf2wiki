# Set up a remote GPU host

> **Experimental.** Remote mode works but has no full public end-to-end validation yet. For production
> use, prefer local mode until this note is lifted.

Run pdf2wiki on a machine without a GPU and offload conversion to a GPU box over SSH. pdf2wiki runs
`pdf2wiki convert` on the remote host and pulls the artifacts back with `scp`.

## Requirements

- The GPU host meets the [conversion prerequisites](install.md#prerequisites) (NVIDIA GPU, MinerU on
  `PATH`, `build-essential`) and has **pdf2wiki installed**.
- **Key-based SSH** from your machine to the host — no password prompts (a batch cannot answer them).
  Test it: `ssh <host> echo ok`.
- The source PDFs live in a directory on the **remote** host.

## Configure

Add a `[remote]` section to your [config](../reference/configuration.md):

```toml
[remote]
host = "gpu-box"                 # or user@host, or a ~/.ssh/config alias
books_dir = "/mnt/d/Books"       # where the PDFs live on the remote host
workdir = "~/pdf2wiki-remote"    # remote scratch (holds logs/)
```

## Convert remotely

Point `--remote` at the host (or rely on `[remote] host`). In remote mode the `pdf` argument is a
**filename under `books_dir`**, not a local path:

```bash
pdf2wiki convert my-book.pdf --name my-book --remote gpu-box
```

pdf2wiki checks the SSH connection once, runs the conversion on the host (logging to
`<workdir>/logs/<slug>.log`), and reports success from the remote command's exit code. For a batch,
add `--remote` to `pdf2wiki batch`; it fetches each book's `.md` and `images/` back to the stage dir.

## How success is judged

pdf2wiki trusts the remote **exit code**, never the log text — a technical book's own content is full
of words like "error" and "failed". If a book fails, read its remote log
(`<workdir>/logs/<slug>.log`).

## Troubleshooting

- **Connectivity check fails** — see [troubleshooting](troubleshoot.md#ssh-connectivity-check-fails).
- A mid-run SSH drop does not necessarily kill a detached remote job; on reconnect, check before
  assuming the work was lost.
