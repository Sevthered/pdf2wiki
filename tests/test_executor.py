"""Tests for executor path handling and config resolution (no ssh/GPU needed)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pdf2wiki.config import Config, load_config
from pdf2wiki.executor import SSHExecutor, _remote_path


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
    inner = captured["cmds"][0][2]
    assert "~" not in inner          # every remote path home-relative, none tilde-quoted
    assert "books/book.pdf" in inner
    assert "--out out" in inner


def test_config_defaults_and_project_override(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = load_config()
    assert cfg.convert.timeout == 7200
    assert cfg.qa.seed == 42
    (tmp_path / "pdf2wiki.toml").write_text("[convert]\ntimeout = 60\ngap = 5\n")
    cfg = load_config()
    assert cfg.convert.timeout == 60
    assert cfg.convert.gap == 5
    assert cfg.convert.seg == 40          # untouched keys keep defaults


def test_config_ignores_unknown_keys(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pdf2wiki.toml").write_text("[convert]\nnot_a_real_key = 1\n")
    cfg = load_config()                   # must not raise
    assert isinstance(cfg, Config)


def test_config_reads_hybrid_server_url(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert load_config().mineru.hybrid_server_url == ""      # default: local hybrid-engine
    (tmp_path / "pdf2wiki.toml").write_text(
        "[mineru]\nhybrid_server_url = \"http://box:8000/v1\"\n")
    assert load_config().mineru.hybrid_server_url == "http://box:8000/v1"


def _convert_args(**over):
    from types import SimpleNamespace
    base = dict(pdf="b.pdf", name="slug", out=None, remote=None, hybrid_server_url=None)
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
    assert cfg.mineru.hybrid_server_url == "http://box:8000/v1"   # flag overrode config
    assert seen["cfg"] is cfg                                     # cfg threaded to convert_book


def test_convert_remote_and_hybrid_url_mutually_exclusive(capsys):
    from pdf2wiki import cli
    cfg = load_config()
    rc = cli._cmd_convert(
        _convert_args(remote="gpu-box", hybrid_server_url="http://box:8000/v1"), cfg)
    assert rc == 2
    assert "mutually exclusive" in capsys.readouterr().err
