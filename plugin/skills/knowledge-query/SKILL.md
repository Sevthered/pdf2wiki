---
name: knowledge-query
description: "Consult a plain-Markdown Obsidian knowledge vault (distilled from technical books, the 'LLM Wiki' pattern) as first-stop reference when planning or designing work in a domain the vault covers. Discovers coverage from the vault itself (a grep over its pages, then its domain pages for scope) — not a fixed list. Triggers on: /knowledge-query, check the wiki, what does the wiki say, what do the books say, planning tasks in a covered domain when a project CLAUDE.md subscribes to a vault."
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
   values) still get verified against current official docs before executing. The era is the `year`
   field in the frontmatter of the book's chapters and index page, or in `wiki/sources/<book>.md`.
3. **If the vault doesn't cover it, say so and move on** — don't force a citation. The **coverage
   pre-check** below says whether the topic is there. Run it before any topic lookup. Skip it when the
   user names the page, and for a question about the vault's scope or recent vault work.

## Coverage pre-check: first, before any page read

A domain that exists is not proof that the vault covers the topic: a "networking" domain can still
have no page on the protocol in question. So run one cheap check yourself, with no page reads, before
any lookup. The core terms are the topics the question asks about, one per sub-question. Write each
term and its synonyms as one regular expression, with `.?` where a name can hold a space
or a hyphen. Count them all in one call. The `knowledge-researcher` agent uses the same script:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/vault_coverage.py <vault> '<term>' ['<term>' ...]
```

Each term is a Python regular expression, matched without regard to case: `circuit.?breaker`,
`retry|backoff`, `c\+\+`, or `\bnat\b` for a whole word. `python3 … vault_coverage.py --help`
gives the full term syntax. The script counts **files** under `wiki/concepts/` and `wiki/entities/`,
subfolders too: file name, Markdown heading (never a line in the frontmatter or in a code fence), and
body. It prints `term F/H/B VERDICT`, the files with a filename or heading hit, the matching text of
each body hit for a PASSING term (15 lines at most per list), and a last `Coverage:` line. It reads no
page into your context. If the path above still shows `${CLAUDE_PLUGIN_ROOT}`, find the script with
`find ~/.claude/plugins -name vault_coverage.py`.

**Short terms false-match.** `quic` matches "quick", and `nat` matches "NATS" and "Signature": use
`\b`. Read the body match lines that the script prints before you trust a PASSING verdict. A hit that
is clearly about something else does not count: give the count without it, and say so
(`vpn 0/0/12, all incidental → NONE`).

- **Any filename or heading hit (COVERED):** go on, with the covered terms only.
- **Body hits only (PASSING):** usually incidental. Read the one or two likeliest pages yourself if
  their names or match lines look relevant. Otherwise treat the term as not covered.
- **No hit (NONE):** first widen the term **one time**, with synonyms and related names
  (`leader.?election|raft|consensus`). If that also finds nothing, **do not spawn** for this term.
  Record "the vault has nothing on X (filename/heading/body 0/0/0)" and go to the official docs for
  it.

A body hit that is a `[!gap]` callout saying the source does not cover the topic is evidence of
absence: count the term as NONE.

When the vault has nothing, the docs research is mechanical: a cheaper model does it well, so keep
the top model for judgment.

## Vault scope: discover it, do not assume it

For a question about what the vault covers, read what it actually covers now. Never rely on a
hardcoded domain list: the vault grows as books are ingested.
1. `wiki/index.md` — master catalog: current domains, sources, page counts, depth-bar exemplar pages.
2. `ls wiki/domains/` and read the relevant `wiki/domains/<domain>.md` — each lists its books + concept/
   entity pages.

Whether one topic is covered is the pre-check's call, not the domain list's.

## Navigation protocol

Reading pages, not navigating to them, is what a vault lookup costs. So **triage before you read**, and
stop as soon as you have what you need:

1. Concept/entity pages are the answer: `wiki/concepts/<Page-Name>.md`, `wiki/entities/<Page-Name>.md`.
   Filenames are unique, so the pre-check's filename and heading hits are the candidate list. Rank
   them by which page is likely to **answer** the question — not by which mentions the terms most —
   then read in that order.
2. `wiki/index.md` and `wiki/domains/<domain>.md` — ONLY for a question about the vault's own scope
   (see above).
3. `wiki/hot.md` — **ONLY** if the question is about recent vault work. It is append-at-top, grows every
   session, and can be the largest file in the wiki; do not read it as a matter of routine.
4. Raw book chapters (`<domain>/<book>/NN-<title>.md`) ONLY if a wiki page cites the chapter and you
   need more depth than the page carries, or the user asks for the source passage. `NN` counts files,
   not the book's chapters: cover, preface and part pages come first. To find "Chapter 3", read the
   table in `<domain>/<book>/<book>-index.md` (the book's index page, `tags: [book-index]`, not a
   chapter) and open the row whose title names chapter 3. The table's `#` column is the file order
   too. If no title carries chapter numbers, match the chapter title that the wiki page gives. A
   chapter file such as `35-index.md` is the printed index at the back of the book, not this page. If
   the book folder has no index page, grep its `# ` headings for the chapter title.

Stop reading when two pages in a row add nothing you needed — the ranked list has gone dry. If you stop
with the question only partly answered, say which candidates you left unopened rather than truncating
silently.

## Context discipline

- **Single known concept** → Read that one page directly.
- **Broad lookup** ("how should I design X", "what patterns exist for Y", multi-page synthesis),
  **after the pre-check says COVERED** → spawn the `knowledge-researcher` agent with the question and
  the script's whole output (the per-term lines, the hit files and the `Coverage:` line), so it does
  not count again and has its candidate list. It navigates the
  vault and returns a distilled, cited answer — keeps long pages out of the main context.

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
