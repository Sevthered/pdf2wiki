# Query your first vault

This tutorial walks you through one consultation of a knowledge vault, end to end. By the time you
finish you will have pointed the plugin at a vault, asked it a planning question, and seen it answer
with `[[Page-Name]]` citations drawn from the vault's own pages.

You need the plugin installed ([install the plugin](../how-to/install.md)) and a vault to read. A vault
is any Obsidian-style directory laid out as `wiki/{concepts,entities,sources,domains}/*.md` plus
`wiki/{index,overview,hot,log}.md`. If you don't have one, the companion
[pdf2wiki](../../README.md) converter builds one from PDF books; you can also hand-write one in the
[expected layout](../reference/vault-layout.md).

## Step 1 — Point the plugin at your vault

The plugin never hardcodes a path. The simplest way to set one is a block in the consuming project's
`CLAUDE.md`:

```markdown
## Knowledge wiki
Vault: /path/to/your/vault
```

That's one of three resolution methods — see [configure the vault location](../how-to/configure-vault-location.md)
for the environment variable and the ask-me fallback.

## Step 2 — Ask a planning question

In a Claude Code session inside that project, ask something in a domain the vault covers — phrased as
planning, not trivia:

```
What does the wiki say about designing a retry/backoff policy for this service?
```

The `knowledge-query` skill triggers on phrasing like "what does the wiki say" (or invoke it
explicitly with `/knowledge-query`). It first reads the vault's **actual** coverage — `wiki/index.md`
and `wiki/domains/` — to check the topic is covered, then navigates
`hot.md → index.md → domain → concept pages` and stops as soon as it has enough.

## Step 3 — Read the answer

The answer comes back grounded in specific pages, each cited as `[[Page-Name]]` — the mechanisms,
parameter names, defaults, and trade-offs the pages actually record, not a general-knowledge summary.
If the topic falls outside what `wiki/domains/` covers, the skill says so plainly instead of forcing a
citation.

Watch for **trust markers** in the answer. Pages carry honesty callouts — `[!warning]`, `[!gap]`,
`[!contradiction]`, `[!bug]` — and the skill carries them through rather than presenting flagged
content as settled fact. See [vault layout](../reference/vault-layout.md#trust-markers).

## What you just did

You configured a vault location, asked a domain question, and got a cited, vault-grounded answer that
stayed inside your main context — for a broad multi-page lookup, the skill instead spawns the
[`knowledge-researcher` agent](../reference/skills-and-agent.md#knowledge-researcher-agent) to keep long
pages out of your context.

## Next steps

- Review a whole project against the vault: [review a project](../how-to/review-a-project.md).
- Understand why the vault is plain Markdown read just-in-time: [why an LLM wiki](../explanation/why-llm-wiki.md).
