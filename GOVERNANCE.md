# Governance

This document describes how pdf2wiki is governed, who does what, and how the project would continue
if the maintainer stepped away. It is deliberately lightweight — pdf2wiki is a small, single-maintainer
project, and this document says so plainly rather than pretending to a larger structure.

## Governance model

pdf2wiki uses a **single-maintainer** model. The maintainer sets direction, reviews and merges
contributions, and cuts releases. Decisions are made **in the open** on GitHub: design discussion and
proposals happen in issues and pull requests, and the maintainer decides. There is no formal voting or
committee — the project is too small for that to be meaningful.

Anyone may propose a change. The path is always the same: open an issue to discuss (optional for small
fixes), then a pull request with tests and updated docs. The maintainer reviews it against the project's
conventions (see [CONTRIBUTING.md](CONTRIBUTING.md)) and either merges it, requests changes, or explains
why it does not fit.

## Roles and responsibilities

- **Maintainer** — currently **[@Sevthered](https://github.com/Sevthered)**, the sole maintainer.
  Responsible for: the project [roadmap](ROADMAP.md) and direction, reviewing and merging pull requests, cutting
  releases (PyPI + GitHub, see the release process in the project docs), responding to security reports
  (see [SECURITY.md](SECURITY.md)), and enforcing the [Code of Conduct](CODE_OF_CONDUCT.md).
- **Contributors** — anyone who opens a pull request. Responsible for: following the conventions in
  [CONTRIBUTING.md](CONTRIBUTING.md), keeping the test suite green, and updating docs alongside code.
- **Users** — anyone using pdf2wiki. Encouraged to file issues for bugs and enhancement requests, and to
  report vulnerabilities privately per [SECURITY.md](SECURITY.md).

It is always clear who holds the maintainer role: it is the account listed above and shown in the
repository's ownership.

## Continuity

pdf2wiki is designed to survive the loss of any single person — including its sole maintainer — with
minimal interruption. If the maintainer becomes unable or unwilling to continue, the project can be
picked up and kept running (issues created and closed, changes accepted, and new versions released)
within a week, because:

- **It is public and freely licensed.** The full source and history are on GitHub under
  **AGPL-3.0-or-later**, and the plugin subtree under MIT. Anyone may fork and continue the project;
  the license guarantees that right.
- **It is fully documented.** A complete [Diátaxis](https://diataxis.fr/) documentation set under
  `docs/` covers installation, usage, the architecture (arc42/C4), and the release process. A new
  maintainer does not need tribal knowledge to build, test, or release.
- **It uses standard, portable tooling.** Build and test run with `uv` + `hatchling` and `pytest` on
  any Linux/macOS machine (`uv sync`; `uv run pytest`). There is nothing bespoke to reverse-engineer.
- **No single-point secret blocks a fork.** Releases use PyPI **Trusted Publishing** (OIDC, no stored
  token). A new maintainer would publish under their own PyPI project / Trusted Publisher, but all prior
  releases remain available on PyPI and GitHub, and the code itself has no locked dependency on any one
  person's credentials.

To be clear and honest: pdf2wiki currently has **one** maintainer, so its "bus factor" is 1. Continuity
here means the project is *forkable and resumable by a competent newcomer within a week*, not that a
second maintainer is already in place.

## Changing this document

Changes to governance are proposed by pull request against this file and decided by the maintainer, in
the open, like any other change.
