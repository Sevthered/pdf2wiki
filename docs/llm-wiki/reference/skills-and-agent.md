# Skills and agent

Precise reference for the three assets llm-wiki ships in v0.1 — two skills and one agent, all query
side. All three resolve the vault the same way ([configure the vault location](../how-to/configure-vault-location.md))
and are **read-only on the vault**. For the directory shape they read, see
[vault layout](vault-layout.md).

## `knowledge-query` skill

Consult the vault before planning or designing work in a domain it covers.

| | |
|---|---|
| **Name** | `knowledge-query` |
| **Triggers** | `/knowledge-query`; phrasing like "check the wiki", "what does the wiki say", "what do the books say"; a planning/design task in a covered domain when the project's `CLAUDE.md` subscribes to a vault. |
| **Allowed tools** | Read, Grep, Glob, Agent, Bash |
| **Input** | The planning question or design topic. |

**Behavior.** Resolves the vault root, then discovers coverage **dynamically** — reads `wiki/index.md`
and `ls wiki/domains/` + the matching `wiki/domains/<domain>.md`, never a hardcoded domain list. If no
domain matches, it says the vault doesn't cover the topic and moves on. Otherwise it navigates in order
— `hot.md → index.md → domains/<domain>.md → concept/entity pages` — stopping as soon as it has what it
needs, and only opens raw book chapters when a page cites one and lacks the depth. For a **single known
concept** it reads that one page directly; for a **broad, multi-page** lookup it spawns the
`knowledge-researcher` agent to keep long pages out of the main context.

**Output.** A vault-grounded answer citing the pages it leaned on as `[[Page-Name]]`. It complements —
does not replace — the doc-first rule: version-sensitive facts (APIs, flags, defaults) are still
verified against current official docs before execution. Trust markers (`[!warning]`, `[!gap]`,
`[!contradiction]`, `[!bug]`) are carried into the answer, never presented as settled fact.

## `knowledge-review` skill

In-depth, vault-grounded review/lint of a project. Reports; does not fix. Read-only on project code.

| | |
|---|---|
| **Name** | `knowledge-review` |
| **Triggers** | `/knowledge-review`; "review against the wiki", "wiki-grounded review", "lint against the vault", "audit project with the knowledge vault". |
| **Allowed tools** | Read, Grep, Glob, Bash, Agent, Write |
| **Input** | Optional scope argument: `/knowledge-review [path or area]` — default is the current project root; may narrow to a directory or a named domain. |

**Behavior.** Five phases: (1) **detect** — read the vault's real `wiki/domains/`, inventory the
project, and map file signals to the domains that actually exist; state detected scope before fanning
out; (2) **checklist** — one `knowledge-researcher` agent per detected domain extracts a review
checklist from the vault pages, each item tied to a `[[Page-Name]]` (which pages to anchor on is
discovered, not hardcoded); (3) **review** — one read-only agent per (domain × area), comparing code to
each checklist item and reporting satisfied items too; (4) **verify and rank** — drop any finding
lacking both a `file:line` and a `[[Page-Name]]`, filter era-only findings against current docs,
respect trust markers, dedup, and rank 🔴→🟠→🟡→🔵; (5) **report**. Saying "thorough"/"deep" adds an
adversarial pass that tries to refute each 🔴/🟠 finding.

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

**Behavior.** Resolves the vault root; if none is configured it states so and stops (it runs
non-interactively, so it does not ask). It reads `wiki/index.md` (skipping `hot.md` unless the question
is about recent vault work), identifies the domain(s) dynamically from `wiki/domains/`, locates
candidate pages via domain-page links and `Glob`/`Grep` over `wiki/concepts/` and `wiki/entities/`,
reads the relevant pages fully, and only opens raw book chapters when a page cites one and lacks depth.
It answers **from the vault only** — it never invents content beyond the pages and never edits a file.

**Output.** Raw findings, not a chatty message, in four parts:

- **Answer** — the distilled technical answer (mechanisms, code/config, parameter names and defaults,
  trade-offs, step sequences); specifics over summary.
- **Citations** — every claim tied to `[[Page-Name]]` plus path; all pages consulted listed.
- **Flags** — any `[!warning]`/`[!gap]`/`[!contradiction]`/`[!bug]` callouts touching the answer,
  reproduced; book era noted where version-sensitivity matters.
- **Not covered** — what the vault does not answer, determined from what was actually found.
