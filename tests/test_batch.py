"""Batch isolation tests: one book's convert/fetch error must NOT abort the whole run.

Regression: ex.convert/ex.fetch were called outside any try — a TimeoutExpired (SSHExecutor
subprocess) or FileNotFoundError (resolve_binary) propagated out of run_batch, killing every
remaining book, contradicting the documented resumable-batch contract.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pdf2wiki.batch as batch
import pdf2wiki.cli as cli
from pdf2wiki.config import load_config


def _books_toml(tmp_path):
    p = tmp_path / "books.toml"
    p.write_text(
        '[[book]]\npdf = "a.pdf"\nslug = "book-a"\ndomain = "d1"\n\n'
        '[[book]]\npdf = "b.pdf"\nslug = "book-b"\ndomain = "d2"\n'
    )
    return str(p)


def test_convert_exception_marks_failed_and_continues(tmp_path, monkeypatch):
    class FakeEx:
        def check(self):
            pass

        def convert(self, pdf, slug, out_root, timeout):
            raise subprocess.TimeoutExpired(cmd="mineru", timeout=1)   # the real abort path

        def fetch(self, slug, out_root, work):
            raise AssertionError("fetch must not be reached after a convert error")

    monkeypatch.setattr(batch, "LocalExecutor", FakeEx)
    cfg = load_config()
    manifest = batch.run_batch(_books_toml(tmp_path), cfg, str(tmp_path / "stage"), remote=None)

    assert manifest["book-a"]["status"] == "convert_failed"   # book-a failed...
    assert manifest["book-b"]["status"] == "convert_failed"   # ...and book-b STILL ran (no abort)
    assert "error" in manifest["book-a"]


def test_fetch_exception_marks_failed_and_continues(tmp_path, monkeypatch):
    class FakeEx:
        def check(self):
            pass

        def convert(self, pdf, slug, out_root, timeout):
            return True, "ok"

        def fetch(self, slug, out_root, work):
            raise FileNotFoundError("scp target missing")

    monkeypatch.setattr(batch, "LocalExecutor", FakeEx)
    cfg = load_config()
    manifest = batch.run_batch(_books_toml(tmp_path), cfg, str(tmp_path / "stage"), remote=None)

    assert manifest["book-a"]["status"] == "fetch_failed"
    assert manifest["book-b"]["status"] == "fetch_failed"


def test_cmd_batch_returns_nonzero_when_a_book_failed(monkeypatch):
    # CI/automation must be able to detect a partial batch — batch used to always exit 0.
    monkeypatch.setattr(batch, "run_batch",
                        lambda *a, **k: {"book-a": {"status": "done"},
                                         "book-b": {"status": "convert_failed"}})
    assert cli.main(["batch", "books.toml"]) == 1


def test_cmd_batch_returns_zero_when_all_done(monkeypatch):
    monkeypatch.setattr(batch, "run_batch",
                        lambda *a, **k: {"book-a": {"status": "done"},
                                         "book-b": {"status": "done"}})
    assert cli.main(["batch", "books.toml"]) == 0
