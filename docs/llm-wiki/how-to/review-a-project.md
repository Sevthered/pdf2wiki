# Review a project

The `knowledge-review` skill lints a project against what your vault actually says. Every finding is
grounded in a vault page and pinned to a `file:line` — no vibes-based lint. It is **read-only on your
code**: it reports, it does not fix. It never writes to the vault.

You need a [configured vault location](configure-vault-location.md) and the plugin
[installed](install.md).

## Run it

```
/knowledge-review [path or area]
```

- **No argument** → reviews the current project root.
- **An argument** narrows the scope — a directory (`src/api`) or a domain in words
  ("just the k8s manifests", "API security only").

## What it does

The skill runs in phases and tells you the detected scope before it does the expensive work:

1. **Detect** — reads the vault's real coverage (`wiki/domains/`), inventories your project, and maps
   your files to the domains the vault actually covers. Domains with no signal, or no vault coverage,
   are skipped.
2. **Checklist** — for each detected domain, a `knowledge-researcher` agent extracts a concrete review
   checklist from the vault pages (must-haves, common mistakes, anti-patterns), each item tied to a
   `[[Page-Name]]`.
3. **Review** — parallel read-only agents compare your code against each checklist item.
4. **Verify and rank** — findings without both a `file:line` and a `[[Page-Name]]` are dropped;
   outdated-practice findings are filtered against the book's era; results are deduped and severity-ranked.

Because coverage is discovered per vault, the checklists are only as broad as your vault — a project
area the vault doesn't cover is reported as *not covered*, not silently passed.

## Read the report

The report is a severity-ranked table plus two lists:

```
## Knowledge Review — <project> — <date>
Scope: <detected domains + file counts> · Checklist items: N · Findings: M

| # | Sev | Location | Finding | Wiki guidance | Fix |
|---|-----|----------|---------|---------------|-----|
| 1 | 🔴 | path/file.go:42 | <what the code does wrong> | [[Page-Name]]: <what the page says> | <concrete fix> |

### Satisfied (spot-checks passed)
- <checklist item> — [[Page-Name]] — evidence file:line

### Not covered by the vault
- <areas reviewed only by general judgment, or skipped>
```

Severity runs 🔴 critical (security/correctness/data-loss) → 🟠 major (resilience/observability gaps) →
🟡 minor (pattern deviations) → 🔵 info (improvements). The **Satisfied** list matters: it makes
"nothing found" distinguishable from "not reviewed". The **Not covered** list tells you where the vault
was silent.

Respect the trust markers a finding may carry — a finding based on a `[!warning]`/`[!gap]`/
`[!contradiction]`-flagged page is called out as such. See
[vault layout](../reference/vault-layout.md#trust-markers).

## Go deeper

Say "thorough" or "deep" and the skill adds a second adversarial pass — one agent per 🔴/🟠 finding
tries to refute it against both the code and the vault page before it ships.

## After the report

The skill stops at reporting. Ask afterward if you want fixes applied. If your project has its own
`wiki/` (with an `index.md`), it offers to save the report under `wiki/meta/`; otherwise it offers a
plain file at the project root or scratchpad.

## Related

- Reference for the skill's phases and tools: [skills and agent](../reference/skills-and-agent.md#knowledge-review-skill).
- Consult the vault while planning instead of reviewing: [query your first vault](../tutorials/query-your-first-vault.md).
