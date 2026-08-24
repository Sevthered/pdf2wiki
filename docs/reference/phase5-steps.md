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
| 2 | `symbol_pua` | md | Remaps Private Use Area codepoints that publisher PDFs emit for Symbol-font and Wingdings-font glyphs (π, Σ, →, ≠, ∇, ×, ✓). Every entry in its table was verified against a rendered page. Each entry records the book, the PDF page and the font that emitted the codepoint. Also turns a PUA bullet marker at line start into a real list item. Two markers are known: `U+F0A1` (a Wingdings2 square) and `U+F077` (a Wingdings diamond). Only the square has a verified reading after a heading's hashes, so a diamond there is left alone and reported. A Symbol-font space becomes a real space, but one at a line edge is dropped, because two of them are a hard break in Markdown. Only the whitespace after the last Symbol space stays, so the drop does not uncover a hard break. CommonMark has a second hard break, a line-final backslash, and one real space stays in front of it for the same reason. Scoped **outside** code fences. Unrecognized PUA is left alone and reported. A bullet marker that opens a line is also left alone and reported, if it cannot be read as a list item. That occurs when it is indented four **columns** or more, or when it has no space after it. It also occurs when an operator such as `=` follows the marker. Each marker slot is a Greek letter in the Symbol font, and a formula that starts with that letter is not a list item. A tab is one character and four columns, so any tab in the indent defers the marker. Deletion would flatten a nested list. A `U+F077` in the middle of a line is left alone and reported, because only `U+F0A1` has a verified reading there. A line-opening `U+F0B7` is also left alone, because it is a multiplication dot in one book and a list bullet in another. Runs a second time after `caption_unbleed`, which can promote a glyph from code to prose when it unwraps a fence. | md with real characters instead of invisible ones |
| 3 | `caption_unbleed` | md | Lifts a `Listing/Figure/Table/Example N.M …` caption that MinerU trapped inside a code fence out to a bold line above the fence, or drops a caption-only fence entirely. | md with captions un-bled from code |
| 4 | `lang_retag` | md | Re-detects each code fence's language, then rewrites the fence tag. Precedence is a `# file: x.ext` hint, then a trusted specific MinerU tag (resolved through the alias/extension table), then a keyword heuristic, else `text`. Tags the heuristic cannot detect but books do emit (`hcl`, `qml`, `vhdl`, `gherkin`, `graphql`) are trusted as-is. MinerU's known-wrong guesses (`swift`, `erlang`) are always re-detected. See [the detection order](#lang_retag-detection-order). | md with reliable language tags |
| 5 | `dash_normalize` | md | Inside code fences only, converts a typographic en/em-dash used as a long-flag prefix (`–dev`) to `--` and a U+2212 minus to `-`. | md with correct dashes in code |
| 6 | `mermaid_repair` | md | Sanitizes ```mermaid``` node labels so the diagram parses — literal `\n` → `<br>`, inner quotes → `'`, inner brackets → `()`, closes unclosed labels, drops orphan brackets. | md with parseable Mermaid |
| 7 | `code_unescape` | md | Inside code fences only, strips MinerU's markdown-punctuation escapes (`\$ \* \~ \_` `` \` `` `\# \@ \% \& \!`) while preserving real string/regex escapes (`\n \t \d \s \" \\`). | md with clean code fences |
| 8 | `chapter_split` | md file | Splits at fence-aware H1 boundaries (plus mistagged `## Appendix X.` H2s) into per-chapter files with YAML frontmatter. | `00-front-matter.md` + `NN-slug.md` files |

## Chapter frontmatter

`chapter_split` injects this frontmatter into every chapter file:

```yaml
---
title: 'Chapter 3: Advanced Features'
book: <slug>            # from --book
chapter: 3              # integer order; front matter = 0
source: <pdf-filename>  # from --source-name (else the md path)
tags: [book]
---
```

Files are named `00-front-matter.md` (all content before the first boundary) then `NN-slug.md`, where
`NN` is the two-digit order and the slug is the lowercased, hyphenated, 60-char-truncated heading.
Image paths are **not** rewritten — chapter files share the same directory as `images/`, so relative
references stay correct.

If the Markdown has no detectable boundary, `chapter_split` raises an error rather than emit a single
undivided file — fix the headings and re-run.

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
