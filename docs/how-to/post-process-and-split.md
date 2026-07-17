# Post-process and split into chapters

After [converting a book](convert-a-book.md) you have a single `<slug>.md`. `phase5` cleans it and
splits it into per-chapter files. It runs the [six-step chain](../reference/phase5-steps.md).

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

This overwrites the `.md` with the cleaned version and writes chapter files to
`~/pdf2wiki/out/my-book/chapters/` (override with `--out DIR`).

## Keep the source filename in frontmatter

Pass `--source-name` the original PDF filename. It becomes each chapter's frontmatter `source:` field,
so a staging or temp path never leaks into your published Markdown. Without it, the `.md` path is used.

## Chapter output

You get `00-front-matter.md` plus one `NN-slug.md` per chapter, each with YAML frontmatter
(`title`, `book`, `chapter`, `source`, `tags: [book]`). Image references stay relative, so keep the
`images/` folder alongside the chapter files. See [phase5 steps](../reference/phase5-steps.md#chapter-frontmatter).

If `phase5` reports that it found no chapter boundaries, the Markdown has no usable H1 headings — check
the converted `.md` before splitting.

## Next

- Repair or inspect diagrams: the Mermaid step runs automatically; see
  [troubleshooting](troubleshoot.md).
- Do this for many books at once: [run a batch](run-a-batch.md).
