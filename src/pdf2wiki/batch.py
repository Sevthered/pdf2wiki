# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

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
import sys
import time
import tomllib
from typing import Any

from .executor import LocalExecutor, SSHExecutor
from .phase5 import run_chain


def _breaker_trips(ex: LocalExecutor | SSHExecutor, consec: int, threshold: int) -> bool:
    """Circuit-Breaker-Pattern: after `threshold` consecutive book failures, re-probe executor health.
    A dead SSH host / GPU box makes every remaining book fast-fail (the start-only preflight can't catch
    a mid-batch death — the '17 books failed in minutes' failure mode), so abort instead of hammering.
    A healthy probe means the failures are content-related → continue. LocalExecutor.check() is a no-op,
    so local batches never trip."""
    if consec < threshold:
        return False
    print(f"  {consec} consecutive failures — re-checking executor health…", file=sys.stderr)
    try:
        ex.check()
    except Exception as e:
        print(
            f"ABORT: executor unreachable after {consec} consecutive failures (circuit breaker): {e}",
            file=sys.stderr,
        )
        return True
    print("  executor still healthy — failures look content-related, continuing.", file=sys.stderr)
    return False


def load_books(books_toml: str) -> list[dict[str, Any]]:
    with open(books_toml, "rb") as f:
        data = tomllib.load(f)
    books: list[dict[str, Any]] = data.get("book", [])
    for b in books:
        if "pdf" not in b or "slug" not in b:
            raise ValueError(f"each [[book]] needs `pdf` and `slug`: {b}")
    return books


def run_batch(
    books_toml: str,
    cfg: Any,
    stage_dir: str,
    remote: str | None = None,
    max_books: int | None = None,
    only: str | None = None,
    vault: str | None = None,
) -> dict[str, Any]:
    """Run the batch. Returns the final status manifest."""
    stage = os.path.expanduser(stage_dir)
    os.makedirs(stage, exist_ok=True)
    manifest_path = os.path.join(stage, "manifest.json")
    stop_file = os.path.join(stage, "STOP")

    manifest: dict[str, Any] = {}
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)
        except json.JSONDecodeError as e:
            raise SystemExit(
                f"status manifest {manifest_path} is corrupt ({e}). "
                f"Repair or delete it (deleting restarts every book) and re-run."
            ) from e

    def save() -> None:
        # atomic: a kill mid-dump must never truncate the manifest (it's the resume backbone)
        tmp = manifest_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=1)
        os.replace(tmp, manifest_path)

    ex: LocalExecutor | SSHExecutor  # no shared base; both satisfy the calls used below
    if remote:
        ex = SSHExecutor(
            remote,
            cfg.remote.books_dir,
            cfg.remote.workdir,
            cfg.remote.connect_timeout,
            cfg.remote.convert_timeout,
            cfg.remote.fetch_timeout,
            cfg.remote.reap_grace,
        )
    else:
        ex = LocalExecutor()
    ex.check()  # fail fast before touching any book

    books = load_books(books_toml)
    attempted = 0
    consec = 0  # consecutive failures, for the circuit breaker
    threshold = cfg.remote.max_consec_fail
    for b in books:
        slug, domain = b["slug"], b.get("domain", "")
        if only is not None and slug != only:
            continue
        if max_books is not None and attempted >= max_books:
            print(
                f"--max-books {max_books} reached — stopping cleanly (done books skip on re-run)."
            )
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
            manifest[slug] = {
                "status": "convert_failed",
                "domain": domain,
                "error": str(e),
                "error_class": type(e).__name__,
            }
            save()
            consec += 1
            if _breaker_trips(ex, consec, threshold):
                break
            continue
        if not ok:
            print(f"  CONVERT FAILED: {slug} — log tail:\n{log[-2000:]}")
            manifest[slug] = {
                "status": "convert_failed",
                "domain": domain,
                "error_class": "permanent",
            }
            save()
            consec += 1
            if _breaker_trips(ex, consec, threshold):
                break
            continue

        work = os.path.join(stage, slug)
        try:
            fetched = ex.fetch(slug, cfg.convert.out_root, work, cfg.remote.fetch_timeout)
        except Exception as e:
            print(f"  FETCH ERROR: {slug}: {e}")
            manifest[slug] = {
                "status": "fetch_failed",
                "domain": domain,
                "error": str(e),
                "error_class": type(e).__name__,
            }
            save()
            consec += 1
            if _breaker_trips(ex, consec, threshold):
                break
            continue
        if not fetched:
            manifest[slug] = {"status": "fetch_failed", "domain": domain, "error_class": "fetch"}
            save()
            consec += 1
            if _breaker_trips(ex, consec, threshold):
                break
            continue
        if isinstance(ex, LocalExecutor):
            work = ex.artifacts_dir(slug, cfg.convert.out_root)

        md = os.path.join(work, f"{slug}.md")
        try:
            run_chain(
                md,
                slug,
                out_dir=os.path.join(work, "chapters"),
                source_name=os.path.basename(b["pdf"]),
                apply=True,
            )
        except Exception as e:
            print(f"  PHASE5 FAILED: {slug}: {e}")
            manifest[slug] = {"status": "phase5_failed", "domain": domain, "error_class": "phase5"}
            save()
            consec += 1
            if _breaker_trips(ex, consec, threshold):
                break
            continue
        # chapters need the shared images/ dir next to them for relative refs to resolve
        img_src = os.path.join(work, "images")
        img_dst = os.path.join(work, "chapters", "images")
        if os.path.isdir(img_src):
            os.makedirs(img_dst, exist_ok=True)
            for img in os.listdir(img_src):
                shutil.copy(os.path.join(img_src, img), os.path.join(img_dst, img))

        consec = 0  # a success resets the circuit breaker
        entry: dict[str, Any] = {
            "status": "done",
            "domain": domain,
            "minutes": round((time.time() - t0) / 60, 1),
        }
        if vault:
            dest = (
                os.path.join(os.path.expanduser(vault), domain, slug)
                if domain
                else os.path.join(os.path.expanduser(vault), slug)
            )
            shutil.copytree(os.path.join(work, "chapters"), dest, dirs_exist_ok=True)
            entry["vault_path"] = dest
            print(f"  DONE {slug} -> {dest} ({entry['minutes']} min)")
        else:
            print(f"  DONE {slug} -> {os.path.join(work, 'chapters')} ({entry['minutes']} min)")
        manifest[slug] = entry
        save()
    print("BATCH COMPLETE")
    return manifest
