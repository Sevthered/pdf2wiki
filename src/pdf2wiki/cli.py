# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""pdf2wiki command-line interface.

Convention: every mutating command is DRY-RUN by default and requires --apply to write
(exceptions: convert and qa, whose whole purpose is producing new artifacts in their own
output directories — they never modify existing files in place).
"""

import argparse
import json
import sys
from typing import Any

from .config import load_config


def _cmd_convert(a: argparse.Namespace, cfg: Any) -> int:
    from .executor import LocalExecutor, SSHExecutor

    if a.mineru_cloud:
        # Fully-managed cloud path (no GPU, no local MinerU): uploads the PDF to mineru.net. Mutually
        # exclusive with the local/remote/offload modes. See improvement-pdf2wiki-mineru-cloud-adapter.
        if a.remote or a.hybrid_server_url:
            print(
                "error: --mineru-cloud cannot combine with --remote or --hybrid-server-url "
                "(it runs the whole conversion in the mineru.net cloud). Pick one.",
                file=sys.stderr,
            )
            return 2
        out_root = a.out or cfg.convert.out_root
        if a.cloud_model == "merge":
            # dual-pass merge pseudo-model: 2 cloud calls (pipeline + vlm) + our local base-driven merge.
            # See decision-pdf2wiki-cloud-dual-merge.
            from .convert import convert_book_cloud_merge

            ok, log = convert_book_cloud_merge(a.pdf, a.name, out_root, cfg=cfg)
            return 0 if ok else 1
        from .convert import convert_book_cloud

        if a.cloud_model:
            cfg.mineru_cloud.model_version = a.cloud_model
        ok, log = convert_book_cloud(a.pdf, a.name, out_root, cfg=cfg)
        return 0 if ok else 1
    if a.hybrid_server_url:
        cfg.mineru.hybrid_server_url = a.hybrid_server_url
    if a.remote or cfg.remote.host:
        # --remote (whole-convert over SSH) and --hybrid-server-url (local pipeline + remote hybrid
        # VLM) are distinct, mutually exclusive convert strategies — refuse rather than silently
        # ignore one. See decision-pdf2wiki-api-hybrid-offload.
        if cfg.mineru.hybrid_server_url:
            print(
                "error: --remote and --hybrid-server-url are mutually exclusive convert modes "
                "(--remote runs the whole conversion on the SSH host; --hybrid-server-url runs "
                "pipeline locally and offloads only the hybrid VLM pass). Pick one.",
                file=sys.stderr,
            )
            return 2
        host = a.remote or cfg.remote.host
        ex = SSHExecutor(
            host,
            cfg.remote.books_dir,
            cfg.remote.workdir,
            cfg.remote.connect_timeout,
            cfg.remote.convert_timeout,
            cfg.remote.fetch_timeout,
            cfg.remote.reap_grace,
        )
        ex.check()
        ok, log = ex.convert(a.pdf, a.name, a.out or cfg.convert.out_root)
        print(log)  # remote log was captured on the remote host — show it
    else:
        local = LocalExecutor()  # own name: its convert() takes cfg, SSHExecutor's doesn't
        ok, log = local.convert(
            a.pdf, a.name, a.out or cfg.convert.out_root, cfg.convert.timeout, cfg=cfg
        )
        # local progress already streamed live by convert_book — don't print the log twice
    return 0 if ok else 1


def _cmd_phase5(a: argparse.Namespace, cfg: Any) -> int:
    from .phase5 import run_chain

    report = run_chain(a.md, a.book, out_dir=a.out, source_name=a.source_name, apply=a.apply)
    print(f"caption_unbleed: {report['caption_unbleed']['unwrapped']} unwrapped")
    lr = report["lang_retag"]
    print(f"lang_retag: {lr['changes']} changes {lr['stats']}")
    print(f"dash_normalize: {report['dash_normalize']['fixes']} fixes")
    mr = report["mermaid_repair"]
    print(
        f"mermaid_repair: {mr['blocks_changed']} blocks, "
        f"parse-breaker score {mr['score_before']} -> {mr['score_after']}"
    )
    print(f"code_unescape: {report['code_unescape']['fixes']} fixes")
    cs = report["chapter_split"]
    print(f"chapter_split: {cs['boundaries']} boundaries")
    for i, t in enumerate(cs["titles"], 1):
        print(f"  {i:2d}. {t}")
    if a.apply:
        print(f"\nAPPLIED — wrote {len(cs['files'])} chapter files")
    else:
        print(f"\n(dry-run — would write {len(cs['files'])} chapter files; pass --apply)")
    return 0


def _cmd_qa_sample(a: argparse.Namespace, cfg: Any) -> int:
    from .qa.sample import sample_pages

    r = sample_pages(
        a.pdf,
        a.name,
        a.qa_root or cfg.qa.root,
        n=a.pages or cfg.qa.pages,
        seed=a.seed if a.seed is not None else cfg.qa.seed,
        dpi=a.dpi or cfg.qa.dpi,
    )
    print(
        f"{a.name}: sampled {len(r['pages'])} pages (seed {r['seed']}) "
        f"from range {r['range'][0]}-{r['range'][1]} of {r['page_count']}"
    )
    print("pages:", r["pages"])
    print(f"sample pdf: {r['sample_pdf']} ; PNGs in {r['qa_dir']}/pages/")
    return 0


def _cmd_qa_review(a: argparse.Namespace, cfg: Any) -> int:
    from .qa.review import build_review

    r = build_review(a.qa_dir, a.name, blocks_path=a.blocks)
    print(f"wrote {r['review']} ; pages with content: {r['pages_with_content']}/{r['sampled']}")
    return 0


def _cmd_qa_flagged(a: argparse.Namespace, cfg: Any) -> int:
    from .qa.flagged import flagged_report

    reports = sorted(
        (flagged_report(p) for p in a.blocks), key=lambda r: r["flagged"], reverse=True
    )
    print(f"{'flagged':>7} {'diverged':>8} {'indent':>6} {'code':>5}  book")
    for r in reports:
        print(
            f"{r['flagged']:>7} {r['diverged']:>8} {r['indent_suspect']:>6} {r['code_blocks']:>5}  {r['name']}"
        )
    if len(reports) == 1:  # single book -> also list the blocks to eyeball
        print()
        for e in reports[0]["blocks"]:
            print(f"  p{e['page']:<4} [{e['lang'] or '?'}] {e['flag']}: {e['snippet']}")
    return 0


def _cmd_scan(a: argparse.Namespace, cfg: Any) -> int:
    from .scan import scan_dir

    print(json.dumps(scan_dir(a.directory), indent=1))
    return 0


def _cmd_batch(a: argparse.Namespace, cfg: Any) -> int:
    from .batch import run_batch

    manifest = run_batch(
        a.books,
        cfg,
        a.stage,
        remote=a.remote or (cfg.remote.host or None),
        max_books=a.max_books,
        only=a.only,
        vault=a.vault or (cfg.output.vault or None),
    )
    failed = [(s, e) for s, e in manifest.items() if e.get("status") != "done"]
    if failed:  # non-zero exit so CI/automation can detect a partial batch
        from collections import Counter

        by_class = Counter(e.get("error_class", "unknown") for _, e in failed)
        rollup = ", ".join(f"{k}×{v}" for k, v in by_class.most_common())
        print(f"batch: {len(failed)} book(s) not done — by class: {rollup}", file=sys.stderr)
        print(f"  not done: {[s for s, _ in failed]}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="pdf2wiki",
        description="Convert technical books (native-text PDFs) into "
        "clean, chapter-split, LLM-ready Markdown.",
    )
    ap.add_argument("--config", default=None, help="explicit config TOML path")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("convert", help="convert one PDF (dual-pass MinerU merge)")
    p.add_argument("pdf")
    p.add_argument("--name", required=True, help="output slug")
    p.add_argument("--out", default=None, help="output root (default from config)")
    p.add_argument("--remote", default=None, help="ssh host to run the conversion on")
    p.add_argument(
        "--hybrid-server-url",
        default=None,
        help="offload only the hybrid VLM pass to this OpenAI-compatible MinerU server "
        "(pipeline stays local); BYO server, no auth. Mutually exclusive with --remote",
    )
    p.add_argument(
        "--mineru-cloud",
        action="store_true",
        help="convert via the fully-managed mineru.net cloud (no GPU / no local MinerU). "
        "Uploads the PDF to a third-party cloud — needs a token (env MINERU_API_TOKEN "
        "or [mineru_cloud]). Mutually exclusive with --remote/--hybrid-server-url",
    )
    p.add_argument(
        "--cloud-model",
        default=None,
        choices=["pipeline", "vlm", "MinerU-HTML", "merge"],
        help="mineru.net model_version for --mineru-cloud (default: pipeline = code-safe; "
        "vlm adds indent/tables but CORRUPTS code; merge = run BOTH pipeline+vlm in the "
        "cloud and splice locally = clean code AND indent/tables, GPU-less)",
    )
    p.set_defaults(fn=_cmd_convert)

    p = sub.add_parser("phase5", help="post-process a converted .md (dry-run by default)")
    p.add_argument("md")
    p.add_argument("--book", required=True, help="book slug for frontmatter")
    p.add_argument("--out", default=None, help="chapter output dir (default: <md dir>/chapters)")
    p.add_argument(
        "--source-name",
        default=None,
        help="original PDF filename for frontmatter `source:` (avoids leaking a staging path)",
    )
    p.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    p.set_defaults(fn=_cmd_phase5)

    pqa = sub.add_parser("qa", help="conversion QA tools")
    qsub = pqa.add_subparsers(dest="qa_cmd", required=True)
    p = qsub.add_parser("sample", help="sample N random pages -> sample PDF + PNGs")
    p.add_argument("pdf")
    p.add_argument("name")
    p.add_argument("-n", "--pages", type=int, default=None)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--dpi", type=int, default=None)
    p.add_argument("--qa-root", default=None)
    p.set_defaults(fn=_cmd_qa_sample)
    p = qsub.add_parser("review", help="build per-page review.txt from blocks.json")
    p.add_argument("qa_dir")
    p.add_argument("name")
    p.add_argument("--blocks", default=None, help="explicit blocks.json path")
    p.set_defaults(fn=_cmd_qa_review)
    p = qsub.add_parser(
        "flags",
        help="report code blocks the VLM diverged on (from blocks.json), "
        "ranked across books — the highest-signal QA sample",
    )
    p.add_argument("blocks", nargs="+", help="one or more converted-book blocks.json paths")
    p.set_defaults(fn=_cmd_qa_flagged)

    p = sub.add_parser("scan", help="scan a directory of PDFs -> title/year guesses (JSON)")
    p.add_argument("directory")
    p.set_defaults(fn=_cmd_scan)

    p = sub.add_parser("batch", help="manifest-driven multi-book run (resumable)")
    p.add_argument("books", help="books TOML file ([[book]] entries with pdf/slug/domain)")
    p.add_argument("--stage", default="~/pdf2wiki/stage", help="staging + status-manifest dir")
    p.add_argument("--remote", default=None, help="ssh host to convert on")
    p.add_argument(
        "--max-books", type=int, default=None, help="stop after this many books attempted this run"
    )
    p.add_argument("--only", default=None, help="run only this slug")
    p.add_argument("--vault", default=None, help="final placement root (e.g. an Obsidian vault)")
    p.set_defaults(fn=_cmd_batch)

    a = ap.parse_args(argv)
    cfg = load_config(a.config)
    exit_code: int = a.fn(a, cfg)  # each _cmd_* returns an int exit code
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
