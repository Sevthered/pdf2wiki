# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

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
            raise subprocess.TimeoutExpired(cmd="mineru", timeout=1)  # the real abort path

        def fetch(self, slug, out_root, work):
            raise AssertionError("fetch must not be reached after a convert error")

    monkeypatch.setattr(batch, "LocalExecutor", FakeEx)
    cfg = load_config()
    manifest = batch.run_batch(_books_toml(tmp_path), cfg, str(tmp_path / "stage"), remote=None)

    assert manifest["book-a"]["status"] == "convert_failed"  # book-a failed...
    assert manifest["book-b"]["status"] == "convert_failed"  # ...and book-b STILL ran (no abort)
    assert "error" in manifest["book-a"]


def test_fetch_exception_marks_failed_and_continues(tmp_path, monkeypatch):
    class FakeEx:
        def check(self):
            pass

        def convert(self, pdf, slug, out_root, timeout):
            return True, "ok"

        def fetch(self, slug, out_root, work, timeout=None):
            raise FileNotFoundError("scp target missing")

    monkeypatch.setattr(batch, "LocalExecutor", FakeEx)
    cfg = load_config()
    manifest = batch.run_batch(_books_toml(tmp_path), cfg, str(tmp_path / "stage"), remote=None)

    assert manifest["book-a"]["status"] == "fetch_failed"
    assert manifest["book-b"]["status"] == "fetch_failed"


def test_cmd_batch_returns_nonzero_when_a_book_failed(monkeypatch):
    # CI/automation must be able to detect a partial batch — batch used to always exit 0.
    monkeypatch.setattr(
        batch,
        "run_batch",
        lambda *a, **k: {"book-a": {"status": "done"}, "book-b": {"status": "convert_failed"}},
    )
    assert cli.main(["batch", "books.toml"]) == 1


def test_cmd_batch_returns_zero_when_all_done(monkeypatch):
    monkeypatch.setattr(
        batch,
        "run_batch",
        lambda *a, **k: {"book-a": {"status": "done"}, "book-b": {"status": "done"}},
    )
    assert cli.main(["batch", "books.toml"]) == 0


def _books_toml_n(tmp_path, n):
    body = "\n".join(
        f'[[book]]\npdf = "b{i}.pdf"\nslug = "book-{i}"\ndomain = "d"\n' for i in range(n)
    )
    p = tmp_path / "many.toml"
    p.write_text(body)
    return str(p)


def test_circuit_breaker_aborts_when_executor_dies_midbatch(tmp_path, monkeypatch):
    # a mid-batch dependency death must trip the breaker after N consecutive failures and abort,
    # not fast-fail every remaining book (the '17 books in minutes' failure mode).
    class FakeEx:
        def __init__(self):
            self.checks = 0

        def check(self):
            self.checks += 1
            if self.checks > 1:  # start preflight ok; mid-batch re-probe finds it dead
                raise Exception("host down")

        def convert(self, pdf, slug, out_root, timeout):
            raise subprocess.TimeoutExpired(cmd="x", timeout=1)

        def fetch(self, *a, **k):
            raise AssertionError("never reached")

    monkeypatch.setattr(batch, "LocalExecutor", FakeEx)
    cfg = load_config()  # max_consec_fail default = 3
    manifest = batch.run_batch(
        _books_toml_n(tmp_path, 6), cfg, str(tmp_path / "stage"), remote=None
    )
    failed = [s for s, e in manifest.items() if e["status"] == "convert_failed"]
    assert len(failed) == 3  # aborted after 3 consecutive, not all 6
    assert "book-3" not in manifest and "book-5" not in manifest  # later books never attempted
    assert manifest["book-0"]["error_class"] == "TimeoutExpired"


def test_no_breaker_when_executor_stays_healthy(tmp_path, monkeypatch):
    # content failures (executor healthy) must NOT trip the breaker — every book is still attempted.
    class FakeEx:
        def check(self):
            pass  # always healthy

        def convert(self, pdf, slug, out_root, timeout):
            return False, "FAILED coverage"  # ok=False content failure

        def fetch(self, *a, **k):
            raise AssertionError("never reached")

    monkeypatch.setattr(batch, "LocalExecutor", FakeEx)
    cfg = load_config()
    manifest = batch.run_batch(
        _books_toml_n(tmp_path, 5), cfg, str(tmp_path / "stage"), remote=None
    )
    failed = [s for s, e in manifest.items() if e["status"] == "convert_failed"]
    assert len(failed) == 5  # all attempted, no premature abort
    assert manifest["book-0"]["error_class"] == "permanent"


def test_cmd_batch_rolls_up_error_class(monkeypatch, capsys):
    # a partial batch must aggregate error_class so a cluster of same-kind failures reads as one line.
    monkeypatch.setattr(
        batch,
        "run_batch",
        lambda *a, **k: {
            "book-a": {"status": "done"},
            "book-b": {"status": "convert_failed", "error_class": "permanent"},
            "book-c": {"status": "convert_failed", "error_class": "permanent"},
            "book-d": {"status": "convert_failed", "error_class": "TimeoutExpired"},
        },
    )
    assert cli.main(["batch", "books.toml"]) == 1
    err = capsys.readouterr().err
    assert "3 book(s) not done" in err
    assert "permanent×2" in err and "TimeoutExpired×1" in err
    assert "not done:" in err  # slug detail retained
