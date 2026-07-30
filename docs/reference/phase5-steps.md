# Phase 5 steps reference

`phase5` runs six post-processors in a fixed order on a converted `.md`. The first five transform the
Markdown string; the sixth splits it into chapter files. Order matters — each step depends on the
previous one's output. See [post-process and split](../how-to/post-process-and-split.md) for how to run
it, and [`phase5` in the CLI reference](cli.md#phase5) for flags.

The chain is a dry-run by default. Every string transformer is idempotent, and all of them except
`mermaid_repair` leave ```mermaid``` fences untouched (the guard is case-insensitive and tolerates an
info-string suffix).

## How fences are recognised

All six steps find code blocks through one shared lexer, `pdf2wiki.phase5.fences`, rather than their own
regex. It follows CommonMark's fenced-code rules as far as converter output needs:

- **opener** — up to three spaces of indent, then three or more backticks, then a free-form info
  string. A backtick fence's info string may not contain a backtick. Backtick-only, deliberately:
  MinerU emits only backtick fences, and a `~~~` run is real content (console output, ASCII art) in
  every book converted so far — treating it as a fence let a *pair* of tilde divider rows in prose
  lex as one code block, corrupting the prose between them and costing `chapter_split` any chapter
  boundary inside.
- **closer** — the same fence character, at least as long as the opener, with nothing but whitespace
  after it.
- **language** — the first whitespace-separated token of the info string, lowercased. Any remainder
  (`java {highlight=2}`) is preserved when a step rewrites the tag; an info string that *starts* with
  `{` is Pandoc attribute syntax, whose language is fused into the attribute list, so `lang_retag`
  leaves those blocks alone rather than guess.
- **an opener with no matching closer is not a block.** CommonMark would render the rest of the
  document as code; these steps *rewrite* what they match, so a single stray fence would strip escapes
  out of prose and cost `chapter_split` every later chapter boundary. Malformed input is left
  byte-for-byte alone instead.
- Re-emitting a block without changing it is byte-identical, including its indent and fence run, so a
  step can only alter what it means to alter.

## The chain

| # | Step | Reads | Does | Produces |
|---|------|-------|------|----------|
| 1 | `caption_unbleed` | md | Lifts a `Listing/Figure/Table/Example N.M …` caption that MinerU trapped inside a code fence out to a bold line above the fence, or drops a caption-only fence entirely. | md with captions un-bled from code |
| 2 | `lang_retag` | md | Re-detects each code fence's language by precedence — a `# file: x.ext` hint, then a trusted specific MinerU tag (resolved through the alias/extension table), then a keyword heuristic, else `text` — and rewrites the fence tag. Tags the heuristic cannot detect but books do emit (`hcl`, `qml`, `vhdl`, `gherkin`, `graphql`) are trusted as-is; MinerU's known-wrong guesses (`swift`, `erlang`) are always re-detected. See [the detection order](#lang_retag-detection-order). | md with reliable language tags |
| 3 | `dash_normalize` | md | Inside code fences only, converts a typographic en/em-dash used as a long-flag prefix (`–dev`) to `--` and a U+2212 minus to `-`. | md with correct dashes in code |
| 4 | `mermaid_repair` | md | Sanitizes ```mermaid``` node labels so the diagram parses — literal `\n` → `<br>`, inner quotes → `'`, inner brackets → `()`, closes unclosed labels, drops orphan brackets. | md with parseable Mermaid |
| 5 | `code_unescape` | md | Inside code fences only, strips MinerU's markdown-punctuation escapes (`\$ \* \~ \_` `` \` `` `\# \@ \% \& \!`) while preserving real string/regex escapes (`\n \t \d \s \" \\`). | md with clean code fences |
| 6 | `chapter_split` | md file | Splits at fence-aware H1 boundaries (plus mistagged `## Appendix X.` H2s) into per-chapter files with YAML frontmatter. | `00-front-matter.md` + `NN-slug.md` files |

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
references keep resolving.

If the Markdown has no detectable boundary, `chapter_split` raises an error rather than emit a single
undivided file — fix the headings and re-run.

## `lang_retag` detection order

The keyword heuristic is precision-first: a block it cannot identify becomes `text` rather than
borrowing a neighbouring language's tag. Order matters, because the loose branches key off tokens
several languages share, so the families with an unmistakable marker are resolved first:

1. **`http`** — a request line or a header block.
2. **`bash`** — the block *opens* with a `$ `/`➜ ` prompt, so it is a terminal session whatever
   language its output quotes. Only the opening line counts: books also print a program's output as
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

**Known limits.** A schema/IDL language with no branch of its own can borrow a neighbour's tag when
its syntax overlaps: a FlatBuffers `table`/`namespace` block reads as `typescript` (its field syntax
is the same `name:type` shape as a TS property annotation) and a Thrift `struct` can read as `c`.
Measured over a 1674-page, 13240-block reference vault, that's 2 blocks, both `text` before any
brace-family branch existed. (A prior, larger count here bundled in four C/C++/Rust `enum` blocks
that were misdetected as `typescript`; that was a real defect, not a schema-overlap limit — fixed by
requiring `export` on an `enum` before it counts as TypeScript.) Allman-braced JavaScript can read as
`pseudocode` (2 blocks), and a `kubectl -o go-template=…` command as `go` (1 block).

## Why this order

`caption_unbleed` first, so `lang_retag` detects language on clean code. `lang_retag` before
`dash_normalize` and `code_unescape`, which scope their edits to code fences. `mermaid_repair` before
the split, so diagrams are fixed while still in one document. `chapter_split` last, because the
other five must land before the Markdown is cut into files.
