# Troubleshooting

Recipes for the failures you are most likely to hit. Each entry is a symptom and its fix.

## `mineru` not found

**Symptom:** `convert` fails with a `FileNotFoundError` naming `mineru`.

**Fix:** MinerU is not on your `PATH`. Either add it, or set the explicit path in
[config](../reference/configuration.md):

```toml
[mineru]
binary = "/opt/mineru/.venv/bin/mineru"
```

## vLLM: "Failed to find C compiler"

**Symptom:** the hybrid pass dies at engine init with a compiler error.

**Fix:** MinerU's vLLM backend JIT-compiles CUDA kernels and needs a C toolchain:

```bash
sudo apt install build-essential python3-dev
```

This is not a GPU or VRAM problem.

## Out of GPU memory

**Symptom:** a hybrid pass fails with a CUDA out-of-memory error.

**Fix:** lower the hybrid run length so fewer pages are in flight at once — reduce `[convert] maxrun`
(default 25) in [config](../reference/configuration.md). The pipeline targets ~8 GB VRAM; very dense
pages can still spike. Completed passes are cached, so re-running resumes.

## Coverage gate hard-stop

**Symptom:** `convert` exits with a `CoverageError` naming one or more pages.

**Why:** those pages have real text in the PDF but produced zero extracted blocks — extraction dropped
them. pdf2wiki [refuses to emit a book with a silent hole](../explanation/how-the-merge-works.md#the-coverage-gate).

**Fix:** inspect the named pages. If they are genuinely content (not blank/decorative), the PDF may
have an unusual text layer; try re-running (transient), or [QA-sample](qa-a-conversion.md) around those
pages to see what MinerU produces. This gate is a feature — it surfaces a real gap rather than shipping
one.

## A cryptic `FileNotFoundError` mentioning `--host`

**Symptom:** a MinerU subprocess fails with an odd error referencing something like `--host`.

**Why:** MinerU imports stdlib modules (`profile`, `inspect`, `code`, …) at runtime. If it runs from a
directory containing a file named after one of those, Python imports your file instead.

**Fix:** you should not hit this in normal use — pdf2wiki runs MinerU from a clean working directory
(`[convert] workdir`). If you customized `workdir`, make sure it contains no `.py` files named after
stdlib modules.

## SSH connectivity check fails

**Symptom:** remote `convert`/`batch` fails immediately with an execution error before any book runs.

**Fix:** pdf2wiki verifies the SSH connection once up front. Confirm key-based access works:

```bash
ssh <host> echo ok
```

Fix your `~/.ssh/config` / keys until that prints `ok` with no password prompt, then retry. See
[set up a remote GPU host](set-up-remote-gpu.md).

## Corrupt batch manifest

**Symptom:** `batch` exits telling you the manifest could not be parsed.

**Fix:** `<stage>/manifest.json` is not valid JSON (e.g. a kill mid-write on an old version). Repair
the JSON, or delete the file to start the manifest fresh — already-`done` books will simply re-run.

## Broken Mermaid diagrams

**Symptom:** a diagram from a converted book does not render.

**Why/fix:** VLM-transcribed Mermaid can be imperfect. The [`mermaid_repair`](../reference/phase5-steps.md)
step in `phase5` sanitizes common parse-breakers automatically — make sure you ran `phase5` on the
converted `.md`. Complex diagrams may still need a manual touch-up.
