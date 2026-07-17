# Convert your first book

This tutorial takes you from a PDF on disk to clean, chapter-split Markdown. Follow it start to finish
on one book — every step is spelled out and nothing branches. By the end you will have run the whole
pipeline once and seen what it produces.

You need pdf2wiki and MinerU installed already. If you don't, do that first:
[install pdf2wiki](../how-to/install.md). You also need one **native-text** technical-book PDF (a
normal digital PDF, not a scan).

## Step 1 — Convert the PDF

Pick your PDF and give the output a short name (a *slug*):

```bash
pdf2wiki convert ~/books/effective-go.pdf --name effective-go
```

pdf2wiki reads every page, runs the vision model on the pages that have tables, figures, or code, and
merges the two into one Markdown file. You'll see progress stream by. When it finishes, look at what it
made:

```bash
ls ~/pdf2wiki/out/effective-go/
```

You should see:

```
effective-go.md    images/    blocks.json    base_0_39/    hy_...
```

`effective-go.md` is your whole book as Markdown. Open it — the code should be exact and the tables
should have real grids.

## Step 2 — Preview the post-processing

The raw Markdown is one long file. The `phase5` command cleans it up and splits it into chapters. Run
it first **without** writing anything — this is a preview:

```bash
pdf2wiki phase5 ~/pdf2wiki/out/effective-go/effective-go.md --book effective-go
```

Read the output. It tells you how many captions it lifted, how many code languages it re-tagged, and —
at the end — the list of chapters it found. Nothing has been written yet.

## Step 3 — Apply it

Happy with the preview? Run it again with `--apply` to write the files:

```bash
pdf2wiki phase5 ~/pdf2wiki/out/effective-go/effective-go.md \
  --book effective-go \
  --source-name effective-go.pdf \
  --apply
```

Now look at the chapters:

```bash
ls ~/pdf2wiki/out/effective-go/chapters/
```

```
00-front-matter.md   01-introduction.md   02-...
```

Open one. It starts with a small YAML block (`title`, `book`, `chapter`, …) and contains just that
chapter, ready to drop into a Markdown knowledge base.

## What you just did

You ran the whole pipeline: a dual-pass conversion, then a six-step cleanup and chapter split. That's
the core loop.

## Next steps

- Understand *why* it works this way: [why a dual-backend pipeline](../explanation/why-dual-backend.md).
- Convert many books at once: [run a batch](../how-to/run-a-batch.md).
- Check a conversion's quality: [QA a conversion](../how-to/qa-a-conversion.md).
