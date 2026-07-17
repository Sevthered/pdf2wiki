# Design principles

The conventions that shape how pdf2wiki behaves. Knowing these explains why commands act the way they
do.

## Dry-run by default

Every command that would modify existing files is a dry-run until you pass `--apply`. `phase5` reports
exactly what it would change and writes nothing without it. The exceptions are `convert` and `qa`,
whose whole purpose is to create new artifacts in their own output directories — they never touch
existing files, so they run for real. The principle: a command should never surprise you by
overwriting.

## Idempotent fixers

Each phase 5 transformer can run twice with no additional effect. Re-running the chain on already-clean
Markdown is safe and a no-op. This makes the pipeline forgiving: if you are unsure whether a step ran,
run it again.

## Resumable conversion

A conversion is a sequence of MinerU passes, each cached behind a `.done` sentinel that is written only
after the pass exits cleanly and produced output. A crash loses only the pass in flight; a re-run skips
every completed pass and continues. This is why re-converting a book that mostly finished is cheap.

## Zero-fail scrape

The [coverage gate](how-the-merge-works.md#the-coverage-gate) hard-stops rather than emit a book with a
silently dropped page. A loud, fixable failure is preferred over a quiet gap. The same instinct drives
code token-verify: divergent code is flagged, never silently trusted.

## Never suppress the subprocess

MinerU's stderr is captured to a per-pass log, never discarded. When a pass fails, the error report
names the exact pass, page range, and log path — because a swallowed traceback costs far more time than
it saves.

## Clean working directory

MinerU (via vLLM/torch) imports stdlib modules like `profile`, `inspect`, and `code` at runtime. If it
runs from a directory containing a helper named after one of those modules, Python imports the helper
instead and fails cryptically. So MinerU subprocesses always run from a dedicated clean working
directory (`[convert] workdir`), never the project directory.

## Check connectivity once

In remote mode the SSH connection is verified a single time up front. A dead connection then fails fast
with a clear message, instead of failing every book in a batch near-instantly and mislabeling the whole
run. Remote success is judged by the remote command's exit code, never by scanning the log for words
like "error" — a technical book's own text is full of them.

## Sequential batch

`batch` processes books one at a time. The pipeline is built around a single GPU, so there is no
concurrency to exploit; sequential keeps VRAM predictable and failures isolated — one book's failure
never aborts the run.
