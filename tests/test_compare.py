# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""`pdf2wiki compare`: two output folders, file by file.

The release gate ran `phase5` from the last tag and from `main` into two folders and compared them
with `diff -r -I '^source: '`. These tests pin the same answer: only the frontmatter `source:` line
may differ, and a body line that starts with `source:` still counts.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pdf2wiki import cli
from pdf2wiki.compare import compare_dirs, render_human, strip_keys

FM = '---\ntitle: "T"\nbook: "b"\nsource: "{src}"\ntags: [book]\n---\n'


def chapter(src: str, body: str = "# 1 Intro\n\nText.\n") -> str:
    return FM.format(src=src) + body


def write(path, text: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_bytes(text.encode("utf-8"))


def by_path(report):
    return {f["path"]: f for f in report["files"]}


# --- strip_keys -----------------------------------------------------------------------------------


def test_strip_keys_removes_the_frontmatter_line_only():
    text = chapter("/stage/a/b.pdf", "# 1 Intro\n\nsource: the body keeps this line\n")
    out = strip_keys(text, ["source"])
    assert 'source: "/stage' not in out
    assert "source: the body keeps this line\n" in out
    assert out.startswith('---\ntitle: "T"\nbook: "b"\ntags: [book]\n---\n')


def test_strip_keys_removes_the_continuation_lines_of_a_multi_line_value():
    text = (
        "---\ntitle: T\nauthors:\n  - Ann\n  - Bob\nsource: >\n  /stage/a\n  /b.pdf\n"
        "tags:\n- x\n- y\nbook: b\n---\nbody\n"
    )
    assert strip_keys(text, ["source", "authors", "tags"]) == "---\ntitle: T\nbook: b\n---\nbody\n"


def test_strip_keys_keeps_a_longer_key_an_indented_key_and_other_keys():
    text = "---\nsourcename: x\nmeta:\n  source: y\nsource: z\n---\n"
    assert strip_keys(text, ["source"]) == "---\nsourcename: x\nmeta:\n  source: y\n---\n"


def test_strip_keys_keeps_a_blank_line_after_a_removed_key():
    assert strip_keys("---\nsource: a\n\nbook: b\n---\n", ["source"]) == "---\n\nbook: b\n---\n"
    assert strip_keys("---\nsource: a\n\n---\n", ["source"]) == "---\n\n---\n"


def test_strip_keys_removes_a_block_scalar_with_blank_and_comment_lines_inside():
    text = (
        "---\nsource: |\n  /stage/a\n\n  # a comment\n   \n  /b.pdf\n\n"
        "list:\n- a\n\n- b\nbook: b\n---\nbody\n"
    )
    assert strip_keys(text, ["source", "list"]) == "---\n\nbook: b\n---\nbody\n"


def test_strip_keys_without_a_closed_frontmatter_changes_nothing():
    no_fm = "source: a\nbody\n"
    unclosed = "---\nsource: a\nbody\n"
    late = "\n---\nsource: a\n---\n"
    for text in (no_fm, unclosed, late, ""):
        assert strip_keys(text, ["source"]) == text


def test_strip_keys_reads_crlf_frontmatter_and_a_dots_end_line():
    text = "---\r\nsource: a\r\nbook: b\r\n...\r\nsource: body\r\n"
    assert strip_keys(text, ["source"]) == "---\r\nbook: b\r\n...\r\nsource: body\r\n"


def test_strip_keys_with_no_keys_changes_nothing():
    text = chapter("a.pdf")
    assert strip_keys(text, []) == text


# --- compare_dirs ---------------------------------------------------------------------------------


def test_files_that_differ_only_in_source_are_the_same(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    write(old / "b" / "01-a.md", chapter("/stage/old/b.pdf"))
    write(new / "b" / "01-a.md", chapter("/stage/new/b.pdf"))
    rep = compare_dirs(str(old), str(new))
    assert rep["ignore_keys"] == ["source"]
    assert rep["files"] == [
        {"path": "b/01-a.md", "status": "same", "utf8": True, "added": 0, "removed": 0}
    ]
    assert rep["totals"]["same"] == 1 and rep["exit_code"] == 0


def test_an_ignore_key_list_replaces_the_default(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    write(old / "01-a.md", chapter("/stage/old/b.pdf"))
    write(new / "01-a.md", chapter("/stage/new/b.pdf"))
    rep = compare_dirs(str(old), str(new), ["nothing-real"])
    f = rep["files"][0]
    assert f["status"] == "different" and (f["added"], f["removed"]) == (1, 1)
    assert rep["exit_code"] == 1


def test_a_body_line_that_starts_with_source_still_counts(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    write(old / "a.md", chapter("x", "source: one\n"))
    write(new / "a.md", chapter("y", "source: two\nmore\n"))
    f = compare_dirs(str(old), str(new))["files"][0]
    assert f["status"] == "different" and (f["added"], f["removed"]) == (2, 1)


def test_files_only_on_one_side_are_reported_and_sorted(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    write(old / "z.md", "z\n")
    write(old / "b" / "gone.md", "g\n")
    write(new / "a.md", "a\n")
    write(new / "z.md", "z\n")
    rep = compare_dirs(str(old), str(new))
    assert [(f["path"], f["status"]) for f in rep["files"]] == [
        ("a.md", "only_in_new"),
        ("b/gone.md", "only_in_old"),
        ("z.md", "same"),
    ]
    t = rep["totals"]
    assert (t["compared"], t["same"], t["only_in_old"], t["only_in_new"]) == (1, 1, 1, 1)
    assert rep["exit_code"] == 1


def test_crlf_differs_from_lf_and_is_named_as_line_ends_only(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    write(old / "a.md", "one\ntwo\n")
    write(new / "a.md", "one\r\ntwo\r\n")
    f = compare_dirs(str(old), str(new))["files"][0]
    assert f["status"] == "different" and f["line_ends_only"] is True
    assert (f["added"], f["removed"]) == (2, 2)


def test_a_missing_last_newline_is_a_line_end_difference(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    write(old / "a.md", "one\ntwo")
    write(new / "a.md", "one\ntwo\n")
    f = compare_dirs(str(old), str(new), diff_lines=10)["files"][0]
    assert f["line_ends_only"] is True and (f["added"], f["removed"]) == (1, 1)
    assert f["diff"][-2:] == ["-two", "+two"]


def test_a_text_line_separator_is_not_a_line_break(tmp_path):
    # str.splitlines() breaks at U+2028 and form feed too; the diff must count "\n" lines only
    old, new = tmp_path / "old", tmp_path / "new"
    write(old / "a.md", "a b\x0cc\n")
    write(new / "a.md", "a b\x0cC\n")
    f = compare_dirs(str(old), str(new))["files"][0]
    assert (f["added"], f["removed"]) == (1, 1) and f["line_ends_only"] is False


def test_a_file_that_is_not_utf8_is_compared_as_bytes(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    write(old / "same.md", b"caf\xe9\n")
    write(new / "same.md", b"caf\xe9\n")
    write(old / "diff.md", b"source: a\ncaf\xe9\n")
    write(new / "diff.md", "source: a\ncafé\n")
    rep = compare_dirs(str(old), str(new), diff_lines=5)
    files = by_path(rep)
    assert files["same.md"] == {
        "path": "same.md",
        "status": "same",
        "utf8": False,
        "added": None,
        "removed": None,
    }
    assert files["diff.md"]["status"] == "different" and files["diff.md"]["utf8"] is False
    assert files["diff.md"]["added"] is None and "diff" not in files["diff.md"]
    assert rep["totals"]["not_utf8"] == 2 and rep["exit_code"] == 1


def test_other_files_are_paired_by_path_but_not_read(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    write(old / "a.md", "a\n")
    write(new / "a.md", "a\n")
    write(old / "book.log", "old log\n")
    write(new / "book.log", "new log\n")
    rep = compare_dirs(str(old), str(new))
    assert by_path(rep)["book.log"] == {"path": "book.log", "status": "not_compared"}
    assert rep["totals"]["not_compared"] == 1 and rep["exit_code"] == 0


def test_an_other_file_on_one_side_only_is_a_difference(tmp_path):
    # a new version that stops writing a chapter's images must not pass the gate
    old, new = tmp_path / "old", tmp_path / "new"
    write(old / "a.md", "a\n")
    write(new / "a.md", "a\n")
    write(old / "images" / "x.jpg", b"\xff\xd8")
    write(new / "images" / "y.jpg", b"\xff\xd8")
    rep = compare_dirs(str(old), str(new))
    assert by_path(rep)["images/x.jpg"]["status"] == "only_in_old"
    assert by_path(rep)["images/y.jpg"]["status"] == "only_in_new"
    t = rep["totals"]
    assert (t["only_in_old"], t["only_in_new"], t["not_compared"]) == (1, 1, 0)
    assert rep["exit_code"] == 1


def test_markdown_files_pair_by_any_case_of_md_and_markdown(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    for name in ("A.MD", "b.Markdown", "c.markdown"):
        write(old / name, f"{name} old\n")
        write(new / name, f"{name} new\n")
    rep = compare_dirs(str(old), str(new))
    assert {f["path"]: f["status"] for f in rep["files"]} == dict.fromkeys(
        ("A.MD", "b.Markdown", "c.markdown"), "different"
    )


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="needs symlinks")
def test_a_file_symlink_is_followed_and_a_directory_symlink_is_not(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    write(tmp_path / "real.md", "same\n")
    write(new / "a.md", "same\n")
    old.mkdir()
    os.symlink(tmp_path / "real.md", old / "a.md")
    # a link back to its own folder: os.walk(followlinks=False) never enters it
    os.symlink(old, old / "loop")
    os.symlink(new, new / "loop")
    rep = compare_dirs(str(old), str(new))
    assert by_path(rep)["a.md"]["status"] == "same"
    assert by_path(rep)["loop"]["status"] == "not_compared" and rep["exit_code"] == 0


def test_diff_lines_keep_the_first_n_lines_of_the_unified_diff(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    write(old / "a.md", chapter("x", "one\ntwo\nthree\n"))
    write(new / "a.md", chapter("y", "one\nTWO\nthree\n"))
    full = compare_dirs(str(old), str(new), diff_lines=100)["files"][0]["diff"]
    assert full[:2] == ["--- old/a.md", "+++ new/a.md"]
    assert "-two" in full and "+TWO" in full
    assert compare_dirs(str(old), str(new), diff_lines=3)["files"][0]["diff"] == full[:3]
    assert "diff" not in compare_dirs(str(old), str(new))["files"][0]


def test_a_hunk_names_the_line_numbers_of_the_real_files(tmp_path):
    # the ignored source line is gone from the compared text, but the @@ numbers are the real
    # ones: old has a one-line source (line 4), new a two-line one (lines 4-5)
    old, new = tmp_path / "old", tmp_path / "new"
    write(old / "a.md", chapter("x", "one\ntwo\nthree\n"))
    write(new / "a.md", chapter("y", "one\nTWO\nthree\n").replace('source: "y"', "source: >\n  y"))
    diff = compare_dirs(str(old), str(new), diff_lines=100)["files"][0]["diff"]
    assert diff == [
        "--- old/a.md",
        "+++ new/a.md",
        "@@ -5,5 +6,5 @@",
        " tags: [book]",
        " ---",
        " one",
        "-two",
        "+TWO",
        " three",
    ]


def test_a_hunk_for_inserted_lines_and_for_one_line(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    write(old / "a.md", "")
    write(new / "a.md", "x\n")
    assert compare_dirs(str(old), str(new), diff_lines=9)["files"][0]["diff"][2] == "@@ -0,0 +1 @@"
    write(old / "a.md", "a\nb\nc\nd\ne\nf\ng\nh\n")
    write(new / "a.md", "a\nb\nc\nd\ne\nf\ng\nX\nh\n")
    diff = compare_dirs(str(old), str(new), diff_lines=9)["files"][0]["diff"]
    assert diff[2] == "@@ -5,4 +5,5 @@" and diff[-2:] == ["+X", " h"]


def test_counts_and_hunks_agree_on_a_repetitive_file(tmp_path):
    # difflib's autojunk treats a line seen in over 1% of a 200+ line file as junk; the counts
    # and the hunks must come from the same match
    old, new = tmp_path / "old", tmp_path / "new"
    write(old / "a.md", "x\n" * 250 + "a\n")
    write(new / "a.md", "a\n" + "x\n" * 250)
    f = compare_dirs(str(old), str(new), diff_lines=10_000)["files"][0]
    hunk_minus = sum(1 for x in f["diff"][2:] if x.startswith("-"))
    hunk_plus = sum(1 for x in f["diff"][2:] if x.startswith("+"))
    assert (f["added"], f["removed"]) == (hunk_plus, hunk_minus) == (1, 1)


@pytest.mark.parametrize(
    "case, message",
    [
        ("missing", "is not a folder"),
        ("file", "is not a folder"),
        ("same", "OLD and NEW are the same folder"),
        ("nested", "one folder is inside the other"),
    ],
)
def test_bad_folders_raise_value_error(tmp_path, case, message):
    old, new = tmp_path / "old", tmp_path / "new"
    old.mkdir()
    new.mkdir()
    if case == "missing":
        new = tmp_path / "nope"
    elif case == "file":
        new = tmp_path / "f.md"
        write(new, "x\n")
    elif case == "same":
        new = tmp_path / "old" / ".." / "old"
    else:
        new = old / "sub"
        new.mkdir()
    with pytest.raises(ValueError, match=message):
        compare_dirs(str(old), str(new))


def test_a_folder_given_in_another_case_is_the_same_folder(tmp_path):
    old = tmp_path / "old"
    (old / "sub").mkdir(parents=True)
    if not (tmp_path / "OLD").exists():
        pytest.skip("this file system is case-sensitive")
    with pytest.raises(ValueError, match="the same folder"):
        compare_dirs(str(old), str(tmp_path / "OLD"))
    with pytest.raises(ValueError, match="one folder is inside the other"):
        compare_dirs(str(tmp_path / "OLD" / "sub"), str(old))


def test_an_empty_ignore_key_is_refused(tmp_path):
    (tmp_path / "o").mkdir()
    (tmp_path / "n").mkdir()
    for key in ("", "a:b", "a b"):
        with pytest.raises(ValueError, match="not a frontmatter key"):
            compare_dirs(str(tmp_path / "o"), str(tmp_path / "n"), [key])


# --- render_human ---------------------------------------------------------------------------------


def test_render_human_lists_what_differs_and_the_totals(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    write(old / "same.md", "s\n")
    write(new / "same.md", "s\n")
    write(old / "d.md", "a\nb\n")
    write(new / "d.md", "a\nB\nc\n")
    write(old / "crlf.md", "a\n")
    write(new / "crlf.md", "a\r\n")
    write(old / "bin.md", b"\xe9")
    write(new / "bin.md", b"\xea")
    write(old / "gone.md", "g\n")
    write(new / "new.md", "n\n")
    write(new / "x.log", "log\n")
    write(old / "y.log", "old\n")
    write(new / "y.log", "new\n")
    out = render_human(compare_dirs(str(old), str(new), diff_lines=6))
    lines = out.splitlines()
    assert lines[0] == f"compare {old} -> {new} (frontmatter keys ignored: source)"
    assert "different    bin.md  (not UTF-8: the bytes differ)" in lines
    assert "different    crlf.md  +1 -1 (line ends only)" in lines
    assert "different    d.md  +2 -1" in lines
    assert "only in OLD  gone.md" in lines
    assert "only in NEW  new.md" in lines and "only in NEW  x.log" in lines
    assert "    -a" in lines and "    +a␍" in lines
    assert "    --- old/d.md" in lines and "    +++ new/d.md" in lines
    assert "same.md" not in out
    assert lines[-1] == (
        "4 compared (1 not UTF-8): 1 same, 3 different. 1 only in OLD, 2 only in NEW. "
        "1 other file in both folders, not read."
    )


def test_render_human_for_two_equal_folders_is_the_totals_only(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    write(old / "a.md", "a\n")
    write(new / "a.md", "a\n")
    out = render_human(compare_dirs(str(old), str(new), ["source", "updated"]))
    assert out.splitlines() == [
        f"compare {old} -> {new} (frontmatter keys ignored: source, updated)",
        "1 compared: 1 same, 0 different. 0 only in OLD, 0 only in NEW. "
        "0 other files in both folders, not read.",
    ]


def test_render_human_says_when_no_key_is_ignored(tmp_path):
    (tmp_path / "o").mkdir()
    (tmp_path / "n").mkdir()
    out = render_human(compare_dirs(str(tmp_path / "o"), str(tmp_path / "n"), []))
    assert out.splitlines()[0].endswith("(frontmatter keys ignored: none)")


# --- CLI ------------------------------------------------------------------------------------------


def _pair(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    write(old / "b" / "01-a.md", chapter("/stage/old/b.pdf"))
    write(new / "b" / "01-a.md", chapter("/stage/new/b.pdf"))
    write(old / "b.log", "old\n")
    write(new / "b.log", "new\n")
    return old, new


def test_cli_compare_exit_0_when_only_source_differs(tmp_path, capsys):
    old, new = _pair(tmp_path)
    assert cli.main(["compare", str(old), str(new)]) == 0
    out = capsys.readouterr().out
    assert "1 compared: 1 same, 0 different." in out
    assert "1 other file in both folders, not read." in out


def test_cli_compare_does_not_read_the_config_file(tmp_path, capsys):
    old, new = _pair(tmp_path)
    bad = tmp_path / "bad.toml"
    bad.write_text("this is [not toml\n", encoding="utf-8")
    assert cli.main(["--config", str(bad), "compare", str(old), str(new)]) == 0
    assert cli.main(["--config", str(bad), "link", str(old)]) == 2


def test_cli_compare_no_ignore_compares_every_key(tmp_path, capsys):
    old, new = _pair(tmp_path)
    assert cli.main(["compare", str(old), str(new), "--no-ignore", "--json"]) == 1
    rep = json.loads(capsys.readouterr().out)
    assert rep["ignore_keys"] == [] and rep["totals"]["different"] == 1
    with pytest.raises(SystemExit):
        cli.main(["compare", str(old), str(new), "--no-ignore", "--ignore-key", "a"])
    assert "not allowed with argument" in capsys.readouterr().err


def test_cli_compare_exit_1_and_diff_when_the_key_is_not_ignored(tmp_path, capsys):
    old, new = _pair(tmp_path)
    args = ["compare", str(old), str(new), "--ignore-key", "nothing-real", "--diff", "20"]
    assert cli.main(args) == 1
    out = capsys.readouterr().out
    assert "different    b/01-a.md  +1 -1" in out
    assert '    -source: "/stage/old/b.pdf"' in out and '    +source: "/stage/new/b.pdf"' in out


def test_cli_compare_repeats_ignore_key(tmp_path, capsys):
    old, new = _pair(tmp_path)
    write(new / "b" / "01-a.md", chapter("/stage/new/b.pdf").replace('book: "b"', 'book: "c"'))
    args = ["compare", str(old), str(new), "--ignore-key", "source", "--ignore-key", "book"]
    assert cli.main([*args, "--json"]) == 0
    rep = json.loads(capsys.readouterr().out)
    assert rep["ignore_keys"] == ["source", "book"] and rep["exit_code"] == 0


def test_cli_compare_json_holds_every_file(tmp_path, capsys):
    old, new = _pair(tmp_path)
    write(new / "extra.md", "x\n")
    assert cli.main(["compare", str(old), str(new), "--json"]) == 1
    rep = json.loads(capsys.readouterr().out)
    assert [f["status"] for f in rep["files"]] == ["not_compared", "same", "only_in_new"]
    assert rep["old"] == str(old) and rep["new"] == str(new)
    assert rep["totals"]["not_compared"] == 1


def test_cli_compare_exit_2_on_a_bad_folder_or_a_negative_diff(tmp_path, capsys):
    old, _ = _pair(tmp_path)
    assert cli.main(["compare", str(old), str(tmp_path / "nope")]) == 2
    assert "is not a folder" in capsys.readouterr().err
    assert cli.main(["compare", str(old), str(old)]) == 2
    assert "the same folder" in capsys.readouterr().err
    assert cli.main(["compare", str(old), str(tmp_path / "new"), "--diff", "-1"]) == 2
    assert "--diff must be 0 or more" in capsys.readouterr().err


def test_cli_compare_exit_2_when_a_file_cannot_be_read(tmp_path, capsys):
    old, new = _pair(tmp_path)
    os.symlink(tmp_path / "missing.md", old / "broken.md")
    write(new / "broken.md", "x\n")
    assert cli.main(["compare", str(old), str(new)]) == 2
    assert "broken.md" in capsys.readouterr().err


def test_a_directory_symlink_named_like_a_markdown_file_is_paired_not_read(tmp_path):
    """Review round 2: the `.md` branch looked at the name only, so `open` raised
    IsADirectoryError on a directory symlink called `notes.md` and the whole compare stopped."""
    for side in ("old", "new"):
        (tmp_path / side / "target").mkdir(parents=True)
        (tmp_path / side / "notes.md").symlink_to(tmp_path / side / "target")
    report = compare_dirs(str(tmp_path / "old"), str(tmp_path / "new"))
    by_path = {f["path"]: f["status"] for f in report["files"]}
    assert by_path["notes.md"] == "not_compared"
    assert report["exit_code"] == 0
