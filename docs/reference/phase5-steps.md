# Phase 5 steps reference

`phase5` runs eight post-processors in a fixed order on a converted `.md`. The first seven transform
the Markdown string. The eighth splits it into chapter files. Order matters — each step depends on the
previous one's output. See [post-process and split](../how-to/post-process-and-split.md) for how to run
it, and [`phase5` in the CLI reference](cli.md#phase5) for flags.

The chain is a dry-run by default. Every string transformer is idempotent, and all of them except
`mermaid_repair` leave ```mermaid``` fences untouched (the guard is case-insensitive and tolerates an
info-string suffix).

## How fences are recognized

Every step that treats code differently from prose finds code blocks through one shared lexer,
`pdf2wiki.phase5.fences`, rather than its own regex. (`illegal_codepoints` is the one exception: it
edits the whole document, fences included, so it parses no structure at all.) The lexer follows
CommonMark's fenced-code rules as far as converter output needs:

- **opener** — up to three spaces of indent, then three or more backticks, then a free-form info
  string. A backtick fence's info string may not contain a backtick. Backtick-only, deliberately:
  MinerU emits only backtick fences. In every book converted so far, a `~~~` run is real content such
  as console output or ASCII art. When the lexer treated it as a fence, a *pair* of tilde divider rows
  in prose lexed as one code block. That corrupted the prose between them, and cost `chapter_split`
  any chapter boundary inside.
- **closer** — the same fence character, at least as long as the opener, with nothing but whitespace
  after it.
- **language** — the first whitespace-separated token of the info string, lowercased. Any remainder
  (`java {highlight=2}`) is preserved when a step rewrites the tag. An info string that *starts* with
  `{` is Pandoc attribute syntax, whose language is fused into the attribute list. `lang_retag` leaves
  those blocks alone rather than guess.
- **an opener with no matching closer is not a block.** CommonMark would render the rest of the
  document as code. These steps *rewrite* what they match, so a single stray fence would strip escapes
  out of prose and cost `chapter_split` every later chapter boundary. Malformed input is left
  byte-for-byte alone instead.
- A block re-emitted without a change is byte-identical, down to its indent and fence run. A step can
  therefore only alter what it means to alter.

## The chain

| # | Step | Reads | Does | Produces |
|---|------|-------|------|----------|
| 1 | `illegal_codepoints` | md | Removes codepoints that are illegal in interchange text. Those are raw `U+0000`, the `U+FDD0`–`U+FDEF` block, and the plane-end `U+FFFE`/`U+FFFF` pairs. Scoped to the **whole document, code fences included**. Private Use Area codepoints are left for `symbol_pua`. Drops rather than substitutes, because the characters print as nothing. A removal between two alphanumerics joins two words and is reported as `word_joins`. | md that is text, not binary |
| 2 | `symbol_pua` | md | Remaps Private Use Area codepoints that publisher PDFs emit for Symbol-font and Wingdings-font glyphs (π, Σ, →, ≠, ∇, ×, ✓). Every entry in its table was verified against a rendered page. Each entry records the book, the PDF page and the font that emitted the codepoint. Also turns a PUA bullet marker at line start into a real list item. Two markers are known: `U+F0A1` (a Wingdings2 square) and `U+F077` (a Wingdings diamond). Only the square has a verified reading after a heading's hashes, so a diamond there is left alone and reported. A Symbol-font space becomes a real space, but one at a line edge is dropped, because two of them are a hard break in Markdown. Only the whitespace after the last Symbol space stays, so the drop does not uncover a hard break. At the line head the mirror rule applies. Only the whitespace before the first Symbol space stays. That is the indent the parser read before the step, because every real space behind a Symbol space is content. Without this rule a Symbol space and then four real spaces becomes an indented code block. Two real spaces can move a paragraph into the list item above it. So the head is cut back each time the indent grows, not only at four columns. The head is cut back only when an ASCII letter starts the text behind the Symbol space. The head must also hold only spaces, tabs, Symbol spaces and the Unicode space characters that are not ASCII, such as `U+00A0` and `U+2003`. These characters are text to CommonMark, so the cut-back keeps them and deletes only the real spaces and tabs in front of them (#99). The whitespace in front of the first Symbol space must be less than four columns. A Symbol space at the line head stays in place when the text behind it can open a block. Examples are `# Title`, `- item` and a code fence. The Symbol space is the only thing that keeps such a line a paragraph line, and no rendered page shows which reading is correct. The step reports each Symbol space that stays. The report says that the text can open a block, not that it does, so the operator must read the source page. The Symbol space is still dropped when a bullet marker leads or opens the line. It is also dropped when the text starts with an ASCII letter. The same applies to any other letter, and to any character that is not ASCII. In those two cases no real space behind the Symbol space can become indent. This list is narrow on purpose, so text such as `**bold**` also keeps its Symbol space. The Symbol space also stays at the end of a line in one case. Without it, the line could be an underline, a thematic break, a link reference definition or the header row of a table. It stays inside the text when no text is in front of it. A real space there can complete a heading or a list item. A task marker such as `[x]` is not completed either. These two rules apply only to a line that has no bullet marker in it. A line that no rule covers keeps the handling of the previous release. The step reads one line and cannot see a paragraph above it. CommonMark has a second hard break, a line-final backslash, and one real space stays in front of it for the same reason. Scoped **outside** code fences. Unrecognized PUA is left alone and reported. A bullet marker that opens a line is also left alone and reported, if it cannot be read as a list item. That occurs when it is indented four **columns** or more, or when it has no space after it. It also occurs when an operator such as `=` follows the marker. Each marker slot is a Greek letter in the Symbol font, and a formula that starts with that letter is not a list item. A tab is one character and four columns, so any tab in the indent defers the marker. Deletion would flatten a nested list. A `U+F077` in the middle of a line is left alone and reported, because only `U+F0A1` has a verified reading there. A line-opening `U+F0B7` is also left alone, because it is a multiplication dot in one book and a list bullet in another. Runs a second time after `caption_unbleed`, which can promote a glyph from code to prose when it unwraps a fence. | md with real characters instead of invisible ones |
| 3 | `caption_unbleed` | md | Lifts a `Listing/Figure/Table/Example N.M …` caption that MinerU trapped inside a code fence out to a bold line above the fence, or drops a caption-only fence entirely. | md with captions un-bled from code |
| 4 | `lang_retag` | md | Re-detects each code fence's language, then rewrites the fence tag. Precedence is a `# file: x.ext` hint, then a trusted specific MinerU tag (resolved through the alias/extension table), then a keyword heuristic, else `text`. Tags the heuristic cannot detect but books do emit (`hcl`, `qml`, `vhdl`, `gherkin`, `graphql`) are trusted as-is. MinerU's known-wrong guesses (`swift`, `erlang`) are always re-detected. See [the detection order](#lang_retag-detection-order). | md with reliable language tags |
| 5 | `dash_normalize` | md | Inside code fences only, converts a typographic en/em-dash used as a long-flag prefix (`–dev`) to `--` and a U+2212 minus to `-`. | md with correct dashes in code |
| 6 | `mermaid_repair` | md | Sanitizes ```mermaid``` node labels so the diagram parses — literal `\n` → `<br>`, inner quotes → `'`, inner brackets → `()`, closes unclosed labels, drops orphan brackets. | md with parseable Mermaid |
| 7 | `code_unescape` | md | Inside code fences only, strips MinerU's markdown-punctuation escapes (`\$ \* \~ \_` `` \` `` `\# \@ \% \& \!`) while preserving real string/regex escapes (`\n \t \d \s \" \\`). | md with clean code fences |
| 8 | `chapter_split` | md file | Splits at fence-aware H1 boundaries (plus mistagged `## Appendix X.` H2s) into per-chapter files with YAML frontmatter. Adds the book metadata and the PDF page range of each chapter when they are known. See [chapter frontmatter](#chapter-frontmatter). | `00-front-matter.md` + `NN-slug.md` files |
| 9 | `book_index` | the split | Writes `<slug>-index.md`, the entry page of the book. It holds the book metadata and one table row per chapter file, with a link and the PDF pages. See [book index](#book-index). | `<slug>-index.md` |

## Chapter frontmatter

`chapter_split` injects this frontmatter into every chapter file:

```yaml
---
title: "Chapter 3: Using CMake in Popular IDEs"
book: "modern-cmake-for-cpp"        # from --book
book_title: "Modern CMake for C++"  # book metadata, only when known
authors: ["Ann Author"]             # book metadata, only when known
year: 2024                          # book metadata, only when known
isbn: "9781805121800"               # book metadata, only when known
publisher: "Packt Publishing Ltd."  # book metadata, only when known
chapter: 10                         # integer order; front matter = 0
pdf_pages: [106, 125]               # only when blocks.json gives both ends
source: "<pdf-filename>"            # from --source-name (else the md path)
tags: [book]
---
```

The five base fields are always there: `title`, `book`, `chapter`, `source` and `tags`. Each other
field is written only when its value is known. A book with no metadata and no `blocks.json` gets the
five base fields only, the same as in 0.2.

### Where the book metadata comes from

`phase5` reads the metadata from one of these sources, in this order:

1. The PDF given with `--pdf`.
2. The `book.json` beside the converted `.md`. `convert` writes this file.
3. Nothing. The text is then the only source.

The front of the repaired text then fills each field that is still empty. The copyright page is in
that text, so the ISBN, the year and the publisher are found without the PDF. The title and the
authors come from the PDF metadata only.

Each field has one rule, and a field without a match stays empty:

| Field | Rule |
|-------|------|
| `book_title` | The PDF metadata title. A title that names a file or a template, such as `Microsoft Word - draft.docx`, is dropped. |
| `authors` | The PDF metadata author, split at `;`, `&` and `and`. A comma splits only when each part has two words or more, so `Richardson, Chris` stays one author. |
| `year` | The latest year on a copyright line, such as `Copyright © 2023`, `©2021 by` or `Copyright © 2015, 2021`. A "First published" date does not count. A bare `(c)` does not count, because a list item can start with it. A line that starts like a code comment does not count either, such as `// Copyright 2025 Google LLC`. In PDF text a line that starts with `#` or `*` is a comment too. In Markdown such a line is a heading, emphasis or a list item, so it counts. The year can be on the line below the copyright sign. |
| `isbn` | The first ISBN that passes its checksum, written as digits. A 13-digit ISBN must start with 978 or 979. The label can be `ISBN`, `ISBN-13`, `ISBN 13:`, `eISBN` or `ISBN (ebook)`. Hyphens can be ASCII or the Unicode hyphens and dashes from `U+2010` to `U+2015`. |
| `publisher` | The first of two kinds of line in the text. One kind is a `Published by` line, cut at the street address. A name with a year in it is prose, not a publisher. The other kind is a line that is not a heading and holds only a company name, such as `Manning Publications Co.`. The name must end in Publications, Publishing, Press or Media and then Co, Inc, Ltd or LLC. |

Only the first 40,000 characters of the text are read. The back pages of a book often list other
books, and their ISBNs are not this book's. Code fences are skipped, because a license header in a
code sample, such as `// Copyright 2025 Google LLC`, is not the copyright of the book. Only the
first copyright statement counts, with any other copyright line in the 15 lines below it.

**Limit.** A license header that the converter wrote as a heading outside a fence, such as
`# Copyright 2024 The Kubernetes Authors`, looks like a copyright heading. It gives the year only
when no copyright statement comes before it.

### Where the page ranges come from

`pdf_pages` comes from the `blocks.json` beside the converted `.md`. Each heading block there
records the PDF page it is on. A chapter starts on the page of its heading and ends on the page
before the next chapter starts. The numbers are 1-based PDF pages, as a PDF viewer counts them. They
are not the page numbers that the book prints.

**Limit.** A chapter that runs on to the page where the next chapter starts does not get that page.
Four converted books were measured. On each first page of a chapter, every block belonged to that
chapter. This was true also when the converter put the block before the heading. Examples are a
large chapter number, an image, and the first paragraphs.

A chapter whose heading is not found gets no `pdf_pages`. The chapter before it gets none either,
because its end is not known.

Files are named `00-front-matter.md` (all content before the first boundary) then `NN-slug.md`, where
`NN` is the two-digit order and the slug is the lowercased, hyphenated, 60-char-truncated heading.
Image paths are **not** rewritten — chapter files share the same directory as `images/`, so relative
references stay correct.

If the Markdown has no detectable boundary, `chapter_split` raises an error rather than emit a single
undivided file — fix the headings and re-run.

## Book index

`book_index` writes `<slug>-index.md` beside the chapter files, for example
`modern-cmake-for-cpp-index.md`:

```markdown
---
title: "Modern CMake for C++"
book: "modern-cmake-for-cpp"
year: 2024
isbn: "9781805121800"
publisher: "Packt Publishing Ltd."
source: "modern-cmake-for-cpp.pdf"
tags: [book-index]
---

# Modern CMake for C++

Packt Publishing Ltd. · 2024 · ISBN 9781805121800

| # | Chapter | PDF pages |
|---|---|---|
| 1 | [Cover](01-cover.md) | 1–1 |
| 8 | [Chapter 1: First Steps with CMake](08-chapter-1-first-steps-with-cmake.md) | 30–67 |
```

The example leaves out rows 2 to 7 and the rows after row 8.

The links are CommonMark relative links, so Obsidian, GitHub and static site generators follow them.
When the title is not known, the page uses the book slug. A chapter title escapes its Markdown
punctuation, so a `|` or a `<T>` in a title does not break the table.

The name holds the slug so that it is unique in a vault with many books. A plain `index.md` in
each book folder would make the vault's existing `[[index]]` links ambiguous. A plain `<slug>.md`
would collide with the source page that an ingest writes for the book.

## `lang_retag` detection order

The keyword heuristic is precision-first: a block it cannot identify becomes `text`. It does not
borrow a neighboring language's tag. Order matters, because the loose branches key off tokens
several languages share, so the families with an unmistakable marker are resolved first:

1. **`http`** — a request line or a header block.
2. **`bash`** — the block *opens* with a `$ `/`➜ ` prompt, so it is a terminal session whatever
   language its output quotes. Only the first line counts: books also print a program's output as
   a trailing `$ …` line inside the source block.
3. **`pseudocode`** — an assignment arrow (`←`) or a brace-less `function f(x)` header.
4. **`html`** — the block opens with markup and uses HTML element names. JavaScript that assembles
   markup inside a string stays JavaScript.
5. **`cmake`** — a build command in call form, or a `CMAKE_*`/`${PROJECT_*}` variable.
6. **`rust`** — `fn`, `let mut`, an attribute, a bang-macro, `use std::…`, `-> Result<…>`. Before the
   C family, because `std::` is Rust's path separator as much as C++'s.
7. **`cpp` / `c`** — the preprocessor and the C standard library, split on C++-only vocabulary
   (`std::`, `template<`, `public:`, a C++ header). Before `java`, whose typed-var form
   (`Widget w = make_widget();`) and `class` keyword would otherwise claim these blocks.
8. **`makefile`, then `go`** — Make is checked first because it shares Go's `:=`.
9. **`javascript` / `typescript`** — before `ruby`, since an arrow function reads as a hashrocket,
   and before `bash`, since `export function` reads as a shell `export`.
10. `ruby`, `yaml`, `dockerfile`, `xml`, `json`, `java`, `python`, `sql`, `bash`, `ini`,
    `properties`, generic `yaml` — then `text`.

**Known limits.** A schema or IDL language with no branch of its own can borrow a neighbor's tag when
its syntax overlaps. A FlatBuffers `table`/`namespace` block reads as `typescript`, because its field
syntax is the same `name:type` shape as a TS property annotation. A Thrift `struct` can read as `c`.
Measured over a 1674-page, 13240-block reference vault, that is 2 blocks. Both were `text` before any
brace-family branch existed.

A prior, larger count here bundled in four C/C++/Rust `enum` blocks misdetected as `typescript`. That
was a real defect rather than a schema-overlap limit, and it is fixed: an `enum` now needs `export`
before it counts as TypeScript.

Allman-braced JavaScript can read as `pseudocode` (2 blocks), and a `kubectl -o go-template=…` command
as `go` (1 block).

## Why this order

`illegal_codepoints` runs first. A raw NUL makes the page binary to grep-based tooling, and no lexer,
detector or splitter below expects that byte. It is removed before anything parses the document.

`symbol_pua` runs next, because it repairs characters and line-level structure that every later step
parses. A PUA bullet marker at line start otherwise reaches `chapter_split` as a fake heading, and a
glyph it misses corrupts prose invisibly.

`caption_unbleed` runs then, so that `lang_retag` detects language on clean code. `symbol_pua` runs a
second time after it, because an unwrapped caption-only fence can promote a glyph into prose that the
first pass correctly skipped.

`lang_retag` runs before `dash_normalize` and `code_unescape`, which scope their edits to code fences.
`mermaid_repair` runs before the split, so that diagrams are fixed while still in one document.
`chapter_split` runs last, because the other seven must land before the Markdown is cut into files.
