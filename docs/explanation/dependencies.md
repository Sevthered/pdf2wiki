# Dependency management

How pdf2wiki selects, obtains, tracks, and updates its third-party dependencies.

## Selection

Dependencies are kept deliberately minimal. pdf2wiki has only two runtime dependencies —
[`pymupdf`](https://pypi.org/project/PyMuPDF/) (PDF parsing) and [`requests`](https://pypi.org/project/requests/)
(the mineru.net cloud API) — and prefers the Python standard library wherever practical. A new dependency is
added only when it removes materially more complexity than it introduces, is actively maintained, and carries
an OSI-approved license compatible with the project's AGPL-3.0-or-later. MinerU, the conversion engine, is
driven as an external subprocess rather than imported, so it is not a Python dependency.

## Obtaining and pinning

Runtime dependencies are declared in [`pyproject.toml`](../../pyproject.toml) under `[project].dependencies`
with conservative version ranges (for example `pymupdf>=1.24,<2`). They are resolved and installed from
[PyPI](https://pypi.org) by `uv` (or `pip`). A `uv.lock` file pins exact versions for local development; it is
intentionally **not committed**, because pdf2wiki is a published library and consumers resolve compatible
versions from the declared ranges at install time.

## Tracking and updating

- **[Dependabot](../../.github/dependabot.yml)** opens pull requests for new dependency versions, raises
  **security alerts**, and — with automated security fixes enabled — opens fix PRs when a dependency has a known
  vulnerability.
- **GitHub Actions** used in CI are **pinned to commit SHAs** and bumped by Dependabot.
- **[OpenSSF Scorecard](../../.github/workflows/scorecard.yml)** continuously scores the project's supply-chain
  posture.
- **License compliance** is enforced in CI with `reuse lint` ([REUSE](https://reuse.software/) 3.3), so a file
  or dependency with an incompatible license is caught.

Every dependency change flows through the normal review path: a pull request that must pass CI (tests on
Python 3.11–3.13, ruff, mypy, reuse lint) before it can be merged.
