# 0003. AGPL converter + MIT plugin; drive MinerU as a subprocess

- Status: accepted
- Date: 2026-07-23 (recorded retrospectively)
- Deciders: Sevthered (maintainer)

> **Not legal advice.** This records the reasoning behind the licensing choices, citing documented
> conventions (the AGPL-3.0 text, the FSF GPL FAQ, Red Hat's published commentary). License obligations
> are fact-specific; consult a qualified attorney for a definitive determination.

## Context and Problem Statement

pdf2wiki drives **MinerU**, which is licensed **AGPL-3.0**, as its conversion engine. It also ships a
small companion — the `llm-wiki` Claude Code plugin under `plugin/` — that is a separate concern (it
*queries* a produced vault; it does not convert). Two questions had to be resolved: (a) what license the
project carries given its dependency on AGPL MinerU, and (b) whether combining pdf2wiki with MinerU
creates a single "combined work" or a "mere aggregation" of two programs.

## Considered Options

- **License:** MIT/Apache for the whole repo · AGPL for the whole repo · **AGPL converter + MIT plugin**.
- **MinerU coupling:** import MinerU as a Python library (in-process) · **drive its CLI as a subprocess**.

## Decision Outcome

- **The converter is `AGPL-3.0-or-later`; the `plugin/` is `MIT`.** The converter is derivative of / tightly
  bound to AGPL MinerU, so AGPL is the honest, compatible choice. The plugin is an independent query-side
  tool with no MinerU coupling, so it stays permissive (MIT) to maximise reuse. The split is declared in
  metadata: `pyproject.toml` `license = "AGPL-3.0-or-later"` (the wheel packages only `src/pdf2wiki`, so it
  is AGPL-only), and `plugin/LICENSE` carries MIT. *The plugin is intentionally NOT added to the wheel's
  `license-files`, so an MIT license is never bundled into the AGPL distribution.*
- **MinerU is driven as a subprocess** (its CLI, via arguments + a JSON hand-off), not imported. Per the
  FSF GPL FAQ, the combination test turns on the *mechanism* and *semantics* of communication: "pipes,
  sockets and command-line arguments are communication mechanisms normally used between two separate
  programs… the modules normally are separate programs," unless the semantics are "intimate enough,
  exchanging complex internal data structures." pdf2wiki communicates at arm's length (separate process,
  CLI args, `content_list.json` hand-off), so the documented convention treats them as **separate programs
  / mere aggregation** rather than one combined work. (Both are AGPL-compatible here regardless, since the
  converter is itself AGPL.) The AGPL §13 network-source obligation is documented to trigger only for a
  *modified* work offered over a network — a locally-run CLI does not by itself trigger it.

### Consequences

- **Good:** licensing is honest and machine-readable; the permissive plugin can be reused freely; the
  subprocess boundary keeps MinerU replaceable and testable (the boundary is faked in tests), and keeps the
  legal relationship simple.
- **Bad / trade-off:** AGPL narrows who will adopt the converter (some organisations avoid AGPL); the
  subprocess boundary costs process-spawn overhead and a parse step versus an in-process API.

## More Information

FSF GPL FAQ ("mere aggregation"); AGPL-3.0 §13; Red Hat legal commentary on §13. `LICENSE`,
`plugin/LICENSE`, `pyproject.toml`. Related: [0004](0004-execution-backends-behind-one-port.md).
