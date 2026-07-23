# Architecture Decision Records

This directory records the significant, hard-to-reverse decisions behind pdf2wiki — *what* was
decided, *what alternatives were rejected*, and *why*, dated at the point of decision. It complements
the [explanation docs](../explanation/) (which describe how the system works *now*): an ADR is an
immutable record of a choice and its trade-offs, which a later ADR can *supersede*.

Format: [MADR 4.0.0](https://adr.github.io/madr/). Files are numbered `NNNN-title.md`.

> These records were **written retrospectively** (2026-07) from the design as it stands, not captured
> live at each decision. They are accurate to the code and the evidence that drove each choice; the
> dates reflect when the reasoning was set down, not necessarily when the code first landed.

| # | Decision |
|---|----------|
| [0001](0001-dual-backend-pipeline-and-hybrid.md) | Convert with two MinerU backends and merge, not one |
| [0002](0002-code-merge-by-token-verification.md) | Reconcile code by token-verification, keeping pipeline truth |
| [0003](0003-agpl-converter-mit-plugin-and-subprocess.md) | AGPL converter + MIT plugin; drive MinerU as a subprocess |
| [0004](0004-execution-backends-behind-one-port.md) | Execution backends behind one Executor port (+ cloud strategy) |
| [0005](0005-remote-mode-path-and-connection-hardening.md) | Remote-mode hardening: absolute MinerU paths + SSH keepalive |
