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
│   ├── hot.md                # recent-context cache (it grows with each session)
│   ├── log.md                # change log
│   ├── domains/              # one <domain>.md per domain — the map of the vault's scope
│   │   └── <domain>.md
│   ├── concepts/             # deep concept reference pages
│   │   └── <Page-Name>.md
│   ├── entities/             # entity/tool/API reference pages
│   │   └── <Page-Name>.md
│   └── sources/              # per-source (book) metadata pages
│       └── <source>.md
└── <domain>/                 # optional raw source chapters
    └── <book-slug>/
        ├── <book-slug>-index.md   # book index page: chapter list, PDF pages, book metadata
        └── NN-<title>.md          # one chapter per file, NN = file order
```

## What each part is for

| Path | Role in the plugin's navigation |
|---|---|
| `wiki/index.md` | Master catalog of current domains, sources and exemplar pages. The plugin reads it for a question about the scope of the vault. |
| `wiki/hot.md` | Recent-context cache. New text goes at the top, so the file grows with each session and can be the largest file in the wiki. The skills and the agent read it only for a question about recent vault work. |
| `wiki/domains/<domain>.md` | The map of the vault's **scope**. Each one lists its books and its concept and entity pages. The plugin reads it for a question about scope and for a review checklist. It never uses a hardcoded domain list. A grep over the pages decides if one topic is covered. |
| `wiki/concepts/<Page-Name>.md`, `wiki/entities/<Page-Name>.md` | Deep reference articles (code, parameters, defaults, trade-offs, gotchas). Filenames are unique, so a match on a file name finds the page for a topic. |
| `wiki/sources/` | Per-source metadata (a book's identity/era). |
| `<domain>/<book-slug>/NN-<title>.md` | Optional raw book chapters. The plugin opens one only when a wiki page cites the chapter and the page does not have the necessary depth. `NN` is the file order, not the chapter number of the book. |
| `<domain>/<book-slug>/<book-slug>-index.md` | Optional book index page that `pdf2wiki phase5` writes, with `tags: [book-index]`. It holds the book metadata and the chapter list with PDF pages. It is not a chapter. The plugin uses its table to find the file of a cited chapter. |

Page filenames are unique topic names (kebab- or Pascal-case), so a case-insensitive match on the file
name, such as `circuit.?breaker`, finds `Circuit-Breaker-Pattern.md`. Cross-page references are
`[[Page-Name]]` wikilinks by filename.

## Book folders

The plugin reads these facts from a book folder when they are there. A vault that another tool built
can lack them. Then the plugin uses the citation on the wiki page and a glob over the book folder.

- **File order is not chapter order.** Cover, preface and part pages come before chapter 1. Thus the
  book's "Chapter 3" can be the file `09-chapter-3-….md`. The frontmatter `chapter:` field also counts
  files. To find a cited chapter, the plugin reads the table in `<book-slug>-index.md`.
- **Two files can end in `-index.md`.** The book index page is `<book-slug>-index.md`. A chapter file
  such as `35-index.md` is the printed index at the back of the book.
- **Book metadata.** The chapter frontmatter can have `book_title`, `authors`, `year`, `isbn`,
  `publisher` and `pdf_pages`. The frontmatter of the book index page can have `title`, `authors`,
  `year`, `isbn`, `publisher` and `pdf_page_count`. The plugin uses `year` as the era of the book.
- **Cross-reference links.** `pdf2wiki phase5 --links` and `pdf2wiki link` change "figure 6.2" in the
  text into a relative link, such as `[figure 6.2](12-chapter-6.md#^fig-6-2)`. The plugin follows such
  a link to its target.

## Navigation order

The `knowledge-query` skill and the agent read in this order. They stop when they have enough. The
`knowledge-review` skill starts at `domains/<domain>.md` instead, because it needs the pages of a
whole domain.

1. A **coverage check**: the script `vault_coverage.py` counts the files in `wiki/concepts/` and
   `wiki/entities/` whose name, heading or text has a term of the question. A `#` line in a code fence
   is not a heading. The check reads no page. If no file name or heading has a term, the answer is
   "not covered". A question about the scope of the vault, or a named page, needs no check.
2. The **concept and entity pages** that the check found, in order of how likely each one is to answer.
   The reads stop when two pages in sequence add nothing necessary.
3. `index.md` and `domains/<domain>.md`, only if the question is about the scope of the vault.
4. **Raw chapters**, only if a page cites the chapter and does not have the necessary depth.
5. `hot.md`, only for a question about recent vault work.

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
