# Post-process and split into chapters

After you [convert a book](convert-a-book.md), you have a single `<slug>.md`. `phase5` cleans it and
splits it into per-chapter files. It runs the [post-processing chain](../reference/phase5-steps.md).

## Preview first (dry-run)

`phase5` is a dry-run by default — it writes nothing and reports what it would do:

```bash
pdf2wiki phase5 ~/pdf2wiki/out/my-book/my-book.md --book my-book
```

You get a per-step summary (captions unwrapped, languages retagged, dashes and escapes fixed, Mermaid
repaired) and the list of chapter boundaries it found.

## Apply

When the preview looks right, write the files:

```bash
pdf2wiki phase5 ~/pdf2wiki/out/my-book/my-book.md \
  --book my-book \
  --source-name my-book.pdf \
  --apply
```

This writes the chapter files to `~/pdf2wiki/out/my-book/chapters/` (override with `--out DIR`).
The source `.md` is not changed. Each chapter file holds the cleaned text.

## Keep the source filename in frontmatter

Pass `--source-name` the original PDF filename. It becomes each chapter's frontmatter `source:` field,
so a staging or temp path never leaks into your published Markdown. Without it, the `.md` path is used.

## Chapter output

You get `00-front-matter.md` plus one `NN-slug.md` per chapter, each with YAML frontmatter
(`title`, `book`, `chapter`, `source`, `tags: [book]`). Image references stay relative, so keep the
`images/` folder alongside the chapter files. See [phase5 steps](../reference/phase5-steps.md#chapter-frontmatter).

You also get `<slug>-index.md`, for example `my-book-index.md`. It is the entry page of the book,
with a link to each chapter file.

## Add the book metadata

`phase5` adds the book title, the authors, the year, the ISBN and the publisher to each chapter. It
also adds the PDF pages of each chapter. It reads two files that `convert` writes beside the `.md`:
`book.json` and `blocks.json`. You do not have to do anything when they are there.

A book that an older pdf2wiki converted has no `book.json`. Give `phase5` the PDF instead:

```bash
pdf2wiki phase5 ~/pdf2wiki/out/my-book/my-book.md --book my-book \
  --pdf ~/books/my-book.pdf --apply
```

Without either source, `phase5` still finds the ISBN, the year and the publisher on the copyright
page in the text. The title and the authors then stay out.

If `phase5` reports that it found no chapter boundaries, the Markdown has no usable H1 headings — check
the converted `.md` before the split.

## Next

- Repair or inspect diagrams: the Mermaid step runs automatically. See
  [troubleshooting](troubleshoot.md).
- Do this for many books at once: [run a batch](run-a-batch.md).
