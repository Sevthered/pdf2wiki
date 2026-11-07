# CLI reference

Every `pdf2wiki` command, flag, default, and exit code. For task-oriented walkthroughs see the
[how-to guides](../how-to/). For the config file see [configuration](configuration.md).

```
pdf2wiki [--version] [--config PATH] <command> ...
```

`--version` prints `pdf2wiki <version>` and exits.

`--config PATH` points at an explicit config TOML. A path that does not exist is an error (exit 2).
Without it,
pdf2wiki reads `~/.config/pdf2wiki/config.toml` and then `./pdf2wiki.toml`, over the built-in defaults.
The project file wins. See [configuration](configuration.md).

**Dry-run convention:** mutating commands default to dry-run and require `--apply` to write. The
exceptions are `convert` and `qa`, whose purpose is to produce new artifacts in their own output
directories — they never modify existing files in place.

## `convert`

Convert one PDF into merged Markdown with the [dual-pass pipeline](../explanation/how-the-merge-works.md).

```
pdf2wiki convert <pdf> --name <slug> [--out DIR]
                       [--remote HOST | --hybrid-server-url URL | --mineru-cloud [--cloud-model MODEL]]
```

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `pdf` | yes | — | Path to the source PDF (local mode), or a filename under the remote `books_dir` when `--remote` is used. |
| `--name` | yes | — | Output slug. It names the output folder and the `.md` file. |
| `--out` | no | `convert.out_root` (`~/pdf2wiki/out`) | Output root. The book lands in `<out>/<slug>/`. |
| `--remote` | no | `remote.host` from config | SSH host to run the *whole* conversion on (experimental — see [configure a remote GPU host](../how-to/set-up-remote-gpu.md)). |
| `--hybrid-server-url` | no | `mineru.hybrid_server_url` from config | Offload **only** the hybrid VLM pass to a BYO OpenAI-compatible MinerU server. The pipeline pass stays local (runs on CPU). Preserves `--effort` (Mermaid/chart transcription). See [offload the hybrid pass](../how-to/offload-hybrid-to-a-server.md). |
| `--mineru-cloud` | no | off | Convert via the fully-managed [mineru.net](https://mineru.net) Cloud — **no GPU, no local MinerU**, token only. Uploads the PDF to a third-party cloud. See [convert in the cloud](../how-to/convert-in-the-cloud.md). |
| `--cloud-model` | no | `mineru_cloud.model_version` (`pipeline`) | Cloud parse model, only with `--mineru-cloud`: `pipeline` (code-safe, flat indent) · `vlm` (indent/tables but corrupts code) · `MinerU-HTML` · `merge` (runs both `pipeline`+`vlm` in the cloud and splices locally = clean code **and** indent/tables, GPU-less, and costs 2× quota). |

`--remote`, `--hybrid-server-url`, and `--mineru-cloud` are **mutually exclusive** convert strategies.
If you pass more than one, the command exits with code `2` and a message that names the conflict.
It does not choose one silently.

Writes `<out>/<slug>/<slug>.md`, `images/`, `blocks.json`, and `book.json` — see
[output layout](output-layout.md).
Exit code `0` on success. Exit code `1` on failure: a MinerU or cloud pass failed, or the
[coverage gate](../explanation/how-the-merge-works.md#the-coverage-gate) hard-stopped. Exit code `2`
on a mutually-exclusive-flag misuse.

## `phase5`

Run the [post-processing chain](phase5-steps.md) on a converted `.md` and split it into
per-chapter files. **Dry-run by default** — pass `--apply` to write.

```
pdf2wiki phase5 <md> --book <slug> [--out DIR] [--source-name PDF] [--pdf PDF]
                     [--links off|obsidian|markdown] [--apply]
```

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `md` | yes | — | Path to the converted `.md`. |
| `--book` | yes | — | Book slug written into each chapter's frontmatter. |
| `--out` | no | `<md dir>/chapters` | Directory for the split chapter files. |
| `--source-name` | no | the `md` path | Original PDF filename for the frontmatter `source:` field (keeps staging paths out of frontmatter). |
| `--pdf` | no | `book.json` beside the `md` | Read the book metadata (title, authors, year, ISBN, publisher) from this PDF. Use it for a book that an older pdf2wiki converted, which has no `book.json`. A path that cannot be read stops the command with exit code `2` before it writes a file. See [where the book metadata comes from](phase5-steps.md#where-the-book-metadata-comes-from). |
| `--links` | no | `off` | Link the cross-references across the chapter files: `obsidian` (block ids) or `markdown` (HTML anchors). See [cross-references](phase5-steps.md#cross-references). |
| `--apply` | no | off (dry-run) | Write the chapter files. The source `.md` is not changed. Without it, pdf2wiki reports what it would do and writes nothing. |

Prints a per-step report (unwrapped captions, retag count, dash/mermaid/unescape fixes, chapter
boundaries). The `book_index` line names the metadata source and each field found, with its rule. The
`pdf_pages` line says how many chapters got a page range. With `--apply`, `phase5` also writes
`<slug>-index.md` beside the chapter files. Exit code `0`.

## `link`

Link the cross-references in a folder of chapter files that exists, such as a book in a vault. It is
the `xref` step of `phase5`, without the rest of the chain. **Dry-run by default.** Pass `--apply` to
write.

```
pdf2wiki link <dir> [--style obsidian|markdown] [--apply] [--json]
```

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `dir` | yes | — | The folder that holds the chapter files of one book. |
| `--style` | no | `obsidian` | `obsidian`: block ids on captions. `markdown`: HTML anchors, which Obsidian does not follow. Both write relative links. See [cross-references](phase5-steps.md#cross-references). |
| `--apply` | no | off (dry-run) | Write the chapter files that change. The command writes these files in place. Without it, pdf2wiki reports what it would do and writes nothing. |
| `--json` | no | off | Print the report as JSON. The report also lists the files that change. |

A chapter file is a `.md` file whose frontmatter holds `book:` and `chapter:`, as `phase5` writes it.
The command does not change other files, such as `<slug>-index.md`. It stops with exit code `2` when
the folder holds no chapter file. It also stops when the folder holds chapter files of more than one
book, because a link must not point into another book.

With `--apply`, the command writes each changed file to a temporary file first, then replaces the
chapter files. If a temporary file cannot be written, no chapter file changes, and the command stops
with exit code `2`. If a replace fails, the error names how many files were written. A second run
with `--apply` writes no file.

A file with only CRLF line ends keeps them. Other files get LF line ends. A file keeps its mode.
For a symlink, the command writes the file that the link points to.
Exit code `0`.

## `compare`

Compare the `.md` files of two folders, such as the output of two `phase5` runs. The command only
reads the folders. See [compare the output of two versions](../how-to/compare-two-versions.md).

```
pdf2wiki compare <old> <new> [--ignore-key KEY... | --no-ignore] [--diff N] [--json]
```

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `old` | yes | — | The folder of the old output. It can hold one book or a folder for each book. |
| `new` | yes | — | The folder of the new output. |
| `--ignore-key` | no | `source` | Remove this top-level frontmatter key before the compare. Give the flag one time for each key. The keys you give replace the default. |
| `--no-ignore` | no | off | Compare all frontmatter keys, also `source`. You cannot use it with `--ignore-key`. |
| `--diff` | no | `0` | Print the first N lines of the unified diff of each different file. `0` prints no diff. The `@@` line numbers are the line numbers of the real files. The text output shows a carriage return as `␍`. |
| `--json` | no | off | Print the report as JSON. The JSON report also lists the files that are the same. |

The command pairs the files by their path in the folder. It compares the text of Markdown files only:
`.md` and `.markdown`, in uppercase or lowercase. It pairs the other files too, but it does not read
them. A file of any type in one folder only is a difference.

The command follows a symlink to a file. It does not go into a symlink to a folder (`os.walk` with
`followlinks=False`). It pairs that symlink like a file that it does not read.

An ignored key is removed only from the frontmatter at the start of the file. The lines below the key
that start with a space, a tab or `- ` are removed too, because they hold the rest of its value. A
blank line in the value is removed when the value continues after it. A body line is never removed.

A CRLF file is different from the same LF file. A file that is not valid UTF-8 is compared as bytes,
with no line counts and no diff.

Exit code `0` when all Markdown files are the same and no file is in one folder only. Exit code `1`
when a Markdown file is different or a file is in one folder only. Exit code `2` on an error. For
example, a folder does not exist, OLD and NEW are the same folder, or one folder is in the other. A
file that cannot be read also gives exit code `2`.

## `listings`

Count, export and check the code blocks in a folder of chapter files. The command does not change
the chapter files.

```
pdf2wiki listings <dir> [--out NEW_DIR] [--check] [--json]
```

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `dir` | yes | — | The folder that holds the chapter files of one book. |
| `--out` | no | — | Write each code block to its own file in `NEW_DIR`, and write `index.json`. `NEW_DIR` must not exist or must be empty. See [exported listings](output-layout.md#exported-listings). |
| `--check` | no | off | Parse each code block, and put each failure in one class. |
| `--json` | no | off | Print the report as JSON. |

The command reads the same chapter files as `link`. A code block starts with a backtick fence and
ends with a closing fence. A fence with no closing fence is not a block. Without options, the
command prints the number of blocks for each language and for each chapter file.

With `--out`, the command stops with exit code `2` when `NEW_DIR` holds a file. The command never
writes over a file. Each file holds the text of one block, with LF line ends.

`--check` uses only the Python standard library:

| Language tag | Check |
|--------------|-------|
| `python`, `py`, `python3` | `ast.parse` |
| `json` | `json.loads` |
| `toml` | `tomllib.loads`. The result depends on the Python version. |
| `xml` | `xml.etree.ElementTree.fromstring`. Use it only on files that you trust, such as your own books. |
| `go`, `c`, `cpp`, `java`, `javascript`, `typescript`, `rust`, `csharp`, `kotlin`, `swift`, `scala`, `php`, `dart`, `groovy` | The brackets `()[]{}` must balance outside strings and comments. |
| other tags, or no tag | Not checked. |

The check puts each block in one class:

| Class | Meaning |
|-------|---------|
| `ok` | The block parses. |
| `fragment` | The block is a part of a program. Python: a REPL session, an elision (`…`), or an indented excerpt. Brace languages and JSON: the brackets open before the block or close after it. JSON can also be an elision, a member list, or several documents. XML can have several top-level elements. |
| `wrong-language?` | The block fails for its tag. The language detector of `phase5` names a different language, and the block passes the check of that language. A block of pseudocode, HTML or HTTP under a checked tag is also in this class. |
| `error` | Any other failure. The report shows the message of the parser. |

`--check` always exits with code `0`. A book often shows code in parts, so a failed parse is not a
failure of the command.

The report counts the classes for each language. It lists each `error` and `wrong-language?` block
as `file:line lang class: message`. The line is the line of the opening fence. A line number in a
message counts from the first line of the block.

The command stops with exit code `2` when the folder holds no chapter file, or chapter files of more
than one book. Otherwise the exit code is `0`.

## `qa sample`

Sample random pages into a small PDF plus rendered PNGs, so you can convert just the sample and
back-check it. See [QA a conversion](../how-to/qa-a-conversion.md).

```
pdf2wiki qa sample <pdf> <name> [-n PAGES] [--seed SEED] [--dpi DPI] [--qa-root DIR]
```

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `pdf` | yes | — | Source PDF. |
| `name` | yes | — | QA run name (names the QA subfolder). |
| `-n`, `--pages` | no | `qa.pages` (`20`) | Number of pages to sample. |
| `--seed` | no | `qa.seed` (`42`) | RNG seed (reproducible sampling). |
| `--dpi` | no | `qa.dpi` (`140`) | PNG render resolution. |
| `--qa-root` | no | `qa.root` (`~/pdf2wiki/qa`) | QA output root. |

Pages are drawn from the middle 5–95% of the book to skip front/back matter. Writes
`<qa-root>/<name>/<name>_sample.pdf`, `pages/*.png`, and `mapping.json`.

## `qa review`

Build a per-page `review.txt` from a converted sample's `blocks.json`, aligned with the sample PNGs.

```
pdf2wiki qa review <qa_dir> <name> [--blocks PATH]
```

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `qa_dir` | yes | — | The QA run directory (from `qa sample`). |
| `name` | yes | — | QA run name. |
| `--blocks` | no | `<qa_dir>/out/<name>_sample/blocks.json` | Explicit `blocks.json` path. |

Writes `<qa_dir>/review.txt`.

## `doctor`

Check this machine and the remote host. The command is read-only and has no `--apply` flag.

```
pdf2wiki doctor [--remote HOST] [--json]
```

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--remote HOST` | no | `[remote].host` | SSH host to check. |
| `--json` | no | off | Print `{"version", "checks", "fails", "warns"}` as JSON. |

Each check has a status. The human output shows `ok`, `warn`, `FAIL`, or `skip`. The JSON `status`
field holds `ok`, `warn`, `fail`, or `skip`. A failed check has a `fix:` line. In JSON, it is the
`fix` field.
The command checks these groups:

- **core:** Python, pdf2wiki, and PyMuPDF versions. The config files that were read. A `--config` path
  that does not exist is a failure. An inline `[mineru_cloud].token` is a warning in any config file
  but the user file.
- **local convert:** The MinerU binary and version. Whether the MinerU torch sees CUDA. The GPU
  name and memory. A C compiler. A workdir with no names that shadow the standard library, and no other
  Python modules. Free disk space. On other systems than Linux, the group is one `skip` line. When
  `[mineru].hybrid_server_url` is set, the MinerU binary and version checks also run there.
- **hybrid server:** A TCP connection to `[mineru].hybrid_server_url`. The command sends no HTTP request.
- **remote:** A check that the host is a valid SSH destination (a value that starts with `-` is
  refused). SSH access, the remote pdf2wiki version, and `[remote].books_dir`. When SSH fails, the
  command compares the subnet of this machine with the subnet of the host. It tells you when this
  machine is on another network.
- **cloud:** The place and the length of each configured mineru.net token. The command never prints
  the token. It sends nothing to mineru.net.

Exit codes: `0` when no check failed, `1` when at least one check failed.

## `scan`

Scan a directory of PDFs and print title/year guesses as JSON — a triage aid, not ground truth.

```
pdf2wiki scan <directory>
```

Prints a JSON array, one record per PDF: `{file, pages, title, title_conf, year, year_conf}`. The
`*_conf` fields report how each guess was derived (e.g. `text`, `filename-fallback`, `copyright-line`,
`loose-year`, `none-found`).

## `batch`

Convert many books from a manifest, resumably. See [run a batch](../how-to/run-a-batch.md).

```
pdf2wiki batch <books.toml> [--stage DIR] [--remote HOST] [--max-books N] [--only SLUG] [--vault DIR]
               [--links off|obsidian|markdown]
```

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `books` | yes | — | Books TOML with `[[book]]` entries (`pdf`, `slug`, optional `domain`). |
| `--stage` | no | `~/pdf2wiki/stage` | Staging dir. It also holds the resume `manifest.json` and the `STOP` file. |
| `--remote` | no | `remote.host` from config | SSH host to convert on. |
| `--max-books` | no | unlimited | Stop after this many books *attempted* this run. |
| `--only` | no | — | Run only this slug. |
| `--vault` | no | `output.vault` from config | Final placement root. Chapters copy to `<vault>/<domain>/<slug>/`. |
| `--links` | no | `output.links` from config, else `off` | Link the cross-references in each book, as `phase5 --links`. See [cross-references](phase5-steps.md#cross-references). |

Runs `convert → fetch → phase5 → optional vault placement` per book, sequentially. Resumable: only a
book with status `done` is skipped on re-run. Any failed book retries. Drop a file named `STOP` in the
stage dir to halt cleanly between books. See [manifest states](pipeline-stages.md#batch-manifest-states).

With `--links`, the manifest entry of a book records the style in `links`.
A book with the status `done` is not linked again when you change the style.
To link it, run [`pdf2wiki link`](#link) on its chapter folder.
