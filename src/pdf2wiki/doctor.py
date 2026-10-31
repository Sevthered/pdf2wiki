# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""`pdf2wiki doctor`: read-only environment checks.

Each check encodes a failure that cost real time before:

- vllm's Triton JIT needs a C compiler; a minimal Ubuntu has none.
- A helper file named like a stdlib module (`profile.py`) in MinerU's cwd shadows the stdlib.
- An SSH timeout was blamed on a sleeping host while this machine sat on the wrong network.
- The remote host ran an older pdf2wiki than the control machine.

The command changes nothing and sends nothing to a third party. The only network traffic is the
SSH and TCP probes below. A token is never read into any output: only its source and its length.
"""

from __future__ import annotations

import importlib
import ipaddress
import os
import platform
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlparse

OK, WARN, FAIL, SKIP = "ok", "warn", "fail", "skip"

MIN_VRAM_MIB = 8192  # MinerU's hybrid pass needs about 8 GB
MIN_FREE_GIB = 10


@dataclass
class Check:
    group: str
    name: str
    status: str  # ok | warn | fail | skip
    detail: str
    fix: str = ""


# ---------- the one subprocess seam ----------


def _run(
    cmd: list[str], timeout: int, env: dict[str, str] | None = None, cwd: str | None = None
) -> tuple[int, str, str]:
    """Run `cmd`, return (returncode, stdout, stderr). Never raises: a missing binary or a timeout
    gives returncode -1 and the reason in stderr. Every subprocess in this module goes through
    here, so tests patch one function."""
    try:
        r = subprocess.run(  # noqa: S603 - list-form argv, no shell
            cmd, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd
        )
    except subprocess.TimeoutExpired:
        return -1, "", f"timed out after {timeout}s"
    except OSError as e:
        return -1, "", str(e)
    return r.returncode, r.stdout, r.stderr


def _first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


# ---------- config files and tokens ----------


def check_config(report: Any, explicit: bool | None = None) -> list[Check]:
    """Report each file load_config_report found, and each problem it listed."""
    if explicit is None:
        explicit = report.explicit
    out = []
    fatal = {p.path for p in report.problems if p.kind in ("read", "parse")}
    for f in report.files:
        if f.exists and f.path not in fatal:
            out.append(Check("core", "config", OK, f"loaded {f.path}"))
        elif not f.exists and explicit:
            # every other command exits 2 on a missing explicit path; doctor says why
            out.append(
                Check(
                    "core",
                    "config",
                    FAIL,
                    f"--config {f.path} does not exist, so every other pdf2wiki command stops with exit 2",
                    "correct the path or remove --config",
                )
            )
    for p in report.problems:
        if p.kind == "read":
            out.append(
                Check(
                    "core",
                    "config",
                    FAIL,
                    f"cannot read {p.path}: {p.message}",
                    "check that the path is a file and that you may read it",
                )
            )
        elif p.kind == "parse":
            out.append(
                Check(
                    "core",
                    "config",
                    FAIL,
                    f"cannot parse {p.path}: {p.message}",
                    "fix the TOML syntax, and save the file as UTF-8",
                )
            )
        else:
            fix = (
                f"make [{p.section}] a table"
                if not p.key
                else f"set {p.key} in [{p.section}] to {p.expected}"
            )
            out.append(
                Check(
                    "core",
                    "config",
                    FAIL,
                    f"wrong type in {p.path}: {p.message}; every other command stops on this value "
                    "(doctor goes on with the default)",
                    fix,
                )
            )
    if not explicit and not any(f.exists for f in report.files):
        searched = ", ".join(f.path for f in report.files)
        out.append(
            Check("core", "config", OK, f"no config file found ({searched}); using defaults")
        )
    return out


def _token_sources(cfg: Any) -> list[tuple[str, Any]]:
    """Each configured token in resolution order as (label, TokenRead), read through the
    converter's own helpers so the two cannot drift. The value is dropped here: only the length,
    the error and the cause go on."""
    from dataclasses import replace

    from .convert.cloud import read_token, token_sources

    return [(src.label, replace(read_token(src), value="")) for src in token_sources(cfg)]


def check_inline_token(report: Any) -> list[Check]:
    """Warn for an inline token in any config file except the user-level one, which lives
    outside every repository. A project file, or a `--config ./books.toml`, can be committed."""
    from .config import config_candidates

    user = os.path.abspath(config_candidates()[0])
    out = []
    for f in report.files:
        if f.data is None or os.path.abspath(f.path) == user:
            continue
        section = f.data.get("mineru_cloud", {})
        tok = section.get("token", "") if isinstance(section, dict) else ""
        if isinstance(tok, str) and tok.strip():
            out.append(
                Check(
                    "core",
                    "inline token",
                    WARN,
                    f"{f.path} sets [mineru_cloud].token inline; a commit can leak it",
                    "use env MINERU_API_TOKEN or [mineru_cloud].token_file instead",
                )
            )
    return out


# ---------- core ----------


def check_python() -> Check:
    return Check("core", "python", OK, f"{platform.python_version()} ({sys.executable})")


def check_version() -> Check:
    from . import __version__

    return Check("core", "pdf2wiki", OK, __version__)


def check_pymupdf() -> Check:
    try:
        fitz = importlib.import_module("pymupdf")
    except ImportError as e:
        return Check(
            "core",
            "pymupdf",
            FAIL,
            f"import failed: {e}",
            "reinstall pdf2wiki: pip install pymupdf",
        )
    return Check("core", "pymupdf", OK, str(getattr(fitz, "__version__", "unknown")))


# ---------- local convert ----------


def check_os() -> Check | None:
    if platform.system() == "Linux":
        return None
    return Check(
        "local convert",
        "os",
        SKIP,
        f"{platform.system()}: local conversion targets Linux with an NVIDIA CUDA GPU. "
        "Use --remote HOST or --mineru-cloud instead",
    )


def other_convert_path(cfg: Any, remote: str | None, tokens: list[tuple[str, Any]]) -> bool:
    """Can a book convert without local MinerU? Computed once per run. A hybrid server does not
    count: its offload still runs the pipeline pass through the local `mineru` binary."""
    usable = any(r.length for _, r in tokens)
    return bool(remote or cfg.remote.host or usable)


def check_mineru_binary(cfg: Any, other_path: bool) -> tuple[Check, str | None]:
    def missing(detail: str, fix: str) -> tuple[Check, None]:
        status = WARN if other_path else FAIL
        return Check("local convert", "mineru binary", status, detail, fix), None

    try:
        path = cfg.mineru.resolve_binary()
    except FileNotFoundError:
        return missing(
            "mineru not found on PATH and [mineru].binary is not set",
            "install MinerU, or set [mineru].binary in pdf2wiki.toml",
        )
    if not (os.path.isfile(path) and os.access(path, os.X_OK)):
        return missing(f"{path} is not an executable file", "correct [mineru].binary")
    return Check("local convert", "mineru binary", OK, path), path


def check_mineru_version(mineru: str) -> Check:
    rc, out, err = _run([mineru, "--version"], 60)
    line = _first_line(out) or _first_line(err)
    if rc != 0:
        return Check(
            "local convert",
            "mineru version",
            WARN,
            f"`mineru --version` failed (exit {rc}): {line}",
            "run `mineru --version` by hand and read the whole error",
        )
    return Check("local convert", "mineru version", OK, line)


_SHELLS = {"sh", "bash", "dash", "zsh"}
_TRAMPOLINE = "'" * 3 + "exec'"  # pip's long-path launcher: sh, then a python-quoted exec line


_TRAMPOLINE_RELATIVE = re.compile(
    r"""^\s*"\$\(dirname -- "\$\(realpath -- "\$0"\)"\)"/'?([^'"\s$`]+)'?"""
)


def _trampoline_python(mineru: str, rest: str) -> str | None:
    """The interpreter named by pip's or uv's trampoline line (the part after `'''exec'`).
    The relocatable form puts a shell expression in the path. It means the directory of the
    real script, so resolve that here. Any other `$` or backtick form is not safe to guess."""
    m = _TRAMPOLINE_RELATIVE.match(rest)
    if m:
        return os.path.join(os.path.dirname(os.path.realpath(mineru)), m.group(1))
    try:
        exec_line = shlex.split(rest)
    except ValueError:
        return None
    if not exec_line or "$" in exec_line[0] or "`" in exec_line[0]:
        return None
    return exec_line[0]


def _shebang_python(mineru: str) -> str | None:
    """The interpreter a console script runs under. Three shapes: `#!/path/python`,
    `#!/usr/bin/env [-S] [flags] python3 [args]`, and pip's trampoline (`#!/bin/sh`, then an
    exec line that names the real interpreter)."""
    try:
        with open(mineru, "rb") as f:
            lines = f.read(1024).decode("utf-8", "replace").splitlines()
    except OSError:
        return None
    if not lines or not lines[0].startswith("#!"):
        return None
    try:
        parts = shlex.split(lines[0][2:])
    except ValueError:
        return None
    if not parts:
        return None
    base = os.path.basename(parts[0])
    if base in _SHELLS:
        if len(lines) > 1 and lines[1].startswith(_TRAMPOLINE):
            return _trampoline_python(mineru, lines[1][len(_TRAMPOLINE) :])
        return None  # a shell wrapper (conda, module launchers) hides the interpreter
    if base == "env":
        from .convert.merge import _mineru_env

        # MinerU runs with this PATH, not doctor's own
        path = _mineru_env()["PATH"]
        for tok in parts[1:]:
            if tok.startswith("-") or "=" in tok:
                continue  # -S, -u, NAME=value belong to env itself
            return shutil.which(tok, path=path)
        return None
    return parts[0]


def check_torch(cfg: Any, mineru: str, other_path: bool = False) -> Check:
    name = "mineru torch"
    py = _shebang_python(mineru)
    if not py:
        return Check(
            "local convert",
            name,
            WARN,
            f"cannot read the interpreter from the shebang of {mineru}",
            "run MinerU's python by hand: import torch; torch.cuda.is_available()",
        )
    code = "import torch;print(torch.__version__);print(torch.cuda.is_available())"
    from .convert.merge import _mineru_env

    # `-c` puts the cwd first on sys.path, so a shadowing file in the caller's cwd would break
    # the probe itself. Run it in an empty directory, with the env MinerU gets.
    with tempfile.TemporaryDirectory() as clean:
        rc, out, err = _run([py, "-c", code], 120, env=_mineru_env(), cwd=clean)
    lines = out.split()
    if rc != 0 or len(lines) < 2:
        return Check(
            "local convert",
            name,
            WARN,
            f"{py} could not import torch: {_first_line(err) or 'no output'}",
            "reinstall MinerU with its torch dependency",
        )
    version, cuda = lines[0], lines[1] == "True"
    if cuda:
        return Check("local convert", name, OK, f"torch {version}, CUDA available ({py})")
    if cfg.mineru.hybrid_server_url:
        return Check(
            "local convert",
            name,
            WARN,
            f"torch {version}, CUDA not available; only the pipeline pass runs here, on CPU",
        )
    return Check(
        "local convert",
        name,
        WARN if other_path else FAIL,
        f"torch {version} reports CUDA not available ({py})",
        "install a CUDA build of torch that matches the driver, or set --hybrid-server-url",
    )


def check_gpu() -> Check:
    from .convert.merge import _mineru_env

    env = _mineru_env()
    exe = shutil.which("nvidia-smi", path=env.get("PATH"))
    if not exe:
        return Check(
            "local convert",
            "gpu",
            WARN,
            "nvidia-smi not found",
            "install the NVIDIA driver (on WSL2 the driver lives on Windows)",
        )
    rc, out, err = _run(
        [exe, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"], 30, env=env
    )
    line = _first_line(out)
    if rc != 0 or "," not in line:
        return Check(
            "local convert",
            "gpu",
            WARN,
            f"nvidia-smi failed (exit {rc}): {_first_line(err) or line or 'no output'}",
            "run nvidia-smi by hand and read the whole error",
        )
    name, _, mem = line.rpartition(",")
    try:
        mib = int(float(mem.strip()))
    except ValueError:
        return Check("local convert", "gpu", WARN, f"cannot read the memory size from: {line}")
    detail = f"{name.strip()}, {mib} MiB"
    if mib < MIN_VRAM_MIB:
        return Check(
            "local convert",
            "gpu",
            WARN,
            f"{detail}; the MinerU hybrid pass needs about 8 GB",
            "use --hybrid-server-url or --mineru-cloud for the hybrid pass",
        )
    return Check("local convert", "gpu", OK, detail)


def check_compiler(cfg: Any, other_path: bool = False) -> Check | None:
    if cfg.mineru.hybrid_server_url:
        return None  # the hybrid pass runs elsewhere, so no local Triton JIT
    # Mirrors triton-lang/triton python/triton/runtime/build.py, `_find_compiler("c")` (read on
    # main, commit d06f067, 2026-03-19): $CC if set (taken as written), else gcc, else clang.
    # It never tries `cc`. If none is found it raises `Failed to find C compiler`.
    cc_env = os.environ.get("CC")
    if cc_env:
        return Check("local convert", "c compiler", OK, f"$CC is set: {cc_env}")
    found = shutil.which("gcc") or shutil.which("clang")
    if found:
        return Check("local convert", "c compiler", OK, found)
    return Check(
        "local convert",
        "c compiler",
        WARN if other_path else FAIL,
        "no gcc or clang on PATH and $CC is not set; vllm's Triton JIT compiles CUDA kernels at "
        "engine start and dies with `Failed to find C compiler`",
        "sudo apt install build-essential python3-dev, or set $CC",
    )


_MODULE_SUFFIXES = (".py", ".pyc", ".so", ".pyd")


def _importable_name(path: str, entry: str) -> str | None:
    """The module name Python would import `entry` as, or None if it is not importable.
    A file counts by its suffix (`x.cpython-312-x86_64-linux-gnu.so` imports as `x`). A directory
    counts only with an `__init__.py`: one without is a namespace portion, which a regular
    module later on sys.path still beats."""
    if entry.startswith(".") or entry == "__pycache__":
        return None
    if os.path.isdir(path):
        return entry if os.path.isfile(os.path.join(path, "__init__.py")) else None
    if entry.endswith((".py", ".pyc")):
        stem = os.path.splitext(entry)[0]  # `json.backup.py` imports as nothing
        return stem if stem.isidentifier() else None
    if entry.endswith((".so", ".pyd")):
        stem = entry.split(".")[0]  # the ABI tag form: `x.cpython-312-...so` imports as `x`
        return stem if stem.isidentifier() else None
    return None


def check_workdir(cfg: Any) -> Check:
    d = os.path.expanduser(cfg.convert.workdir)
    if not os.path.isdir(d):
        return Check(
            "local convert", "workdir", OK, f"{d} does not exist yet; convert creates it clean"
        )
    std = sys.stdlib_module_names
    shadow: list[str] = []
    other: list[str] = []
    for entry in sorted(os.listdir(d)):
        full = os.path.join(d, entry)
        name = _importable_name(full, entry)
        if name is None:
            continue
        label = entry + "/" if os.path.isdir(full) else entry
        (shadow if name in std else other).append(label)
    if shadow:
        extra = f"; also importable: {', '.join(other)}" if other else ""
        return Check(
            "local convert",
            "workdir",
            FAIL,
            f"{d} holds names that shadow the stdlib: {', '.join(shadow)}. "
            f"MinerU imports them instead of the stdlib{extra}",
            "move or rename them, or point [convert].workdir at an empty directory",
        )
    if other:
        return Check(
            "local convert",
            "workdir",
            WARN,
            f"{d} should hold no Python modules, because MinerU runs from it and they can "
            f"shadow installed packages: {', '.join(other)}",
            "move them out, or point [convert].workdir at an empty directory",
        )
    return Check("local convert", "workdir", OK, f"{d} holds no importable modules")


def check_disk(cfg: Any) -> Check:
    p = os.path.abspath(os.path.expanduser(cfg.convert.out_root))
    while not os.path.exists(p) and os.path.dirname(p) != p:
        p = os.path.dirname(p)
    try:
        free = shutil.disk_usage(p).free / 2**30
    except OSError as e:
        return Check("local convert", "disk", WARN, f"cannot read free space at {p}: {e}")
    detail = f"{free:.1f} GiB free at {p}"
    if free < MIN_FREE_GIB:
        return Check(
            "local convert",
            "disk",
            WARN,
            f"{detail}; a book run needs about {MIN_FREE_GIB} GiB",
            "free space or set [convert].out_root on a larger disk",
        )
    return Check("local convert", "disk", OK, detail)


# ---------- hybrid server ----------


def check_hybrid_server(url: str) -> Check:
    u = urlparse(url)
    host = u.hostname
    if not host:
        return Check(
            "hybrid server",
            "tcp",
            FAIL,
            f"cannot read a host from {url!r}",
            "set --hybrid-server-url to http://HOST:PORT",
        )
    try:
        port = u.port or (443 if u.scheme == "https" else 80)
    except ValueError:
        return Check(
            "hybrid server",
            "tcp",
            FAIL,
            f"invalid port in {url!r}",
            "fix the port in [mineru].hybrid_server_url",
        )
    try:
        with socket.create_connection((host, port), timeout=5):
            pass
    except OSError as e:
        return Check(
            "hybrid server",
            "tcp",
            FAIL,
            f"cannot connect to {host}:{port}: {e}",
            "start the MinerU server, or check the address and the network",
        )
    return Check("hybrid server", "tcp", OK, f"{host}:{port} accepts connections")


# ---------- remote ----------


def _ssh_target(host: str) -> tuple[str, int] | None:
    rc, out, _ = _run(["ssh", "-G", "--", host], 10)
    if rc != 0:
        return None
    hostname, port = "", 22
    for line in out.splitlines():
        key, _, val = line.partition(" ")
        if key == "hostname":
            hostname = val.strip()
        elif key == "port":
            port = int(val.strip())
    return (hostname, port) if hostname else None


def _source_address(ip: str, port: int) -> str:
    """The local address the OS would use to reach `ip`. A UDP connect sends no packet."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((ip, port))
        return str(s.getsockname()[0])
    finally:
        s.close()


_PRIVATE_BLOCKS = [
    ipaddress.IPv4Network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
]


def _private_block(addr: str) -> ipaddress.IPv4Network | None:
    ip = ipaddress.IPv4Address(addr)
    return next((b for b in _PRIVATE_BLOCKS if ip in b), None)


def network_hint(host: str) -> tuple[str, str] | None:
    """Best-effort (detail, fix) for an SSH that timed out. Any error gives None, never a crash.

    A verdict needs proof: the host is in a private block, and this machine is in another block or
    in none. Two addresses in one block but different /24 nets prove nothing (a /16 LAN is
    common), so that case is worded as a possibility."""
    try:
        target = _ssh_target(host)
        if not target:
            return None
        name, port = target
        ip = str(socket.getaddrinfo(name, port, socket.AF_INET)[0][4][0])
        src = _source_address(ip, port)
        host_block = _private_block(ip)
        if host_block is None:
            return None  # a public target says nothing about our subnet
        net24 = ipaddress.ip_network(f"{ip}/24", strict=False)
        if ipaddress.ip_address(src) in net24:
            return (
                f"this machine ({src}) is on the host's subnet ({ip})",
                "the host may be asleep or off: wake it, then run doctor again",
            )
        if _private_block(src) != host_block:
            return (
                f"this machine ({src}) is on a different network than the host ({ip}); "
                f"it needs an address in {net24}",
                "join the host's network first, and only then wake the host",
            )
        return (
            f"this machine ({src}) may be on a different network than the host ({ip})",
            "if this machine is not on the host's network, join it first. "
            "Otherwise the host may be asleep or off",
        )
    except Exception:
        return None


def _ssh_failure_kind(err: str) -> str:
    low = err.lower()
    if "host key verification failed" in low or "identification has changed" in low:
        return "hostkey"
    if "permission denied" in low:
        return "auth"
    if "timed out" in low or "no route to host" in low or "network is unreachable" in low:
        return "network"
    return "other"


def _ssh_failure_fix(host: str, kind: str) -> str:
    if kind == "auth":
        return "the host answers but refuses this key: authorize the key on the host and ssh-add it"
    if kind == "hostkey":
        return (
            f"a new host: run `ssh {host}` once and accept its key. "
            f"A changed key: run `ssh-keygen -R {host}`, then connect again"
        )
    if kind == "network":
        return (
            f"run `ssh -v {host}` to see where it stops, and check that the host is awake "
            "and that this machine is on its network"
        )
    return (
        f"run `ssh -v {host}` to see why, and check the HostName and Port for {host} "
        "in ~/.ssh/config"
    )


def _remote_version_check(rc: int, out: str, err: str) -> Check:
    from . import __version__

    text, low = _first_line(out), err.lower()
    if rc in (255, -1):  # ssh itself failed, or our timeout fired
        return Check(
            "remote",
            "pdf2wiki",
            WARN,
            "could not read the remote version (connection lost or timed out)",
            "run doctor again, and run `ssh -v HOST` if it keeps happening",
        )
    if rc == 127 or (rc != 0 and "not found" in low):
        return Check(
            "remote",
            "pdf2wiki",
            WARN,
            "pdf2wiki not found on the remote PATH",
            "install pdf2wiki on the host, or put it on the PATH of a non-interactive shell",
        )
    if rc != 0:
        if "unrecognized arguments" in low or "usage:" in low:
            return Check(
                "remote",
                "pdf2wiki",
                WARN,
                "remote pdf2wiki has no --version, so it is older than this one",
                "upgrade pdf2wiki on the host",
            )
        return Check(
            "remote",
            "pdf2wiki",
            WARN,
            f"`pdf2wiki --version` failed on the host (exit {rc}): {_first_line(err)}",
            "run it on the host by hand and read the whole error",
        )
    if not text:
        return Check("remote", "pdf2wiki", WARN, "the host printed no version")
    rv = text.split()[-1]
    if rv == __version__:
        return Check("remote", "pdf2wiki", OK, f"remote {rv} matches local")
    return Check(
        "remote",
        "pdf2wiki",
        WARN,
        f"remote {rv}, local {__version__}",
        "upgrade the older side so both run the same version",
    )


def check_remote(cfg: Any, host: str) -> list[Check]:
    from .executor import InvalidHostError, SSHExecutor, _remote_path, validate_host

    try:
        validate_host(host)  # before any ssh: a host such as -oProxyCommand=... is an option
    except InvalidHostError as e:
        return [
            Check(
                "remote",
                "ssh",
                FAIL,
                str(e),
                "set [remote].host or --remote to an ssh alias or user@host",
            )
        ]
    ex = SSHExecutor(
        host, cfg.remote.books_dir, cfg.remote.workdir, connect_timeout=cfg.remote.connect_timeout
    )
    opts = ex._ssh_opts()
    t = cfg.remote.connect_timeout + 5
    rc, out, err = _run(["ssh", *opts, "--", host, "echo ok"], t)
    if rc != 0 or "ok" not in out:
        detail = f"cannot reach {host} over SSH: {_first_line(err) or 'connect timeout'}"
        kind = _ssh_failure_kind(err) if err.strip() else "network"
        fix = _ssh_failure_fix(host, kind)
        if kind == "network":
            hint = network_hint(host)
            if hint:
                detail, fix = f"{detail}. {hint[0]}", hint[1]
        return [Check("remote", "ssh", FAIL, detail, fix)]
    checks = [Check("remote", "ssh", OK, f"{host} answers")]
    # One ssh call for the version and the books_dir, because the idle-stopping WSL box can drop
    # a later connection. Markers keep the parse exact; POSIX sh only, as executor.convert does.
    script = (
        'v=$(pdf2wiki --version 2>&1); r=$?; echo "VERRC=$r"; '
        "echo \"VER=$(printf %s \"$v\" | tr '\\n' ' ')\""
    )
    books = cfg.remote.books_dir
    path = _remote_path(books) if books else ""
    if path:
        script += f"; if test -d {shlex.quote(path)}; then echo DIR=yes; else echo DIR=no; fi"
    rc, out, err = _run(["ssh", *opts, "--", host, script], t + 10)
    marks = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    if rc != 0 or "VERRC" not in marks:  # ssh dropped (255) or timed out (-1): nothing was read
        checks.append(_remote_version_check(rc if rc != 0 else 255, "", err))
        if path:
            checks.append(
                Check(
                    "remote",
                    "books_dir",
                    WARN,
                    f"could not check {path} on {host} (connection lost or timed out)",
                    "run doctor again",
                )
            )
        return checks
    vrc = int(marks["VERRC"]) if marks["VERRC"].isdigit() else 1
    text = marks.get("VER", "").strip()
    checks.append(_remote_version_check(vrc, text if vrc == 0 else "", text if vrc != 0 else ""))
    if path:
        if marks.get("DIR") == "yes":
            checks.append(Check("remote", "books_dir", OK, f"{path} exists on {host}"))
        else:
            checks.append(
                Check(
                    "remote",
                    "books_dir",
                    FAIL,
                    f"{path} is not a directory on {host}",
                    "create it or correct [remote].books_dir",
                )
            )
    return checks


# ---------- cloud ----------


def _token_fix(cause: str) -> str:
    return {
        "missing": "create the file, or correct [mineru_cloud].token_file",
        "permission": "change the file permissions so you may read it (chmod u+r)",
        "decode": "save the file as UTF-8, with the token and nothing else",
    }.get(cause, "point [mineru_cloud].token_file at a readable text file")


def check_cloud(tokens: list[tuple[str, Any]]) -> list[Check]:
    out = []
    winner = next((label for label, r in tokens if r.length), None)
    for label, r in tokens:
        if r.error:
            # a source that wins first makes an unreadable later source harmless
            if winner:
                detail = f"{label} is unreadable ({r.error}) but is not used, because {winner} wins"
                out.append(Check("cloud", "token", WARN, detail, "fix or remove token_file"))
            else:
                out.append(
                    Check("cloud", "token", FAIL, f"{label}: {r.error}", _token_fix(r.cause))
                )
        elif not r.length:
            out.append(Check("cloud", "token", WARN, f"{label}: file is empty"))
        else:
            out.append(Check("cloud", "token", OK, f"{label}, {r.length} characters"))
    return out


# ---------- driver ----------


def _try(group: str, name: str, fn: Callable[[], Any]) -> tuple[Any, list[Check]]:
    """Run one check. A crash becomes a FAIL line, because doctor must always print its report."""
    try:
        return fn(), []
    except Exception as e:
        crash = Check(
            group,
            name,
            FAIL,
            f"check crashed: {type(e).__name__}: {e}",
            "report this as a pdf2wiki bug, with the line above",
        )
        return None, [crash]


def _safe(group: str, name: str, fn: Callable[[], Any]) -> list[Check]:
    res, crash = _try(group, name, fn)
    if crash:
        return crash
    if res is None:
        return []
    return list(res) if isinstance(res, list) else [res]


def run_checks(report: Any, *, remote: str | None = None) -> list[Check]:
    """Run every check. `report` is the ConfigReport from load_config_report: it holds the merged
    config, the files read, and the problems found."""
    cfg = report.config
    checks: list[Check] = []

    def add(group: str, name: str, fn: Callable[[], Any]) -> None:
        checks.extend(_safe(group, name, fn))

    add("core", "python", check_python)
    add("core", "pdf2wiki", check_version)
    add("core", "pymupdf", check_pymupdf)
    add("core", "config", lambda: check_config(report))
    add("core", "inline token", lambda: check_inline_token(report))

    tokens, crash = _try("cloud", "token", lambda: _token_sources(cfg))
    checks.extend(crash)
    tokens = tokens or []
    other = other_convert_path(cfg, remote, tokens)

    on_linux = platform.system() == "Linux"
    hybrid = bool(cfg.mineru.hybrid_server_url)
    skip = check_os()
    if skip:
        checks.append(skip)
    # The hybrid offload still runs the pipeline pass through the local mineru binary, so that
    # check runs even where local GPU conversion is skipped.
    if on_linux or hybrid:
        res, crash = _try("local convert", "mineru binary", lambda: check_mineru_binary(cfg, other))
        checks.extend(crash)
        mineru: str | None = None
        if res is not None:
            binary, mineru = res
            checks.append(binary)
        if mineru:
            add("local convert", "mineru version", lambda: check_mineru_version(str(mineru)))
            if on_linux:
                add("local convert", "mineru torch", lambda: check_torch(cfg, str(mineru), other))
    if on_linux:
        add("local convert", "gpu", check_gpu)
        add("local convert", "c compiler", lambda: check_compiler(cfg, other))
        add("local convert", "workdir", lambda: check_workdir(cfg))
        add("local convert", "disk", lambda: check_disk(cfg))

    if hybrid:
        add("hybrid server", "tcp", lambda: check_hybrid_server(cfg.mineru.hybrid_server_url))
    host = remote or cfg.remote.host
    if host:
        add("remote", "ssh", lambda: check_remote(cfg, host))
    add("cloud", "token", lambda: check_cloud(tokens))
    return checks


# ---------- output ----------

_WORD = {OK: "ok", WARN: "warn", FAIL: "FAIL", SKIP: "skip"}


def counts(checks: list[Check]) -> tuple[int, int]:
    return (
        sum(c.status == FAIL for c in checks),
        sum(c.status == WARN for c in checks),
    )


def render_human(checks: list[Check], version: str) -> str:
    lines = [f"pdf2wiki doctor {version}"]
    group = None
    width = max((len(c.name) for c in checks), default=0)
    for c in checks:
        if c.group != group:
            group = c.group
            lines += ["", group]
        lines.append(f"  {_WORD[c.status]:<5} {c.name:<{width}}  {c.detail}")
        if c.fix:
            lines.append(f"  {'':<5} {'':<{width}}  fix: {c.fix}")
    fails, warns = counts(checks)
    lines += ["", f"{fails} fail, {warns} warn"]
    return "\n".join(lines)


def render_json(checks: list[Check], version: str) -> dict[str, Any]:
    fails, warns = counts(checks)
    return {
        "version": version,
        "checks": [asdict(c) for c in checks],
        "fails": fails,
        "warns": warns,
    }
