"""Execution backends: run the converter and fetch its artifacts, locally or over SSH.

LocalExecutor runs everything on this machine (the default — single machine with a local GPU).
SSHExecutor drives a remote GPU machine over SSH: the converter runs there, artifacts are pulled
back with scp. Requirements for remote mode: an OpenSSH-reachable host with pdf2wiki + MinerU
installed, key-based auth (no password prompts mid-batch).
"""
from __future__ import annotations

import os
import shlex
import subprocess


class ExecutionError(RuntimeError):
    pass


class LocalExecutor:
    def check(self) -> None:
        pass  # nothing to verify locally

    def convert(self, pdf_path: str, slug: str, out_root: str, timeout: int,
                cfg=None) -> tuple[bool, str]:
        """Run the converter locally. Returns (ok, log_text). `cfg` carries CLI overrides (e.g.
        --hybrid-server-url); when None, convert_book loads the default config."""
        from .convert import convert_book  # lazy: keep GPU-path imports out of CLI startup
        return convert_book(pdf_path, slug, out_root, timeout=timeout, cfg=cfg)

    def fetch(self, slug: str, out_root: str, dest_dir: str) -> bool:
        """Local mode: artifacts are already on disk — just report where."""
        src = os.path.join(os.path.expanduser(out_root), slug)
        return os.path.exists(os.path.join(src, f"{slug}.md"))

    def artifacts_dir(self, slug: str, out_root: str) -> str:
        return os.path.join(os.path.expanduser(out_root), slug)


def _remote_path(p: str) -> str:
    """Normalize a remote path: `~/x` becomes `x` (relative to the remote home, which is where
    non-interactive ssh commands start). shlex.quote() would otherwise make the tilde literal —
    the remote shell never expands a quoted `~`."""
    return p[2:] if p.startswith("~/") else p


class SSHExecutor:
    def __init__(self, host: str, books_dir: str, workdir: str,
                 connect_timeout: int = 8, convert_timeout: int = 7200):
        self.host = host
        self.books_dir = _remote_path(books_dir) if books_dir else books_dir
        self.workdir = _remote_path(workdir)
        self.connect_timeout = connect_timeout
        self.convert_timeout = convert_timeout

    def _run(self, cmd: list[str], timeout: int | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    def check(self) -> None:
        """Verify SSH connectivity ONCE before a batch. Without this, a dead connection makes
        every book fail near-instantly (a connect-timeout, not a real conversion failure) and a
        batch loop would burn through the entire list in minutes, mislabeling every book as
        failed."""
        r = self._run(["ssh", "-o", f"ConnectTimeout={self.connect_timeout}", self.host, "echo ok"])
        if "ok" not in r.stdout:
            raise ExecutionError(
                f"cannot reach {self.host} over SSH: {r.stderr.strip() or 'connect timeout'}"
            )

    def convert(self, pdf_filename: str, slug: str, out_root: str, timeout: int | None = None) -> tuple[bool, str]:
        """Run pdf2wiki's converter on the remote host. pdf_filename is relative to books_dir.
        Returns (ok, remote_log_text)."""
        remote_pdf = f"{self.books_dir}/{pdf_filename}"
        out_root = _remote_path(out_root)
        log = f"{self.workdir}/logs/{slug}.log"
        inner = (
            f"mkdir -p {shlex.quote(self.workdir)}/logs && "
            f"pdf2wiki convert {shlex.quote(remote_pdf)} --name {shlex.quote(slug)} "
            f"--out {shlex.quote(out_root)} > {shlex.quote(log)} 2>&1; echo EXIT=$?"
        )
        r = self._run(["ssh", self.host, inner], timeout=timeout or self.convert_timeout)
        logfetch = self._run(["ssh", self.host, f"cat {shlex.quote(log)}"])
        logtext = logfetch.stdout if logfetch.returncode == 0 else \
            f"(could not fetch remote log {log}: {logfetch.stderr.strip()})"
        # the remote CLI's exit code is authoritative (pdf2wiki convert returns non-zero on any
        # failure) — do not scrape the log for failure words; book content may contain them
        ok = "EXIT=0" in r.stdout
        return ok, logtext

    def fetch(self, slug: str, out_root: str, dest_dir: str) -> bool:
        """Pull <out_root>/<slug>/{<slug>.md, images/} from the remote host. scp exit codes are
        checked — a partial pull must fail loudly, not continue with missing artifacts."""
        os.makedirs(dest_dir, exist_ok=True)
        out_root = _remote_path(out_root)
        md = f"{out_root}/{slug}/{slug}.md"
        r1 = self._run(["scp", "-q", f"{self.host}:{md}", os.path.join(dest_dir, f"{slug}.md")])
        if r1.returncode != 0:
            return False
        r2 = self._run(["scp", "-q", "-r", f"{self.host}:{out_root}/{slug}/images",
                        os.path.join(dest_dir, "images")])
        # a book with zero figures legitimately has no images dir — only the md is mandatory
        if r2.returncode != 0 and "No such file" not in (r2.stderr or ""):
            return False
        return os.path.exists(os.path.join(dest_dir, f"{slug}.md"))

    def artifacts_dir(self, slug: str, out_root: str) -> str:
        raise ExecutionError("remote artifacts must be fetched first (use fetch())")
