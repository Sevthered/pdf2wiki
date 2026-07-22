# pdf2wiki documentation

pdf2wiki converts native-text technical-book PDFs into clean, chapter-split, LLM-ready Markdown using a
dual-pass MinerU pipeline plus fidelity-preserving post-processing.

The documentation is organized by what you are trying to do. Pick the entry point that matches your
need — a high-level sense of the layout will tell you where to look.

## [Tutorials](tutorials/) — learning by doing

Start here if pdf2wiki is new to you.

- [Convert your first book](tutorials/convert-your-first-book.md) — a full guided run, PDF to chapters.

## [How-to guides](how-to/) — get a specific task done

For when you already know the tool and need to accomplish something.

- [Install pdf2wiki](how-to/install.md)
- [Convert a book](how-to/convert-a-book.md)
- [Post-process and split into chapters](how-to/post-process-and-split.md)
- [Run a batch](how-to/run-a-batch.md)
- [QA a conversion](how-to/qa-a-conversion.md)
- [Set up a remote GPU host](how-to/set-up-remote-gpu.md) *(experimental)*
- [Troubleshooting](how-to/troubleshoot.md)

## [Reference](reference/) — look up the facts

Precise, complete descriptions of the machinery.

- [CLI reference](reference/cli.md) — every command, flag, and default
- [Configuration](reference/configuration.md) — the config file schema
- [Pipeline stages](reference/pipeline-stages.md) — stages and their on-disk artifacts
- [Phase 5 steps](reference/phase5-steps.md) — the six post-processors
- [Output layout](reference/output-layout.md) — what gets written, and the fidelity markers

## [Explanation](explanation/) — understand why

Background and design rationale.

- [Why a dual-backend pipeline](explanation/why-dual-backend.md)
- [How the merge works](explanation/how-the-merge-works.md)
- [Design principles](explanation/design-principles.md)

## [Architecture](architecture/)

- [Architecture](architecture/architecture.md) — arc42-style overview with C4 diagrams.

## [llm-wiki plugin (Claude Code)](llm-wiki/)

A standalone Claude Code plugin to **consult** and **review your code against** a knowledge vault of
the shape pdf2wiki builds — the query side of the "LLM Wiki" pattern. It works with any such vault and
does not require pdf2wiki. See the [llm-wiki docs](llm-wiki/README.md).

---

This doc set follows the [Diátaxis](https://diataxis.fr/) framework: tutorials, how-to guides,
reference, and explanation each serve a distinct need and are kept separate on purpose.
