# llm-wiki — a Claude Code plugin

Consult, and review your code against, a plain-Markdown **knowledge vault** — deep reference pages
distilled from technical books, built for an LLM to read (and write) the same files a human reads. This
is the "LLM Wiki" pattern: a durable, plain-Markdown knowledge base you query just-in-time instead of a
vector store.

**Standalone.** It works with **any** Obsidian-style vault laid out as:

```
<vault>/wiki/{concepts,entities,sources,domains}/*.md
<vault>/wiki/{index,overview,hot,log}.md
<vault>/<domain>/<book-slug>/NN-chapter.md      # optional raw source chapters
```

Coverage is discovered **from the vault itself** (`wiki/domains/`, `wiki/index.md`) — nothing about your
domains or page names is hardcoded. The companion [pdf2wiki](https://github.com/Sevthered/pdf2wiki)
converter builds a vault in this shape from PDFs, but you can build one by hand or with any tool.

## What's in it (v0.1 — query side)

| Asset | Type | Use |
|---|---|---|
| `knowledge-query` | skill | Consult the vault before planning/designing; cite `[[Page-Name]]`. |
| `knowledge-review` | skill | Review a project against what the vault says; severity-ranked findings, each citing `file:line` + `[[Page-Name]]`. |
| `knowledge-researcher` | agent | Read-only multi-page lookups that stay out of your main context. |

_Ingest-side tooling (build/extend a vault) ships in a later release._

## Install

```bash
claude plugin marketplace add https://github.com/Sevthered/pdf2wiki
claude plugin install llm-wiki@pdf2wiki
```

Update later with `claude plugin marketplace update pdf2wiki`.

## Configure your vault location

The plugin never hardcodes a path. It resolves the vault root in this order:

1. A block in your project's `CLAUDE.md`:
   ```markdown
   ## Knowledge wiki
   Vault: /absolute/path/to/your/vault
   ```
2. The `KNOWLEDGE_VAULT` environment variable: `export KNOWLEDGE_VAULT=/path/to/vault`
3. Otherwise it asks.

## Use

- Planning in a domain your vault covers → invoke `knowledge-query` (or just ask; it triggers on
  "what does the wiki say…"). It reads `hot.md → index.md → domain → concept pages` and answers with
  `[[Page-Name]]` citations.
- `/knowledge-review [path]` → detects which of the vault's domains the project touches, builds checklists
  from the pages, fans out review agents, and reports ranked findings.

Pages carry honesty callouts (`[!warning]`, `[!gap]`, `[!contradiction]`, `[!bug]`); the skills respect
them and never present flagged content as settled fact.

## License

MIT (this plugin). The pdf2wiki converter in the parent repository is AGPL-3.0.
