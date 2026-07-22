# llm-wiki documentation

llm-wiki is a standalone Claude Code plugin (v0.1, MIT) that lets Claude **consult** and **review your
code against** a plain-Markdown Obsidian knowledge vault — the "LLM Wiki" pattern: a knowledge base an
LLM reads just-in-time, an alternative to RAG/embeddings.

It works with **any** vault laid out as `wiki/{concepts,entities,sources,domains}/*.md` plus
`wiki/{index,overview,hot,log}.md`. Coverage is discovered from the vault itself — nothing about your
domains or page names is hardcoded. It pairs with the [pdf2wiki](../README.md) converter, which builds
such a vault from PDFs, but does not require it.

v0.1 ships the **query side only** — two skills and one agent. Ingest tooling is a later release.

The documentation is organized by what you are trying to do.

## [Tutorials](tutorials/) — learning by doing

Start here if the plugin is new to you.

- [Query your first vault](tutorials/query-your-first-vault.md) — a guided first consultation.

## [How-to guides](how-to/) — get a specific task done

- [Install the plugin](how-to/install.md)
- [Configure the vault location](how-to/configure-vault-location.md) — the three-way resolution.
- [Review a project](how-to/review-a-project.md) — run `knowledge-review` and read its report.

## [Reference](reference/) — look up the facts

- [Skills and agent](reference/skills-and-agent.md) — precise reference for all three assets.
- [Vault layout](reference/vault-layout.md) — the directories, files, and trust markers the plugin expects.

## [Explanation](explanation/) — understand why

- [Why an LLM wiki](explanation/why-llm-wiki.md) — plain-Markdown, just-in-time reading vs RAG/embeddings.

---

This doc set follows the [Diátaxis](https://diataxis.fr/) framework: tutorials, how-to guides,
reference, and explanation each serve a distinct need and are kept separate on purpose.
