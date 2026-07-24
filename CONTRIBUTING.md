# Contributing to pdf2wiki

Thanks for your interest. This guide covers the development setup and the conventions the project
follows. By participating you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md); see
[GOVERNANCE.md](GOVERNANCE.md) for how decisions are made and who maintains the project.

## Development setup

pdf2wiki uses [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/Sevthered/pdf2wiki
cd pdf2wiki
uv sync            # create the venv and install dev dependencies
```

You do **not** need a GPU or MinerU to work on most of the code: the converter's pure functions, the
whole `phase5` chain, `scan`, and the executors are all unit-tested without one. Only running an actual
`convert` needs MinerU and a GPU — see the [install guide](docs/how-to/install.md).

## Run the tests

```bash
uv run pytest -q
```

Tests live in `tests/` and use synthetic fixtures (no PDFs, no network, no GPU). Please add or update
tests for any behavior change and keep the suite green.

## Lint & license compliance

CI runs `ruff check` (including the `flake8-bandit` security-lint rules, `S`), `ruff format --check`,
`reuse lint`, `mypy`, and `pytest`, plus an OpenSSF Scorecard scan. Run the first set locally
with `uv run <tool>`. The project is [REUSE](https://reuse.software/) 3.3 compliant — every source
file carries an SPDX header (`src/**` is AGPL-3.0-or-later, `plugin/**` is MIT); non-code files are
covered by `REUSE.toml`. Install the pre-commit hook to catch a missing header before you commit:

```bash
uv run pre-commit install
```

How dependencies are selected, pinned, and tracked is documented in
[Dependency management](docs/explanation/dependencies.md).

## Conventions

- **Coding standards.** Python code follows [PEP 8](https://peps.python.org/pep-0008/). Style and imports
  are enforced by `ruff`, formatting by `ruff format`, and types by `mypy --strict` (all configured in
  `pyproject.toml` and gated in CI), so contributions must pass them. Beyond that, match the surrounding
  code and keep changes surgical.
- **Dry-run by default.** Any command that modifies existing files must default to a dry-run and
  require `--apply` (see [design principles](docs/explanation/design-principles.md)). `convert` and
  `qa` are the only exceptions — they only create new artifacts.
- **Idempotent transforms.** `phase5` steps must be safe to run twice.
- **Fidelity first.** Never silently trust VLM-transcribed code — divergences are flagged, not hidden.
- **Docs-as-code.** Documentation lives in `docs/`, organized by the [Diátaxis](https://diataxis.fr/)
  framework (tutorials / how-to / reference / explanation). Update the relevant page in the same change
  as the code, and keep one topic to one page. Documentation is kept current with the code; known
  documentation defects are tracked as GitHub issues and fixed.

## Submitting changes

1. Branch from `main`.
2. Make the change with tests and docs updated.
3. Ensure `uv run pytest -q` passes.
4. Commit with a sign-off: `git commit -s` (see [Sign your work](#sign-your-work-dco) below).
5. Open a pull request describing what changed and why.

## Code review

Every change — including the maintainer's own — lands through a pull request and is reviewed before it
is merged. Reviews are conducted on GitHub against the checklist below; a change is **acceptable only
when all of it holds**:

- **CI is green.** The full test suite passes on Python 3.11–3.13, and `ruff check`, `ruff format
  --check`, `mypy --strict`, and `reuse lint` all pass (enforced as required status checks).
- **Sign-off present.** Every non-bot commit carries a DCO `Signed-off-by` trailer (checked in CI).
- **Tests accompany behavior changes.** New or changed behavior adds or updates tests, and coverage
  must not regress.
- **Docs are updated in the same change** as the code they describe (docs-as-code).
- **The change is in scope and surgical** — it does only what its description says, with no unrelated
  refactoring.
- **Security implications are considered** against the
  [assurance case](docs/security/assurance-case.md): input validation, subprocess handling, secret
  handling, and network egress.

The reviewer either approves or requests changes with specific, actionable feedback. Branch protection
blocks the merge until the required checks pass.

## Sign your work (DCO)

Contributions must be signed off under the [Developer Certificate of Origin](https://developercertificate.org/)
(DCO) — a lightweight statement that you wrote the patch, or otherwise have the right to submit it under
the project's license. It is *not* a CLA and assigns no copyright; it is the same mechanism the Linux
kernel and many CNCF projects use.

Add the sign-off automatically with the `-s` flag:

```bash
git commit -s -m "your message"
```

This appends a trailer to the commit message using your configured `user.name` / `user.email`:

```
Signed-off-by: Your Name <you@example.com>
```

If you forgot it on the most recent commit, amend with `git commit --amend -s`. By adding the
sign-off you certify the four statements of the DCO 1.1 linked above.

## License

By contributing, you agree that your contributions are licensed under the project's
[AGPL-3.0-or-later](LICENSE) license.
