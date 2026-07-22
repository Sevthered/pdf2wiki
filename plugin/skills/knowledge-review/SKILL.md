---
name: knowledge-review
description: "In-depth, wiki-grounded review/lint of a project against a distilled-Markdown knowledge vault. Detects which of the vault's domains the project touches (dynamically, from the vault's own domain pages), builds review checklists from vault pages, fans out parallel review agents, and reports severity-ranked findings each citing file:line + [[Page-Name]]. Triggers on: /knowledge-review, review against the wiki, wiki-grounded review, lint against the vault, audit project with the knowledge vault."
---

# knowledge-review: Wiki-Grounded Project Review

Review a project against what the vault actually says. Every finding is grounded in a vault page — no
vibes-based lint. **Read-only on project code.** This skill reports; it does not fix. Apply fixes only
if the user asks afterward. Never write to the vault.

## Vault location (not hardcoded)

Resolve the vault root in this order — do NOT assume a path:
1. A `## Knowledge wiki` block in the project's `CLAUDE.md` with a line `Vault: <absolute path>`.
2. The `$KNOWLEDGE_VAULT` environment variable.
3. If neither is set, ask the user for the vault path.

See the `knowledge-query` skill for the vault layout + navigation protocol.

## Scope argument

`/knowledge-review [path or area]` — default = current project root. User may narrow to a directory or a
domain ("just the k8s manifests", "API security only").

## Phase 1 — Detect: what does this project touch, and what does the vault cover?

First read the vault's ACTUAL coverage — never assume a fixed domain set:
- `ls <vault>/wiki/domains/` and skim each `wiki/domains/<domain>.md` to learn what this vault covers now.

Then inventory the project (Glob/Grep/ls, cheap) and map signals → the vault domains that exist. The table
below is an ILLUSTRATIVE heuristic set — **extend/replace it with your vault's real domains**; if a signal
maps to no existing domain page, the vault doesn't cover it:

| Example signal | Example domain (verify it exists in this vault) |
|---|---|
| `*.yaml` with `apiVersion:`/`kind:`, `Chart.yaml`, helm/kustomize | a kubernetes / distributed-systems domain |
| `go.mod`, `*.go` | a go / systems domain |
| HTTP handlers, OpenAPI, auth/JWT/OAuth code | an api-security domain |
| Dockerfiles, CI configs, Terraform | a delivery / distributed-systems domain |
| sklearn/keras/tensorflow imports, notebooks | an ml domain |

Skip domains with no signal OR no vault coverage. State detected scope to the user before fanning out.

## Phase 2 — Checklist: extract review criteria from the vault

For each detected domain, spawn **one `knowledge-researcher` agent** (parallel, single message) asking:
*"Extract a concrete review checklist for <area> from the vault: what the pages say a correct/
production-grade implementation must have, common mistakes, anti-patterns, security requirements. Return
checklist items each tied to [[Page-Name]]."*

**Do NOT hardcode which pages to anchor on** — the researcher discovers the relevant pages from the vault's
current contents. (Anchor pages differ per vault; a fresh vault has entirely different page names.)

## Phase 3 — Review: fan out per dimension

One read-only review agent per (domain × project area) pair — parallel, single message, `Explore` or
`general-purpose` type. Each agent gets:
- its checklist from Phase 2 (inline in the prompt, with the `[[Page-Name]]` per item),
- the concrete file list for its area,
- the output contract below.

Agent instruction core: *"Compare the code against each checklist item. Report only what you can pin to
file:line. For each finding: what the code does, what the vault page says it should do, severity. Also
report checklist items the project satisfies — absence of findings must be distinguishable from absence of
coverage."*

## Phase 4 — Verify and rank

- **Drop any finding without both** a `file:line` anchor and a `[[Page-Name]]` citation.
- **Era filter**: book content has a publication era. Kill findings that only reflect outdated practice
  (deprecated APIs, old versions) unless the underlying principle still holds — when in doubt, verify
  against current official docs before reporting.
- Respect vault trust markers: never base a finding on a `[!warning]`/`[!gap]`/`[!contradiction]`-flagged
  claim without saying so.
- Dedup across agents; rank: 🔴 critical (security/correctness/data-loss) → 🟠 major (resilience/
  observability gaps) → 🟡 minor (pattern deviations) → 🔵 info (improvements).

## Phase 5 — Report

```
## Knowledge Review — <project> — <date>
Scope: <detected domains + file counts> · Checklist items: N · Findings: M

| # | Sev | Location | Finding | Wiki guidance | Fix |
|---|-----|----------|---------|---------------|-----|
| 1 | 🔴 | path/file.go:42 | <what code does wrong> | [[Page-Name]]: <what page says> | <concrete fix> |

### Satisfied (spot-checks passed)
- <checklist item> — [[Page-Name]] — evidence file:line

### Not covered by the vault
- <areas reviewed only by general judgment, or skipped>
```

If the project has a wiki (`wiki/` with `index.md`), offer to save the report as
`wiki/meta/knowledge-review-<date>.md` (frontmatter per project conventions) and add an index + log entry.
Otherwise offer a plain file at project root or scratchpad.

## Scale

Default: one researcher per domain + one reviewer per dimension (typically 3–6 agents). User says
"thorough"/"deep": add a second adversarial pass — one agent per 🔴/🟠 finding attempting to refute it
against both the code and the vault page before it ships.
