# Roadmap

This roadmap describes what pdf2wiki intends to do — and deliberately does **not** intend to do — over
roughly the next year (2026 H2 → 2027). It is a direction, not a contract: priorities shift as real
book conversions surface real problems. Dates are intentionally coarse.

## Planned / in scope

- **Reach OpenSSF Best Practices Silver.** Governance, code of conduct, an assurance case (threat model),
  ≥ 80% statement coverage, DCO sign-off, and signed release tags. (This roadmap itself is part of that.)
- **Validate remote and cloud modes at full-book batch scale.** Both `--remote` (SSH GPU) and
  `--mineru-cloud` have a verified single-book end-to-end run; the next step is exercising them across a
  multi-book batch and hardening whatever breaks at scale.
- **Improve math / equation fidelity.** Formula pages currently transcribe unevenly (digit-spacing,
  occasional semantic slips). Investigate a LaTeX-emitting path and better equation handling.
- **Broaden conversion robustness.** More resilient handling of unusual layouts, tables, and diagrams;
  reduce the number of blocks that land in the QA-flagged bucket.
- **Evaluate unified-VLM backend upgrades** (e.g. newer single-model OCR/layout engines) — strictly
  **gated on a code-fidelity smoke test first**, because every VLM tried so far corrupts code and cannot
  replace the byte-perfect `pipeline -m txt` path.
- **Ingest-side of the llm-wiki plugin.** The query/review side ships today; the vault-ingestion side is
  a later release.

## Out of scope / not planned

- **OpenSSF Gold.** Gold requires two or more maintainers and independent two-person code review;
  pdf2wiki is a single-maintainer project, so Gold is not an honest goal while that holds.
- **Native Windows or macOS conversion.** Conversion targets Linux + NVIDIA/CUDA (WSL2 counts). The
  pure-Python post-processing is portable, but running MinerU is not a cross-platform goal.
- **Reimplementing MinerU.** pdf2wiki orchestrates MinerU as an external tool; it will not fork or
  reimplement the underlying OCR/layout models.
- **Paid or proprietary OCR / vision services** as a required dependency. The project stays
  free/open-source; the optional mineru.net cloud path is behind an explicit opt-in and is not required.
- **A graphical user interface.** pdf2wiki is a CLI and a library; a GUI is not planned.

## How this changes

The roadmap is revised by pull request against this file, decided by the maintainer in the open — see
[GOVERNANCE.md](GOVERNANCE.md).
