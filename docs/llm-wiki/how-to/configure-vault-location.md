# Configure the vault location

The plugin never hardcodes a vault path. All three assets — `knowledge-query`, `knowledge-review`, and
`knowledge-researcher` — resolve the vault root the same way, in the same order, and stop at the first
one that is set.

## Resolution order

1. **A `## Knowledge wiki` block in the consuming project's `CLAUDE.md`** with a `Vault:` line.
2. **The `KNOWLEDGE_VAULT` environment variable.**
3. **Otherwise the skill asks** you for the path (the `knowledge-researcher` agent instead stops and
   reports that no vault is configured, since it runs non-interactively).

Set exactly one. The `CLAUDE.md` block is the most durable — it travels with the project and is picked
up automatically in every session.

## Method 1 — `CLAUDE.md` block (recommended)

Add this to the consuming project's `CLAUDE.md`:

```markdown
## Knowledge wiki
Vault: /path/to/your/vault
```

The path is the vault root — the directory that contains `wiki/`. See
[vault layout](../reference/vault-layout.md) for what must be under it.

The `knowledge-query` skill also documents a fuller opt-in block, which additionally tells the project
*when* to consult the vault:

```markdown
## Knowledge wiki — consult before planning
Vault: /path/to/your/vault
When planning or designing work in a domain this vault covers (discover via wiki/domains/),
invoke the `knowledge-query` skill FIRST and ground the plan in vault pages (cite [[Page-Name]]).
Complements — does not replace — the doc-first rule.
```

## Method 2 — environment variable

For a machine-wide default, or a project without a `CLAUDE.md` block:

```bash
export KNOWLEDGE_VAULT=/path/to/your/vault
```

The `CLAUDE.md` block wins over this if both are present.

## Method 3 — the skill asks

With neither set, `knowledge-query` and `knowledge-review` ask for the vault path at invocation time.
This is fine for a one-off but means answering the prompt every session — prefer method 1 or 2 for
anything recurring.

## Next

- Consult the vault: the [tutorial](../tutorials/query-your-first-vault.md).
- Review a project: [review a project](review-a-project.md).
