# Convert a book

You have MinerU installed and a native-text PDF. This guide converts it to merged Markdown.

## Convert the whole book

```bash
pdf2wiki convert ~/books/my-book.pdf --name my-book
```

This writes `~/pdf2wiki/out/my-book/` containing `my-book.md`, `images/`, and `blocks.json`. Change the
output root with `--out DIR` or the `[convert] out_root` [config](../reference/configuration.md) field.

The run does a fast pipeline pass over every page, then hybrid VLM passes on the pages that carry
tables, images, code, equations, or charts, then merges them. Progress streams to your terminal.

## Convert a page range

`convert` always processes the whole book. To convert a slice for testing, use the
[QA sampler](qa-a-conversion.md), which builds a small sample PDF you can convert on its own.

## When the coverage gate stops the run

If the converter exits with a `CoverageError`, it found a page that has real text but produced zero
extracted blocks — a silently dropped page. This is intentional: pdf2wiki refuses to emit a book with
an invisible hole. See [troubleshooting](troubleshoot.md#coverage-gate-hard-stop).

## Re-running is cheap

Each MinerU pass is cached behind a `.done` sentinel. If a run fails partway, fix the cause and run the
same command again — completed passes are skipped and the run resumes. Do **not** delete the `base_*` /
`hy_*` directories unless you want a full re-conversion.

## Next

- Post-process and split into chapters: [post-process and split](post-process-and-split.md).
- Convert many books: [run a batch](run-a-batch.md).
