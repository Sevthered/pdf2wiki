---
name: knowledge-query
description: "Consult a plain-Markdown Obsidian knowledge vault (distilled from technical books, the 'LLM Wiki' pattern) as first-stop reference when planning or designing work in a domain the vault covers. Discovers coverage dynamically from the vault's own domain pages — not a fixed list. Triggers on: /knowledge-query, check the wiki, what does the wiki say, what do the books say, planning tasks in a covered domain when a project CLAUDE.md subscribes to a vault."
---

# knowledge-query: Consult the Knowledge Vault Before Planning

The vault holds deep reference pages (code, configs, parameters, gotchas) distilled from professional
books, built to be relied on **instead of re-researching**. When planning or designing work in a domain
the vault covers, ground the plan in vault pages first.

## Vault location (not hardcoded)

Resolve the vault root in this order — do NOT assume a path:
1. A `## Knowledge wiki` block in the consuming project's `CLAUDE.md` with a line `Vault: <absolute path>`.
2. The `$KNOWLEDGE_VAULT` environment variable (`echo $KNOWLEDGE_VAULT`).
3. If neither is set, ask the user for the vault path.

All `wiki/...` paths below are relative to that root. Layout: `wiki/{concepts,entities,sources,domains}/`,
`wiki/{index,overview,hot,log}.md`, and per-domain book chapters under `<domain>/<book-slug>/`.

## The rule

1. **Consult before planning.** Before writing a plan or making a design decision in a covered domain,
   look up what the vault says. Cite the pages the plan leans on as `[[Page-Name]]`.
2. **Complements — never replaces — the doc-first rule.** Book content has a publication era; the vault
   gives concepts, patterns, trade-offs, and gotchas, but version-sensitive facts (APIs, flags, defaults,
   values) still get verified against current official docs before executing.
3. **If the vault doesn't cover it, say so and move on** — don't force a citation.

## Discover coverage dynamically (do NOT assume a fixed domain list)

The vault grows as books are ingested, so read what it actually covers now:
1. `wiki/index.md` — master catalog: current domains, sources, page counts, depth-bar exemplar pages.
2. `ls wiki/domains/` and read the relevant `wiki/domains/<domain>.md` — each lists its books + concept/
   entity pages. This is the authoritative coverage map; never rely on a hardcoded one.
If no domain matches the task, the vault doesn't cover it — say so.

## Navigation protocol

Read in this order — stop as soon as you have what you need:
1. `wiki/hot.md` — recent context, ~1 screen.
2. `wiki/index.md` — master catalog.
3. `wiki/domains/<domain>.md` — domain index → links to concept/entity pages.
4. Concept/entity pages: `wiki/concepts/<Page-Name>.md`, `wiki/entities/<Page-Name>.md`.
   Filenames are unique — `Grep`/`Glob` for a topic works (e.g. `Glob wiki/concepts/*Circuit*`).
5. Raw book chapters (`<domain>/<book>/NN-chapter.md`) ONLY if a wiki page cites the chapter and you
   need more depth than the page carries.

## Context discipline

- **Single known concept** → Read that one page directly.
- **Broad lookup** ("how should I design X", "what patterns exist for Y", multi-page synthesis) → spawn
  the `knowledge-researcher` agent with the question. It navigates the vault and returns a distilled,
  cited answer — keeps long pages out of the main context.

## Trust markers

Pages carry honesty callouts — respect them:
- `[!warning]` — known source error (book bug, misattribution).
- `[!gap]` — source didn't cover it / converter dropped it.
- `[!contradiction]` — book claim contradicted by other evidence.
- `[!bug]` — real bug in the book's code, reconstructed on the page.

Never present flagged content as settled fact; carry the flag into the plan.

## Vault is read-only from here

This skill READS the vault. Never write/edit vault files from a consuming project — ingestion and
maintenance happen in the vault's own dedicated sessions, not from a project that merely consults it.

## Per-project opt-in

A project subscribes by adding this block to its `CLAUDE.md`:

```markdown
## Knowledge wiki — consult before planning
Vault: /absolute/path/to/your/vault
When planning or designing work in a domain this vault covers (discover via wiki/domains/),
invoke the `knowledge-query` skill FIRST and ground the plan in vault pages (cite [[Page-Name]]).
Complements — does not replace — the doc-first rule.
```
