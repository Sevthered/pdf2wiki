# QA a conversion

Before trusting a full conversion, spot-check the pipeline on a random sample of pages and back-check
the Markdown against the rendered PDF pages.

## 1. Sample pages

```bash
pdf2wiki qa sample ~/books/my-book.pdf my-book
```

This draws 20 random pages (change with `-n`) from the middle 5–95% of the book — skipping front and
back matter — and writes to `~/pdf2wiki/qa/my-book/`:

- `my-book_sample.pdf` — a small PDF of just those pages;
- `pages/*.png` — each sampled page rendered at 140 DPI (change with `--dpi`);
- `mapping.json` — which sample index maps to which original page.

Sampling is seeded (`--seed`, default 42), so the same command reproduces the same pages.

## 2. Convert the sample

Convert the small sample PDF like any book:

```bash
pdf2wiki convert ~/pdf2wiki/qa/my-book/my-book_sample.pdf --name my-book_sample \
  --out ~/pdf2wiki/qa/my-book/out
```

## 3. Build a review

Turn the sample's `blocks.json` into a per-page `review.txt` aligned with the PNGs:

```bash
pdf2wiki qa review ~/pdf2wiki/qa/my-book my-book
```

This writes `~/pdf2wiki/qa/my-book/review.txt` with a `SAMPLE NN (original page X)` section per page.

## 4. Back-check

Open `review.txt` next to the matching `pages/*.png` and compare: does the Markdown match the page?
Look especially at code fidelity, table grids, and figure captions. The
[stats glossary](../reference/output-layout.md#stats-glossary) helps you read the converter's counters.

> **Triage a directory of PDFs first?** Use `pdf2wiki scan <dir>` to print title/year guesses as JSON
> before deciding what to convert.
