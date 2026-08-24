# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **A dropped Symbol space at a line end no longer uncovers a backslash hard break.** `symbol_pua`
  deletes a `U+F020` at a line edge, because two real spaces there are a hard break in CommonMark.
  CommonMark has a second hard break, spec 6.7: a line-final unescaped backslash. A line that ends
  in a backslash and then a Symbol space has no break, because the Symbol space is the last
  character. The drop made the backslash line-final and added a break the printed page does not
  have. One real space stays now, which keeps the rendering and is no break. The run of backslashes
  decides it. An even run is an escape, it prints one literal backslash, and it never broke a line.
  Counted as `tail_backslash_spaced_f020`, apart from the space cut-back, because it adds a
  character where the cut-back removes them. Measured with cmark, the reference implementation, over
  108 line shapes: 10 of them changed whether the line breaks before this fix, and 0 do after it. No
  converted file holds `U+F020` (221 files, 2,392 vault pages), so the defect is latent.
  ([#78](https://github.com/Sevthered/pdf2wiki/issues/78))

### Changed
- **The position truth table holds 46,668 shapes (from 36,948), and it reaches the new counter.**
  No body in the table ended in a backslash, so no shape reached `tail_backslash_spaced_f020` while
  its sibling `tail_collapsed_f020` was reached 8,856 times. A refactor that deleted the new rule
  reproduced the snapshot AND its sha256 digest without a change. A backslash-terminated body closes
  that hole: 2,160 shapes reach the counter now, and the rule was removed once to prove the table
  fails without it. The count of shapes that change again on a second pass is still 15, and every
  one is still the filed pair of adjacent markers.

## [0.2.10] - 2026-08-23

### Added
- **Deterministic tests for the unclosed-label branch of `mermaid_repair`.** Only a property test
  reached that branch, and only when hypothesis generated an unclosed label. Six identical coverage
  runs gave two different totals, and the true value sat on the 93/94 rounding boundary. Five new
  tests close an unclosed `[`, `{` and `(` label, a `'` opener, and prove the repair is idempotent.
  A clean Mermaid block now has a test too. `mermaid_repair` is at 100% without hypothesis, and the
  project total is the same number on every run.
- **`symbol_pua` reads a second list marker, `U+F077`.** *Advanced Algorithms and Data Structures*
  p494 prints a filled diamond from the `Wingdings` font at the start of each list item. The step
  knew only the `Wingdings2` square, `U+F0A1`. A line that opens with the diamond is a list item
  now. The release note of 0.2.9 reported the codepoint under `unknown`. A rendered page verified
  the reading, as the table requires. The evidence is per reading. No page shows the diamond
  promoted to a heading, so after a heading's hashes the step keeps it and counts it as
  `line_leading_marker_deferred`. The square keeps its verified heading reading.
- **A marker that opens a line before an operator is not a list item.** Each marker slot is a Greek
  letter in the Adobe Symbol encoding (`0x77` is omega, `0xA1` is Upsilon1). The step keeps a marker
  that an operator follows, and counts it as `line_leading_marker_deferred`. The operators are `=`,
  `≈`, `≠`, `≡`, `±`, `×`, `÷`, the arrows, `∇`, `≤`, `≥`, `∈`, `∉` and `∞`. The set holds operators
  only, and not `·`, which is what the step makes of a verified inline dot. A bullet before a formula
  is a real list item in this corpus: *Advanced Algorithms* p445 prints a square before
  `d*(n+k)*log(k) < n*k*d ⇔ ...`, and `<` and `>` cost six real items in *Microservices
  Patterns*.
  The marker counts of all 219 converted files are unchanged.
- **A new residue, `marker_no_reading`.** Only `U+F0A1` has a verified reading in the middle of a
  line, where the step deletes it as a separator. `U+F077` has none, so the step keeps it there and
  reports it. The `phase5` and `batch` commands print the count, with the instruction to render the
  page.

### Changed
- The position truth table holds 20,748 shapes (from 10,232). It covers both markers, and a body
  that starts with a letter before an operator (`x = 2`), which is text. 360 rows of the old table
  moved, every one with `= 2x` after the marker, and none other. Across all diamond shapes the
  positional reading equals the square's, the diamond is never deleted, and it survives exactly where
  the square was deleted.
- The idempotence test still counts 15 unstable shapes, all `U+F0A1` pairs. A first version of
  the second marker promoted it to a heading, and 12 new shapes changed on the second pass: pass
  one kept the second diamond, and pass two read `# <D> ` as a heading again. The heading reading
  was withheld, and those 12 shapes went away with it.
- The residue line for `line_leading_marker_deferred` names every cause the counter has now.

### Fixed
- **Dropping a line-edge Symbol space no longer uncovers a hard break.** `U+F020` is not whitespace
  to CommonMark, so a line that ends in it has no hard break. `symbol_pua` deleted it and left the
  real spaces behind it in place: `"x  <SPACE>"` became `"x  "`, a `<br>` the page does not have.
  The tail is now cut back to the whitespace that followed the last Symbol space. That is all
  CommonMark saw before the step. When nothing followed it, one space stays. A break that was
  already there stays. A bare marker keeps the gap it needs. Counted as `tail_collapsed_f020`
  when a break was averted. The truth table gained four mixed tails. Against `main`, no shape
  changes how a marker is read. The only text changes are trailing whitespace on the lines where
  a break was averted. A new test pins that a Symbol space at the line end never decides how a
  marker is read. No corpus file holds `U+F020` (221 files on the box, the 2,392-file vault).
- **`pdf2wiki batch | head` no longer ends the batch.** When the reader of stdout closed the pipe,
  the next `print` raised `BrokenPipeError` at the per-book header. `run_batch` stopped and wrote no
  manifest, so the next run converted every finished book again. A closed pipe
  is not a book's failure. `main` now installs one guard on stdout for every command: on the first
  broken write it points the real file descriptor at the null device, says so once on stderr, and
  discards later output. The run continues to its end with its real exit code, and the interpreter's
  flush at exit cannot raise the same error. Proven on a real shell pipe in a subprocess. A second
  round on the GPU box found the short-run hole. With one book, every print after the header sat
  in the block buffer. Nothing reached the dead pipe before `main` returned, and the interpreter's
  own flush raised (exit 120). `main` now flushes through the guard before it steps aside.
- **`pdf2wiki phase5 --apply` no longer writes the source `.md`.** It wrote the repaired text back
  over the input so that `chapter_split` could read it from disk, and it did that before the split
  ran. A split that found no chapter boundary still left the input changed. The `batch` command
  went through the same code. The CLI reference said that no command changes an existing file in
  place, and the how-to said the opposite. The chain now hands the repaired text to the split
  step directly. The source file keeps its bytes and its modification time in both modes. The dry
  run also plans the split on the repaired text now. Before, it read the unrepaired file from
  disk, so its planned files could differ from what `--apply` then wrote. Found when a
  verification run on the GPU box rewrote two production converter outputs.

## [0.2.9] - 2026-08-21

This release improves `symbol_pua`. Version 0.2.8 added the step. This version makes the step worth a
run.

The verified glyph table grew from 3 codepoints to 20. A converted math page now keeps θ, φ, α, λ, Σ,
×, ·, ≠, ≡, ≈ and ∇. Before this release the page lost them, and no reader could see the loss. A
person read every entry from a rendered page. No entry comes from an encoding chart. That difference
changed the correct answer two times.

The second half of the release is position. The meaning of a marker depends on its place in the line.
Five separate rules read that place. One result was a deleted nested list, which the step counted as
a repair. One function reads the position now. The indent limit counts columns, which is the unit
CommonMark uses.

The release also adds the first tests for the orchestration layer. Statement coverage moved from 82%
to 93%. The user-facing documentation now follows ASD-STE100 Simplified Technical English. The
repository has a read-only mirror at Codeberg.

### Added
- **A read-only mirror of the repository at
  [codeberg.org/Sevthered/pdf2wiki](https://codeberg.org/Sevthered/pdf2wiki).** GitHub stays
  canonical, and it keeps the issues, the pull requests and the releases. A new workflow,
  `.github/workflows/mirror.yml`, pushes `refs/heads/*` and `refs/tags/*` when `main` moves and when
  a `v*` tag arrives. Codeberg disabled new automatic pull mirrors in 2020, so the copy has to be
  pushed in from this side. The workflow authenticates with a Codeberg deploy key. That key can
  write to one repository and to no other. The workflow also pins the Codeberg host key by its
  published fingerprint. It never uses `git push --mirror`, because that command would prune
  Forgejo's own `refs/pull/*` and break the pull-request views on the copy. `CONTRIBUTING.md` and
  `security-insights.yml` both name the mirror. The attested controls apply to the GitHub
  repository alone.
- **`symbol_pua` now covers the Symbol-font glyphs a math book actually uses**: the table grew from
  3 verified codepoints to 20. `Math for Programmers` alone emits **17 distinct** Private Use Area
  codepoints, of which the table held `π` and the structurally-handled bullet, so a converted math
  page dropped `θ`, `φ`, `α`, `λ`, `Σ`, `×`, `·`, `≠`, `≡`, `≈`, `∇`, a Symbol-font space and the
  parentheses of a radical — each one silently, since a PUA codepoint has no glyph in any normal
  font. `Mastering Blockchain` adds `∞` and `✓`, also new here. Measured on a converted
  10-page slice of that book's chapter 12: `unknown: {f071: 4, f061: 3, f066: 1}`, `total_changes: 0`
  before, 8 remaps and an empty `unknown` after, with `where α (the Greek letter alpha)` and
  `–αv/m` restored to what the page prints.
- Every entry was verified by rendering the page it came from and reading the printed character, as
  the module requires. One finding that only rendering can produce: `U+F0B7` (set at 4 pt) and
  `U+F0D7` (10 pt) print the **same** centered multiplication dot, so both map to `MIDDLE DOT`,
  while `U+F053` and `U+F0E5` both print a capital Sigma in two different books — a per-codepoint
  table derived from an encoding chart would have split all four differently.
- **Tests for the orchestration layer, which had none.** `convert_book`, `run_batch`, the executors
  and the CLI command bodies were covered only where a unit test happened to reach them, so the
  layer an operator actually runs was the least proven part of the package. The new tests fake the
  MinerU subprocess but use a **real PDF** and run **phase 5 for real**, so the coverage gate, the
  chapter files and their frontmatter are the actual artifacts rather than stubs that agree with
  the code. They pin the contracts that matter on a bad day: the coverage gate hard-stops and writes
  nothing rather than leaving a short book on disk, a blank page is not mistaken for a dropped one, a
  failed pass is reported instead of raised into the batch loop, an offloaded hybrid failure never
  falls back to the local GPU, one book's failure does not abort the run, and a corrupt manifest is
  refused instead of restarting every book. Statement coverage **82% → 93%**, and the suite
  went from **236 to 276** tests. (The release as a whole ships **308**.)
- **A "Build from source" section in the install guide** (`docs/how-to/install.md`), linked from
  CONTRIBUTING: clone, `uv build` (or `python -m build`), install the resulting wheel, and the
  dev-environment commands CI runs. Every command was executed before it was documented. This closes
  **OSPS-DO-07.01**, a control the OSPS Baseline added in its `2026-02-19` release.

### Changed
- **The five position-dependent readings in `symbol_pua` are one function.** A marker was read in
  five ways — after a heading's hashes, opening a line inside the indent limit, opening a line
  outside it, separating two words, and flush between two of them — and those readings lived in
  three anchored regular expressions and two branches of a character walk. Every change to the rule
  therefore meant five separate decisions, and nine fresh-context review rounds found the same shape
  of defect again and again: a caution added where the author was looking, and not where the same
  constant is read next door. Position is decided once now, by `classify`, and what each position
  means is a table. No behavior changed except the tab defect above, and that is proven rather than
  asserted: all **10,232** shapes in the positional truth table were run through the old code and
  the new, **452** differ, and **every one of the 452** carries a tab to the left of the marker.
  Across the 219 converted files the two agree on every output and every count. ⚠ The truth table
  grew while this was written, because the first version of it carried **one marker per line** and
  therefore could not see what a marker's action leaves behind for the next one. It could not: the
  heading action emits `# `, which is itself a valid heading prefix, so `#<M>   <M> ` counted two
  promoted headings on one heading. A line opens **once** now, whichever way the marker that opened
  it was read, which is what the anchored patterns gave for free by running a single time. The table
  carries two-marker shapes from now on.
- **The user-facing documentation is now written to ASD-STE100 Simplified Technical English.** The
  corpus is `README.md`, `CONTRIBUTING.md`, `docs/README.md`, `docs/how-to/`, `docs/tutorials/` and
  `docs/reference/`. Measured against the mechanically-decidable rules, it went from **97 violations
  to 0**: 58 semicolons (rule 8.1, which STE bans outright), 28 descriptive sentences over 25 words
  (6.3), 5 procedural sentences over 20 words (5.1), one over-long parenthetical (8.5) and 5 British
  spellings (1.14). The counts are what the checker reports today over that corpus at `v0.2.8`; a
  house line-width rule it also carries is not an STE rule and is excluded from the total.
  Sentence length was measured under the standard's own counting rules 8.4–8.6 rather than by splitting
  on whitespace, so a parenthetical counts as one word in its host sentence and as a sentence of its
  own, while a number-plus-unit, an abbreviation or an alphanumeric identifier each count as one word.
  No behavior changed, and no factual claim, number or data-egress warning was altered — that was the
  explicit subject of an independent review of the diff. Judgment-dependent rules (approved meanings,
  active voice, one topic per sentence) are not claimed. STE is a controlled language built to reduce
  ambiguity for non-native readers, for translators, and — per the standard itself — for language
  models, which is the audience this project's output is written for.
- **Rule 9.3, the phrasal-verb ban, applied to the documentation.** STE forbids combining two approved
  words into a phrasal verb, because the combination carries a meaning neither word's own entry covers
  and the dictionary does not flag it — so the writer, not a lookup, is the check. Six instances, all
  replaced by a single word that states the meaning directly: *set up a remote GPU host* → **configure**
  a remote GPU host (the page title and its four inbound link texts), and *a file you keep out of
  version control* → a file you **exclude** from version control. The file name
  `docs/how-to/set-up-remote-gpu.md` is deliberately unchanged: STE governs prose, not file naming, and
  renaming a published page would break external links for no gain in clarity.
- **`docs/README.md` is now inside the documentation corpus.** It is the index to the pages already
  covered, and leaving it out was an oversight in how the corpus was named rather than a decision. It
  carried a 27-word sentence, an over-wide line, a progressive verb (*what you are trying to do*) and
  two phrasal verbs (*set up*, *look up the facts*) — including the one that made the index disagree
  with the page it points at.
- **Rule 3.5, the `-ing` restriction, applied to the same corpus.** STE permits an `-ing` form only as
  a technical noun (its own examples are *Cleaning, Testing, Handling, Packaging, Shipping,
  Troubleshooting*) or as a modifier inside one. Every other use — a gerund after a preposition, a
  reduced relative participle, a progressive verb — is rewritten: *before uploading* → *before you
  upload*, *a directory containing a file* → *a directory that holds a file*, *the box kept working* →
  *the box continued*. **Three headings changed, so three anchors changed with them** — the
  data-usage-and-privacy heading in the cloud guide, and two in the troubleshooting guide. The one
  in-repo link that pointed at an old slug was updated, and every cross-file anchor was re-verified,
  but an **external** deep link to any of the three now lands at the top of the page instead of the
  section. **54 instances were rewritten**, counted as instances the checker no longer reports rather
  than as `-ing` tokens removed from the diff, which is a larger number because some rewrites
  eliminated a word the checker never flagged. A further **31** were never violations at all: the checker's allow-list
  was missing words the standard itself permits, so fixing the checker rather than the prose accounts
  for them — measured by re-running the corrected checker against the pre-change text, which reports
  79 rather than 110. The remaining **25** are the permitted kind — `a listing`, `working directory`,
  `mutating commands`, `grep-based tooling` — which is why the count does not reach zero, and why it
  should not be read as outstanding work.
- **`security-insights.yml` now self-attests OSPS Baseline Level 2** (cumulative on Level 1), and —
  the part that matters for anyone reading the claim — **names the baseline version it was assessed
  against**, `2026-02-19`. The previous Level 1 attestation was measured against `2025-02-25`; two
  releases since then added five controls (`BR-03.02`, `BR-07.01`, `QA-05.02`, `BR-01.03` at Level 1,
  `DO-07.01` at Level 2) and removed one, so a conformance claim naming no version decays silently as
  the standard moves. Four of the five were already met — secret-scanning push protection, no binary
  artifacts in version control, no workflow granting credentials to untrusted code, and a
  Trusted-Publishing distribution path — and the fifth is the build documentation above. Level 3 is
  explicitly **not** claimed: `QA-07.01` requires a non-author approver, which a single-maintainer
  project cannot honestly meet. Also filled the previously empty
  `project.documentation.design` field with the architecture document.
- **The two rewrites the table cannot express are now positional, not blanket.** `U+F0B7` is
  verified *inline* as a multiplication dot, but the same glyph opens a bulleted line in publisher
  templates and no rendered page in the corpus settles that case — so a line-leading one is **left
  alone** and reported as `line_leading_dot_deferred` rather than flattening a list into middle-dot
  paragraphs. The Symbol-font space `U+F020` is substituted **before** the bullet/heading passes
  (which test for real whitespace, and `"\uf020".isspace()` is `False`, so a bullet separated from
  its text by one used to survive into the output as an invisible codepoint with its list item
  lost), and one landing at a line edge is dropped rather than spaced, because two of them at end
  of line are a CommonMark hard break. That hard break is the only reason. A line that holds one
  Symbol space and nothing else splits a paragraph either way: `U+F020` is not whitespace to
  CommonMark, so such a line is a paragraph continuation before this step and blank after it,
  whichever way the space is handled.
- Every PUA codepoint in `symbol_pua.py` and in the tests is now written as a `\uXXXX` escape
  instead of the literal character. A literal is invisible in an editor, a diff and a review — the
  same property that makes this whole defect class hard to see. No behavior change.
- **A new refusal counter, `line_leading_marker_deferred`.** It counts a PUA bullet marker that
  opens a line and that the list pass declined, which `symbol_pua` now leaves in place instead of
  deleting (see Fixed). Like `stray_unhandled` and `line_leading_dot_deferred` it is a refusal, not
  an edit, so it stays out of `total_changes`. `remap()` always carries the key, on the normal
  report and on the CRLF refusal alike, and `phase5.residue_lines()` prints it — so both the
  `phase5` command and `batch` say what was left and what to do about it.
- **A Symbol-font space that is deleted is reported as `dropped_f020`, not `remap_f020`.** One at a
  line edge is dropped rather than substituted, and counting a deletion as a remap said the step had
  written a space where the page prints one. Both still count toward `total_changes`, because both
  are edits. The key is new in this release, and `remap()` always carries it — on the normal report
  and on the CRLF refusal alike — so a caller written against the documented return contract reads
  it without a `KeyError` guard. A test pins the full key set.

### Fixed
- **`symbol_pua` deleted the Symbol-font space that follows a line-opening `U+F0B7`.** That codepoint
  is a multiplication dot inline and a list bullet in other books, so the step deliberately leaves
  such a line alone and counts it. It did not: the line was split at the dot *before* the Symbol
  space was substituted, which made the space look line-leading, and a leading Symbol space is
  dropped rather than spaced. `<dot><symbol space>Text` came out as `<dot>Text`, with the marker
  glued to the first word and the change reported as one edit — to the one line the step promises
  not to touch. The space is now substituted first. That order also lets a Symbol space *before* the
  dot reach the deferral at all, which it could not, because `[ \t]` does not match one.
- **`pdf2wiki batch` threw the phase-5 report away.** Every unverified codepoint, every refusal and
  every glyph left inside a fence was computed and discarded on exactly the runs that build a vault
  — the `phase5` command printed them, and the command that converts ten books did not. The lines
  now come from `phase5.residue_lines()`, which both commands call, and the batch prefixes each with
  the book slug. Printing the report never decides the fate of a book that converted, which took two
  guards. The report is printed **below** the `except` that classifies a phase-5 failure, because
  the chapters are already written by then and an exception from printing — a `UnicodeEncodeError`
  on the warning sign to a non-UTF-8 stdout, say — would otherwise mark a book that converted
  correctly as `phase5_failed`, trip the circuit breaker and re-convert it on the next resume. It
  also carries its own `except`, because outside that `try` and unguarded the same exception left
  `run_batch` altogether: the remaining books never converted, no manifest was written, and the book
  was re-converted anyway. The fallback line is plain ASCII and carries no exception text, since the
  failure it reports is an encoding error on the characters the report is made of, and the fallback
  is guarded in turn for the same reason. ⚠ This covers a write that fails for the report's own
  characters. It does not make `batch` survive a stdout that is broken for everything: a
  `BrokenPipeError` from `pdf2wiki batch | head` still stops the run at the per-book header print.
- **`symbol_pua` DELETED a PUA bullet indented four spaces or more, and counted it as a repair.**
  Present in 0.2.8 and in every book converted with it. The list and heading readings both
  carry CommonMark's three-column indent limit, so a nested marker matched neither and fell through
  to the stray-marker branch, where the indent on its left is whitespace — the condition that
  allows a deletion. A nested list flattened into continuation text of its parent item, and the
  count landed in `stray_markers`, the counter for a *successful* cleanup, so no residue counter
  moved and nothing reached the operator. A marker that opens a line is now left in place and
  counted as `line_leading_marker_deferred`, never removed: **a deletion is not a
  list-recognition rule either**, which is the mirror of the argument that removed the same bound
  from the `U+F0B7` refusal one line above. "Opens the line" allows one `*` ahead of the marker,
  because both marker patterns do — MinerU misplaces an emphasis opener there, and without it
  `    *<PUA> nested` still flattened. A marker in **column 0** that the list pass declined is
  reported as line-opening as well: it was counted as `stray_unhandled` before, whose message reads
  "mid-word marker", which sent the reader looking for a word join that is not there. The mid-line readings are unchanged — whitespace on
  both sides is still a safe cleanup, and a marker flush between two words is still
  `stray_unhandled`. ⚠ The 219-file converted corpus could not have found this: `stray_markers` is
  2 across all of it, so the defect hides inside the number used to prove a change is free.
- **`symbol_pua` read a tab-indented marker as a list item, because it counted the indent in
  characters and CommonMark counts it in columns.** Present in 0.2.8. A tab is one character and
  **four columns**, so the three-character indent limit accepted a marker standing at column 4 or
  beyond, and `\t<PUA> nested` became `\t- nested` — which outside a list context is an **indented
  code block**, the very structure the line-opening refusal exists to avoid. `     nested`, at the
  same column, was refused. One column, two answers. The indent is measured in columns now, against
  CommonMark's four-column tab stop, so any tab in the indent defers the marker and reports it as
  `line_leading_marker_deferred`. The heading path carries the same limit, so a marker after hashes
  that a tab pushed past column 3 is no longer reported as `heading_markers`: that line is not a
  heading, and the marker is read by position alone. ⚠ The `U+F0B7` refusal is deliberately
  **unbounded** and is unaffected — a tab-indented dot already deferred. Measured across the 219
  converted files: **zero** change to any output or any count, which is the corpus limit this
  module's tests were rebuilt around rather than a claim that the defect was not real.
- **The line-leading `U+F0B7` refusal stopped applying to a nested list.** Its pattern copied
  the list reading's CommonMark indent limit, but a refusal is not a list-recognition
  rule: a dot opening a line indented four spaces or more was rewritten to a middle dot and counted
  as a repair, which is exactly the flattening of a bulleted list the step says it never performs.
  The indent is unbounded there now.
- **The `phase5` report never printed `line_leading_dot_deferred`.** The step counts every
  line-opening `U+F0B7` it refuses to interpret, its own documentation says that count needs a human
  for the same reason an unknown codepoint does, and no command printed it. A document made only of
  such lines reported zero changes, zero unknown and zero warnings while keeping every one of those
  invisible codepoints. It is now a ⚠ line that says what the codepoint is and what to do about it.
- **The `phase5` report described a document other than the one it writes.** Three separate
  defects in the same lines. `stray_unhandled` was **summed** across the two `symbol_pua` passes, so
  a document holding two mid-word markers reported four: a refusal is not an edit, and both passes
  read the whole document and report the same untouched marker. `in_code` came from the **first**
  pass, which is wrong in the other direction — `caption_unbleed` runs between the passes, and a
  glyph it lifts out of a fence is repaired by the second pass, so the report said a glyph was still
  stuck in a code fence after it was fixed. And the unknown-codepoint residue was read as
  `first or second`, which no longer says which document is being described. Everything that counts
  **what the document still holds** now comes from the second pass, the one that read the text this
  chain goes on to write, while counts of actual changes stay summed across both. ⚠ A **refusal**
  keeps the high-water mark of the two passes instead: a codepoint the first pass declines to touch
  can be removed by the second, and reporting the second alone would drop the signal precisely
  because something acted on it.

- Removed a dead `cli.py` branch that printed a "SKIPPED — CRLF" warning that could never fire
  through the `phase5` CLI (`run_chain` reads every file in universal-newline mode, so `symbol_pua`'s
  own CRLF guard never sees a `\r\n` to trip on). `run_chain`'s docstring now says explicitly that
  the chain normalizes line endings to LF as a side effect. No behavior change — this documents and
  cleans up what already shipped, and corrects the 0.2.8 entry below's overclaim about where that
  guard is reachable. See bug-pdf2wiki-crlf-guard-unreachable.

## [0.2.8] - 2026-08-02

A codepoint-fidelity release: two new phase-5 steps for characters that arrive in the markdown as
something no reader can see. Both defects are **silent** — the output stays grammatical and plausible,
so no coverage gate, linter or token-verify can catch either, and both are present in every earlier
published release.

### Added
- **New phase-5 step `symbol_pua`: Symbol-font glyphs that render as nothing are remapped to the
  characters the page prints.** Publisher PDFs (the four affected books in the reference corpus are all
  Manning) embed a `SymbolMT` subset and emit its glyphs as **Private Use Area** codepoints with **no
  `ToUnicode` map**. `pymupdf` returns them verbatim and MinerU carries them into the markdown, where
  they have no glyph in any normal font: `2<U+F070> radians` reads as **"2 radians"**, and `sin(4πt)`
  as `sin(4t)`. Both converter backends produce it — they share the embedded text layer for prose — so
  no backend choice avoids it. The step runs first in the chain and **again right after
  `caption_unbleed`**, which unwraps caption-only fences and so can promote a glyph that the first pass
  correctly skipped as in-code into prose that no later step would fix.
  **The mapping table is ground truth, not the font spec:** every entry was verified by rendering the
  source page. `U+F0E5` occupies Adobe Symbol's *summation* slot, but the book that uses it prints a
  capital Sigma — deriving the table from the encoding would have written the wrong character.
  Unverified PUA codepoints are left untouched and reported rather than guessed. `U+F0A1` is a list
  *marker*, not a character, so a line opening with it becomes a real markdown list item; a marker
  promoted into a heading only loses the glyph, since demoting the heading would restructure documents
  whose chapters are already split and whose headings may be link targets. Scoped outside fenced code
  throughout. `remap()` itself refuses on CRLF input rather than risk a mis-lexed fence (`fences` is
  LF-only) — but `phase5`'s chain reads every file in universal-newline mode, so that guard is for a
  direct library caller, not what a CLI user sees: a CRLF book runs through normally and is rewritten
  with LF endings as a side effect of the chain running at all.
  <!-- corrected 2026-08-10 — original wording here overclaimed a guard reachable from the CLI; see
       bug-pdf2wiki-crlf-guard-unreachable. Historical release entry, correcting for accuracy only. -->
  A marker left
  flush between two non-space characters is **not** removed — it is counted as `stray_unhandled`,
  because removing it there would silently weld two words together.
- **New phase-5 step `illegal_codepoints`, first in the chain: raw NUL and Unicode noncharacters are
  removed from converted markdown.** A source PDF's text layer can hold `U+FFFF` where a font subset
  failed to encode a character (*Modern C++ Tutorial* p55: a CJK word inside a C++ string literal,
  printing blank), and MinerU writes each one out as a raw `U+0000` — confirmed in MinerU's own raw
  chunk output, upstream of any merge code. A NUL makes the page **binary** to most tooling: `grep`
  silently stops matching, so the page becomes invisible to the dead-link, orphan and content lints
  that are supposed to guard it. The new step removes `U+0000`, the `U+FDD0`–`U+FDEF` block and the
  plane-end `U+FFFE`/`U+FFFF` pairs across the **whole document, code fences included** — the
  occurrence that motivated it is inside a ```` ```cpp ```` block, which `symbol_pua` is deliberately
  scoped never to enter. Private Use Area codepoints are **not** touched; those carry real characters
  and remain `symbol_pua`'s job. The codepoints are dropped rather than replaced with `U+FFFD`,
  matching what the page prints (they are blank) and avoiding a character the source never had inside
  a string literal. A removal that sat between two alphanumerics joins two words, so each is counted
  as `word_joins` and flagged by the CLI instead of passing silently.

## [0.2.7] - 2026-07-31

A phase-5 correctness release. Every fix here is present in every earlier published release
(0.1.0 through 0.2.6), so books converted with those versions carry the defects in their output and
need re-running from a pre-phase-5 markdown to recover. Three of them were found by reviewing the
diffs of the other two.

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

[Unreleased]: https://github.com/Sevthered/pdf2wiki/compare/v0.2.10...HEAD
[0.2.10]: https://github.com/Sevthered/pdf2wiki/compare/v0.2.9...v0.2.10
[0.2.9]: https://github.com/Sevthered/pdf2wiki/compare/v0.2.8...v0.2.9
[0.2.8]: https://github.com/Sevthered/pdf2wiki/compare/v0.2.7...v0.2.8
[0.2.7]: https://github.com/Sevthered/pdf2wiki/compare/v0.2.6...v0.2.7
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
