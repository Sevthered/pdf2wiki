# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for `pdf2wiki doctor`. No real ssh, GPU, or network: every outside call is patched."""

import json
import os
import socket
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pdf2wiki.doctor as doctor
from pdf2wiki import __version__, cli
from pdf2wiki.config import Config
from pdf2wiki.convert.cloud import TokenRead
from pdf2wiki.doctor import FAIL, OK, SKIP, WARN, Check

SECRET = "tok-SECRET-VALUE-1234567890"
REAL_RUN = subprocess.run  # kept before the autouse fixture blocks subprocess


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """No ambient token, no real home config, cwd without a pdf2wiki.toml."""
    monkeypatch.delenv("MINERU_API_TOKEN", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    # Pin the host: the suite must give the same answer on a Linux CI runner and on a Mac. No test
    # may reach a real subprocess, `which`, GPU or network; a test that needs one patches it itself.
    monkeypatch.setattr(doctor.platform, "system", lambda: "Darwin")

    def no_subprocess(*a, **k):
        raise AssertionError(f"real subprocess in a unit test: {a!r}")

    monkeypatch.setattr(doctor.subprocess, "run", no_subprocess)
    monkeypatch.setattr(doctor.shutil, "which", lambda *a, **k: None)


def run_checks(cfg=None, *, config_path=None, remote=None):
    """doctor.run_checks takes a ConfigReport; tests hand in a Config and get one built."""
    from pdf2wiki.config import load_config_report

    report = load_config_report(config_path)
    if cfg is not None:
        report.config = cfg
    return doctor.run_checks(report, remote=remote)


def by_name(checks: list[Check], name: str) -> list[Check]:
    return [c for c in checks if c.name == name]


def one(checks: list[Check], name: str) -> Check:
    found = by_name(checks, name)
    assert len(found) == 1, [c.name for c in checks]
    return found[0]


def linux(monkeypatch):
    monkeypatch.setattr(doctor.platform, "system", lambda: "Linux")


def cfg_in(tmp_path) -> Config:
    cfg = Config()
    cfg.convert.workdir = str(tmp_path / "run")
    cfg.convert.out_root = str(tmp_path / "out")
    return cfg


# ---------- core ----------


def test_core_checks_ok():
    checks = run_checks(Config())
    assert one(checks, "python").status == OK
    assert one(checks, "pdf2wiki").detail == __version__
    assert one(checks, "pymupdf").status == OK


def test_pymupdf_import_failure_fails(monkeypatch):
    def boom(name):
        raise ImportError("no module")

    monkeypatch.setattr(doctor.importlib, "import_module", boom)
    c = doctor.check_pymupdf()
    assert c.status == FAIL and "no module" in c.detail


def test_explicit_missing_config_fails(tmp_path):
    missing = str(tmp_path / "nope.toml")
    checks = run_checks(Config(), config_path=missing)
    c = one(checks, "config")
    assert c.status == FAIL and missing in c.detail and "exit 2" in c.detail


def test_bad_toml_fails_with_parse_error(tmp_path):
    p = tmp_path / "bad.toml"
    p.write_text("[mineru\nbinary = 1\n")
    c = one(run_checks(Config(), config_path=str(p)), "config")
    assert c.status == FAIL and "cannot parse" in c.detail


def test_good_config_reported_loaded(tmp_path):
    p = tmp_path / "ok.toml"
    p.write_text("[convert]\ntimeout = 5\n")
    c = one(run_checks(Config(), config_path=str(p)), "config")
    assert c.status == OK and "loaded" in c.detail


def test_search_order_reports_both_files(tmp_path):
    home_cfg = tmp_path / "home" / ".config" / "pdf2wiki"
    home_cfg.mkdir(parents=True)
    (home_cfg / "config.toml").write_text("[qa]\ndpi = 100\n")
    (tmp_path / "pdf2wiki.toml").write_text("[qa]\ndpi = 90\n")
    loaded = [c for c in run_checks(Config()) if c.name == "config"]
    assert len(loaded) == 2 and all(c.status == OK for c in loaded)


def test_inline_token_in_project_file_warns(tmp_path):
    (tmp_path / "pdf2wiki.toml").write_text(f'[mineru_cloud]\ntoken = "{SECRET}"\n')
    c = one(run_checks(Config()), "inline token")
    assert c.status == WARN and "MINERU_API_TOKEN" in c.fix
    assert SECRET not in c.detail and SECRET not in c.fix


# ---------- local convert ----------


def test_non_linux_skips_local(monkeypatch):
    monkeypatch.setattr(doctor.platform, "system", lambda: "Darwin")
    checks = run_checks(Config())
    c = one(checks, "os")
    assert c.status == SKIP and "--remote" in c.detail and "--mineru-cloud" in c.detail
    assert not by_name(checks, "mineru binary")


def _no_mineru(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda *a, **k: None)


def test_mineru_missing_fails_without_other_path(monkeypatch, tmp_path):
    linux(monkeypatch)
    _no_mineru(monkeypatch)
    checks = run_checks(cfg_in(tmp_path))
    assert one(checks, "mineru binary").status == FAIL
    assert not by_name(checks, "mineru version") and not by_name(checks, "mineru torch")


@pytest.mark.parametrize("how", ["cfg_remote", "arg_remote", "token"])
def test_mineru_missing_warns_with_other_path(monkeypatch, tmp_path, how):
    linux(monkeypatch)
    _no_mineru(monkeypatch)
    monkeypatch.setattr(doctor, "_run", lambda *a, **k: (-1, "", "x"))
    monkeypatch.setattr(doctor, "network_hint", lambda h: None)
    monkeypatch.setattr(
        doctor, "check_hybrid_server", lambda u: Check("hybrid server", "tcp", OK, "")
    )
    cfg = cfg_in(tmp_path)
    remote = None
    if how == "cfg_remote":
        cfg.remote.host = "box"
    elif how == "arg_remote":
        remote = "box"
    else:
        monkeypatch.setenv("MINERU_API_TOKEN", SECRET)
    assert one(run_checks(cfg, remote=remote), "mineru binary").status == WARN


def test_hybrid_server_does_not_excuse_a_missing_mineru(monkeypatch, tmp_path):
    # the offload still runs the pipeline pass through the local mineru binary
    linux(monkeypatch)
    _no_mineru(monkeypatch)
    monkeypatch.setattr(
        doctor, "check_hybrid_server", lambda u: Check("hybrid server", "tcp", OK, "")
    )
    cfg = cfg_in(tmp_path)
    cfg.mineru.hybrid_server_url = "http://h:1"
    assert one(run_checks(cfg), "mineru binary").status == FAIL
    assert not by_name(run_checks(cfg), "c compiler")  # but no local vllm: the compiler is moot


def test_off_linux_with_hybrid_still_checks_the_mineru_binary(monkeypatch, tmp_path):
    monkeypatch.setattr(
        doctor, "check_hybrid_server", lambda u: Check("hybrid server", "tcp", OK, "")
    )
    cfg = cfg_in(tmp_path)
    cfg.mineru.hybrid_server_url = "http://h:1"
    checks = run_checks(cfg)  # the autouse fixture pins Darwin
    skip = one(checks, "os")
    assert skip.status == SKIP and "--hybrid-server-url" not in skip.detail
    assert one(checks, "mineru binary").status == FAIL  # not found, and hybrid is no excuse
    for name in ("gpu", "c compiler", "workdir", "disk", "mineru torch"):
        assert not by_name(checks, name)


def _fake_mineru(tmp_path, shebang="#!/opt/venv/bin/python\n"):
    m = tmp_path / "mineru"
    m.write_text(shebang + "print(1)\n")
    m.chmod(0o755)
    return str(m)


def test_mineru_version_ok_and_warn(monkeypatch):
    monkeypatch.setattr(doctor, "_run", lambda *a, **k: (0, "mineru, version 3.4.2\n", ""))
    assert doctor.check_mineru_version("m").detail == "mineru, version 3.4.2"
    monkeypatch.setattr(doctor, "_run", lambda *a, **k: (1, "", "Traceback\nboom"))
    assert doctor.check_mineru_version("m").status == WARN


def test_torch_cuda_ok(monkeypatch, tmp_path):
    m = _fake_mineru(tmp_path)
    seen = {}

    def fake(cmd, timeout, env=None, cwd=None):
        seen.update(cmd=cmd, env=env, cwd=cwd, cwd_was_dir=bool(cwd and os.path.isdir(cwd)))
        return 0, "2.11.0+cu130\nTrue\n", ""

    monkeypatch.setattr(doctor, "_run", fake)
    c = doctor.check_torch(Config(), m)
    assert c.status == OK and seen["cmd"][0] == "/opt/venv/bin/python"
    # the probe runs in an empty directory with MinerU's env, never in the caller's cwd
    assert seen["cwd_was_dir"] and seen["cwd"] != os.getcwd() and seen["env"] is not None


def test_torch_no_cuda_fails_or_warns_with_hybrid(monkeypatch, tmp_path):
    m = _fake_mineru(tmp_path)
    monkeypatch.setattr(doctor, "_run", lambda *a, **k: (0, "2.11.0\nFalse\n", ""))
    assert doctor.check_torch(Config(), m).status == FAIL
    cfg = Config()
    cfg.mineru.hybrid_server_url = "http://h:1"
    assert doctor.check_torch(cfg, m).status == WARN


def test_torch_import_error_and_bad_shebang(monkeypatch, tmp_path):
    m = _fake_mineru(tmp_path)
    monkeypatch.setattr(doctor, "_run", lambda *a, **k: (1, "", "ModuleNotFoundError: torch"))
    assert doctor.check_torch(Config(), m).status == WARN
    bare = tmp_path / "bare"
    bare.write_text("no shebang\n")
    assert doctor.check_torch(Config(), str(bare)).status == WARN


def test_shebang_env_form(monkeypatch, tmp_path):
    m = _fake_mineru(tmp_path, "#!/usr/bin/env python3\n")
    monkeypatch.setattr(doctor.shutil, "which", lambda n, **k: "/usr/bin/python3")
    assert doctor._shebang_python(m) == "/usr/bin/python3"


def _gpu(monkeypatch, rc, out, err="", which="/usr/bin/nvidia-smi"):
    monkeypatch.setattr(doctor.shutil, "which", lambda n, **k: which)
    monkeypatch.setattr(doctor, "_run", lambda *a, **k: (rc, out, err))


def test_gpu_ok(monkeypatch):
    _gpu(monkeypatch, 0, "NVIDIA GeForce RTX 3080 Ti, 12288\n")
    c = doctor.check_gpu()
    assert c.status == OK and "12288 MiB" in c.detail and "3080 Ti" in c.detail


def test_gpu_small_warns_and_missing_warns(monkeypatch):
    _gpu(monkeypatch, 0, "GTX 1060, 6144\n")
    assert doctor.check_gpu().status == WARN
    _gpu(monkeypatch, 0, "", which=None)
    assert doctor.check_gpu().status == WARN
    _gpu(monkeypatch, 9, "", "driver mismatch")
    c = doctor.check_gpu()
    assert c.status == WARN and "driver mismatch" in c.detail


def test_gpu_uses_wsl_path(monkeypatch):
    seen = {}

    def which(n, path=None):
        seen["path"] = path
        return None

    monkeypatch.setattr(doctor.shutil, "which", which)
    monkeypatch.setattr(os.path, "isdir", lambda p: p == "/usr/lib/wsl/lib")
    doctor.check_gpu()
    assert seen["path"].startswith("/usr/lib/wsl/lib:")


def test_compiler(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda n, **k: None)
    c = doctor.check_compiler(Config())
    assert c and c.status == FAIL
    assert "Triton" in c.detail and "build-essential" in c.fix
    monkeypatch.setattr(
        doctor.shutil, "which", lambda n, **k: "/usr/bin/gcc" if n == "gcc" else None
    )
    c = doctor.check_compiler(Config())
    assert c and c.status == OK
    cfg = Config()
    cfg.mineru.hybrid_server_url = "http://h:1"
    assert doctor.check_compiler(cfg) is None


def test_workdir_detects_stdlib_shadow(tmp_path):
    cfg = cfg_in(tmp_path)
    run = tmp_path / "run"
    run.mkdir()
    (run / "profile.py").write_text("")
    (run / "inspect").mkdir()
    (run / "inspect" / "__init__.py").write_text("")
    (run / "json").mkdir()  # no __init__.py: a namespace portion, the stdlib still wins
    (run / "helper.py").write_text("")
    c = doctor.check_workdir(cfg)
    assert c.status == FAIL
    assert (
        "profile.py" in c.detail
        and "inspect/" in c.detail
        and "also importable: helper.py" in c.detail
        and "json" not in c.detail
    )
    assert "rename" in c.fix


def test_workdir_clean_and_missing(tmp_path):
    cfg = cfg_in(tmp_path)
    assert doctor.check_workdir(cfg).status == OK  # missing dir: convert creates it clean
    (tmp_path / "run").mkdir()
    (tmp_path / "run" / "notes.txt").write_text("")
    assert doctor.check_workdir(cfg).status == OK


def test_disk_low_and_ok(monkeypatch, tmp_path):
    cfg = cfg_in(tmp_path)
    Usage = type("U", (), {})

    def usage(free_gib):
        u = Usage()
        u.free = int(free_gib * 2**30)
        return u

    seen = {}

    def low(p):
        seen["p"] = p
        return usage(3)

    monkeypatch.setattr(doctor.shutil, "disk_usage", low)
    assert doctor.check_disk(cfg).status == WARN
    assert seen["p"] == str(tmp_path)  # out_root missing: nearest existing ancestor
    monkeypatch.setattr(doctor.shutil, "disk_usage", lambda p: usage(200))
    assert doctor.check_disk(cfg).status == OK


# ---------- hybrid server ----------


def test_hybrid_server_connect(monkeypatch):
    seen = {}

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def ok(addr, timeout):
        seen["addr"], seen["timeout"] = addr, timeout
        return Conn()

    monkeypatch.setattr(doctor.socket, "create_connection", ok)
    assert doctor.check_hybrid_server("https://gpu.example/v1").status == OK
    assert seen["addr"] == ("gpu.example", 443) and seen["timeout"] == 5
    doctor.check_hybrid_server("http://gpu.example")
    assert seen["addr"] == ("gpu.example", 80)

    def refuse(addr, timeout):
        raise ConnectionRefusedError("refused")

    monkeypatch.setattr(doctor.socket, "create_connection", refuse)
    c = doctor.check_hybrid_server("http://gpu.example:8000")
    assert c.status == FAIL and "gpu.example:8000" in c.detail


# ---------- remote ----------


def fake_ssh(
    monkeypatch,
    *,
    echo=(0, "ok\n", ""),
    version=(0, "pdf2wiki 9.9.9\n", ""),
    test_d=0,
    probe=None,
):
    """Fake the ssh calls. The reachability probe is `echo ok`. Everything after it is ONE call
    that prints marker lines (VERRC=, VER=, DIR=); `probe` overrides it, to drop the link."""
    calls = []

    def run(cmd, timeout, env=None, cwd=None):
        calls.append(cmd)
        tail = cmd[-1]
        if tail == "echo ok":
            return echo
        if "pdf2wiki --version" in tail:
            if probe is not None:
                return probe
            vrc, vout, verr = version
            if vrc in (255, -1):
                return (vrc, "", verr)
            text = (vout or verr).replace("\n", " ").strip()
            lines = [f"VERRC={vrc}", f"VER={text}"]
            if "test -d" in tail:
                lines.append("DIR=yes" if test_d == 0 else "DIR=no")
            return (0, "\n".join(lines) + "\n", "")
        return (-1, "", "unexpected")

    monkeypatch.setattr(doctor, "_run", run)
    return calls


def test_remote_ssh_ok_same_version(monkeypatch):
    fake_ssh(monkeypatch, version=(0, f"pdf2wiki {__version__}\n", ""))
    checks = doctor.check_remote(Config(), "box")
    assert [c.status for c in checks] == [OK, OK]


def test_remote_version_differs_warns(monkeypatch):
    fake_ssh(monkeypatch)
    c = one(doctor.check_remote(Config(), "box"), "pdf2wiki")
    assert c.status == WARN and f"remote 9.9.9, local {__version__}" == c.detail


def test_remote_no_version_flag_warns(monkeypatch):
    fake_ssh(monkeypatch, version=(2, "", "error: unrecognized arguments: --version"))
    c = one(doctor.check_remote(Config(), "box"), "pdf2wiki")
    assert c.status == WARN and "older" in c.detail and "upgrade" in c.fix


def test_remote_command_not_found_warns(monkeypatch):
    fake_ssh(monkeypatch, version=(127, "", "bash: pdf2wiki: command not found"))
    c = one(doctor.check_remote(Config(), "box"), "pdf2wiki")
    assert c.status == WARN and "PATH" in c.detail


def test_remote_books_dir(monkeypatch):
    cfg = Config()
    cfg.remote.books_dir = "~/my books"
    calls = fake_ssh(monkeypatch, test_d=0)
    assert one(doctor.check_remote(cfg, "box"), "books_dir").status == OK
    assert len(calls) == 2  # `echo ok`, then ONE call for the version and the directory
    assert "test -d 'my books'" in calls[-1][-1]  # ~/ dropped, then quoted
    fake_ssh(monkeypatch, test_d=1)
    c = one(doctor.check_remote(cfg, "box"), "books_dir")
    assert c.status == FAIL


def test_remote_ssh_opts_are_executor_opts(monkeypatch):
    calls = fake_ssh(monkeypatch)
    doctor.check_remote(Config(), "box")
    assert "BatchMode=yes" in calls[0] and calls[0][0] == "ssh"
    assert calls[0][-3:-1] == ["--", "box"]  # `--` ends the options before the destination


def _patch_net(monkeypatch, ip, src):
    monkeypatch.setattr(doctor, "_ssh_target", lambda h: (ip, 2222))
    monkeypatch.setattr(doctor.socket, "getaddrinfo", lambda n, p, f: [(f, 0, 0, "", (n, p))])
    monkeypatch.setattr(doctor, "_source_address", lambda i, p: src)


def test_ssh_failure_different_subnet_hint(monkeypatch):
    fake_ssh(monkeypatch, echo=(255, "", "ssh: connect to host x: Operation timed out"))
    _patch_net(monkeypatch, "192.168.111.125", "10.10.1.42")
    (c,) = doctor.check_remote(Config(), "gpu-desktop")
    assert c.status == FAIL
    assert "different network" in c.detail and "10.10.1.42" in c.detail
    assert c.fix.startswith("join the host's network first") and "wake" in c.fix


def test_ssh_failure_same_subnet_hint(monkeypatch):
    fake_ssh(monkeypatch, echo=(255, "", "Operation timed out"))
    _patch_net(monkeypatch, "192.168.111.125", "192.168.111.40")
    (c,) = doctor.check_remote(Config(), "gpu-desktop")
    assert c.status == FAIL and "asleep or off" in c.fix
    assert "different network" not in c.detail


def test_ssh_failure_hint_errors_are_swallowed(monkeypatch):
    fake_ssh(monkeypatch, echo=(255, "", "Operation timed out"))

    def boom(h):
        raise RuntimeError("no ssh -G")

    monkeypatch.setattr(doctor, "_ssh_target", boom)
    (c,) = doctor.check_remote(Config(), "box")
    assert c.status == FAIL and "ssh -v" in c.fix and "Operation timed out" in c.detail


def test_ssh_failure_public_target_gives_no_subnet_claim(monkeypatch):
    fake_ssh(monkeypatch, echo=(255, "", "Operation timed out"))
    _patch_net(monkeypatch, "8.8.8.8", "10.0.0.2")
    (c,) = doctor.check_remote(Config(), "box")
    assert "ssh -v" in c.fix and "network" not in c.detail.split("SSH:")[1]


def test_source_address_sends_nothing(monkeypatch):
    seen = []

    class Sock:
        def __init__(self, fam, kind):
            seen.append((fam, kind))

        def connect(self, addr):
            seen.append(addr)

        def getsockname(self):
            return ("10.1.2.3", 5555)

        def close(self):
            seen.append("closed")

        def sendto(self, *a):  # pragma: no cover - must never run
            raise AssertionError("a packet was sent")

    monkeypatch.setattr(doctor.socket, "socket", Sock)
    assert doctor._source_address("192.168.111.125", 2222) == "10.1.2.3"
    assert seen[0] == (socket.AF_INET, socket.SOCK_DGRAM) and seen[-1] == "closed"


def test_ssh_target_parses_ssh_g(monkeypatch):
    out = "user sebas\nhostname 192.168.111.125\nport 2222\n"
    monkeypatch.setattr(doctor, "_run", lambda *a, **k: (0, out, ""))
    assert doctor._ssh_target("gpu-desktop") == ("192.168.111.125", 2222)


# ---------- cloud ----------


def test_cloud_reports_length_never_value(monkeypatch, capsys):
    monkeypatch.setenv("MINERU_API_TOKEN", SECRET)
    checks = run_checks(Config())
    c = one(checks, "token")
    assert c.status == OK and f"{len(SECRET)} characters" in c.detail
    assert "MINERU_API_TOKEN" in c.detail
    human = doctor.render_human(checks, __version__)
    js = json.dumps(doctor.render_json(checks, __version__))
    for blob in (human, js):
        assert SECRET not in blob
        assert SECRET[:6] not in blob and SECRET[-6:] not in blob


def test_cloud_inline_and_file_sources(tmp_path):
    tf = tmp_path / "tok"
    tf.write_text(SECRET + "\n")
    cfg = Config()
    cfg.mineru_cloud.token = SECRET
    cfg.mineru_cloud.token_file = str(tf)
    cs = by_name(doctor.check_cloud(doctor._token_sources(cfg)), "token")
    assert len(cs) == 2 and all(c.status == OK for c in cs)
    assert "config inline" in cs[0].detail and str(tf) in cs[1].detail
    assert all(SECRET not in c.detail + c.fix for c in cs)


def test_cloud_missing_token_file_fails(tmp_path):
    cfg = Config()
    cfg.mineru_cloud.token_file = str(tmp_path / "gone")
    (c,) = doctor.check_cloud(doctor._token_sources(cfg))
    assert c.status == FAIL and "gone" in c.detail


def test_cloud_group_absent_without_token():
    assert doctor.check_cloud(doctor._token_sources(Config())) == []


# ---------- output and CLI ----------


def test_render_human_shape():
    checks = [
        Check("core", "python", OK, "3.13"),
        Check("core", "config", WARN, "w"),
        Check("remote", "ssh", FAIL, "bad", "do this"),
        Check("local convert", "os", SKIP, "s"),
    ]
    text = doctor.render_human(checks, "1.2.3")
    lines = text.splitlines()
    assert lines[0] == "pdf2wiki doctor 1.2.3"
    assert "  ok    python" in text and "  warn  config" in text
    assert "  FAIL  ssh" in text and "  skip  os" in text
    assert any(l.strip().startswith("fix: do this") for l in lines)
    assert lines[-1] == "1 fail, 1 warn"


def test_render_json_shape():
    checks = [Check("core", "a", OK, "d"), Check("core", "b", FAIL, "x", "f")]
    j = doctor.render_json(checks, "1.2.3")
    assert j["version"] == "1.2.3" and j["fails"] == 1 and j["warns"] == 0
    assert j["checks"][1] == {
        "group": "core",
        "name": "b",
        "status": "fail",
        "detail": "x",
        "fix": "f",
    }


def test_cli_exit_code_fail_and_ok(monkeypatch, capsys):
    monkeypatch.setattr(doctor, "run_checks", lambda *a, **k: [Check("core", "x", FAIL, "d")])
    assert cli.main(["doctor"]) == 1
    monkeypatch.setattr(doctor, "run_checks", lambda *a, **k: [Check("core", "x", WARN, "d")])
    assert cli.main(["doctor"]) == 0
    assert "0 fail, 1 warn" in capsys.readouterr().out


def test_cli_json_and_remote_passthrough(monkeypatch, capsys):
    seen = {}

    def fake(report, *, remote=None):
        seen.update(remote=remote, explicit=report.explicit)
        return [Check("core", "x", OK, "d")]

    monkeypatch.setattr(doctor, "run_checks", fake)
    assert cli.main(["--config", "c.toml", "doctor", "--remote", "box", "--json"]) == 0
    assert seen == {"remote": "box", "explicit": True}
    data = json.loads(capsys.readouterr().out)
    assert data["version"] == __version__ and data["fails"] == 0


def test_cli_doctor_survives_broken_config(tmp_path, capsys):
    p = tmp_path / "bad.toml"
    p.write_text("[mineru\n")
    assert cli.main(["--config", str(p), "doctor"]) == 1
    assert "cannot parse" in capsys.readouterr().out


def test_cli_other_commands_exit_2_on_broken_config(tmp_path, capsys):
    p = tmp_path / "bad.toml"
    p.write_text("[mineru\n")
    assert cli.main(["--config", str(p), "scan", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("error: ") and "cannot parse" in err and str(p) in err
    assert "Traceback" not in err


def test_cli_missing_explicit_config_exits_2(tmp_path, capsys):
    missing = tmp_path / "bookz.toml"
    assert cli.main(["--config", str(missing), "scan", str(tmp_path)]) == 2
    assert "does not exist" in capsys.readouterr().err
    # the default search paths stay optional
    assert cli.main(["scan", str(tmp_path)]) == 0


def test_two_files_int_then_float_for_a_float_field(tmp_path):
    # a value is checked against the field's DEFAULT type, not against the merged value
    from pdf2wiki.config import load_config

    home_cfg = tmp_path / "home" / ".config" / "pdf2wiki"
    home_cfg.mkdir(parents=True)
    (home_cfg / "config.toml").write_text("[mineru_cloud]\nretry_base_delay = 2\n")
    (tmp_path / "pdf2wiki.toml").write_text("[mineru_cloud]\nretry_base_delay = 2.5\n")
    cfg = load_config()
    assert cfg.mineru_cloud.retry_base_delay == 2.5
    (tmp_path / "pdf2wiki.toml").unlink()
    cfg = load_config()
    assert cfg.mineru_cloud.retry_base_delay == 2.0 and isinstance(
        cfg.mineru_cloud.retry_base_delay, float
    )


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["--version"])
    assert e.value.code == 0
    assert capsys.readouterr().out.strip() == f"pdf2wiki {__version__}"


# ---------- review fixes ----------


def test_config_candidates_is_the_search_list():
    from pdf2wiki.config import config_candidates

    assert config_candidates("x.toml") == ["x.toml"]
    home, local = config_candidates()
    assert home.endswith(os.path.join(".config", "pdf2wiki", "config.toml"))
    assert local == "pdf2wiki.toml"


def test_lenient_load_keeps_valid_files(tmp_path):
    from pdf2wiki.config import ConfigError, load_config

    home_cfg = tmp_path / "home" / ".config" / "pdf2wiki"
    home_cfg.mkdir(parents=True)
    (home_cfg / "config.toml").write_text('[remote]\nhost = "box"\n')
    (tmp_path / "pdf2wiki.toml").write_text("[mineru\n")  # syntax error
    assert load_config(strict=False).remote.host == "box"
    with pytest.raises(ConfigError, match="cannot parse"):
        load_config()


def test_lenient_load_skips_non_table_and_bad_bytes(tmp_path):
    from pdf2wiki.config import load_config

    (tmp_path / "pdf2wiki.toml").write_text('mineru = 1\n[remote]\nhost = "box"\n')
    assert load_config(strict=False).remote.host == "box"
    from pdf2wiki.config import ConfigError

    with pytest.raises(ConfigError, match=r"\[mineru\] must be a table"):
        load_config()
    bad = tmp_path / "bad.toml"
    bad.write_bytes(b"[remote]\nhost = '\xff\xfe'\n")
    assert load_config(str(bad), strict=False).remote.host == ""
    with pytest.raises(ValueError):
        load_config(str(bad))


def test_cli_doctor_keeps_valid_file_when_another_is_broken(tmp_path, monkeypatch):
    home_cfg = tmp_path / "home" / ".config" / "pdf2wiki"
    home_cfg.mkdir(parents=True)
    (home_cfg / "config.toml").write_text('[remote]\nhost = "box"\n')
    (tmp_path / "pdf2wiki.toml").write_text("[mineru\n")
    seen = {}

    def fake(report, *, remote=None):
        seen["host"] = report.config.remote.host
        return []

    monkeypatch.setattr(doctor, "run_checks", fake)
    cli.main(["doctor"])
    assert seen["host"] == "box"


def test_non_utf8_and_non_table_config_report_fail_without_crash(tmp_path, capsys):
    bad = tmp_path / "bad.toml"
    bad.write_bytes(b"[remote]\nhost = '\xff\xfe'\n")
    assert cli.main(["--config", str(bad), "doctor"]) == 1
    assert "cannot parse" in capsys.readouterr().out
    nt = tmp_path / "nt.toml"
    nt.write_text("mineru = 1\n")
    assert cli.main(["--config", str(nt), "doctor"]) == 1
    assert "[mineru] must be a table" in capsys.readouterr().out


@pytest.mark.parametrize("how", ["cfg_remote", "arg_remote"])
def test_compiler_and_torch_soften_with_another_convert_path(monkeypatch, tmp_path, how):
    cfg = Config()
    remote = None
    if how == "cfg_remote":
        cfg.remote.host = "box"
    else:
        remote = "box"
    assert doctor.other_convert_path(cfg, remote, []) is True
    assert doctor.other_convert_path(Config(), None, []) is False
    c = doctor.check_compiler(cfg, True)
    assert c and c.status == WARN
    m = _fake_mineru(tmp_path)
    monkeypatch.setattr(doctor, "_run", lambda *a, **k: (0, "2.11.0\nFalse\n", ""))
    assert doctor.check_torch(cfg, m, True).status == WARN


def test_ssh_auth_failure_gets_key_fix_not_wake_hint(monkeypatch):
    fake_ssh(monkeypatch, echo=(255, "", "sebas@box: Permission denied (publickey)."))
    monkeypatch.setattr(doctor, "network_hint", lambda h: pytest.fail("subnet hint on auth error"))
    (c,) = doctor.check_remote(Config(), "box")
    assert c.status == FAIL and "key" in c.fix and "wake" not in c.fix


def test_ssh_hostkey_failure_gets_known_hosts_fix(monkeypatch):
    fake_ssh(monkeypatch, echo=(255, "", "Host key verification failed."))
    monkeypatch.setattr(doctor, "network_hint", lambda h: pytest.fail("subnet hint on host key"))
    (c,) = doctor.check_remote(Config(), "box")
    assert "ssh-keygen -R box" in c.fix and "accept its key" in c.fix
    assert "wake" not in c.fix


def test_same_block_other_24_is_a_possibility_not_a_verdict(monkeypatch):
    _patch_net(monkeypatch, "10.0.1.40", "10.0.2.15")
    detail, fix = doctor.network_hint("box")
    assert "may be on a different network" in detail
    assert "is on a different network than" not in detail
    assert "asleep" in fix


def test_other_private_block_and_public_source_are_verdicts(monkeypatch):
    _patch_net(monkeypatch, "192.168.111.125", "172.20.10.2")  # a phone hotspot
    assert "is on a different network than" in doctor.network_hint("box")[0]
    _patch_net(monkeypatch, "192.168.111.125", "81.2.3.4")
    assert "is on a different network than" in doctor.network_hint("box")[0]


def _script(tmp_path, text):
    m = tmp_path / "m"
    m.write_text(text)
    return str(m)


def test_shebang_pip_trampoline(tmp_path):
    t = "'" * 3
    text = f'#!/bin/sh\n{t}exec\' "/very/long/venv/bin/python" "$0" "$@"\n\' {t}\nimport x\n'
    assert doctor._shebang_python(_script(tmp_path, text)) == "/very/long/venv/bin/python"


def test_shebang_env_dash_s_with_flags(monkeypatch, tmp_path):
    seen = []

    def which(n, **k):
        seen.append(n)
        return "/usr/bin/" + n

    monkeypatch.setattr(doctor.shutil, "which", which)
    m = _script(tmp_path, "#!/usr/bin/env -S python3 -u\nprint(1)\n")
    assert doctor._shebang_python(m) == "/usr/bin/python3" and seen == ["python3"]
    m = _script(tmp_path, "#!/usr/bin/env -S -u PYTHONPATH=/x python3.12 -u\n")
    assert doctor._shebang_python(m) == "/usr/bin/python3.12"


def test_token_order_is_shared_with_the_converter(monkeypatch, tmp_path):
    from pdf2wiki.convert import cloud

    tf = tmp_path / "t"
    tf.write_text("file-token\n")
    cfg = Config()
    cfg.mineru_cloud.token_file = str(tf)
    monkeypatch.setenv("MINERU_API_TOKEN", "env-token")
    assert cloud._resolve_token(cfg) == "env-token"  # env beats the file
    assert cloud.token_sources(cfg)[0].label == "env MINERU_API_TOKEN"
    assert [label for label, _ in doctor._token_sources(cfg)] == [
        t.label for t in cloud.token_sources(cfg)
    ]
    cfg.mineru_cloud.token = "inline-token"
    assert cloud._resolve_token(cfg) == "inline-token"  # inline beats env


def test_resolve_token_error_names_a_missing_token_file(tmp_path):
    from pdf2wiki.convert import cloud

    cfg = Config()
    cfg.mineru_cloud.token_file = str(tmp_path / "gone")
    with pytest.raises(cloud.CloudError, match="gone"):
        cloud._resolve_token(cfg)


# ---------- round 2 ----------


def test_env_token_wins_over_a_broken_token_file(monkeypatch, tmp_path):
    from pdf2wiki.convert import cloud

    bad = tmp_path / "tok"
    bad.write_bytes(b"\xff\xfe\x00bad")  # not UTF-8
    cfg = Config()
    cfg.mineru_cloud.token_file = str(bad)
    monkeypatch.setenv("MINERU_API_TOKEN", SECRET)
    assert cloud._resolve_token(cfg) == SECRET  # the file is never opened
    cfg.mineru_cloud.token_file = str(tmp_path)  # a directory
    assert cloud._resolve_token(cfg) == SECRET


def test_broken_token_file_is_reported_not_raised(monkeypatch, tmp_path):
    from pdf2wiki.convert import cloud

    bad = tmp_path / "tok"
    bad.write_bytes(b"\xff\xfe\x00bad")
    cfg = Config()
    cfg.mineru_cloud.token_file = str(bad)
    toks = doctor._token_sources(cfg)
    assert (
        len(toks) == 1 and toks[0][1].error and toks[0][1].length is None and toks[0][1].value == ""
    )
    (c,) = doctor.check_cloud(toks)
    assert c.status == FAIL and c.fix  # nothing else resolves a token
    with pytest.raises(cloud.CloudError, match="cannot read"):
        cloud._resolve_token(cfg)
    # a winning source makes the unreadable file harmless: WARN, and the run exits 0
    monkeypatch.setenv("MINERU_API_TOKEN", SECRET)
    cs = doctor.check_cloud(doctor._token_sources(cfg))
    assert [c.status for c in cs] == [OK, WARN]
    assert "not used" in cs[1].detail and "env MINERU_API_TOKEN" in cs[1].detail
    assert all(SECRET not in c.detail + c.fix for c in cs)
    checks = run_checks(cfg)  # no traceback
    assert not [c for c in checks if c.status == FAIL]


def test_wrong_value_types_become_config_fails_and_defaults(tmp_path, capsys):
    p = tmp_path / "t.toml"
    p.write_text('[remote]\nconnect_timeout = "8"\n[convert]\nworkdir = 5\ntimeout = true\n')
    from pdf2wiki.config import load_config_report

    rep = load_config_report(str(p))
    assert rep.config.remote.connect_timeout == 8 and rep.config.convert.workdir.startswith("~")
    assert [(x.section, x.key) for x in rep.problems] == [
        ("convert", "workdir"),
        ("convert", "timeout"),
        ("remote", "connect_timeout"),
    ]
    assert cli.main(["--config", str(p), "doctor"]) == 1
    out = capsys.readouterr().out
    assert "wrong type" in out and "set connect_timeout in [remote] to an integer" in out


def test_strict_load_stops_early_on_a_wrong_type(tmp_path):
    from pdf2wiki.config import ConfigError, load_config

    p = tmp_path / "t.toml"
    p.write_text('[remote]\nconnect_timeout = "8"\n')
    with pytest.raises(ConfigError) as e:
        load_config(str(p))
    msg = str(e.value)
    assert str(p) in msg and "[remote] connect_timeout" in msg
    assert "an integer" in msg and "str" in msg


def test_cli_wrong_type_exits_2_with_no_traceback(tmp_path, capsys):
    p = tmp_path / "t.toml"
    p.write_text('[convert]\ntimeout = "7200"\n')
    assert cli.main(["--config", str(p), "scan", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("error: ") and "[convert] timeout must be an integer" in err
    assert "Traceback" not in err


def test_a_crashing_check_becomes_a_fail_line(monkeypatch):
    def boom():
        raise RuntimeError("kaput")

    monkeypatch.setattr(doctor, "check_pymupdf", boom)
    checks = run_checks(Config())
    (c,) = [c for c in checks if "crashed" in c.detail]
    assert c.status == FAIL and "RuntimeError: kaput" in c.detail and c.fix
    assert one(checks, "python").status == OK  # the rest still ran


@pytest.mark.parametrize(
    ("rc", "err", "needle"),
    [
        (255, "ssh: Connection closed", "connection lost or timed out"),
        (-1, "timed out after 25s", "connection lost or timed out"),
        (127, "bash: pdf2wiki: command not found", "not found on the remote PATH"),
        (2, "usage: pdf2wiki\npdf2wiki: error: unrecognized arguments: --version", "older"),
        (1, "Traceback\nImportError: boom", "failed on the host (exit 1): Traceback"),
    ],
)
def test_remote_version_failures_are_told_apart(monkeypatch, rc, err, needle):
    fake_ssh(monkeypatch, version=(rc, "", err))
    c = one(doctor.check_remote(Config(), "box"), "pdf2wiki")
    assert c.status == WARN and needle in c.detail and c.fix


def test_shell_wrapper_that_is_not_pips_gives_no_interpreter(tmp_path):
    m = _script(tmp_path, '#!/bin/sh\nexec "$CONDA_PREFIX/bin/python" "$@"\n')
    assert doctor._shebang_python(m) is None
    assert doctor.check_torch(Config(), m).status == WARN


def test_config_problems_are_labelled_by_kind(tmp_path):
    from pdf2wiki.config import load_config_report

    d = tmp_path / "adir"
    d.mkdir()
    (c,) = [c for c in doctor.check_config(load_config_report(str(d)), True) if c.status == FAIL]
    assert "cannot read" in c.detail and "may read it" in c.fix
    bad = tmp_path / "bad.toml"
    bad.write_text("[mineru\n")
    (c,) = [c for c in doctor.check_config(load_config_report(str(bad)), True) if c.status == FAIL]
    assert "cannot parse" in c.detail and "UTF-8" in c.fix
    nt = tmp_path / "nt.toml"
    nt.write_text("mineru = 1\n")
    (c,) = [c for c in doctor.check_config(load_config_report(str(nt)), True) if c.status == FAIL]
    assert "wrong type" in c.detail and c.fix == "make [mineru] a table"


def test_token_sources_resolved_once_per_run(monkeypatch):
    from pdf2wiki.convert import cloud

    calls = []
    real = cloud.token_sources
    monkeypatch.setattr(cloud, "token_sources", lambda cfg: calls.append(1) or real(cfg))
    linux(monkeypatch)
    run_checks(Config())
    assert len(calls) == 1


def test_every_fail_has_a_fix(monkeypatch, tmp_path):
    fails: list[Check] = []

    def ssh_case(err, ip_net=None):
        fake_ssh(monkeypatch, echo=(255, "", err))
        monkeypatch.setattr(doctor, "network_hint", lambda h: None)
        fails.extend(doctor.check_remote(Config(), "box"))

    ssh_case("ssh: connect to host box port 22: Connection refused")
    ssh_case("ssh: Could not resolve hostname box")
    ssh_case("ssh: connect to host box port 22: Operation timed out")  # hint is None
    ssh_case("Permission denied (publickey).")
    ssh_case("Host key verification failed.")
    fails.append(doctor.check_hybrid_server("http://h:abc"))
    fails.append(doctor.check_hybrid_server("http:///nohost"))
    monkeypatch.setattr(doctor, "_run", lambda *a, **k: (0, "", ""))
    fake_ssh(monkeypatch, test_d=1)
    cfg = Config()
    cfg.remote.books_dir = "books"
    fails.extend(doctor.check_remote(cfg, "box"))
    fails.append(
        doctor.check_cloud([("token_file x", TokenRead(error="gone", cause="missing"))])[0]
    )
    fails.append(doctor.check_compiler(Config()))
    monkeypatch.setattr(doctor, "_run", lambda *a, **k: (0, "2.0\nFalse\n", ""))
    fails.append(doctor.check_torch(Config(), _fake_mineru(tmp_path)))
    fails.append(doctor.check_mineru_binary(Config(), False)[0])
    monkeypatch.setattr(
        doctor.importlib, "import_module", lambda n: (_ for _ in ()).throw(ImportError("x"))
    )
    fails.append(doctor.check_pymupdf())
    run = tmp_path / "run"
    run.mkdir()
    (run / "profile.py").write_text("")
    wd = Config()
    wd.convert.workdir = str(run)
    fails.append(doctor.check_workdir(wd))
    from pdf2wiki.config import load_config_report

    fails.extend(doctor.check_config(load_config_report(str(tmp_path / "missing.toml")), True))
    fails = [c for c in fails if c and c.status == FAIL]
    assert len(fails) >= 14
    assert [c.name for c in fails if not c.fix] == []


# ---------- round 3 ----------


def test_version_rc0_is_not_called_missing_because_of_bashrc_noise(monkeypatch):
    fake_ssh(
        monkeypatch,
        version=(0, f"pdf2wiki {__version__}\n", "bash: conda: command not found\n"),
    )
    c = one(doctor.check_remote(Config(), "box"), "pdf2wiki")
    assert c.status == OK


def test_books_dir_probe_tells_a_dropped_ssh_from_a_missing_dir(monkeypatch):
    cfg = Config()
    cfg.remote.books_dir = "/data/books"
    for rc in (255, -1):  # the link dropped after `echo ok` answered
        fake_ssh(monkeypatch, probe=(rc, "", "Connection to box closed"))
        checks = doctor.check_remote(cfg, "box")
        assert one(checks, "books_dir").status == WARN
        assert "could not check" in one(checks, "books_dir").detail
        assert one(checks, "pdf2wiki").status == WARN
    fake_ssh(monkeypatch, test_d=1)
    assert one(doctor.check_remote(cfg, "box"), "books_dir").status == FAIL


def test_compiler_mirrors_triton_cc_then_gcc_then_clang(monkeypatch):
    # triton/runtime/build.py _find_compiler("c"): $CC, else gcc, else clang. Never `cc`.
    monkeypatch.delenv("CC", raising=False)
    only = {"cc"}
    monkeypatch.setattr(
        doctor.shutil, "which", lambda n, **k: f"/usr/bin/{n}" if n in only else None
    )
    assert doctor.check_compiler(Config()).status == FAIL  # `cc` alone does not satisfy Triton
    only.clear()
    only.add("clang")
    c = doctor.check_compiler(Config())
    assert c.status == OK and c.detail == "/usr/bin/clang"
    only.add("gcc")
    assert doctor.check_compiler(Config()).detail == "/usr/bin/gcc"
    only.clear()
    monkeypatch.setenv("CC", "/opt/cc")
    c = doctor.check_compiler(Config())
    assert c.status == OK and "/opt/cc" in c.detail


def test_workdir_other_importables_warn_and_stdlib_binaries_fail(tmp_path):
    cfg = cfg_in(tmp_path)
    run = tmp_path / "run"
    run.mkdir()
    (run / "torch.py").write_text("")
    (run / "vllm").mkdir()
    (run / "vllm" / "__init__.py").write_text("")
    (run / "ext.cpython-312-x86_64-linux-gnu.so").write_text("")
    (run / "__pycache__").mkdir()
    (run / "__pycache__" / "__init__.py").write_text("")
    (run / "data").mkdir()  # no __init__.py: not importable
    c = doctor.check_workdir(cfg)
    assert c.status == WARN
    for name in ("torch.py", "vllm/", "ext.cpython"):
        assert name in c.detail
    assert "__pycache__" not in c.detail and "data" not in c.detail
    (run / "profile.pyc").write_text("")
    (run / "select.cpython-312-x86_64-linux-gnu.so").write_text("")
    c = doctor.check_workdir(cfg)
    assert c.status == FAIL and "profile.pyc" in c.detail and "select.cpython" in c.detail
    assert "also importable" in c.detail and "torch.py" in c.detail


def test_inline_token_warns_in_any_file_but_the_user_one(tmp_path):
    from pdf2wiki.config import load_config_report

    books = tmp_path / "books.toml"
    books.write_text(f'[mineru_cloud]\ntoken = "{SECRET}"\n')
    (c,) = doctor.check_inline_token(load_config_report(str(books)))
    assert c.status == WARN and str(books) in c.detail and SECRET not in c.detail + c.fix
    user = tmp_path / "home" / ".config" / "pdf2wiki"
    user.mkdir(parents=True)
    (user / "config.toml").write_text(f'[mineru_cloud]\ntoken = "{SECRET}"\n')
    assert doctor.check_inline_token(load_config_report()) == []


def test_doctor_reads_config_once(monkeypatch):
    import pdf2wiki.config as config_mod

    calls = []
    real = config_mod.load_config_report
    monkeypatch.setattr(
        config_mod, "load_config_report", lambda *a, **k: calls.append(1) or real(*a, **k)
    )
    assert cli.main(["doctor"]) == 0
    assert len(calls) == 1


# ---------- round 4 ----------


@pytest.mark.parametrize(
    ("fake_version_script", "books_ok", "want_version_status"),
    [
        ('echo "pdf2wiki $V"', True, OK),
        (
            'echo "usage: pdf2wiki"; echo "error: unrecognized arguments: --version"; exit 2',
            False,
            WARN,
        ),
    ],
)
def test_the_probe_script_really_runs_in_sh(
    monkeypatch, tmp_path, fake_version_script, books_ok, want_version_status
):
    """Run the one-call script in a real POSIX shell with a stand-in `pdf2wiki`, then parse it."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "pdf2wiki"
    fake.write_text("#!/bin/sh\nV=" + __version__ + "\n" + fake_version_script + "\n")
    fake.chmod(0o755)
    books = tmp_path / "books"
    if books_ok:
        books.mkdir()
    cfg = Config()
    cfg.remote.books_dir = str(books)
    scripts = []

    def run(cmd, timeout, env=None, cwd=None):
        if cmd[-1] == "echo ok":
            return 0, "ok\n", ""
        scripts.append(cmd[-1])
        env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}")
        r = REAL_RUN(["sh", "-c", cmd[-1]], capture_output=True, text=True, env=env)
        return r.returncode, r.stdout, r.stderr

    monkeypatch.setattr(doctor, "_run", run)
    checks = doctor.check_remote(cfg, "box")
    assert len(scripts) == 1
    assert one(checks, "pdf2wiki").status == want_version_status
    assert one(checks, "books_dir").status == (OK if books_ok else FAIL)


@pytest.mark.parametrize(
    ("kind", "needle"),
    [
        ("missing", "create the file"),
        ("permission", "chmod"),
        ("decode", "UTF-8"),
        ("other", "readable text file"),
    ],
)
def test_token_file_fix_follows_the_cause(kind, needle):
    t = ("token_file x", TokenRead(error="boom", cause=kind))
    (c,) = doctor.check_cloud([t])
    assert c.status == FAIL and needle in c.fix


def test_read_token_names_the_cause(tmp_path):
    from pdf2wiki.convert.cloud import TokenSource, read_token

    def src(path):
        def load():
            with open(path, encoding="utf-8") as f:
                return f.read().strip()

        return TokenSource("t", load)

    assert read_token(src(tmp_path / "gone")).cause == "missing"
    assert read_token(src(tmp_path)).cause == "other"  # a directory
    bad = tmp_path / "bad"
    bad.write_bytes(b"\xff\xfe")
    assert read_token(src(bad)).cause == "decode"
    locked = tmp_path / "locked"
    locked.write_text("x")
    locked.chmod(0)
    try:
        r = read_token(src(locked))
        assert r.cause == "permission" or r.value == "x"  # running as root can still read it
    finally:
        locked.chmod(0o600)
    ok = tmp_path / "ok"
    ok.write_text(" tok \n")
    r = read_token(src(ok))
    assert (r.value, r.error, r.cause) == ("tok", "", "")


def test_a_missing_explicit_config_is_still_reported_by_doctor(tmp_path):
    checks = run_checks(config_path=str(tmp_path / "bookz.toml"))
    assert one(checks, "config").status == FAIL


# ---------- round 5 ----------

EVIL = "-oProxyCommand=sh -c 'touch /tmp/pwned'"


@pytest.mark.parametrize("bad", [EVIL, "-oProxyCommand=x", "", "a b", "host\n", "ho\tst", "x\x00"])
def test_validate_host_rejects_option_like_and_unsafe_values(bad):
    from pdf2wiki.executor import InvalidHostError, validate_host

    with pytest.raises(InvalidHostError):
        validate_host(bad)


@pytest.mark.parametrize("good", ["gpu-desktop", "sebas@192.168.111.125", "box.example.com"])
def test_validate_host_accepts_normal_destinations(good):
    from pdf2wiki.executor import validate_host

    assert validate_host(good) == good


def test_ssh_executor_refuses_an_option_as_host():
    from pdf2wiki.executor import ExecutionError, SSHExecutor

    with pytest.raises(ExecutionError):
        SSHExecutor(EVIL, "b", "w")


def test_doctor_runs_no_subprocess_for_an_option_host(monkeypatch):
    def boom(*a, **k):
        pytest.fail("a subprocess ran for an option-like host")

    monkeypatch.setattr(doctor, "_run", boom)
    cfg = Config()
    cfg.remote.host = EVIL  # as a cloned repo's pdf2wiki.toml could set it
    checks = run_checks(cfg)
    c = one(checks, "ssh")
    assert c.status == FAIL and c.fix and "invalid ssh host" in c.detail
    c = one(run_checks(Config(), remote=EVIL), "ssh")  # and --remote
    assert c.status == FAIL


def test_cli_doctor_rejects_the_option_host_end_to_end(tmp_path, capsys):
    (tmp_path / "pdf2wiki.toml").write_text(f'[remote]\nhost = "{EVIL}"\n')
    assert cli.main(["doctor"]) == 1  # the autouse guard fails the test if any subprocess runs
    assert "invalid ssh host" in capsys.readouterr().out


def test_convert_and_batch_refuse_the_option_host_with_exit_2(tmp_path, capsys):
    assert cli.main(["convert", "a.pdf", "--name", "a", "--remote", EVIL]) == 2
    assert "invalid ssh host" in capsys.readouterr().err
    books = tmp_path / "books.toml"
    books.write_text('[[book]]\npdf = "a.pdf"\nslug = "a"\n')
    rc = cli.main(["batch", str(books), "--stage", str(tmp_path / "s"), "--remote", EVIL])
    assert rc == 2
    assert "invalid ssh host" in capsys.readouterr().err


def test_ssh_g_gets_the_double_dash(monkeypatch):
    seen = []
    monkeypatch.setattr(doctor, "_run", lambda cmd, *a, **k: seen.append(cmd) or (1, "", ""))
    doctor._ssh_target("box")
    assert seen[0] == ["ssh", "-G", "--", "box"]


def test_relocatable_trampoline_resolves_next_to_the_real_script(tmp_path):
    t = "'" * 3
    line = f'{t}exec\' "$(dirname -- "$(realpath -- "$0")")"/\'python\' "$0" "$@"'
    m = _script(tmp_path, f"#!/bin/sh\n{line}\n' '''\nimport x\n")
    want = os.path.join(os.path.dirname(os.path.realpath(m)), "python")
    assert doctor._shebang_python(m) == want


def test_trampoline_with_another_shell_expression_gives_no_interpreter(tmp_path):
    t = "'" * 3
    m = _script(tmp_path, f'#!/bin/sh\n{t}exec\' "$HOME/venv/bin/python" "$0" "$@"\n')
    assert doctor._shebang_python(m) is None


def test_stdlib_name_inside_a_longer_filename_is_not_a_shadow(tmp_path):
    cfg = cfg_in(tmp_path)
    run = tmp_path / "run"
    run.mkdir()
    for name in ("json.backup.py", "my-notes.py", "os.old.pyc"):
        (run / name).write_text("")
    assert doctor.check_workdir(cfg).status == OK  # none of these imports as a module
    (run / "json.py").write_text("")
    assert doctor.check_workdir(cfg).status == FAIL


def test_shebang_env_resolves_with_the_mineru_env_path(monkeypatch, tmp_path):
    import pdf2wiki.convert.merge as merge

    seen = {}
    monkeypatch.setattr(merge, "_mineru_env", lambda: {"PATH": "/wsl/lib:/usr/bin"})

    def which(n, path=None):
        seen["path"] = path
        return "/usr/bin/python3"

    monkeypatch.setattr(doctor.shutil, "which", which)
    m = _script(tmp_path, "#!/usr/bin/env python3\n")
    assert doctor._shebang_python(m) == "/usr/bin/python3"
    assert seen["path"] == "/wsl/lib:/usr/bin"


def test_missing_explicit_config_message_matches_what_commands_do(tmp_path):
    c = one(run_checks(config_path=str(tmp_path / "x.toml")), "config")
    assert "every other pdf2wiki command stops with exit 2" in c.detail


def test_wrong_type_message_says_other_commands_stop(tmp_path):
    p = tmp_path / "t.toml"
    p.write_text('[remote]\nconnect_timeout = "8"\n')
    checks = run_checks(config_path=str(p))
    c = next(c for c in checks if c.name == "config" and c.status == FAIL)
    assert "every other command stops on this value" in c.detail
