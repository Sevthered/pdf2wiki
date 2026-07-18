"""Manifest-driven batch conversion: convert -> (fetch) -> phase5 -> optional vault placement.

The book list is a user-supplied TOML file — never code:

    # books.toml
    [[book]]
    pdf = "Some_Technical_Book.pdf"   # path (local mode) or filename under remote books_dir
    slug = "some-technical-book"      # output name, used everywhere downstream
    domain = "distributed-systems"    # optional: subfolder under the output/vault root

Resumable: a JSON status manifest records per-book status next to the book list; a book whose
status is exactly "done" is skipped on re-run. One book's failure is logged and does NOT abort
the batch. Sequential only — a single GPU cannot run concurrent VLM passes.

A STOP file next to the status manifest halts cleanly between books (it is consumed on halt).
"""
from __future__ import annotations

import json
import os
import shutil
import time
import tomllib

from .executor import ExecutionError, LocalExecutor, SSHExecutor
from .phase5 import run_chain


def load_books(books_toml: str) -> list[dict]:
    with open(books_toml, "rb") as f:
        data = tomllib.load(f)
    books = data.get("book", [])
    for b in books:
        if "pdf" not in b or "slug" not in b:
            raise ValueError(f"each [[book]] needs `pdf` and `slug`: {b}")
    return books


def run_batch(books_toml: str, cfg, stage_dir: str, remote: str | None = None,
              max_books: int | None = None, only: str | None = None,
              vault: str | None = None) -> dict:
    """Run the batch. Returns the final status manifest."""
    stage = os.path.expanduser(stage_dir)
    os.makedirs(stage, exist_ok=True)
    manifest_path = os.path.join(stage, "manifest.json")
    stop_file = os.path.join(stage, "STOP")

    manifest: dict = {}
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)
        except json.JSONDecodeError as e:
            raise SystemExit(
                f"status manifest {manifest_path} is corrupt ({e}). "
                f"Repair or delete it (deleting restarts every book) and re-run."
            )

    def save():
        # atomic: a kill mid-dump must never truncate the manifest (it's the resume backbone)
        tmp = manifest_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=1)
        os.replace(tmp, manifest_path)

    if remote:
        ex = SSHExecutor(remote, cfg.remote.books_dir, cfg.remote.workdir,
                         cfg.remote.connect_timeout, cfg.remote.convert_timeout)
    else:
        ex = LocalExecutor()
    ex.check()  # fail fast before touching any book

    books = load_books(books_toml)
    attempted = 0
    for b in books:
        slug, domain = b["slug"], b.get("domain", "")
        if only is not None and slug != only:
            continue
        if max_books is not None and attempted >= max_books:
            print(f"--max-books {max_books} reached — stopping cleanly (done books skip on re-run).")
            break
        if os.path.exists(stop_file):
            print(f"STOP file present ({stop_file}) — halting cleanly between books.")
            os.remove(stop_file)
            break
        if manifest.get(slug, {}).get("status") == "done":
            print(f"[skip] {slug} already done")
            continue
        attempted += 1
        print(f"=== {slug} ({domain or 'no domain'}) ===", flush=True)
        t0 = time.time()

        timeout = cfg.remote.convert_timeout if remote else cfg.convert.timeout
        # convert/fetch must NOT propagate: a TimeoutExpired (SSHExecutor subprocess) or a
        # FileNotFoundError (resolve_binary) here would abort the whole batch, violating the
        # documented "one book's failure does not abort the batch." Mark failed + continue.
        try:
            ok, log = ex.convert(b["pdf"], slug, cfg.convert.out_root, timeout)
        except Exception as e:
            print(f"  CONVERT ERROR: {slug}: {e}")
            manifest[slug] = {"status": "convert_failed", "domain": domain, "error": str(e)}
            save()
            continue
        if not ok:
            print(f"  CONVERT FAILED: {slug} — log tail:\n{log[-2000:]}")
            manifest[slug] = {"status": "convert_failed", "domain": domain}
            save()
            continue

        work = os.path.join(stage, slug)
        try:
            fetched = ex.fetch(slug, cfg.convert.out_root, work)
        except Exception as e:
            print(f"  FETCH ERROR: {slug}: {e}")
            manifest[slug] = {"status": "fetch_failed", "domain": domain, "error": str(e)}
            save()
            continue
        if not fetched:
            manifest[slug] = {"status": "fetch_failed", "domain": domain}
            save()
            continue
        if isinstance(ex, LocalExecutor):
            work = ex.artifacts_dir(slug, cfg.convert.out_root)

        md = os.path.join(work, f"{slug}.md")
        try:
            run_chain(md, slug, out_dir=os.path.join(work, "chapters"),
                      source_name=os.path.basename(b["pdf"]), apply=True)
        except Exception as e:
            print(f"  PHASE5 FAILED: {slug}: {e}")
            manifest[slug] = {"status": "phase5_failed", "domain": domain}
            save()
            continue
        # chapters need the shared images/ dir next to them for relative refs to resolve
        img_src = os.path.join(work, "images")
        img_dst = os.path.join(work, "chapters", "images")
        if os.path.isdir(img_src):
            os.makedirs(img_dst, exist_ok=True)
            for f in os.listdir(img_src):
                shutil.copy(os.path.join(img_src, f), os.path.join(img_dst, f))

        entry = {"status": "done", "domain": domain, "minutes": round((time.time() - t0) / 60, 1)}
        if vault:
            dest = os.path.join(os.path.expanduser(vault), domain, slug) if domain \
                else os.path.join(os.path.expanduser(vault), slug)
            shutil.copytree(os.path.join(work, "chapters"), dest, dirs_exist_ok=True)
            entry["vault_path"] = dest
            print(f"  DONE {slug} -> {dest} ({entry['minutes']} min)")
        else:
            print(f"  DONE {slug} -> {os.path.join(work, 'chapters')} ({entry['minutes']} min)")
        manifest[slug] = entry
        save()
    print("BATCH COMPLETE")
    return manifest
