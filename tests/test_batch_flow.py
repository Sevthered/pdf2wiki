# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Wiring tests for the batch driver's SUCCESS path and its run-control switches.

`tests/test_batch.py` covers the failure-isolation contract (one book's error must not abort the
run). Everything a *successful* book does afterwards was unproven: fetch, phase 5, the images
copy that makes chapter image refs resolve, vault placement, and the manifest entry that makes
the next run skip it. Also covered here: the four ways a run is deliberately cut short
(`--only`, `--max-books`, the STOP file, an already-done book) and the corrupt-manifest refusal.

The converter is faked — it writes the markdown a real conversion would leave behind — but phase 5
runs for real, so the chapter files and their frontmatter are the actual artifact.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pdf2wiki.batch as batch
from pdf2wiki.config import Config
from pdf2wiki.executor import LocalExecutor

BOOK_MD = """Front matter line.

# Chapter 1. Beginnings

Body of the first chapter.

![fig](images/fig.png)

# Chapter 2. Endings

Body of the second chapter.
"""


def _cfg(tmp_path):
    cfg = Config()
    cfg.convert.out_root = str(tmp_path / "out")
    return cfg


def _books_toml(tmp_path, n=2, domain="d"):
    body = "\n".join(
        f'[[book]]\npdf = "b{i}.pdf"\nslug = "book-{i}"\ndomain = "{domain}"\n' for i in range(n)
    )
    p = tmp_path / "books.toml"
    p.write_text(body)
    return str(p)


class FakeLocal(LocalExecutor):
    """A converter that succeeds: leaves the same on-disk shape a real conversion does.

    Subclasses the real LocalExecutor on purpose — `fetch()` and `artifacts_dir()` are the real
    implementations, so the local artifact hand-off is exercised rather than stubbed away.
    """

    def convert(self, pdf_path, slug, out_root, timeout, cfg=None):
        d = os.path.join(os.path.expanduser(out_root), slug)
        os.makedirs(os.path.join(d, "images"), exist_ok=True)
        with open(os.path.join(d, f"{slug}.md"), "w", encoding="utf-8") as f:
            f.write(BOOK_MD)
        with open(os.path.join(d, "images", "fig.png"), "wb") as f:
            f.write(b"\x89PNG")
        return True, "converted"


def test_batch_reports_unverified_codepoints_per_book(tmp_path, monkeypatch, capsys):
    """A batch run is how a whole vault gets built, and it used to discard the phase-5 report.

    Every unverified Private Use Area codepoint and every refusal was computed and thrown away, so
    invisible characters shipped into the vault with nothing said about them. The `phase5` command
    printed them; the command that converts ten books did not.
    """
    monkeypatch.setattr(batch, "LocalExecutor", FakeLocal)
    global BOOK_MD
    keep = BOOK_MD
    BOOK_MD = keep.replace("Body of the first chapter.", "Body with an \uf0ff unverified glyph.")
    try:
        batch.run_batch(_books_toml(tmp_path, 1), _cfg(tmp_path), str(tmp_path / "stage"))
    finally:
        BOOK_MD = keep

    out = capsys.readouterr().out
    assert "book-0: ⚠ UNVERIFIED PUA codepoints left as-is" in out
    assert "f0ff" in out
    assert "phase5.symbol_pua" in out  # tells the reader what to do about it


def test_a_failure_while_reporting_residue_neither_fails_the_book_nor_aborts_the_run(
    tmp_path, monkeypatch, capsys
):
    """Printing the phase-5 report must never decide the fate of a book that converted.

    Two placements were measured wrong before this one. INSIDE the `try` that classifies a phase-5
    failure, an exception from printing -- a `UnicodeEncodeError` on the warning sign to a non-UTF-8
    stdout, say -- marked a book that converted correctly as `phase5_failed`, counted it toward the
    circuit breaker and re-converted it on resume. OUTSIDE that `try` but unguarded, the same
    exception left `run_batch` altogether: the remaining books never converted, no manifest was
    written, and the book was re-converted anyway -- breaking the "one book's failure never aborts
    the run" invariant in `docs/explanation/design-principles.md`.

    So: the book is recorded `done`, the run continues to the next book, and the operator is told
    in ASCII that the report could not be printed.
    """
    monkeypatch.setattr(batch, "LocalExecutor", FakeLocal)

    def boom(_report):
        raise UnicodeEncodeError("ascii", "\u26a0", 0, 1, "ordinal not in range(128)")

    monkeypatch.setattr(batch, "residue_lines", boom)
    stage = tmp_path / "stage"

    manifest = batch.run_batch(_books_toml(tmp_path, 2), _cfg(tmp_path), str(stage))

    # the book that converted is DONE, not failed and not missing
    assert manifest["book-0"]["status"] == "done"
    on_disk = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
    assert on_disk["book-0"]["status"] == "done"  # so the next run skips it
    # and the run was not aborted: the second book still converted
    assert on_disk["book-1"]["status"] == "done"

    out = capsys.readouterr().out
    unprintable = [ln for ln in out.splitlines() if "PHASE5 REPORT UNPRINTABLE" in ln]
    assert len(unprintable) == 2  # both books converted, and both said so
    fallback = unprintable[0]
    assert "book-0: PHASE5 REPORT UNPRINTABLE (UnicodeEncodeError)" in fallback
    assert "pdf2wiki phase5" in fallback  # tells the operator how to read it
    assert fallback.isascii()  # the fallback cannot repeat the failure it reports


class _BrokenStdout:
    """A stdout that fails the way a closed pipe does, on the report and on its fallback alike."""

    def write(self, s):
        if "⚠" in s or "UNPRINTABLE" in s:
            raise BrokenPipeError(32, "Broken pipe")
        return len(s)

    def flush(self):
        pass


def test_a_broken_stdout_does_not_abort_the_run_from_the_recovery_path(tmp_path, monkeypatch):
    """The fallback print is a print too, and it fails for the same reason the report did.

    Here stdout rejects the report's own characters. The report raises, the `except` catches it,
    and the unguarded fallback then raised the identical exception from the recovery path, outside
    every `try`: measured before the guard, `run_batch` raised, no manifest was written, and the
    remaining books never converted -- the same outcome the guard above it exists to prevent. There
    is nowhere left to say anything, so it says nothing and the books survive.

    ⚠ This is NOT a claim that `run_batch` survives a stdout broken for everything. That case is
    handled at the CLI boundary, and `test_batch_runs_to_the_end_when_its_reader_closes_the_pipe`
    proves it through `cli.main`.
    """
    monkeypatch.setattr(batch, "LocalExecutor", FakeLocal)
    monkeypatch.setattr(batch, "residue_lines", lambda _report: ["⚠ 1 unverified codepoint"])
    monkeypatch.setattr(sys, "stdout", _BrokenStdout())
    stage = tmp_path / "stage"

    manifest = batch.run_batch(_books_toml(tmp_path, 2), _cfg(tmp_path), str(stage))

    monkeypatch.undo()
    assert manifest["book-0"]["status"] == "done"
    on_disk = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
    assert on_disk["book-0"]["status"] == "done" and on_disk["book-1"]["status"] == "done"


def test_successful_book_is_split_staged_and_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(batch, "LocalExecutor", FakeLocal)
    cfg = _cfg(tmp_path)

    manifest = batch.run_batch(_books_toml(tmp_path, 1), cfg, str(tmp_path / "stage"))

    entry = manifest["book-0"]
    assert entry["status"] == "done" and entry["domain"] == "d"
    assert isinstance(entry["minutes"], float)
    chapters = os.path.join(str(tmp_path / "out"), "book-0", "chapters")
    names = sorted(os.listdir(chapters))
    assert "01-chapter-1-beginnings.md" in names and "02-chapter-2-endings.md" in names
    # the images dir must sit NEXT TO the chapters or every `images/...` ref 404s in the vault
    assert os.path.exists(os.path.join(chapters, "images", "fig.png"))
    with open(os.path.join(chapters, "01-chapter-1-beginnings.md"), encoding="utf-8") as f:
        body = f.read()
    assert body.startswith("---\n") and 'source: "b0.pdf"' in body  # PDF name, not a staging path
    # the manifest is written, not just returned — that file is the resume backbone
    on_disk = json.loads((tmp_path / "stage" / "manifest.json").read_text(encoding="utf-8"))
    assert on_disk["book-0"]["status"] == "done"


def test_vault_placement_copies_chapters_and_records_the_path(tmp_path, monkeypatch):
    monkeypatch.setattr(batch, "LocalExecutor", FakeLocal)
    vault = tmp_path / "vault"

    manifest = batch.run_batch(
        _books_toml(tmp_path, 1), _cfg(tmp_path), str(tmp_path / "stage"), vault=str(vault)
    )

    dest = vault / "d" / "book-0"  # domain becomes the subfolder
    assert manifest["book-0"]["vault_path"] == str(dest)
    assert (dest / "01-chapter-1-beginnings.md").exists()
    assert (dest / "images" / "fig.png").exists()


def test_book_without_domain_lands_directly_under_the_vault_root(tmp_path, monkeypatch):
    monkeypatch.setattr(batch, "LocalExecutor", FakeLocal)
    p = tmp_path / "nodomain.toml"
    p.write_text('[[book]]\npdf = "b0.pdf"\nslug = "book-0"\n')
    vault = tmp_path / "vault"

    manifest = batch.run_batch(str(p), _cfg(tmp_path), str(tmp_path / "stage"), vault=str(vault))

    assert manifest["book-0"]["vault_path"] == str(vault / "book-0")  # no empty path segment


def test_done_book_is_skipped_on_re_run(tmp_path, monkeypatch):
    # the resume contract: a second run must not re-convert what already finished.
    monkeypatch.setattr(batch, "LocalExecutor", FakeLocal)
    cfg, stage = _cfg(tmp_path), str(tmp_path / "stage")
    books = _books_toml(tmp_path, 1)
    batch.run_batch(books, cfg, stage)

    converts = []

    class Recorder(FakeLocal):
        def convert(self, pdf_path, slug, out_root, timeout, cfg=None):
            converts.append(slug)
            return super().convert(pdf_path, slug, out_root, timeout, cfg)

    monkeypatch.setattr(batch, "LocalExecutor", Recorder)
    manifest = batch.run_batch(books, cfg, stage)

    assert converts == []  # nothing re-converted
    assert manifest["book-0"]["status"] == "done"  # and the entry survived the round-trip


def test_only_runs_the_named_slug(tmp_path, monkeypatch):
    monkeypatch.setattr(batch, "LocalExecutor", FakeLocal)

    manifest = batch.run_batch(
        _books_toml(tmp_path, 3), _cfg(tmp_path), str(tmp_path / "stage"), only="book-1"
    )

    assert list(manifest) == ["book-1"]


def test_max_books_stops_after_n_attempts(tmp_path, monkeypatch):
    monkeypatch.setattr(batch, "LocalExecutor", FakeLocal)

    manifest = batch.run_batch(
        _books_toml(tmp_path, 4), _cfg(tmp_path), str(tmp_path / "stage"), max_books=2
    )

    assert list(manifest) == ["book-0", "book-1"]  # the rest are untouched, not failed


def test_stop_file_halts_between_books_and_is_consumed(tmp_path, monkeypatch):
    # the operator's clean brake. It must be removed on halt, or the next run stops immediately
    # and the batch looks permanently wedged.
    monkeypatch.setattr(batch, "LocalExecutor", FakeLocal)
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "STOP").write_text("")

    manifest = batch.run_batch(_books_toml(tmp_path, 2), _cfg(tmp_path), str(stage))

    assert manifest == {}
    assert not (stage / "STOP").exists()


def test_corrupt_manifest_refuses_instead_of_restarting_every_book(tmp_path, monkeypatch):
    # silently treating an unreadable manifest as empty would re-convert a finished 10-book batch.
    monkeypatch.setattr(batch, "LocalExecutor", FakeLocal)
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "manifest.json").write_text("{not json")

    with pytest.raises(SystemExit, match="corrupt"):
        batch.run_batch(_books_toml(tmp_path, 1), _cfg(tmp_path), str(stage))


def test_books_toml_missing_a_required_key_is_rejected(tmp_path):
    p = tmp_path / "bad.toml"
    p.write_text('[[book]]\npdf = "b.pdf"\n')  # no slug: everything downstream is named by it

    with pytest.raises(ValueError, match="needs `pdf` and `slug`"):
        batch.load_books(str(p))


def test_fetch_returning_false_marks_the_book_fetch_failed(tmp_path, monkeypatch):
    # distinct from a raised fetch error (covered in test_batch.py): a clean False means the
    # artifacts never landed, and phase 5 must not run on a missing file.
    class NoArtifacts(FakeLocal):
        def fetch(self, slug, out_root, dest_dir, timeout=None):
            return False

    monkeypatch.setattr(batch, "LocalExecutor", NoArtifacts)
    monkeypatch.setattr(
        batch, "run_chain", lambda *a, **k: pytest.fail("phase 5 ran without artifacts")
    )

    manifest = batch.run_batch(_books_toml(tmp_path, 1), _cfg(tmp_path), str(tmp_path / "stage"))

    assert manifest["book-0"] == {"status": "fetch_failed", "domain": "d", "error_class": "fetch"}


def test_phase5_failure_is_isolated_to_its_book(tmp_path, monkeypatch):
    monkeypatch.setattr(batch, "LocalExecutor", FakeLocal)

    def boom(*a, **k):
        raise RuntimeError("no chapter boundaries found")

    monkeypatch.setattr(batch, "run_chain", boom)

    manifest = batch.run_batch(_books_toml(tmp_path, 2), _cfg(tmp_path), str(tmp_path / "stage"))

    assert [e["status"] for e in manifest.values()] == ["phase5_failed", "phase5_failed"]
    assert manifest["book-0"]["error_class"] == "phase5"  # both books still attempted


class FakeRemote:
    """A stand-in for SSHExecutor. Deliberately does NOT subclass LocalExecutor.

    That inheritance is load-bearing: `run_batch` branches on `isinstance(ex, LocalExecutor)` to
    decide whether the artifacts are already on disk or arrived via `fetch()` into the stage dir.
    A fake that inherits LocalExecutor drives the LOCAL branch no matter what it is called, so the
    remote path would look covered while never running. `artifacts_dir` raises here exactly as the
    real SSHExecutor does.
    """

    def __init__(self, host, books_dir, workdir, connect, convert_t, fetch_t, reap):
        self.args = dict(
            host=host,
            books_dir=books_dir,
            workdir=workdir,
            connect=connect,
            convert_t=convert_t,
            fetch_t=fetch_t,
            reap=reap,
        )
        FakeRemote.last = self

    def check(self):
        pass

    def convert(self, pdf_filename, slug, out_root, timeout=None):
        return True, "remote log"

    def fetch(self, slug, out_root, dest_dir, timeout=None):
        # what scp does: the artifacts land in dest_dir, NOT in a local out_root
        os.makedirs(os.path.join(dest_dir, "images"), exist_ok=True)
        with open(os.path.join(dest_dir, f"{slug}.md"), "w", encoding="utf-8") as f:
            f.write(BOOK_MD)
        with open(os.path.join(dest_dir, "images", "fig.png"), "wb") as f:
            f.write(b"\x89PNG")
        return True

    def artifacts_dir(self, slug, out_root):
        raise AssertionError("remote artifacts must be fetched, never read from a local out_root")


def test_remote_mode_builds_the_executor_with_the_configured_arguments(tmp_path, monkeypatch):
    # every remote timeout is config-driven; a dropped or misordered argument here silently
    # reverts one of them to a default and the Timeouts-Pattern guarantees stop holding.
    monkeypatch.setattr(batch, "SSHExecutor", FakeRemote)
    cfg = _cfg(tmp_path)
    cfg.remote.books_dir = "~/books"
    cfg.remote.connect_timeout = 11

    batch.run_batch(_books_toml(tmp_path, 1), cfg, str(tmp_path / "stage"), remote="gpu-box")

    seen = FakeRemote.last.args
    assert seen["host"] == "gpu-box" and seen["books_dir"] == "~/books"
    assert seen["connect"] == 11 and seen["convert_t"] == cfg.remote.convert_timeout
    assert seen["fetch_t"] == cfg.remote.fetch_timeout and seen["reap"] == cfg.remote.reap_grace


def test_remote_run_phase5s_the_fetched_stage_dir_not_a_local_out_root(tmp_path, monkeypatch):
    """The remote branch end to end: nothing is ever read from the local `out_root`.

    `run_batch` only rewrites `work` to `ex.artifacts_dir(...)` for a LocalExecutor. On the remote
    path `work` must stay the stage dir that `fetch()` filled, because on this machine `out_root`
    holds nothing at all — the conversion happened on another host. Getting this wrong means phase 5
    runs on a missing file, or worse, on a stale local book of the same slug.
    """
    monkeypatch.setattr(batch, "SSHExecutor", FakeRemote)
    cfg = _cfg(tmp_path)
    stage = tmp_path / "stage"
    vault = tmp_path / "vault"

    manifest = batch.run_batch(
        _books_toml(tmp_path, 1), cfg, str(stage), remote="gpu-box", vault=str(vault)
    )

    assert manifest["book-0"]["status"] == "done"
    # chapters were produced from the FETCHED markdown, under the stage dir
    chapters = stage / "book-0" / "chapters"
    assert (chapters / "01-chapter-1-beginnings.md").exists()
    assert (chapters / "images" / "fig.png").exists()
    assert (vault / "d" / "book-0" / "01-chapter-1-beginnings.md").exists()
    # and the local out_root was never even created, let alone read
    assert not os.path.exists(os.path.join(str(tmp_path / "out"), "book-0"))


class _ClosedPipe:
    """A stdout whose reader is gone: every write fails, not only the report's characters."""

    def __init__(self):
        self.writes = 0

    def write(self, s):
        self.writes += 1
        raise BrokenPipeError(32, "Broken pipe")

    def flush(self):
        pass


def test_batch_runs_to_the_end_when_its_reader_closes_the_pipe(tmp_path, monkeypatch, capsys):
    """`pdf2wiki batch | head` must not end the batch at the first print after the pipe closes.

    Measured before the guard in `cli.main`: `run_batch` raised `BrokenPipeError` at the per-book
    header, no manifest was written, and every book that converted was converted again on the next
    run. The guard sits at the CLI boundary, so this test goes through `cli.main`, not `run_batch`.
    """
    from pdf2wiki import cli

    monkeypatch.setattr(batch, "LocalExecutor", FakeLocal)
    cfg_toml = tmp_path / "cfg.toml"
    cfg_toml.write_text(f'[convert]\nout_root = "{tmp_path / "out"}"\n')
    stage = tmp_path / "stage"
    pipe = _ClosedPipe()
    monkeypatch.setattr(sys, "stdout", pipe)
    rc = cli.main(
        ["--config", str(cfg_toml), "batch", _books_toml(tmp_path, 2), "--stage", str(stage)]
    )
    monkeypatch.undo()

    assert rc == 0
    assert pipe.writes == 1  # the first failure is the last attempt on the dead pipe
    assert "stdout was closed by its reader" in capsys.readouterr().err
    on_disk = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
    assert on_disk["book-0"]["status"] == "done" and on_disk["book-1"]["status"] == "done"


def test_the_guard_redirects_the_real_descriptor_so_the_exit_flush_cannot_raise(tmp_path):
    """On a REAL pipe with its reader closed, the guard must fix the file descriptor too.

    `write()` catching the error is not enough: the interpreter flushes the original stdout at exit,
    and a child process inherits fd 1. Both would hit the dead pipe again. After the first failure
    the descriptor points at the null device and a raw `os.write` on it succeeds.
    """
    import signal

    from pdf2wiki.cli import _StdoutSurvivesItsReader

    previous = signal.signal(signal.SIGPIPE, signal.SIG_IGN)  # a dead pipe must raise, not kill
    r, w = os.pipe()
    os.close(r)
    try:
        inner = os.fdopen(
            w, "w", encoding="utf-8", buffering=1
        )  # line-buffered: "\n" writes through
        guard = _StdoutSurvivesItsReader(inner)
        assert guard.write("first line\n") == len("first line\n")
        assert guard.lost
        assert guard.write("after\n") == len("after\n")  # swallowed, not raised
        assert (
            os.write(w, b"raw\n") == 4
        )  # fd 1-equivalent now reaches /dev/null, not the dead pipe
        inner.flush()
        inner.close()
    finally:
        signal.signal(signal.SIGPIPE, previous)


def test_batch_piped_into_head_exits_zero_and_writes_the_manifest(tmp_path):
    """The real thing: a shell pipe whose reader quits after one line.

    Run in a subprocess so the interpreter's own exit flush is exercised too -- that flush hits
    the dead pipe after `main` has returned, and prints `Exception ignored ... BrokenPipeError`
    unless the descriptor was redirected. The exit code and the manifest are read from disk.
    """
    import subprocess

    cfg_toml = tmp_path / "cfg.toml"
    cfg_toml.write_text(f'[convert]\nout_root = "{tmp_path / "out"}"\n')
    stage = tmp_path / "stage"
    status = tmp_path / "rc"
    driver = tmp_path / "driver.py"
    driver.write_text(
        "import sys\n"
        f"sys.path.insert(0, {os.path.join(os.path.dirname(__file__), '..', 'src')!r})\n"
        f"sys.path.insert(0, {os.path.dirname(__file__)!r})\n"
        "import pdf2wiki.batch as batch\n"
        "from test_batch_flow import FakeLocal\n"
        "from pdf2wiki import cli\n"
        "batch.LocalExecutor = FakeLocal\n"
        f"rc = cli.main(['--config', {str(cfg_toml)!r}, 'batch', {_books_toml(tmp_path, 3)!r},"
        f" '--stage', {str(stage)!r}])\n"
        f"open({str(status)!r}, 'w').write(str(rc))\n"
        "sys.exit(rc)\n"
    )
    shell = f"{sys.executable} {driver} | head -n 1; exit ${{PIPESTATUS[0]}}"
    proc = subprocess.run(  # noqa: S603 -- a pipe needs a shell; every path is this test's own
        ["bash", "-c", shell],  # noqa: S607 -- bash from PATH, the test has no other
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        timeout=120,
    )

    assert proc.returncode == 0, proc.stderr
    assert status.read_text() == "0"
    # proof the dead pipe was hit, not that `head` happened to read everything first
    assert "stdout was closed by its reader" in proc.stderr, proc.stderr
    assert "Exception ignored" not in proc.stderr and "Traceback" not in proc.stderr, proc.stderr
    on_disk = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
    assert [on_disk[f"book-{i}"]["status"] for i in range(3)] == ["done"] * 3
