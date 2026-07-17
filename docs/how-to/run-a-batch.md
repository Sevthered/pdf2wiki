# Run a batch

`batch` converts and post-processes many books from a manifest, resumably. It runs
`convert → phase5 → optional placement` per book, one at a time.

## Write a books manifest

Create a TOML file with one `[[book]]` entry per book:

```toml
[[book]]
pdf = "~/books/effective-go.pdf"
slug = "effective-go"
domain = "go-lang"

[[book]]
pdf = "~/books/microservices-patterns.pdf"
slug = "microservices-patterns"
domain = "distributed-systems"
```

`pdf` and `slug` are required. `domain` is optional; when set (and you use `--vault`), it becomes a
subfolder under the vault. In [remote mode](set-up-remote-gpu.md), `pdf` is a filename under the remote
`books_dir`, not a local path.

## Run it

```bash
pdf2wiki batch books.toml
```

To also place the finished chapters into a knowledge base, set `--vault` (or `[output] vault` in
[config](../reference/configuration.md)):

```bash
pdf2wiki batch books.toml --vault ~/Obsidian/Tech-Books
```

Chapters land in `<vault>/<domain>/<slug>/`.

## Resume, filter, limit

The batch records a `manifest.json` in the stage dir (`--stage`, default `~/pdf2wiki/stage`). On
re-run, only books with status `done` are skipped — any failed book is retried. Useful flags:

- `--only SLUG` — run just one book.
- `--max-books N` — stop after N books attempted this run.
- `--remote HOST` — convert on a remote GPU host.

## Stop cleanly

To halt a long batch between books (not mid-conversion), create a `STOP` file in the stage dir:

```bash
touch ~/pdf2wiki/stage/STOP
```

The batch finishes the current book, consumes the `STOP` file, and exits. Re-run later to continue.

## Read the manifest

Each slug's status is one of `convert_failed`, `fetch_failed`, `phase5_failed`, or `done` — see
[manifest states](../reference/pipeline-stages.md#batch-manifest-states). A failure is recorded and the
batch moves on; it never aborts the whole run. Inspect `manifest.json` to see what failed, fix it, and
re-run.
