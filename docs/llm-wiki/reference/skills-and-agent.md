# Skills and agent

Precise reference for the three assets llm-wiki ships — two skills and one agent, all query
side. All three resolve the vault the same way ([configure the vault location](../how-to/configure-vault-location.md))
and are **read-only on the vault**. For the directory shape they read, see
[vault layout](vault-layout.md).

## `knowledge-query` skill

Consult the vault before planning or designing work in a domain it covers.

| | |
|---|---|
| **Name** | `knowledge-query` |
| **Triggers** | `/knowledge-query`; phrasing like "check the wiki", "what does the wiki say", "what do the books say"; a planning/design task in a covered domain when the project's `CLAUDE.md` subscribes to a vault. |
| **Tools** | The tools of the session. The skill sets no `allowed-tools`. It uses Read, Bash, Grep and Agent. |
| **Input** | The planning question or design topic. |

**Behavior.** The skill does these steps:

1. It finds the vault root.
2. It runs a **coverage pre-check** with `scripts/vault_coverage.py`. For each term of the question,
   the script counts the files in `wiki/concepts/` and `wiki/entities/` whose name, heading or text
   has the term. The counts are case-insensitive. A `#` line in a code fence is not a heading. The
   pre-check reads no page. The skill does not run it when the user names the page, or for a
   question about the scope of the vault.
   - A file name or heading hit means COVERED.
   - A text hit only means PASSING. The skill reads one or two likely pages, or it calls the term not
     covered.
   - No hit means NONE. The skill says that the vault does not cover the topic, and it does not start
     the agent.
3. For a **single known concept**, it reads that one page.
4. For a **broad, multi-page** lookup, it starts the `knowledge-researcher` agent and gives it the
   Coverage line. The long pages then stay out of the main context.
5. It opens a raw book chapter only when a page cites the chapter and does not have the necessary
   depth. It finds the chapter file in the table of the book index page.

It reads `wiki/index.md` and `wiki/domains/` only when the question is about the scope of the vault.
It never uses a hardcoded domain list. It reads `hot.md` only
for a question about recent vault work.

**Output.** A vault-grounded answer citing the pages it leaned on as `[[Page-Name]]`. It complements —
does not replace — the doc-first rule: version-sensitive facts (APIs, flags, defaults) are still
verified against current official docs before execution. The era of a book is the `year` field in
its frontmatter. Trust markers (`[!warning]`, `[!gap]`, `[!contradiction]`, `[!bug]`) are carried
into the answer, never presented as settled fact.

## `knowledge-review` skill

In-depth, vault-grounded review/lint of a project. Reports; does not fix. Read-only on project code.

| | |
|---|---|
| **Name** | `knowledge-review` |
| **Triggers** | `/knowledge-review`; "review against the wiki", "wiki-grounded review", "lint against the vault", "audit project with the knowledge vault". |
| **Tools** | The tools of the session. The skill sets no `allowed-tools`. It uses Read, Grep, Glob, Bash, Agent and Write. |
| **Input** | Optional scope argument: `/knowledge-review [path or area]` — default is the current project root; may narrow to a directory or a named domain. |

**Behavior.** Five phases: (1) **detect** — read the vault's real `wiki/domains/`, inventory the
project, and map file signals to the domains that actually exist; state detected scope before fanning
out; (2) **checklist** — one `knowledge-researcher` agent per detected domain extracts a review
checklist from the vault pages, each item tied to a `[[Page-Name]]` (which pages to anchor on is
discovered, not hardcoded); (3) **review** — one read-only agent per (domain × area), comparing code to
each checklist item and reporting satisfied items too; (4) **verify and rank** — drop any finding
lacking both a `file:line` and a `[[Page-Name]]`, filter era-only findings against current docs,
respect trust markers, dedup, and rank 🔴→🟠→🟡→🔵; (5) **report**.
A domain that gets no checklist item with a page citation gets no reviewer. The report lists it under **Not
covered by the vault**. The era filter reads the `year` field of the book. Saying "thorough"/"deep"
adds an adversarial pass that tries to refute each 🔴/🟠 finding.

**Output.** A severity-ranked findings table plus a **Satisfied** list and a **Not covered by the
vault** list — see [review a project](../how-to/review-a-project.md#read-the-report). The `Write` tool
is used only to save the report (offered under the project's own `wiki/meta/` if it has one, else a
plain file); it is never used to write to the knowledge vault or to fix project code.

## `knowledge-researcher` agent

Read-only researcher for broad or multi-page vault lookups, spawned by the skills (or directly) so long
pages stay out of the caller's context. Do **not** use it for a single known page — read that directly.

| | |
|---|---|
| **Name** | `knowledge-researcher` |
| **Tools** | Read, Grep, Glob, Bash |
| **Input** | A technical question to answer from the vault. |

**Behavior.** The agent does these steps:

1. It finds the vault root. If no vault is configured, it says so and stops. It runs without a user,
   so it does not ask.
2. It runs the **coverage gate**: the same file name, heading and text counts as the pre-check of the
   `knowledge-query` skill. If the caller gives a Coverage line, it uses that line. If no term is
   covered, it returns at once with "Not covered: use the official docs". It skips the gate for a
   question about the vault itself and for a review checklist request.
3. It makes a ranked list of candidate pages from the gate hits. The rank is how likely a page is to
   answer, not how often a page uses the terms.
4. It reads the pages in that order. It stops when the answer is complete, or when two pages in
   sequence add nothing necessary.
5. It reads `wiki/index.md` and `wiki/domains/` only for a question about the scope of the vault or
   a review checklist request. It reads `hot.md` only for a question about recent vault work.
6. It opens a raw book chapter only when a page cites the chapter and does not have the necessary
   depth, or when the caller asks for the source passage. It finds the file in the table of
   `<book-slug>-index.md`, because the `NN` prefix counts
   files, not chapters. It follows a cross-reference link in a chapter instead of a grep.

It answers **from the vault only** — it never invents content beyond the pages and never edits a file.

**Output.** Raw findings, not a chatty message, in five parts. It always returns a report, also a
partial one.

- **Coverage** — the first line: the file name, heading and text counts of each term, and its verdict,
  for example `retry 2/4/19 COVERED; quic 0/0/0 NONE`.

- **Answer** — the distilled technical answer (mechanisms, code/config, parameter names and defaults,
  trade-offs, step sequences); specifics over summary.
- **Citations** — every claim tied to `[[Page-Name]]` plus path; all pages consulted listed.
- **Flags** — any `[!warning]`/`[!gap]`/`[!contradiction]`/`[!bug]` callouts touching the answer,
  reproduced. Where version matters, the `year` of the book.
- **Not covered** — what the vault does not answer, from what the gate and the pages actually showed.
  It also lists the ranked pages that the stop rule left unopened.

## `vault_coverage.py` script

The coverage count that the skill and the agent share. It is in `plugin/scripts/` and needs Python 3
with the standard library only.

| | |
|---|---|
| **Command** | `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/vault_coverage.py <vault> '<term>' ['<term>' ...]` |
| **Term** | A Python regular expression, matched without regard to case, such as `retry\|backoff` or `\bnat\b`. `^` and `$` match at a line. `--help` gives the full syntax. |
| **Exit code** | 0 on success. 2 on a usage error, a vault with no `wiki/` folder, or an invalid regular expression. |

**Output.** One line per term: `term F/H/B VERDICT`, with the number of files that match by file
name, by heading and by body text. The verdict is COVERED (a file name or heading match), PASSING
(body matches only) or NONE.

Under the line, the script lists the files with a file name or heading
match. For a PASSING term, it lists each body match with its matching text. Each list stops at 15
lines and then gives the number of lines left. The last line, `Coverage: …`, joins the term lines.

The script compiles all the terms before it reads a page. Thus a bad term gives no partial output.

**What counts.** The script reads the `.md` files under `wiki/concepts/` and `wiki/entities/`, and
their subfolders. A heading is an ATX heading (`#` to `######`), and the term is matched against the
heading text. A line in the YAML frontmatter or in a fenced code block is never a heading. The fence
rules are those of CommonMark. A fence closes only with the same character, and with a run at least as
long as the opening run.
