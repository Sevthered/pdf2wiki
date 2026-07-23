# Contributing to pdf2wiki

Thanks for your interest. This guide covers the development setup and the conventions the project
follows.

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

CI runs `ruff check`, `ruff format --check`, `reuse lint`, `mypy`, and `pytest`. Run them locally
with `uv run <tool>`. The project is [REUSE](https://reuse.software/) 3.3 compliant — every source
file carries an SPDX header (`src/**` is AGPL-3.0-or-later, `plugin/**` is MIT); non-code files are
covered by `REUSE.toml`. Install the pre-commit hook to catch a missing header before you commit:

```bash
uv run pre-commit install
```

## Conventions

- **Style.** Match the surrounding code. Keep changes surgical.
- **Dry-run by default.** Any command that modifies existing files must default to a dry-run and
  require `--apply` (see [design principles](docs/explanation/design-principles.md)). `convert` and
  `qa` are the only exceptions — they only create new artifacts.
- **Idempotent transforms.** `phase5` steps must be safe to run twice.
- **Fidelity first.** Never silently trust VLM-transcribed code — divergences are flagged, not hidden.
- **Docs-as-code.** Documentation lives in `docs/`, organized by the [Diátaxis](https://diataxis.fr/)
  framework (tutorials / how-to / reference / explanation). Update the relevant page in the same change
  as the code, and keep one topic to one page.

## Submitting changes

1. Branch from `main`.
2. Make the change with tests and docs updated.
3. Ensure `uv run pytest -q` passes.
4. Open a pull request describing what changed and why.

## License

By contributing, you agree that your contributions are licensed under the project's
[AGPL-3.0-or-later](LICENSE) license.
