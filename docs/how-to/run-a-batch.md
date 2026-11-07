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

`pdf` and `slug` are required. `domain` is optional. When set (and you use `--vault`), it becomes a
subfolder under the vault. In [remote mode](set-up-remote-gpu.md), `pdf` is a filename under the remote
`books_dir`, not a local path.

## Run it

```bash
pdf2wiki batch books.toml
```

To also place the finished chapters into a knowledge base, set `--vault` (or `[output] vault` in
[config](../reference/configuration.md)):

```bash
pdf2wiki batch books.toml --vault ~/Obsidian/MyVault
```

Chapters land in `<vault>/<domain>/<slug>/`.

## Link the cross-references

To link "figure 6.2", "listing 4.1" and "chapter 5" to their targets, add `--links`:

```bash
pdf2wiki batch books.toml --vault ~/Obsidian/MyVault --links obsidian
```

You can also set `[output] links` in the [config](../reference/configuration.md).
The `obsidian` style puts a block id on each caption.
The `markdown` style puts an HTML anchor on it.
See [cross-references](../reference/phase5-steps.md#cross-references) for the rules.

The batch skips a book with the status `done`, also when you change the style.
For each such book, the batch prints a note with the `pdf2wiki link` command for its chapter folder.
The folder is the vault copy when the book has one, else the staged chapters.
A book without a `domain` is in `<vault>/<slug>`.

```bash
pdf2wiki link ~/Obsidian/MyVault/<domain>/<slug> --style obsidian --apply
```

The manifest does not record a link that `pdf2wiki link` makes.
Thus the note comes back on each later run with that style.

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
batch moves on. It never aborts the whole run. Inspect `manifest.json` to see what failed, fix it, and
re-run.
