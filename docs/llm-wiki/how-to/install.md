# Install the plugin

llm-wiki is a standalone Claude Code plugin. It has no runtime dependencies of its own — it reads
Markdown files with Claude Code's own tools.

## Prerequisites

- **Claude Code** with plugin support.
- A **knowledge vault** to read, laid out as described in [vault layout](../reference/vault-layout.md).
  You don't need one to install the plugin, but you need one to use it — build one with
  [pdf2wiki](../../README.md) or by hand.

## Install

Add the marketplace, then install the plugin from it:

```bash
claude plugin marketplace add https://github.com/Sevthered/pdf2wiki
claude plugin install llm-wiki@pdf2wiki
```

Update later with:

```bash
claude plugin marketplace update pdf2wiki
```

## Verify

Installing enables two skills (`knowledge-query`, `knowledge-review`) and one agent
(`knowledge-researcher`) — see [skills and agent](../reference/skills-and-agent.md). Confirm they are
available by invoking one:

```
/knowledge-query
```

If no vault is configured, the skill will ask for a path — that's expected. Set one so it doesn't ask
every time: [configure the vault location](configure-vault-location.md).

## Next

- Set where the vault lives: [configure the vault location](configure-vault-location.md).
- Run a first consultation: the [tutorial](../tutorials/query-your-first-vault.md).
