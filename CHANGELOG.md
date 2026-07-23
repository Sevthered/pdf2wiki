# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.1] - 2026-07-23

### Changed
- `requests` is now a **core dependency**; the `cloud` optional extra introduced in 0.2.0 is removed.
  `pip install pdf2wiki` includes the `--mineru-cloud` converter out of the box — install `pdf2wiki`,
  not `pdf2wiki[cloud]`.

## [0.2.0] - 2026-07-23

### Added
Three GPU-less / offload conversion paths, so a machine with no local GPU (or no MinerU at all) can still
convert:
- `convert --hybrid-server-url URL` — offload only the hybrid VLM pass to a BYO OpenAI-compatible MinerU
  server; the pipeline pass stays local (runs on CPU). Effort / image-analysis (Mermaid, chart
  transcription) is preserved. Mutually exclusive with `--remote`; fails fast (never silently falls back).
- `convert --mineru-cloud` — fully-managed conversion via the mineru.net Precision API: no GPU, no MinerU
  install, token only. `--cloud-model pipeline` (default, code-safe) | `vlm` | `MinerU-HTML`. Uploads the
  PDF to a third-party cloud (loud data-egress warning), ≤200 pages/file, token never logged. Needs the
  new `cloud` extra: `pip install 'pdf2wiki[cloud]'`.
- `convert --mineru-cloud --cloud-model merge` — runs BOTH cloud passes (pipeline + vlm) and splices them
  with pdf2wiki's own base-driven merge locally: byte-clean code (pipeline tokens) AND correct
  indentation / tables / Mermaid (vlm), fully GPU-less. Costs 2× the daily page quota and 2× egress.
- New `[mineru_cloud]` config section and `[mineru].hybrid_server_url` setting.
- Docs: how-to guides for offloading the hybrid pass and converting in the cloud.

### Fixed
- The code-diverge merge path now recovers Python indentation from the hybrid pass (fuzzy `difflib`
  re-indent) instead of emitting flat pipeline tokens — Python code with genuine token divergence keeps
  its indentation.

## [0.1.2] - 2026-07-18

### Fixed
Five HIGH-severity correctness/robustness findings from a pre-publish deep scan (all also present in
0.1.0/0.1.1), each landed with a regression test:
- Watermark detection now buckets repeated lines by absolute page, not the chunk-relative `page_idx`
  that reset every pipeline segment — per-page DRM footers on multi-chunk (multi-hundred-page) books
  were never removed before.
- All text files are now opened with `encoding="utf-8"`, so conversion no longer crashes with a
  `UnicodeDecodeError` under a non-UTF-8 locale (e.g. an SSH session with `LANG` unset) on the
  non-ASCII characters real books contain.
- `qa sample` no longer raises `ValueError: Sample larger than population` on short books: the sample
  count is clamped to the available page window (with the whole book used when the 5–95% window is
  empty).
- Chapter-split YAML frontmatter is now emitted with JSON-quoted scalars, producing valid YAML for
  titles containing mixed quotes/backslashes and for `source` filenames containing `:`/`#`/flow
  characters (previously such values produced unparseable frontmatter).
- A single book's convert or fetch failure (e.g. an SSH `TimeoutExpired` or a missing MinerU binary)
  is now caught and recorded per-book instead of aborting the entire batch.

Six MEDIUM findings from the same scan:
- A NUL byte in a code block no longer crashes conversion — the Python indentation sanity check
  (`ast.parse`) now catches the `ValueError` it raises alongside `SyntaxError`.
- A MinerU pass that times out now surfaces as the documented clean hard-stop (`PassFailed`, completed
  passes stay cached) instead of an uncaught `subprocess.TimeoutExpired`.
- `scan` now captures page-level read errors per file (`{file, error}`) instead of letting one corrupt
  page abort the scan of every remaining PDF in the directory.
- `batch` now exits non-zero when any book did not reach `done`, so CI/automation can detect a partial
  run (it previously always exited 0).
- Destination-less level-1 PDF bookmarks (which `get_toc()` reports at page −1) are now dropped instead
  of injecting a spurious H1 at the top of the document and corrupting the chapter split.
- The shared block renderer now tolerates explicit JSON-null field values (not just missing keys),
  fixing crashes when the converter emits a null `content`/`text`/`code_body`.

## [0.1.1] - 2026-07-17

### Added
- `pyproject.toml` project URLs: Repository, Documentation, Issues, and Changelog — so the PyPI page
  links to the GitHub repo and docs.
- README badges (PyPI version, supported Python versions, license).
- `CHANGELOG.md` and `CONTRIBUTING.md`.

### Fixed
- The `phase5` command summary now reports the `code_unescape` step (it ran before but was omitted from
  the printed report).

## [0.1.0] - 2026-07-17

### Added
- Initial release.
- `convert` — dual-pass MinerU pipeline: a `pipeline -m txt` base pass (byte-perfect code from the
  embedded text layer) merged with a hybrid/VLM pass (table grids, Mermaid diagrams), with code
  token-verification and a coverage gate that hard-stops on dropped pages.
- `phase5` — six-step post-processing chain (caption unbleed, language re-tag, dash normalize, Mermaid
  repair, code unescape, chapter split with YAML frontmatter).
- `qa` — reproducible page sampling and per-page review artifacts.
- `scan` — PDF directory triage (title/year guesses).
- `batch` — manifest-driven, resumable multi-book runs with optional SSH-remote GPU execution.
- Full documentation set under `docs/` (Diátaxis: tutorials, how-to, reference, explanation) plus an
  arc42/C4 architecture overview.

[0.1.2]: https://github.com/Sevthered/pdf2wiki/releases/tag/v0.1.2
[0.1.1]: https://github.com/Sevthered/pdf2wiki/releases/tag/v0.1.1
[0.1.0]: https://github.com/Sevthered/pdf2wiki/releases/tag/v0.1.0
