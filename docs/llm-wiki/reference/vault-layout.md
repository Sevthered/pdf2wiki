# Vault layout

The exact directory and file layout llm-wiki expects, and the trust markers it reads on vault pages.
The plugin works with **any** vault in this shape — the [pdf2wiki](../../README.md) converter produces
it, but you can build one by hand. Nothing about your domains or page names is hardcoded; the plugin
discovers coverage from the vault itself.

## Directory layout

Relative to the vault root (the path you set in
[vault-location config](../how-to/configure-vault-location.md)):

```
<vault>/
├── wiki/
│   ├── index.md              # master catalog: domains, sources, page counts, exemplar pages
│   ├── overview.md           # high-level orientation
│   ├── hot.md                # recent-context cache (~1 screen)
│   ├── log.md                # change log
│   ├── domains/              # one <domain>.md per domain — the authoritative coverage map
│   │   └── <domain>.md
│   ├── concepts/             # deep concept reference pages
│   │   └── <Page-Name>.md
│   ├── entities/             # entity/tool/API reference pages
│   │   └── <Page-Name>.md
│   └── sources/              # per-source (book) metadata pages
│       └── <source>.md
└── <domain>/                 # optional raw source chapters
    └── <book-slug>/
        └── NN-chapter.md
```

## What each part is for

| Path | Role in the plugin's navigation |
|---|---|
| `wiki/index.md` | Master catalog. The first thing read to learn current domains, sources, and exemplar pages. |
| `wiki/hot.md` | Recent-context cache, ~1 screen. Read first by `knowledge-query`; skipped by the researcher unless the question is about recent vault work. |
| `wiki/domains/<domain>.md` | The **authoritative coverage map** — each lists its books plus its concept/entity pages. Coverage is read from here, never a hardcoded list. |
| `wiki/concepts/<Page-Name>.md`, `wiki/entities/<Page-Name>.md` | Deep reference articles (code, parameters, defaults, trade-offs, gotchas). Filenames are unique, so `Glob`/`Grep` on a topic works. |
| `wiki/sources/` | Per-source metadata (a book's identity/era). |
| `<domain>/<book-slug>/NN-chapter.md` | Optional raw book chapters, opened only when a wiki page cites the chapter and the page lacks the needed depth. |

Page filenames are unique topic names (kebab- or Pascal-case), so a topic can be found with a glob such
as `wiki/concepts/*Circuit*`. Cross-page references are `[[Page-Name]]` wikilinks by filename.

## Navigation order

Both skills and the agent read shallow-to-deep and stop as soon as they have enough:

`hot.md → index.md → domains/<domain>.md → concept/entity pages → raw chapters (only if cited and needed)`

## Trust markers

Pages carry honesty callouts. The plugin respects them and never presents flagged content as settled
fact — a query answer carries the flag into the plan, and a review finding built on a flagged claim is
labelled as such.

| Marker | Meaning |
|---|---|
| `[!warning]` | Known source error — a book bug or misattribution. |
| `[!gap]` | The source didn't cover it, or the converter dropped it. |
| `[!contradiction]` | A book claim contradicted by other evidence. |
| `[!bug]` | A real bug in the book's code, reconstructed on the page. |

Beyond these markers, book content has a **publication era**: the vault is trusted for concepts,
patterns, trade-offs, and gotchas, but version-sensitive facts (APIs, flags, defaults, values) are
verified against current official docs before being relied on.

## Related

- How the assets traverse this layout: [skills and agent](skills-and-agent.md).
- Why the knowledge base is plain Markdown read just-in-time: [why an LLM wiki](../explanation/why-llm-wiki.md).
