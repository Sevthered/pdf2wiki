# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **Phase 5 no longer rewrites prose as code.** Each phase-5 step carried its own
  ``^(```)([a-zA-Z]*)\n(.*?)^``` `` regex. That pattern cannot match a fence whose info string is not
  letters-only (```` ```c++ ````, ```` ```c# ````, ```` ```objective-c ````,
  ```` ```java {highlight=2} ````) or a fence indented inside a list item — and instead of skipping
  such a block it began matching at the block's **closing** fence and paired it with the **next**
  block's opener, handing the text in between (prose included) to the step as a code body. Observed:
  `code_unescape` stripped markdown escapes out of prose, which its documentation forbids, and
  `lang_retag` wrote a language tag onto a closing fence, breaking the document. All five steps and
  `chapter_split` now share one lexer, `pdf2wiki.phase5.fences`, which follows CommonMark's fenced-code
  rules as far as converter output needs: indent up to three spaces, backtick fences of any length ≥ 3
  (see the tilde entry below for why not tildes too), a closing fence at least the opener's length,
  and free-form info strings. Re-emitting an untouched block is byte-identical. An opener with **no
  matching closer is not treated as a block**:
  CommonMark would render it as code to end of document, but these steps *rewrite* what they match, and
  letting one stray fence claim the document tail would strip escapes out of prose and make
  `chapter_split` swallow every later chapter boundary. A fence whose info string is Pandoc attribute
  syntax (```` ```{.python .numberLines} ````) is left alone rather than rewritten, and a caption lifted
  out of an indented fence keeps that indent so it stays inside its list item.
- **Language tags that the heuristic cannot detect are kept instead of downgraded to `text`.** With
  non-letter and indented fences finally visible, a specific-but-unrecognised tag fell through to the
  keyword heuristic. Added `pseudocode`, `cmake`, `makefile` (`make`, `mk`), `hcl`, `qml`, `vhdl`,
  `gherkin`, `graphql`, `c++`→`cpp`, `c#`/`cs`→`csharp`, `objective-c`/`objc`→`objectivec`,
  `js`→`javascript`, `ts`→`typescript`, `proto`→`protobuf`. MinerU's known-wrong guesses (`swift`,
  `erlang`) are still re-detected on purpose. Measured on a 1674-page reference vault, this preserves
  250+ correct author tags that the previous version rewrote. Tag resolution now consults the
  file-extension map as a fallback, so the alias table lives in one place instead of two.
- **The mermaid guard is case-insensitive** and tolerates an info-string suffix, so a
  ```` ```MERMAID ```` or ```` ```mermaid {theme} ```` block is no longer treated as ordinary code.
- **Mermaid node labels are no longer truncated.** `mermaid_repair` finished label sanitising with
  `s.strip("<br> ")`. `str.strip` takes a *character set*, so every label ending in `b`, `r`, `<`,
  `>`, or a space lost that run: `Load Balancer` → `Load Balance`, `Web` → `We`, `Broker` → `Broke`.
  Only whole leading/trailing `<br>` tokens are stripped now. Books converted with earlier versions
  carry the truncation in their output and need re-running from a pre-phase-5 markdown to recover it.
- **The code token-verify compare no longer flags every C++ block as diverged.** `convert/merge.py`
  stripped fences with `` ```\w* ``, which left `++` (or `#`) from a non-word info string in the
  compare stream. It now removes the whole fence line, anchored to line start — but stays
  backtick-only and indent-agnostic, matching the predicate the hybrid side of the comparison already
  used: a `~~~` run is real content in console output, and erasing it would have hidden genuine
  pipeline-vs-hybrid divergence, while refusing to strip a deeply indented fence would have flagged
  correct blocks.
- **`fences.py` no longer treats `~~~` as a fence character.** MinerU emits only backtick fences, and
  every book converted so far uses `~~~` runs as real content (console output, ASCII art) — but a
  **pair** of tilde divider rows in prose still lexed as one closed block, so `code_unescape`/
  `dash_normalize` rewrote the prose between them and `chapter_split` dropped any chapter boundary
  inside. A single stray tilde row was already inert (no matching closer); the pair was not. The
  lexer is backtick-only now, matching `convert/merge.py`'s `FENCE_LINE`, which already made this
  choice for the same reason. Measured on the 1674-page reference vault: zero blocks change (no
  tilde fences present), so the narrowing costs nothing there.
- **`lang_retag`'s new brace-family branches (previous entry) had five overclaim defects**, found by a
  blind review of their own diff and confirmed by executing the heuristic against the reference vault.
  Each guard was priced (old-vs-new FIXED/BROKEN over all 1674 pages) before landing and costs **0
  BROKEN**; a sixth, unrelated dead-code cleanup from the same review is listed last:
  - A bare `enum X {` (no `export`) is Java/C/C++/Rust far more often than TypeScript in this corpus;
    `TS_STRONG`'s enum alternative exempted it from the export-required rule the rest of the branch
    states as its own design rationale. `enum` now requires `export` like `interface`/`type`.
  - `C_FAMILY`'s `#\s*(include|define|...)` matched an ordinary comment whose first word happened to
    be "define"/"include" (`# define a helper` above a Python `def`, `# include the sidecar` above a
    YAML `services:`). The directive must now be glued to `#`; `#include` additionally requires the
    real `<...>`/`"..."` header syntax a comment never has.
  - `MAKEFILE`'s target-plus-recipe pattern (`target:` followed by a TAB-indented line) matched
    Python's `else:` and Go's `default:`/`case N:` with tab-indented bodies, since it needed only a
    bare colon-terminated token. The target name can no longer be a language keyword.
  - `MAKEFILE`'s built-in-function list included `basename`, which is as much a POSIX coreutils
    idiom (`$(basename "$0")`) as a Make call; `dirname` was already excluded by its own `\b` boundary
    but `basename` was not. Dropped.
  - The `html` gate only required a block to open with `<` and an HTML element name from its list;
    those names overlap non-HTML XML vocabularies (Atom `<link>`/`<title>`, DocBook `<table>`). A
    leading `<?xml` now short-circuits straight to the xml branch.
  - `mermaid_repair._san_inner` ended with a dead second `.strip()` (`str.strip` is idempotent) — a
    leftover from replacing the earlier `s.strip("<br> ")` character-set bug (previous entry). No
    behavior change; removed because it read as if the two calls did something different.

### Added
- **`lang_retag` detects C, C++, CMake, Rust, Go, JavaScript and TypeScript.** The keyword heuristic
  had no branch for any of them, so an untagged fence holding that code was mis-detected rather than
  merely missed: C++ `class Widget {` matched the python branch's bare `\bclass\b`, `Widget w =
  make_widget();` matched java's typed-var form, Go's `import (` matched python's bare `\bimport\b`,
  and TypeScript's `export function` matched the shell branch's `export` verb. Measured against the
  4175 blocks in a 1674-page reference vault that carry an author `c`/`cpp`/`cmake`/`rust`/`go`/
  `javascript`/`typescript` tag, the old heuristic scored **0% on every one of those seven
  languages** — they survived only because a specific tag is trusted before the heuristic runs, so
  the damage fell on the fences MinerU leaves generic. Each new branch is gated on a marker the other
  families cannot produce, and the whole group is resolved before the loose `java`/`python`/`bash`/
  `ruby` branches. Also added: `makefile`, `html` and `pseudocode` gates (Make shares Go's `:=`;
  a page with an inline `<script>` is HTML; Manning's algorithm listings borrow C-ish syntax), a
  terminal-session rule for a block that opens with a `$ ` prompt, and shell verbs for the new
  toolchains (`cargo`/`go` subcommands, `cmake`, `ctest`, `ninja`, `meson`, `bazel`, `gcc`, `clang`,
  `rustc`, `tsc`, `node`, `deno`, `bun`, `conan`, `vcpkg`, `gdb`, `valgrind`). Over the same
  reference set the change corrects **3804** blocks; every block it decides differently from the old
  version was traced to a fence whose recorded tag was itself wrong. `rust` and `typescript` have no
  ground truth in that vault (no such book is converted yet) and are covered by tests only. Detection
  order and its known limits: `docs/reference/phase5-steps.md`.

### Changed
- **llm-wiki plugin 0.1.1** — the bundled Claude Code plugin is versioned independently of the
  converter (`plugin/.claude-plugin/plugin.json`) and is delivered from `main` via
  `/plugin marketplace update pdf2wiki`, not through a PyPI release. This is a plugin-asset change
  only; the converter and its published package are untouched.
  - `knowledge-researcher` now **triages before reading**: it greps a ranked candidate list first and
    falls back to `wiki/index.md` / `wiki/domains/` only when that comes back empty, and it stops
    reading once two consecutive pages add nothing needed. Pages left unopened are declared under
    **Not covered** instead of being silently truncated. Measured on the reference vault, page reads
    were ~80% of the agent's token cost against ~12% for navigation, and constraining reads cut billed
    input by ~70% while still returning the large majority of must-have pages. Expressed as a stopping
    rule rather than a page count, because the right number depends on a vault's page granularity.
  - `knowledge-query` no longer tells readers that `wiki/hot.md` is "recent context, ~1 screen" and to
    read it first. That file is append-at-top and grows every session — on the reference vault it
    measures ~11k tokens, the largest navigation artifact — and the researcher agent already skipped
    it. Reading it is now conditional on the question being about recent vault work.

## [0.2.6] - 2026-07-24

A hardening, quality, and provenance release — the first published via signed, attested Trusted
Publishing. No converter behavior change: conversion output is byte-for-byte identical to 0.2.5.

### Added
- **Typed public API** — the package now ships `py.typed` (PEP 561), so downstream projects' type
  checkers see pdf2wiki's types. The core is `mypy --strict`-clean.
- **[REUSE 3.3](https://reuse.software/) licensing metadata** — per-file SPDX headers plus a
  `REUSE.toml`, so every file's copyright and license are machine-readable.
- **Project governance & security documentation** — `GOVERNANCE.md`, `CODE_OF_CONDUCT.md`
  (Contributor Covenant 2.1), `ROADMAP.md`, and a security **assurance case** at
  `docs/security/assurance-case.md` (threat model, trust boundaries, input-validation map).
- **OpenSSF tooling** — OpenSSF Best Practices badge, an OpenSSF Scorecard workflow, and Codecov
  coverage reporting, all surfaced in the README.

### Security
- **Signed releases.** Distributions are published via PyPI Trusted Publishing (OIDC, no stored
  token) with **PEP 740 provenance attestations**; release tags are cryptographically signed. Verify
  a tag with `git tag -v vX.Y.Z` and the PyPI attestations on each file's page.
- **Static analysis.** CI now runs ruff's `flake8-bandit` (`S`) security ruleset over `src/`.
- **DCO sign-off.** Contributions are signed off under the Developer Certificate of Origin
  (`git commit -s`); vulnerability reporters are credited in advisories unless they opt out.

### Changed
- **Internal typed-`Block` refactor** with a `mypy --strict` CI gate and Hypothesis property tests
  for the `phase5` transformers. Locked byte-identical by golden snapshots — no user-facing change.

## [0.2.5] - 2026-07-23

### Fixed
- **Long remote conversions no longer drop the SSH control channel.** During a long MinerU pass all
  output goes to a remote log file, so the SSH channel is silent for minutes; a NAT/idle timeout
  (common with WSL2 mirrored networking) could drop it, and the batch would then mislabel a
  still-running convert as `convert_failed` while the remote job kept going. All remote ssh/scp calls
  now send keepalives (`ServerAliveInterval=30`, `ServerAliveCountMax=240` ≈ 2 h of tolerated silence).
  If a drop still happens, a re-run resumes from cached (`.done`) passes. Found by the first full-book
  (354-page) remote run.

## [0.2.4] - 2026-07-23

### Fixed
- **Remote convert produced no output** (`no content_list.json`). `run_mineru` handed MinerU a
  *relative* `-o`/`-p`, but MinerU runs with a different working directory (the stdlib-shadow-safe
  `clean_cwd`), so its output landed where pdf2wiki couldn't find it. Only surfaced in `--remote` mode,
  where `--out` is passed home-relative. Now the paths handed to MinerU are absolutized
  (`os.path.abspath`) — idempotent for the already-absolute local case. Found by the first real
  end-to-end remote run; +1 regression test reproducing the cwd divergence.

## [0.2.3] - 2026-07-23

QA + diagnostics from an external review of the repo. No breaking changes; +4 tests (103 → 107).

### Added
- **`pdf2wiki qa flags PATHS...`** — per-book report of the code blocks where the VLM diverged from the
  byte-clean text layer (`_code_flag`), or where hybrid indentation failed a Python ast check
  (`_indent_flag`), read from `blocks.json`. Ranks multiple books by flagged count (which books to
  trust least) and lists each flagged block (page / language / snippet) for a single book — the
  highest-signal spots to spot-check.

### Changed
- **Batch summary rolls up `error_class`** — a partial batch now prints, e.g.,
  `5 book(s) not done — by class: permanent×3, timeout×1, fetch×1` (plus the slug list), so a cluster
  of same-kind failures reads as one diagnosis instead of N separate slugs. Exit code unchanged.

## [0.2.2] - 2026-07-23

Resilience + security hardening from a book-grounded review (Tech-Books vault: Backoff-Retries,
Circuit-Breaker-Pattern, Timeouts-Pattern, Unsafe-Consumption-of-APIs, SSRF-in-APIs). No API changes;
all existing behavior preserved. +10 tests (93 → 103).

### Security
- **Zip-slip guard**: the mineru.net result ZIP (downloaded from a server-supplied URL) is now
  validated member-by-member before extraction — a `../`/absolute member is rejected instead of
  overwriting arbitrary files.
- **HTTPS enforced** on the API base URL, the presigned upload URL, and the result-download URL before
  the Bearer token or the PDF is sent — a config/response downgrade to `http://` is refused.
- **Untrusted-response handling**: submit-response fields are validated (clear error instead of a raw
  `KeyError`); upstream error bodies are truncated + single-lined; presigned URLs are redacted (query
  stripped) in error messages.
- **Token hygiene**: `pdf2wiki.toml` is now gitignored and the config documents preferring
  `MINERU_API_TOKEN` / `token_file` over an inline token.

### Added
- **Retry with backoff + jitter** on the cloud HTTP calls (submit / upload / result download) and
  bounded tolerance for transient errors mid-poll — a momentary network blip or HTTP 429/5xx no longer
  fails an otherwise-healthy conversion. Transient (429/5xx/network) vs permanent (4xx/API-error) is
  classified; permanent errors still fail fast. Tunable: `[mineru_cloud].retries`, `retry_base_delay`,
  `poll_max_transient`.
- **Batch circuit breaker**: after `[remote].max_consec_fail` (default 3) consecutive book failures the
  batch re-probes executor health and aborts if the dependency is dead, instead of fast-failing every
  remaining book. A healthy probe continues (content failures don't trip it).
- **Per-pass cloud resume**: each cloud pass writes a `.done` sentinel; a re-run reuses a completed
  pass instead of re-uploading and re-paying (matches the local converter's `.done` caching).
- Manifest now records an `error_class` per failed book (transient / permanent / timeout / fetch / phase5).

### Changed
- **Remote convert timeout now kills the remote job**: the SSH convert wraps the converter in a
  server-side `timeout Ns` reaper, so a client-side timeout no longer leaves a zombie MinerU/vllm job
  pinning GPU VRAM. SSH/scp calls gain `ConnectTimeout` + `BatchMode=yes`; `fetch()` scp transfers are
  now timeout-bounded and remote paths are shlex-quoted.
- **Local MinerU timeout kills the whole process group** (`start_new_session=True` + `killpg`), so
  orphaned vllm/torch workers no longer survive a timed-out pass.

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

[Unreleased]: https://github.com/Sevthered/pdf2wiki/compare/v0.2.6...HEAD
[0.2.6]: https://github.com/Sevthered/pdf2wiki/compare/v0.2.5...v0.2.6
[0.2.5]: https://github.com/Sevthered/pdf2wiki/compare/v0.2.4...v0.2.5
[0.2.4]: https://github.com/Sevthered/pdf2wiki/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/Sevthered/pdf2wiki/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/Sevthered/pdf2wiki/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/Sevthered/pdf2wiki/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/Sevthered/pdf2wiki/compare/v0.1.2...v0.2.0
[0.1.2]: https://github.com/Sevthered/pdf2wiki/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/Sevthered/pdf2wiki/releases/tag/v0.1.1
[0.1.0]: https://pypi.org/project/pdf2wiki/0.1.0/
