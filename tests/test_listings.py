# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""`pdf2wiki listings`: export a book's code blocks and check whether each one parses.

The block shapes here are the ones measured on a vault of 26 converted books: a bold listing caption
above a fence with a `code-verify` comment between, a caption set as a heading, a REPL session, a
Go function shown without its end, a JavaScript class under a `python` tag, a curly quote typeset
into Python code, a JSON array cut at a page break, and an HTML page under an `xml` tag.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pdf2wiki import cli, listings
from pdf2wiki.phase5 import codecheck, xref

FM = '---\ntitle: "{t}"\nbook: "b"\nchapter: {n}\n---\n'
RSQUO = chr(0x2019)  # a curly apostrophe, as typeset in a book
ELLIPSIS = chr(0x2026)
ARROW = chr(0x2190)


def chap(n: int, body: str) -> str:
    return FM.format(t=f"Chapter {n}", n=n) + body


CH1 = chap(
    1,
    "# 1 Basics\n\n"
    "**Listing 1.1** The *first* program ^lst-1-1\n\n"
    "<!-- code-verify: hybrid VLM diverged from text layer -->\n"
    "```python\nprint('hi')\n```\n\n"
    "Listing 1.2 shows the same in Go.\n\n"
    "```go\nfunc main() {\n```\n\n"
    "```\nplain text\n```\n\n"
    "```python\nunclosed opener, so not a block\n",
)
CH2 = chap(
    2,
    "## Listing 2.1 A class\n\n"
    "```javascript\nclass A { constructor() {} }\n```\n\n"
    '```json\n{"a": 1}\n```\n',
)


MORE = (
    "## 3.1 Section\n"
    "Listing 3.1 Under a heading\n\n"
    "```go\nx\n```\n\n"
    "```go\ny\n```\n\n"
    "*Listing 3.2 Emphasised caption*\n\n"
    "```python\nz\n```\n\n"
    "Listing 3.3 shows the class.\n\n"
    "```go\nw\n```\n"
)


def _book(tmp_path):
    d = tmp_path / "book"
    d.mkdir()
    (d / "01-basics.md").write_text(CH1, encoding="utf-8")
    (d / "02-classes.md").write_text(CH2, encoding="utf-8")
    (d / "b-index.md").write_text('---\ntitle: "B"\nbook: "b"\n---\n\n```python\nx\n```\n')
    return d


def _scan(files):
    return listings.scan(files)


# --- scan and captions ---------------------------------------------------------------------------


def test_scan_finds_closed_blocks_with_their_line_tag_and_exact_body():
    found = _scan({"01-basics.md": CH1, "02-classes.md": CH2})
    assert [(x.chapter, x.index, x.lang) for x in found] == [
        ("01-basics.md", 1, "python"),
        ("01-basics.md", 2, "go"),
        ("01-basics.md", 3, ""),
        ("02-classes.md", 1, "javascript"),
        ("02-classes.md", 2, "json"),
    ]
    lines = CH1.split("\n")
    assert lines[found[0].line - 1] == "```python"  # the 1-based line of the opener
    assert found[0].body == "print('hi')\n"


def test_a_caption_directly_above_the_fence_is_attached_without_markup():
    found = _scan({"01-basics.md": CH1, "02-classes.md": CH2})
    assert found[0].caption == "Listing 1.1 The first program" and found[0].number == "1.1"
    assert found[3].caption == "Listing 2.1 A class" and found[3].number == "2.1"  # a heading


def test_prose_that_starts_like_a_caption_is_no_caption():
    found = _scan({"01-basics.md": CH1})
    assert found[1].caption is None and found[1].number is None  # "Listing 1.2 shows ..."
    assert found[2].caption is None  # the paragraph above is a fence, not a caption


def test_a_caption_with_prose_between_it_and_the_fence_is_not_attached():
    md = "**Listing 3.1** Setup\n\nRun this first:\n\n```bash\nls\n```\n"
    assert _scan({"c.md": md})[0].caption is None


def test_a_caption_paragraph_of_two_lines_is_read_from_its_first_line():
    md = 'Intro.\n\n<a id="lst-3-2"></a>Listing 3.2 A long caption\nthat wraps\n\n```go\nx\n```\n'
    found = _scan({"c.md": md})
    assert found[0].caption == "Listing 3.2 A long caption" and found[0].number == "3.2"


def test_a_heading_caption_is_a_paragraph_of_its_own():
    md = "Text with no blank line after it\n## Listing 4.3 A heading caption\n```go\nx\n```\n"
    assert _scan({"c.md": md})[0].caption == "Listing 4.3 A heading caption"


def test_the_block_after_a_captioned_block_does_not_take_its_caption():
    md = "Listing 4.1 The class\n```java\nclass A {}\n```\n\n```java\nclass B {}\n```\n"
    found = _scan({"c.md": md})
    assert [x.number for x in found] == ["4.1", None]


def test_a_heading_directly_above_a_caption_ends_the_paragraph_before_it():
    md = "## 4.2 Section\nListing 4.2 The thing\n\n```go\nx\n```\n"
    assert _scan({"c.md": md})[0].caption == "Listing 4.2 The thing"


def test_a_list_item_above_makes_the_caption_line_a_continuation_and_no_caption():
    md = "- an item\nListing 4.4 The thing\n\n```go\nx\n```\n"
    assert _scan({"c.md": md})[0].caption is None


def test_a_caption_far_from_its_fence_is_no_caption_as_in_link():
    # `link` needs the fence within two non-blank lines of the caption; `listings` agrees.
    md = "Listing 4.5 The thing\nthat wraps\n<!-- code-verify: x -->\n```go\nx\n```\n"
    assert _scan({"c.md": md})[0].caption is None


def test_listings_and_link_find_the_same_listing_captions():
    # Every listing caption in these files sits above its fence, so the two sets must be equal.
    files = {"01-basics.md": CH1, "02-classes.md": CH2, "03-more.md": chap(3, MORE)}
    targets = sorted(
        (name, t.key)
        for name, text in files.items()
        for t in xref._targets(xref._File(name, text))[0]
        if t.kind == "listing"
    )
    found = sorted((x.chapter, x.number) for x in _scan(files) if x.number is not None)
    assert (
        found
        == targets
        == [
            ("01-basics.md", "1.1"),
            ("02-classes.md", "2.1"),
            ("03-more.md", "3.1"),
            ("03-more.md", "3.2"),
        ]
    )


@pytest.mark.parametrize(
    ("line", "caption"),
    [
        ("Listing 4.1 The __init__ method", "Listing 4.1 The __init__ method"),
        ("**Listing 4.1** The _private helper", "Listing 4.1 The _private helper"),
        ("_Listing 4.1 A whole caption in emphasis_", "Listing 4.1 A whole caption in emphasis"),
        ("*Listing 4.1 The `*ptr` and *bold* words*", "Listing 4.1 The `*ptr` and bold words"),
        ("__Listing 4.1__ my_var and __init__", "Listing 4.1 my_var and __init__"),
        (
            "Listing 8.14 The kafka\\_cluster.yml and `a\\_b`",
            "Listing 8.14 The kafka_cluster.yml and `a\\_b`",
        ),
    ],
)
def test_caption_emphasis_comes_off_but_identifiers_keep_their_underscores(line, caption):
    assert _scan({"c.md": f"{line}\n\n```python\nx\n```\n"})[0].caption == caption


def test_a_figure_caption_or_a_fence_at_the_top_of_the_file_is_no_listing_caption():
    assert _scan({"c.md": "*Figure 3.1 A diagram*\n\n```text\nx\n```\n"})[0].caption is None
    assert _scan({"c.md": "\n```text\nx\n```\n"})[0].caption is None


# --- language names and extensions ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("tag", "lang", "ext"),
    [
        ("python", "python", "py"),
        ("py", "python", "py"),
        ("Python3", "python", "py"),
        ("golang", "go", "go"),
        ("c++", "cpp", "cpp"),
        ("c#", "csharp", "cs"),
        ("rs", "rust", "rs"),
        ("js", "javascript", "js"),
        ("shell", "bash", "sh"),
        ("mermaid", "mermaid", "txt"),
        ("", "", "txt"),
    ],
)
def test_canonical_language_and_extension_come_from_the_lang_retag_tables(tag, lang, ext):
    assert listings.canonical(tag) == lang
    assert listings.extension(tag) == ext


# --- the checks ----------------------------------------------------------------------------------


def _cls(tag, body):
    c = listings.check(tag, body)
    return c.cls, c.message


def test_a_block_with_no_check_is_not_checked():
    assert listings.check("yaml", "a: [\n") == listings.Check("not-checked", "", None)
    assert _cls("", "anything (")[0] == "not-checked"


def test_python_that_parses_is_ok():
    assert listings.check("py", "def f():\n    return 1\n") == listings.Check("ok", "python", None)


@pytest.mark.parametrize(
    ("body", "why"),
    [
        (">>> x = 1\n>>> for i in range(2):\n...     print(i)\n...\n0\n1\n", "a REPL session"),
        (f"def f():\n    {ELLIPSIS}\n    return [1, {ELLIPSIS}]\n", "an elision"),
        ("    def f(self):\n        return 1\n", "an indented excerpt"),
        ("# a comment at column 0\n    x = 1\n    y = 2\n", "an indented excerpt"),
        (f">>> s = [1, {ELLIPSIS}]\n", "a REPL session"),
    ],
)
def test_a_python_piece_is_a_fragment(body, why):
    assert _cls("python", body) == ("fragment", why)


def test_a_curly_quote_in_python_is_an_error_with_the_parser_message():
    cls, msg = _cls("python", f"x = 1\nprint({RSQUO}hi{RSQUO})\n")
    assert cls == "error" and "U+2019" in msg and "(line 2)" in msg


def test_a_repl_session_does_not_hide_a_real_error():
    cls, msg = _cls("python", f">>> print({RSQUO}hi{RSQUO})\n")
    assert cls == "error" and "U+2019" in msg


def test_a_python_block_cut_inside_a_call_is_an_error():
    assert _cls("python", "model.fit(x,\n    epochs=10,\n")[0] == "error"


def test_a_parser_value_error_is_an_error(monkeypatch):
    def boom(_src):
        raise ValueError("")

    monkeypatch.setattr(codecheck.ast, "parse", boom)
    assert _cls("python", "x\n") == ("error", "ValueError")


@pytest.mark.parametrize(
    ("tag", "body", "why"),
    [
        ("python", "class Person {\n  greet() {\n    console.log(\"hi\");\n  }\n}\n",
         "parses as javascript"),
        ("python", "package main\n\nimport (\n    \"fmt\"\n)\n", "parses as go"),
        ("python", "func (s *S) Get() error {\n\tif s.x {\n\t\treturn nil\n\t}\n", "a go fragment"),
        ("python", f"x {ARROW} 0\nfor i in a:\n    x {ARROW} x + i\n", "looks like pseudocode"),
        ("xml", "<html>\n<head><meta charset=\"utf-8\"></head>\n<body><br></body>\n</html>\n",
         "looks like html"),
        ("go", "import os\n\ndef main():\n    # see (a]\n    print(os.getcwd())\n",
         "parses as python"),
    ],
)  # fmt: skip
def test_a_block_that_fails_its_tag_but_matches_another_language_is_wrong_language(tag, body, why):
    assert _cls(tag, body) == ("wrong-language?", why)


def test_a_wrong_language_guess_that_also_fails_stays_an_error():
    # The detector says Go, but the Go brackets cross: no other language explains the block.
    cls, msg = _cls("python", "func main() {\n\tf(x}\n")
    assert cls == "error" and "(line" in msg


def test_a_guess_with_the_same_check_as_the_tag_is_no_wrong_language():
    # A `cpp` block that the detector calls `c` runs the same brace check: that is an error.
    assert _cls("cpp", '#include <stdio.h>\nint main() { printf("x"}; )\n')[0] == "error"


@pytest.mark.parametrize(
    ("body", "cls", "msg"),
    [
        ('func main() {\n\tfmt.Println("(")\n}\n', "ok", None),
        ("func main() {\n\tx := 1\n", "fragment", "a cut excerpt: unclosed '{' from line 1"),
        ("\tx := 1\n}\n}\n", "fragment", "a cut excerpt: unmatched '}' at line 2"),
        ("}\nfunc f() {\n", "fragment", "a cut excerpt: unmatched '}' at line 1"),
        ("func f() {\n\tg(x}\n)\n", "error", "'(' at line 2 closed by '}' at line 2"),
        ("r := '('\ns := `raw (\nstring`\n// a ( comment\n/* a\n( */\nf()\n", "ok", None),
        ('s := "a \\" ("\nf()\n', "ok", None),
        ('s := "lost quote (\nf()\n', "ok", None),
        ("f()\n/* unclosed (", "ok", None),
        ("f() // end (", "ok", None),
    ],
)
def test_the_go_brace_check_skips_strings_runes_and_comments(body, cls, msg):
    assert _cls("go", body) == (cls, msg)


def test_a_backslash_newline_in_a_string_still_counts_the_line():
    body = 's := "a \\\nb"\n(\n}\n'
    assert _cls("go", body) == ("error", "'(' at line 3 closed by '}' at line 4")


def test_a_rust_lifetime_is_no_character_literal():
    body = "fn f<'a>(x: &'a str) -> &'a str {\n    x\n}\nlet c = '{';\n"
    assert _cls("rust", body) == ("ok", None)


def test_javascript_single_quotes_and_template_literals_are_strings():
    body = "const a = 'it (';\nconst b = `x ${y} (\n`;\nf(a, b)\n"
    assert _cls("javascript", body) == ("ok", None)


def test_a_java_text_block_is_one_string():
    assert _cls("java", 'String s = """\n  ( {\n  """;\nf(s);\n') == ("ok", None)


@pytest.mark.parametrize(
    ("body", "cls", "msg"),
    [
        ('{"a": [1, 2]}\n', "ok", None),
        ('{"a": 1, ...}\n', "fragment", "an elision"),
        (f"[1, 2, {ELLIPSIS}]\n", "fragment", "an elision"),
        ('"a": 1,\n"b": 2,\n', "fragment", "a member list without its braces"),
        ('{"a": 1}\n{"b": 2}\n', "fragment", "several JSON documents"),
        ('[\n  {"a": 1},\n  {\n', "fragment", "a cut excerpt: unclosed '[' from line 1"),
        ('  "a": 1\n  },\n  {"b": 2}\n]\n', "fragment", "a cut excerpt: unmatched '}' at line 2"),
    ],
)
def test_json_pieces_are_fragments(body, cls, msg):
    assert _cls("json", body) == (cls, msg)


def test_a_json_defect_is_an_error():
    cls, msg = _cls("json", '{\n  "id": "x",\n  "queue" "y"\n}\n')
    assert cls == "error" and msg.startswith("Expecting ':' delimiter: line 3")
    assert _cls("json", '{"a": [1}\n')[0] == "error"  # crossed brackets are no cut
    assert _cls("json", '{"a": 1}\n{"b": \n')[0] == "fragment"  # still a cut: "{" never closed


def test_json_nested_too_deep_is_a_cut_not_a_crash():
    cls, msg = _cls("json", "[" * 100_000)
    assert cls == "fragment" and msg.startswith("a cut excerpt: unclosed '['")


def test_a_number_over_the_digit_limit_is_an_error_not_a_crash():
    digits = "1" * 5000
    for tag, body in [("json", digits), ("toml", f"x = {digits}\n"), ("python", f"x = {digits}\n")]:
        cls, msg = _cls(tag, body)
        assert cls == "error" and "Exceeds the limit" in msg, tag
    # The second document crashed raw_decode, which only the several-documents test reads.
    cls, msg = _cls("json", '{"a": 1}\n' + digits)
    assert cls == "error" and msg.startswith("Extra data")


def test_an_ellipsis_inside_a_json_string_is_no_elision():
    cls, msg = _cls("json", '{"a": "Loading..." "b": 1}\n')
    assert cls == "error" and msg.startswith("Expecting ',' delimiter")
    assert _cls("json", f'{{"a": "Wait{ELLIPSIS}" "b": 1}}\n')[0] == "error"
    assert _cls("json", '{"a": "x...", ...}\n') == ("fragment", "an elision")


def test_toml_is_checked():
    assert _cls("toml", '[tool]\nname = "x"\n') == ("ok", None)
    cls, msg = _cls("toml", "[tool\n")
    assert cls == "error" and "line 1" in msg


def test_xml_is_checked_and_several_top_level_elements_are_a_fragment():
    assert _cls("xml", "<a><b/></a>\n") == ("ok", None)
    assert _cls("xml", "<groupId>x</groupId>\n<version>1</version>\n") == (
        "fragment",
        "several top-level elements",
    )
    cls, msg = _cls("xml", "<outer>\n  <sub>\n    <inner>\n  </sub>\n</outer>\n")
    assert cls == "error" and "mismatched tag" in msg


def test_xml_with_no_element_at_all_is_an_error_not_a_fragment():
    cls, msg = _cls("xml", "mvn clean install\n")
    assert cls == "error" and "syntax error" in msg


# --- report and summary --------------------------------------------------------------------------


def _checked(files):
    found = _scan(files)
    return found, [listings.check(x.lang, x.body) for x in found]


def test_report_counts_blocks_by_language_and_chapter_without_check():
    found = _scan({"01-basics.md": CH1, "02-classes.md": CH2})
    rep = listings.report(found, None)
    assert rep["blocks"] == 5 and rep["captions"] == 2
    assert rep["languages"] == {"python": 1, "go": 1, "(none)": 1, "javascript": 1, "json": 1}
    assert rep["chapters"] == {"01-basics.md": 3, "02-classes.md": 2}
    assert "classes" not in rep and "findings" not in rep


def test_report_with_check_counts_classes_and_lists_errors_and_wrong_languages():
    md = (
        "```python\nprint(1)\n```\n\n```python\nclass A {\n  m() { console.log(1); }\n}\n```\n\n"
        f"```python\nprint({RSQUO}x{RSQUO})\n```\n\n```go\nfunc f() {{\n```\n\n```text\nx\n```\n"
    )
    found, checks = _checked({"c.md": md})
    rep = listings.report(found, checks)
    assert rep["checked"] == 4  # the text block has no check
    assert rep["classes"] == {
        "python": {"ok": 1, "wrong-language?": 1, "error": 1},
        "go": {"fragment": 1},
    }
    assert [(f["line"], f["class"]) for f in rep["findings"]] == [
        (5, "wrong-language?"),
        (11, "error"),
    ]
    text = "\n".join(listings.summary_lines(rep))
    assert "check: 4 blocks in a checked language" in text
    assert "  python           ok 1  wrong-language? 1  error 1" in text
    assert "c.md:5 python wrong-language?: parses as javascript" in text


def test_summary_without_findings_or_check():
    found, checks = _checked({"c.md": "```python\nx = 1\n```\n"})
    text = "\n".join(listings.summary_lines(listings.report(found, checks)))
    assert "error and wrong-language? blocks:" not in text
    text = "\n".join(listings.summary_lines(listings.report(found, None)))
    assert text.startswith("listings: 1 code blocks in 1 chapter files, 0 with a Listing caption")
    assert "check:" not in text


# --- export --------------------------------------------------------------------------------------


def test_export_writes_each_block_and_an_index(tmp_path):
    found = _scan({"01-basics.md": CH1, "02-classes.md": CH2})
    out = tmp_path / "out"
    assert listings.export(found, str(out), None) == 5
    assert sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()) == [
        "01-basics/01-listing-1-1.py",
        "01-basics/02.go",
        "01-basics/03.txt",
        "02-classes/01-listing-2-1.js",
        "02-classes/02.json",
        "index.json",
    ]
    assert (out / "01-basics/01-listing-1-1.py").read_bytes() == b"print('hi')\n"
    index = json.loads((out / "index.json").read_text(encoding="utf-8"))
    assert index[0] == {
        "chapter": "01-basics.md",
        "line": 11,
        "lang": "python",
        "caption": "Listing 1.1 The first program",
        "path": "01-basics/01-listing-1-1.py",
    }


def test_export_keeps_the_body_bytes_and_numbers_wide_chapters_with_more_digits(tmp_path):
    md = "".join(f"```text\nblock {i} {RSQUO}\r\n```\n\n" for i in range(100)) + "```c\n```\n"
    found = _scan({"big.md": md})
    out = tmp_path / "out"
    listings.export(found, str(out), [listings.check(x.lang, x.body) for x in found])
    assert (out / "big/001.txt").read_bytes() == f"block 0 {RSQUO}\r\n".encode()
    assert (out / "big/101.c").read_bytes() == b""  # an empty block is an empty file
    index = json.loads((out / "index.json").read_text(encoding="utf-8"))
    assert index[0]["check"] == {"class": "not-checked", "message": None}
    assert index[100]["check"] == {"class": "ok", "message": None}


def test_export_refuses_a_directory_that_is_not_empty_or_a_file(tmp_path):
    found = _scan({"c.md": "```text\nx\n```\n"})
    full = tmp_path / "full"
    full.mkdir()
    (full / "keep.txt").write_text("mine")
    with pytest.raises(listings.OutDirError, match="is not empty"):
        listings.export(found, str(full), None)
    assert [p.name for p in full.iterdir()] == ["keep.txt"]
    afile = tmp_path / "afile"
    afile.write_text("x")
    with pytest.raises(listings.OutDirError, match="is not a directory"):
        listings.export(found, str(afile), None)
    empty = tmp_path / "empty"
    empty.mkdir()
    assert listings.export(found, str(empty), None) == 1


# --- the command ---------------------------------------------------------------------------------


def test_listings_reports_counts_and_changes_nothing(tmp_path, capsys):
    d = _book(tmp_path)
    before = {p.name: p.read_bytes() for p in d.iterdir()}
    assert cli.main(["listings", str(d)]) == 0
    assert {p.name: p.read_bytes() for p in d.iterdir()} == before
    out = capsys.readouterr().out
    assert "listings: 5 code blocks in 2 chapter files, 2 with a Listing caption" in out
    assert "check:" not in out  # the index page is no chapter file: its block is not counted


def test_listings_check_exits_0_even_with_errors(tmp_path, capsys):
    d = _book(tmp_path)
    (d / "03-bad.md").write_text(chap(3, f"```python\nprint({RSQUO}x{RSQUO})\n```\n"))
    assert cli.main(["listings", str(d), "--check"]) == 0
    out = capsys.readouterr().out
    assert "03-bad.md:6 python error: invalid character" in out


def test_listings_out_check_json(tmp_path, capsys):
    d = _book(tmp_path)
    out = tmp_path / "exported"
    assert cli.main(["listings", str(d), "--out", str(out), "--check", "--json"]) == 0
    rep = json.loads(capsys.readouterr().out)
    assert rep["written"] == 5 and rep["out"] == str(out)
    assert rep["classes"]["go"] == {"fragment": 1}
    assert json.loads((out / "index.json").read_text())[1]["check"]["class"] == "fragment"


def test_listings_out_writes_lf_line_ends_for_a_crlf_chapter(tmp_path, capsys):
    d = tmp_path / "book"
    d.mkdir()
    (d / "01-a.md").write_bytes(chap(1, "```go\nf()\ng()\n```\n").replace("\n", "\r\n").encode())
    out = tmp_path / "exported"
    assert cli.main(["listings", str(d), "--out", str(out)]) == 0
    assert (out / "01-a" / "01.go").read_bytes() == b"f()\ng()\n"


def test_listings_out_text_names_the_directory(tmp_path, capsys):
    d = _book(tmp_path)
    out = tmp_path / "exported"
    assert cli.main(["listings", str(d), "--out", str(out)]) == 0
    assert f"wrote 5 files and index.json to {out}" in capsys.readouterr().out


def test_listings_refuses_a_full_out_dir_and_a_folder_with_no_chapter(tmp_path, capsys):
    d = _book(tmp_path)
    assert cli.main(["listings", str(d), "--out", str(d)]) == 2
    assert "is not empty" in capsys.readouterr().err
    empty = tmp_path / "none"
    empty.mkdir()
    assert cli.main(["listings", str(empty)]) == 2
    assert "holds no chapter file" in capsys.readouterr().err
