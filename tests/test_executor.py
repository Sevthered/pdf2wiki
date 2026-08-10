# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for executor path handling and config resolution (no ssh/GPU needed)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pdf2wiki.executor as executor
from pdf2wiki.config import Config, load_config
from pdf2wiki.executor import ExecutionError, SSHExecutor, _remote_path


def test_remote_path_strips_tilde():
    # shlex.quote makes a quoted `~` literal on the remote shell — paths must be home-relative
    assert _remote_path("~/pdf2wiki/out") == "pdf2wiki/out"
    assert _remote_path("/abs/path") == "/abs/path"
    assert _remote_path("relative/path") == "relative/path"


def test_ssh_executor_normalizes_paths():
    ex = SSHExecutor("host", "~/books", "~/pdf2wiki-remote")
    assert ex.books_dir == "books"
    assert ex.workdir == "pdf2wiki-remote"


def test_ssh_executor_convert_command_has_no_tilde(monkeypatch):
    ex = SSHExecutor("host", "~/books", "~/work")
    captured = {}

    class R:
        returncode = 0
        stdout = "EXIT=0"
        stderr = ""

    def fake_run(cmd, timeout=None):
        captured.setdefault("cmds", []).append(cmd)
        return R()

    monkeypatch.setattr(ex, "_run", fake_run)
    ok, log = ex.convert("book.pdf", "slug", "~/out")
    assert ok is True
    inner = captured["cmds"][0][-1]  # remote command is the final ssh arg (ssh opts precede it)
    assert "~" not in inner  # every remote path home-relative, none tilde-quoted
    assert "books/book.pdf" in inner
    assert "--out out" in inner
    assert "timeout 7200s pdf2wiki convert" in inner  # remote self-reaper wraps the converter


def test_config_defaults_and_project_override(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = load_config()
    assert cfg.convert.timeout == 7200
    assert cfg.qa.seed == 42
    (tmp_path / "pdf2wiki.toml").write_text("[convert]\ntimeout = 60\ngap = 5\n")
    cfg = load_config()
    assert cfg.convert.timeout == 60
    assert cfg.convert.gap == 5
    assert cfg.convert.seg == 40  # untouched keys keep defaults


def test_config_ignores_unknown_keys(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pdf2wiki.toml").write_text("[convert]\nnot_a_real_key = 1\n")
    cfg = load_config()  # must not raise
    assert isinstance(cfg, Config)


def test_config_reads_hybrid_server_url(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert load_config().mineru.hybrid_server_url == ""  # default: local hybrid-engine
    (tmp_path / "pdf2wiki.toml").write_text('[mineru]\nhybrid_server_url = "http://box:8000/v1"\n')
    assert load_config().mineru.hybrid_server_url == "http://box:8000/v1"


def _convert_args(**over):
    from types import SimpleNamespace

    base = dict(
        pdf="b.pdf",
        name="slug",
        out=None,
        remote=None,
        hybrid_server_url=None,
        mineru_cloud=False,
        cloud_model=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_convert_flag_overrides_cfg_and_threads_to_local(monkeypatch):
    from pdf2wiki import cli, executor

    cfg = load_config()
    seen = {}

    def fake_convert(self, pdf, slug, out, timeout, cfg=None):
        seen["cfg"] = cfg
        return True, "ok"

    monkeypatch.setattr(executor.LocalExecutor, "convert", fake_convert)
    rc = cli._cmd_convert(_convert_args(hybrid_server_url="http://box:8000/v1"), cfg)
    assert rc == 0
    assert cfg.mineru.hybrid_server_url == "http://box:8000/v1"  # flag overrode config
    assert seen["cfg"] is cfg  # cfg threaded to convert_book


def test_convert_remote_and_hybrid_url_mutually_exclusive(capsys):
    from pdf2wiki import cli

    cfg = load_config()
    rc = cli._cmd_convert(
        _convert_args(remote="gpu-box", hybrid_server_url="http://box:8000/v1"), cfg
    )
    assert rc == 2
    assert "mutually exclusive" in capsys.readouterr().err


def test_ssh_check_ok_runs_real_run(monkeypatch):
    # exercises the real _run body (subprocess.run) by patching the module's subprocess, not _run:
    # check() must build an `ssh ... echo ok` argv, bound by connect_timeout + 5, and pass on "ok".
    seen = {}

    class R:
        returncode = 0
        stdout = "ok\n"
        stderr = ""

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["timeout"] = kwargs.get("timeout")
        return R()

    monkeypatch.setattr(executor.subprocess, "run", fake_run)
    SSHExecutor("gpu-box", "~/books", "~/work", connect_timeout=8).check()  # must not raise
    assert seen["cmd"][0] == "ssh" and seen["cmd"][-1] == "echo ok"
    assert "BatchMode=yes" in seen["cmd"]
    assert seen["timeout"] == 13  # connect_timeout + 5


def test_ssh_check_unreachable_raises(monkeypatch):
    class R:
        returncode = 255
        stdout = ""
        stderr = "connect timeout"

    monkeypatch.setattr(executor.subprocess, "run", lambda cmd, **k: R())
    with pytest.raises(ExecutionError, match="cannot reach dead-host"):
        SSHExecutor("dead-host", "~/b", "~/w").check()


def test_ssh_opts_include_keepalive():
    # long silent MinerU passes must not drop the ssh control channel (else the batch mislabels a
    # still-running convert as failed). Every ssh/scp call goes through _ssh_opts.
    opts = SSHExecutor("h", "~/b", "~/w")._ssh_opts()
    assert "ServerAliveInterval=30" in opts and "ServerAliveCountMax=240" in opts
    assert "BatchMode=yes" in opts and any(o.startswith("ConnectTimeout=") for o in opts)


# ---------- local execution ----------


def test_local_convert_delegates_with_timeout_and_cfg(monkeypatch):
    # LocalExecutor is a thin seam over convert_book; if it drops `cfg`, every CLI override
    # (--hybrid-server-url and friends) is silently ignored and the default config runs instead.
    import pdf2wiki.convert as convert_mod

    seen = {}

    def fake_convert_book(pdf, slug, out_root, *, timeout=None, cfg=None):
        seen.update(pdf=pdf, slug=slug, out_root=out_root, timeout=timeout, cfg=cfg)
        return True, "log text"

    monkeypatch.setattr(convert_mod, "convert_book", fake_convert_book)
    cfg = load_config()
    ok, log = executor.LocalExecutor().convert("/b.pdf", "slug", "~/out", 1234, cfg=cfg)

    assert (ok, log) == (True, "log text")
    assert seen["timeout"] == 1234 and seen["cfg"] is cfg
    assert seen["out_root"] == "~/out"  # expansion is convert_book's job, not the executor's


def test_local_fetch_reports_whether_the_markdown_landed(tmp_path):
    ex = executor.LocalExecutor()
    ex.check()  # no-op, but it is called before every batch — it must not raise
    out_root = str(tmp_path / "out")
    assert ex.fetch("slug", out_root, "unused") is False  # nothing converted yet
    d = tmp_path / "out" / "slug"
    d.mkdir(parents=True)
    (d / "slug.md").write_text("# x")
    assert ex.fetch("slug", out_root, "unused") is True
    assert ex.artifacts_dir("slug", out_root) == str(d)


def test_local_fetch_expands_a_tilde_out_root(monkeypatch, tmp_path):
    # the default out_root is `~/pdf2wiki/out`; an unexpanded `~` would make fetch always False
    # and every local book would be marked fetch_failed.
    monkeypatch.setenv("HOME", str(tmp_path))
    d = tmp_path / "pdf2wiki" / "out" / "slug"
    d.mkdir(parents=True)
    (d / "slug.md").write_text("# x")
    ex = executor.LocalExecutor()
    assert ex.fetch("slug", "~/pdf2wiki/out", "unused") is True
    assert ex.artifacts_dir("slug", "~/pdf2wiki/out") == str(d)


# ---------- remote artifact pull ----------


def _fetch_ex(monkeypatch, results, dest_md=None):
    """SSHExecutor whose _run returns `results` in order, optionally creating the fetched md."""
    ex = SSHExecutor("gpu-box", "~/books", "~/work", fetch_timeout=42)
    calls = []

    class R:
        def __init__(self, rc, err=""):
            self.returncode, self.stdout, self.stderr = rc, "", err

    seq = list(results)

    def fake_run(cmd, timeout=None):
        calls.append({"cmd": cmd, "timeout": timeout})
        rc, err = seq.pop(0)
        if rc == 0 and dest_md and cmd[0] == "scp" and "-r" not in cmd:
            with open(cmd[-1], "w") as f:
                f.write("# fetched")
        return R(rc, err)

    monkeypatch.setattr(ex, "_run", fake_run)
    return ex, calls


def test_ssh_fetch_pulls_markdown_and_images(tmp_path, monkeypatch):
    ex, calls = _fetch_ex(monkeypatch, [(0, ""), (0, "")], dest_md=True)

    assert ex.fetch("slug", "~/out", str(tmp_path / "dest")) is True
    md_cmd, img_cmd = calls[0]["cmd"], calls[1]["cmd"]
    assert md_cmd[0] == "scp" and "-r" not in md_cmd
    assert md_cmd[-2] == "gpu-box:out/slug/slug.md"  # home-relative: a quoted ~ never expands
    assert img_cmd[-2] == "gpu-box:out/slug/images" and "-r" in img_cmd
    assert calls[0]["timeout"] == 42 and calls[1]["timeout"] == 42  # every transfer is bounded


def test_ssh_fetch_fails_loudly_when_the_markdown_is_missing(tmp_path, monkeypatch):
    ex, calls = _fetch_ex(monkeypatch, [(1, "No such file")])

    assert ex.fetch("slug", "~/out", str(tmp_path / "dest")) is False
    assert len(calls) == 1  # no point pulling images for a book that produced no markdown


def test_ssh_fetch_tolerates_a_book_with_no_images(tmp_path, monkeypatch):
    # a book with zero figures legitimately has no images/ dir — only the markdown is mandatory.
    ex, _ = _fetch_ex(monkeypatch, [(0, ""), (1, "scp: images: No such file or directory")], True)

    assert ex.fetch("slug", "~/out", str(tmp_path / "dest")) is True


def test_ssh_fetch_rejects_a_partial_image_pull(tmp_path, monkeypatch):
    # any other scp failure (permissions, disconnect mid-transfer) means the figures are
    # incomplete; passing here would stage a book whose image refs silently 404.
    ex, _ = _fetch_ex(monkeypatch, [(0, ""), (1, "Permission denied")], dest_md=True)

    assert ex.fetch("slug", "~/out", str(tmp_path / "dest")) is False


def test_ssh_fetch_reports_false_when_scp_lies_about_success(tmp_path, monkeypatch):
    # exit 0 is not proof: the final check is the file on disk.
    ex, _ = _fetch_ex(monkeypatch, [(0, ""), (0, "")], dest_md=None)

    assert ex.fetch("slug", "~/out", str(tmp_path / "dest")) is False


def test_ssh_artifacts_dir_refuses_to_guess_a_local_path():
    with pytest.raises(ExecutionError, match="must be fetched first"):
        SSHExecutor("h", "~/b", "~/w").artifacts_dir("slug", "~/out")
