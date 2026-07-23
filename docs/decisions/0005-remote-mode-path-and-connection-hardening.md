# 0005. Remote-mode hardening: absolute MinerU paths + SSH keepalive

- Status: accepted
- Date: 2026-07-23 (recorded retrospectively)
- Deciders: Sevthered (maintainer)

## Context and Problem Statement

Remote mode (`--remote`, driving a GPU box over SSH) shipped as *experimental*. The first real end-to-end
remote runs surfaced two failures that unit tests could not — both about the boundary between pdf2wiki's
process and the machinery it drives:

1. **Output vanished.** A remote convert reported `no content_list.json` even though MinerU ran fine. Root
   cause: `run_mineru` handed MinerU a **relative `-o`/`-p`**, but MinerU runs with a *different* working
   directory (`clean_cwd`, the stdlib-shadow-safe dir — see [design principles](../explanation/design-principles.md)),
   so its output landed where pdf2wiki did not look. Local mode was unaffected (its `out_root` is already
   `expanduser`-ed to an absolute path); remote passes a home-relative `--out`.
2. **Long converts were mislabelled failed.** On a full 354-page book the Mac↔box SSH control channel
   dropped mid-convert (the channel is silent for minutes while MinerU logs to a remote file; a NAT/idle
   timeout, common with WSL2 mirrored networking, killed it). The batch then marked a *still-running*
   convert as failed while the remote job orphaned and finished.

## Considered Options

- **(1)** patch each relative path at the call sites · **absolutize the paths handed to MinerU** at the one
  boundary that crosses into a different-cwd process.
- **(2)** wrap converts in a retry/reconnect loop · **keep the SSH control channel alive** so it does not
  drop · document "re-run to resume".

## Decision Outcome

- **(1)** `run_mineru` now passes `os.path.abspath()` for both `-p` and `-o` (idempotent for the already-
  absolute local case) — the single place a pdf2wiki-relative path crosses into MinerU's cwd. Shipped in
  **0.2.4** with a regression test that reproduces the cwd divergence.
- **(2)** every remote `ssh`/`scp` call sends keepalives (`ServerAliveInterval=30`,
  `ServerAliveCountMax=240` ≈ 2 h of tolerated silence), holding the channel open across long silent
  passes. Shipped in **0.2.5**. Deliberately *not* also reclassifying a dropped connection as a distinct
  transient error — the keepalive removes the trigger, and the existing `.done` per-pass resume already
  makes a re-run continue.

Both were validated on a real box: a full-book remote convert now completes end-to-end, and phase-5
`chapter_split` produces per-chapter files.

### Consequences

- **Good:** remote mode is now validated end-to-end for a single-book conversion (not just unit-tested);
  the fixes are minimal and behavior-neutral except at the failure they address; resume via `.done` covers
  any residual drop.
- **Bad / trade-off:** still not exercised at full multi-book batch scale, so the README keeps a "prefer
  local for large runs" note; a genuinely dead box is still caught only by the start-time preflight plus the
  batch circuit breaker, not per-book mid-run.

## More Information

`src/pdf2wiki/convert/merge.py` (`run_mineru`), `src/pdf2wiki/executor.py` (`_ssh_opts`) ·
CHANGELOG 0.2.4 / 0.2.5 · [remote GPU how-to](../how-to/set-up-remote-gpu.md) ·
[troubleshooting](../how-to/troubleshoot.md).
