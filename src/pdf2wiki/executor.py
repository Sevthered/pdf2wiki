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
from typing import Any


class ExecutionError(RuntimeError):
    pass


class LocalExecutor:
    def check(self) -> None:
        pass  # nothing to verify locally

    def convert(
        self, pdf_path: str, slug: str, out_root: str, timeout: int, cfg: Any = None
    ) -> tuple[bool, str]:
        """Run the converter locally. Returns (ok, log_text). `cfg` carries CLI overrides (e.g.
        --hybrid-server-url); when None, convert_book loads the default config."""
        from .convert import convert_book  # lazy: keep GPU-path imports out of CLI startup

        return convert_book(pdf_path, slug, out_root, timeout=timeout, cfg=cfg)

    def fetch(self, slug: str, out_root: str, dest_dir: str, timeout: int | None = None) -> bool:
        """Local mode: artifacts are already on disk — just report where. `timeout` is accepted for
        interface parity with SSHExecutor and ignored (no transfer happens)."""
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
    def __init__(
        self,
        host: str,
        books_dir: str,
        workdir: str,
        connect_timeout: int = 8,
        convert_timeout: int = 7200,
        fetch_timeout: int = 600,
        reap_grace: int = 120,
    ):
        self.host = host
        self.books_dir = _remote_path(books_dir) if books_dir else books_dir
        self.workdir = _remote_path(workdir)
        self.connect_timeout = connect_timeout
        self.convert_timeout = convert_timeout
        self.fetch_timeout = fetch_timeout
        self.reap_grace = reap_grace

    def _ssh_opts(self) -> list[str]:
        # ConnectTimeout bounds the TCP connect; BatchMode=yes fails instead of hanging on an
        # interactive auth/host-key prompt mid-batch (Timeouts-Pattern: bound every remote wait).
        # ServerAlive* keeps the control channel alive across a long MinerU pass: all converter
        # output goes to a remote log file, so the ssh channel is silent for minutes and a NAT/idle
        # timeout (WSL2 mirrored networking is prone to this) would otherwise drop it — the batch
        # would then mislabel a still-running convert as failed. 30s ping × 240 = ~2h tolerated
        # silence, comfortably over one pass and inside the `timeout Ns` reaper.
        return [
            "-o",
            f"ConnectTimeout={self.connect_timeout}",
            "-o",
            "BatchMode=yes",
            "-o",
            "ServerAliveInterval=30",
            "-o",
            "ServerAliveCountMax=240",
        ]

    def _run(self, cmd: list[str], timeout: int | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    def check(self) -> None:
        """Verify SSH connectivity ONCE before a batch. Without this, a dead connection makes
        every book fail near-instantly (a connect-timeout, not a real conversion failure) and a
        batch loop would burn through the entire list in minutes, mislabeling every book as
        failed."""
        r = self._run(
            ["ssh", *self._ssh_opts(), self.host, "echo ok"], timeout=self.connect_timeout + 5
        )
        if "ok" not in r.stdout:
            raise ExecutionError(
                f"cannot reach {self.host} over SSH: {r.stderr.strip() or 'connect timeout'}"
            )

    def convert(
        self, pdf_filename: str, slug: str, out_root: str, timeout: int | None = None
    ) -> tuple[bool, str]:
        """Run pdf2wiki's converter on the remote host. pdf_filename is relative to books_dir.
        Returns (ok, remote_log_text)."""
        t = int(timeout or self.convert_timeout)
        remote_pdf = f"{self.books_dir}/{pdf_filename}"
        out_root = _remote_path(out_root)
        log = f"{self.workdir}/logs/{slug}.log"
        # `timeout {t}s` on the REMOTE side self-reaps the converter (and its vllm/torch children) if
        # the local ssh gives up — Timeouts-Pattern [!warning]: abandoning the local wait does NOT stop
        # the remote work, leaving a zombie job that pins VRAM. The local subprocess waits t+reap_grace
        # so the remote reaper fires first (a remote timeout surfaces as EXIT=124, i.e. not ok).
        inner = (
            f"mkdir -p {shlex.quote(self.workdir)}/logs && "
            f"timeout {t}s pdf2wiki convert {shlex.quote(remote_pdf)} --name {shlex.quote(slug)} "
            f"--out {shlex.quote(out_root)} > {shlex.quote(log)} 2>&1; echo EXIT=$?"
        )
        r = self._run(["ssh", *self._ssh_opts(), self.host, inner], timeout=t + self.reap_grace)
        logfetch = self._run(
            ["ssh", *self._ssh_opts(), self.host, f"cat {shlex.quote(log)}"], timeout=60
        )
        logtext = (
            logfetch.stdout
            if logfetch.returncode == 0
            else f"(could not fetch remote log {log}: {logfetch.stderr.strip()})"
        )
        # the remote CLI's exit code is authoritative (pdf2wiki convert returns non-zero on any
        # failure) — do not scrape the log for failure words; book content may contain them
        ok = "EXIT=0" in r.stdout
        return ok, logtext

    def fetch(self, slug: str, out_root: str, dest_dir: str, timeout: int | None = None) -> bool:
        """Pull <out_root>/<slug>/{<slug>.md, images/} from the remote host. Every scp is timeout-
        bounded (Timeouts-Pattern: a stalled transfer must not hang the batch) and its exit code is
        checked — a partial pull fails loudly. Remote paths are shlex-quoted for the remote shell."""
        t = int(timeout or self.fetch_timeout)
        os.makedirs(dest_dir, exist_ok=True)
        out_root = _remote_path(out_root)
        opts = self._ssh_opts()
        md = shlex.quote(f"{out_root}/{slug}/{slug}.md")
        r1 = self._run(
            ["scp", "-q", *opts, f"{self.host}:{md}", os.path.join(dest_dir, f"{slug}.md")],
            timeout=t,
        )
        if r1.returncode != 0:
            return False
        imgs = shlex.quote(f"{out_root}/{slug}/images")
        r2 = self._run(
            ["scp", "-q", "-r", *opts, f"{self.host}:{imgs}", os.path.join(dest_dir, "images")],
            timeout=t,
        )
        # a book with zero figures legitimately has no images dir — only the md is mandatory
        if r2.returncode != 0 and "No such file" not in (r2.stderr or ""):
            return False
        return os.path.exists(os.path.join(dest_dir, f"{slug}.md"))

    def artifacts_dir(self, slug: str, out_root: str) -> str:
        raise ExecutionError("remote artifacts must be fetched first (use fetch())")
