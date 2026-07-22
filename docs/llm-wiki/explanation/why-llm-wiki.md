# Why an LLM wiki

llm-wiki reads a knowledge base that is nothing but plain Markdown files, laid out for a human and an
LLM to read the same pages. This page explains why that shape — and why it is not a vector store.

## The pattern: a knowledge base an LLM reads just-in-time

The "LLM Wiki" pattern (after Karpathy) is a durable, plain-Markdown knowledge base that an LLM reads
**just-in-time** while it works, and — in fuller setups — writes back to. The unit of knowledge is a
file with a name, not a chunk in an index. To use it, the model navigates: a catalog points at domains,
domains point at pages, pages cross-link to pages. It reads the few pages it needs and stops.

llm-wiki is the query side of that pattern for Claude Code. It consults the vault before you plan
([`knowledge-query`](../reference/skills-and-agent.md#knowledge-query-skill)) and lints your code
against it ([`knowledge-review`](../reference/skills-and-agent.md#knowledge-review-skill)), always
citing the exact page — `[[Page-Name]]` — a claim came from.

## Why plain Markdown instead of RAG/embeddings

A vector store answers "what text is similar to this query"; it retrieves opaque chunks, ranked by an
embedding, with no stable identity and no structure. That is a poor fit for deep technical reference,
where you want the *right page in full* — its code, its parameter defaults, its caveats — not the three
paragraphs nearest in vector space.

Plain Markdown read by navigation gives you what embeddings don't:

- **Legibility.** Every page is human-readable and directly editable. The model reads exactly what you
  read; there is no index to rebuild, drift out of sync, or trust blindly.
- **Stable identity and citation.** A page has a filename, so an answer can cite `[[Page-Name]]` and you
  can open it. A review finding pins to both a `file:line` and a page.
- **Whole-page fidelity.** The model reads a reference article in full — code, defaults, trade-offs,
  gotchas — instead of the top-k fragments a retriever happened to surface.
- **Honesty markers survive.** `[!warning]`, `[!gap]`, `[!contradiction]`, `[!bug]` callouts live on
  the page and travel with the claim (see [vault layout](../reference/vault-layout.md#trust-markers)) —
  a flag that would be flattened away by chunking.
- **No infrastructure.** No embedding model, vector DB, or ingestion index to run and keep fresh — just
  files and the tools Claude already has (Read, Grep, Glob).

The cost is that the model must *find* the page rather than have it retrieved. The vault's shape pays
for that: a shallow-to-deep navigation order (`hot.md → index.md → domain → concept pages`) and unique
filenames that a glob can hit directly.

## Why coverage is discovered, not hardcoded

The plugin never carries a built-in list of domains or page names. On every consultation or review it
reads the vault's **own** `wiki/index.md` and `wiki/domains/` to learn what is covered *now*. This is
deliberate:

- A vault grows as sources are added; a hardcoded list would go stale the moment it does.
- The plugin is **standalone** — it must work against any vault in the expected shape, whose domains and
  page names it cannot know in advance.
- "Not covered" stays honest. Because coverage comes from the live vault, the plugin can distinguish a
  topic the vault is silent on from one it simply didn't retrieve — and say so, instead of forcing a
  citation.

## Where it fits

llm-wiki reads a vault; it does not build one. v0.1 is query side only — ingest tooling to build and
extend a vault is a later release. To create a vault in the shape the plugin expects, the companion
[pdf2wiki](../../README.md) converter distills PDF books into it, or you can author pages by hand
following the [vault layout](../reference/vault-layout.md).
