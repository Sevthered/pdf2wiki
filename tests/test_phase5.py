# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Golden-file style tests for the Phase 5 fixers. All fixtures are synthetic."""

import os
import sys
import textwrap

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pdf2wiki.phase5 import (
    caption_unbleed,
    chapter_split,
    code_unescape,
    dash_normalize,
    illegal_codepoints,
    lang_retag,
    mermaid_repair,
    symbol_pua,
)

# ---------- caption_unbleed ----------


def test_caption_only_fence_unwrapped():
    md = textwrap.dedent("""\
        Some prose.

        ```text
        Listing 1.2 Widget.java: a sample widget
        ```

        ```java
        public class Widget {}
        ```
        """)
    out, changes = caption_unbleed.unbleed(md)
    assert "**Listing 1.2** Widget.java: a sample widget" in out
    assert "```text" not in out
    assert "public class Widget {}" in out  # real code untouched
    assert changes == ["Listing 1.2"]


def test_caption_plus_code_lifts_caption_keeps_code():
    md = "```java\nListing 2.1 Foo.java: foo\npublic class Foo {}\n```\n"
    out, changes = caption_unbleed.unbleed(md)
    assert out.startswith("**Listing 2.1** Foo.java: foo\n\n```java\n")
    assert "public class Foo {}" in out
    assert changes == ["Listing 2.1"]


def test_mermaid_and_plain_fences_untouched():
    md = "```mermaid\nFigure 1.1 not a caption\ngraph TD\n```\n\n```python\nx = 1\n```\n"
    out, changes = caption_unbleed.unbleed(md)
    assert out == md
    assert changes == []


def test_unbleed_idempotent():
    md = "```text\nFigure 3.4 An architecture diagram\n```\n"
    once, _ = caption_unbleed.unbleed(md)
    twice, changes = caption_unbleed.unbleed(once)
    assert once == twice and changes == []


# ---------- lang_retag ----------


def test_file_hint_wins():
    md = '```text\n# file: app.py\nprint("hi")\n```\n'
    out, changes, stats = lang_retag.retag(md)
    assert "```python" in out
    assert stats["ext"] == 1


def test_specific_tag_kept():
    md = "```ruby\nputs 'hi'\n```\n"
    out, changes, stats = lang_retag.retag(md)
    assert "```ruby" in out
    assert stats["kept"] == 1


def test_java_detected_not_python():
    md = "```code\nimport java.util.List;\npublic class A {}\n```\n"
    out, changes, stats = lang_retag.retag(md)
    assert "```java" in out


def test_bare_fence_yaml_k8s():
    md = "```\napiVersion: v1\nkind: Pod\n```\n"
    out, _, _ = lang_retag.retag(md)
    assert "```yaml" in out


def test_mermaid_never_retagged():
    md = "```mermaid\ngraph TD\nA-->B\n```\n"
    out, changes, _ = lang_retag.retag(md)
    assert out == md and changes == []


# ---------- lang_retag: the curly-brace / compiled families ----------
# Every snippet is the shape MinerU emits for these books: an untagged fence, no `# file:` hint.
# `rust` and `typescript` have no ground truth in the reference vault (no such book is converted
# yet), so these cases are the only coverage they have.

CPP_CLASS = """\
#include <vector>

class Widget {
public:
    void draw();
};
"""
CPP_NO_INCLUDE = "Widget w = make_widget();\nstd::vector<int> v = {1, 2, 3};\n"
C_SOURCE = '#include <stdio.h>\n\nint main(void) {\n    printf("hi\\n");\n    return 0;\n}\n'
CMAKE_SCRIPT = """\
cmake_minimum_required(VERSION 3.20)
project(demo LANGUAGES CXX)
add_executable(demo main.cpp)
target_compile_features(demo PRIVATE cxx_std_20)
"""
RUST_FN = """\
use std::collections::HashMap;

#[derive(Debug)]
pub struct Config {
    pub retries: u32,
}

fn main() {
    let mut counts: HashMap<&str, u32> = HashMap::new();
    println!("{:?}", counts);
}
"""
GO_SOURCE = """\
package main

import "fmt"

func main() {
    v, err := load("x")
    if err != nil {
        fmt.Println(err)
    }
}
"""
JS_SOURCE = """\
const fs = require("fs");

function load(name) {
    return fs.readFileSync(name).toString();
}

[1, 2].forEach((n) => console.log(n));
"""
TS_SOURCE = """\
export interface User {
    id: number;
    name: string;
}

export function greet(u: User): string {
    return `hi ${u.name}`;
}
"""
JAVA_INTERFACE = """\
public interface DeleteServiceFacade {
    boolean deleteAStock(String investorId, String symbol);
}
"""


def tag(body: str) -> str:
    return lang_retag.heuristic(body)


def test_cpp_class_not_python():
    assert tag(CPP_CLASS) == "cpp"


def test_cpp_without_include_not_java():
    assert tag(CPP_NO_INCLUDE) == "cpp"


def test_c_source_split_from_cpp():
    assert tag(C_SOURCE) == "c"


def test_cmake_script():
    assert tag(CMAKE_SCRIPT) == "cmake"


def test_rust_source():
    assert tag(RUST_FN) == "rust"


def test_go_source_not_python():
    assert tag(GO_SOURCE) == "go"


def test_javascript_source():
    assert tag(JS_SOURCE) == "javascript"


def test_typescript_source():
    assert tag(TS_SOURCE) == "typescript"


def test_untagged_fence_gets_the_new_language():
    md = f"```\n{GO_SOURCE}```\n"
    out, changes, stats = lang_retag.retag(md)
    assert "```go" in out
    assert stats["kw"] == 1


def test_c_plus_plus_info_string_is_kept_not_re_detected():
    md = "```c++\nint x = 1;\n```\n"
    out, _, stats = lang_retag.retag(md)
    assert "```cpp" in out and stats["kept"] == 1


# ---------- lang_retag: the families the new branches must NOT steal ----------


def test_java_interface_stays_java():
    assert tag(JAVA_INTERFACE) == "java"


def test_java_new_and_fluent_api_stay_java():
    body = """\
@Test
void testTimeout() {
    RestTemplate t = new RestTemplate();
    given().contentType(ContentType.JSON).get("/balance").then().statusCode(504);
}
"""
    assert tag(body) == "java"


def test_ruby_hashrocket_is_not_an_arrow_function():
    assert tag("config = { :retries => 3 }\nputs config\n") == "ruby"


def test_openapi_yaml_type_string_is_not_a_typescript_annotation():
    body = """\
Book:
  type: object
  required: [author, title]
  properties:
    title:  { type: string }
    author: { type: string }
"""
    assert tag(body) == "yaml"


def test_go_test_console_divider_is_not_strict_equality():
    body = "go test -v\n=== RUN   TestSum\n--- PASS: TestSum (0.00s)\nPASS\n"
    assert tag(body) == "bash"


def test_sql_create_table_not_c():
    assert tag("create table events (\n  id bigint,\n  payload text NULL\n);\n") == "sql"


def test_makefile_not_go_despite_colon_equals():
    body = "ARCH ?= avr\nMCU := atmega2560\n\nall: $(TARGET)\n\tavr-gcc -o $@ $<\n"
    assert tag(body) == "makefile"


def test_go_variable_with_capital_name_is_not_a_makefile():
    body = "func TestGetter(t *testing.T) {\n    ID := 1234\n    defer teardown(ID)\n}\n"
    assert tag(body) == "go"


def test_vhdl_assignment_operator_is_not_go():
    body = (
        "architecture arch of FleaFPGA is\n"
        "    signal clk_dvi : std_logic := '0';\n"
        "begin\n"
        "end arch;\n"
    )
    assert tag(body) != "go"


def test_go_assignment_survives_the_vhdl_guard():
    assert tag("serialized := serializeRequest(r)\nlog.Print(serialized)\n") == "go"


def test_shell_install_function_is_not_cmake():
    body = "install() {\n    cp -v build/myapp /usr/local/bin/myapp\n}\n"
    assert tag(body) != "cmake"


def test_cmake_install_with_a_keyword_argument_is_cmake():
    assert tag("install(TARGETS demo DESTINATION bin)\n") == "cmake"


def test_shell_verbs_for_the_new_toolchains():
    assert tag("cargo build --release\ncargo test\n") == "bash"
    assert tag("cmake -S . -B build\ncmake --build build\n") == "bash"
    assert tag("go build ./...\n") == "bash"


def test_html_page_with_inline_script_is_html():
    body = '<!DOCTYPE html>\n<html>\n<body>\n<script>\nconsole.log("hi");\n</script>\n</body>\n</html>\n'
    assert tag(body) == "html"


# ---------- lang_retag: overclaim guards (found reviewing PR #43/#44 against their own diffs) ----------
# Session-22 added the brace-family branches; each of these overclaimed blocks that already had a
# correct home. All priced against the 1674-page reference vault before landing: 0 BROKEN.


def test_bare_enum_is_not_typescript():
    # A bare `enum X {` is Java/C/C++/Rust far more often than TS in this corpus (TS_STRONG used to
    # exempt `enum` from its own export-required rule).
    assert tag("enum Suit {\n    HEARTS, SPADES;\n}\n") != "typescript"
    assert tag("enum State {\n    IDLE,\n    RUNNING\n};\n") != "typescript"


def test_exported_enum_is_still_typescript():
    assert tag("export enum Suit {\n  Hearts, Spades\n}\n") == "typescript"


def test_comment_starting_define_or_include_is_not_c():
    # `#\s*define`/`#\s*include` matched an ordinary comment whose first word happened to be
    # "define"/"include" -- the directive must be glued to `#`, and `#include` needs the real
    # `<...>`/`"..."` header syntax.
    assert tag("# define a helper\ndef square(n):\n    return n * n\n") == "python"
    assert tag("# include the sidecar\nservices:\n  web:\n    image: nginx\n") == "yaml"


def test_real_preprocessor_directives_still_match_c():
    assert tag("#include <stdio.h>\nint main() { return 0; }\n") == "c"
    assert tag("#define MAX 100\nint x = MAX;\n") == "c"


def test_language_keyword_target_line_is_not_makefile():
    # `else:`/`default:` followed by a TAB-indented body matched the Make target-plus-recipe
    # pattern, which needs only a bare colon-terminated token. Neither snippet carries another
    # signal strong enough to name its real language (no `def`/`func`/`package`), so `text` --
    # not `makefile` -- is the correct result; that's the defect this guards against.
    assert tag('for i in range(3):\n\tprint(i)\nelse:\n\tprint("done")\n') != "makefile"
    assert tag('switch v {\ncase 1:\n\treturn "one"\ndefault:\n\treturn "other"\n}\n') != "makefile"


def test_language_keyword_target_line_with_a_real_signal_is_still_detected():
    # Once the block carries its own language signal, the keyword guard doesn't interfere.
    assert tag("def square(n):\n    return n * n\nelse:\n\tpass\n") == "python"


def test_ordinary_target_line_is_still_makefile():
    assert tag("build:\n\tgcc -o out main.c\n") == "makefile"


def test_basename_call_is_not_makefile():
    # `$(basename "$0")` is a POSIX coreutils idiom as much as a Make function call.
    assert tag("#!/bin/bash\nDIR=$(basename $0)\nchmod +x $DIR\n") == "bash"


def test_make_builtin_functions_still_match_makefile():
    assert tag("SRC := $(wildcard *.c)\nOBJ := $(patsubst %.c,%.o,$(SRC))\n") == "makefile"


def test_xml_prolog_is_not_html():
    # The html gate's element-name list overlaps non-HTML XML vocabularies (Atom `<link>`, DocBook
    # `<table>`); a leading `<?xml` must win first.
    body = '<?xml version="1.0"?>\n<feed>\n  <entry><title>t</title><link href="/a"/></entry>\n</feed>\n'
    assert tag(body) == "xml"


def test_javascript_building_markup_in_a_string_stays_javascript():
    body = 'function build() {\n    let html = "<h1>Friends</h1><table>";\n    return html;\n}\n'
    assert tag(body) == "javascript"


def test_pseudocode_arrow_beats_the_brace_families():
    body = "function initFilter(server, minSize)\n    contactsList ← server.loadContacts()\n"
    assert tag(body) == "pseudocode"


def test_source_block_ending_with_a_printed_prompt_line_is_source():
    body = 'func main() {\n    fmt.Println("hi")\n}\n$ {"Number":5}\n'
    assert tag(body) == "go"


def test_block_opening_with_a_prompt_is_a_shell_session():
    body = "$ diff a.go b.go\n13c13\n< temp, err := strconv.Atoi(arg)\n"
    assert tag(body) == "bash"


# ---------- dash_normalize ----------


def test_endash_flag_fixed_in_code_only():
    md = "prose with – dash stays\n\n```bash\nuv add –dev pytest\n```\n"
    out, changes = dash_normalize.normalize(md)
    assert "uv add --dev pytest" in out
    assert "prose with – dash stays" in out
    assert len(changes) == 1


def test_unicode_minus_fixed():
    md = "```python\nx = 5 − 3\n```\n"
    out, changes = dash_normalize.normalize(md)
    assert "x = 5 - 3" in out


# ---------- mermaid_repair ----------


def test_mermaid_quotes_and_brackets_sanitized():
    md = '```mermaid\ngraph TD\nA["{"key": "value"}"] --> B\n```\n'
    out, stats = mermaid_repair.repair(md)
    assert stats["score_after"] <= stats["score_before"]
    assert "&quot;" not in out


def test_mermaid_literal_newline_to_br():
    md = '```mermaid\ngraph TD\nA["line1\\nline2"] --> B\n```\n'
    out, stats = mermaid_repair.repair(md)
    assert "\\n" not in out.replace("```mermaid\n", "")
    assert "<br>" in out


def test_non_mermaid_untouched_by_repair():
    md = '```python\ns = "a\\nb"\n```\n'
    out, stats = mermaid_repair.repair(md)
    assert out == md and stats["blocks_changed"] == 0


# The unclosed-label branch of `_fix_segment` (`OPEN_ONLY`) was reached only when a hypothesis draw
# in test_phase5_properties happened to generate one. Six identical coverage runs gave two different
# totals because of it. These cases reach it on purpose, one per bracket shape, so the closer is
# proven to MATCH the opener and not assumed.
@pytest.mark.parametrize(
    ("opener", "closer"),
    [("[", "]"), ("{", "}"), ("(", ")")],
)
def test_mermaid_unclosed_label_is_closed_with_matching_bracket(opener, closer):
    md = f'```mermaid\ngraph TD\nA{opener}"never closed --> B\n```\n'
    out, stats = mermaid_repair.repair(md)
    assert f'A{opener}"never closed"{closer} --> B' in out
    assert stats["blocks_changed"] == 1
    assert stats["score_before"] > 0 and stats["score_after"] == 0


def test_mermaid_unclosed_label_with_single_quote_opener():
    # `OPEN_ONLY` also accepts a mismatched `'` opener; the output normalises it to `"`.
    md = "```mermaid\ngraph TD\nA['half quoted --> B\n```\n"
    out, _ = mermaid_repair.repair(md)
    assert 'A["half quoted"] --> B' in out


def test_mermaid_unclosed_label_repair_is_idempotent():
    md = '```mermaid\ngraph TD\nA["open --> B{"also open\n```\n'
    once, s1 = mermaid_repair.repair(md)
    twice, s2 = mermaid_repair.repair(once)
    assert once == twice
    assert s1["blocks_changed"] == 1 and s2["blocks_changed"] == 0


def test_clean_mermaid_block_reports_no_change():
    md = '```mermaid\ngraph TD\nA["ok"] --> B\n```\n'
    out, stats = mermaid_repair.repair(md)
    assert out == md
    assert stats == {"blocks_changed": 0, "score_before": 0, "score_after": 0}


# ---------- code_unescape ----------


def test_code_unescape_strips_markdown_punct_in_code():
    md = "```bash\n\\$ go run \\*main.go\n```\n"
    out, changes = code_unescape.unescape(md)
    assert "$ go run *main.go" in out
    assert len(changes) == 1


def test_code_unescape_keeps_real_escapes():
    # \n \t \d \s \" and escaped-backslash must survive
    md = '```go\nfmt.Printf("%d\\n\\t", x)\nr := regexp.MustCompile("[^\\\\s]+\\\\d")\n```\n'
    out, _ = code_unescape.unescape(md)
    assert "%d\\n\\t" in out
    assert "[^\\\\s]+\\\\d" in out


def test_code_unescape_leaves_regex_metachars():
    # \. \( \[ are real regex escapes -> untouched
    md = "```python\nre.match(r'a\\.b\\(c\\)', s)\n```\n"
    out, changes = code_unescape.unescape(md)
    assert "a\\.b\\(c\\)" in out
    assert changes == []


def test_code_unescape_prose_untouched():
    md = "cost was US\\$4.24 million and a \\* footnote\n\n```sh\n\\$ ls\n```\n"
    out, _ = code_unescape.unescape(md)
    assert "US\\$4.24" in out  # prose escape kept
    assert "$ ls" in out  # code escape stripped


def test_code_unescape_skips_mermaid():
    md = "```mermaid\ngraph TD\nA[\\$x] --> B\n```\n"
    out, changes = code_unescape.unescape(md)
    assert out == md and changes == []


def test_code_unescape_idempotent():
    md = "```bash\n\\$ echo \\~/path \\*\n```\n"
    once, _ = code_unescape.unescape(md)
    twice, changes = code_unescape.unescape(once)
    assert once == twice and changes == []


# ---------- chapter_split ----------


def _write(tmp_path, content):
    p = tmp_path / "book.md"
    p.write_text(content)
    return str(p)


def test_split_basic(tmp_path):
    md = _write(tmp_path, "preface text\n\n# Chapter One\nbody1\n\n# Chapter Two\nbody2\n")
    written, bounds = chapter_split.split(md, "testbook", out_dir=str(tmp_path / "ch"))
    names = [os.path.basename(p) for p in written]
    assert names == ["00-front-matter.md", "01-chapter-one.md", "02-chapter-two.md"]
    ch1 = (tmp_path / "ch" / "01-chapter-one.md").read_text()
    assert ch1.startswith("---\n")
    assert 'book: "testbook"' in ch1  # json.dumps -> quoted YAML scalar
    assert "# Chapter One" in ch1


def test_split_frontmatter_is_valid_yaml_with_hostile_title(tmp_path):
    # repr()/raw interpolation emitted invalid YAML on mixed quotes, backslashes, and a
    # source filename with `: ` or a leading flow char. json.dumps always yields a valid scalar.
    md = _write(tmp_path, 'preface\n\n# It\'s a "test": C:\\path & [x]\nbody\n')
    chapter_split.split(
        md, "book: with colon", out_dir=str(tmp_path / "ch"), source_name="[weird]: file #1.pdf"
    )
    ch1 = (tmp_path / "ch" / "01-its-a-test-cpath-x.md").read_text()
    fm = ch1.split("---\n")[1]
    try:
        import yaml  # if PyYAML present, prove it round-trips
    except ImportError:
        assert 'title: "' in fm and 'source: "' in fm
        return
    meta = yaml.safe_load(fm)
    assert meta["title"] == 'It\'s a "test": C:\\path & [x]'
    assert meta["book"] == "book: with colon"
    assert meta["source"] == "[weird]: file #1.pdf"


def test_split_fence_aware(tmp_path):
    md = _write(tmp_path, "# Real Chapter\n```python\n# file: not_a_chapter.py\nx=1\n```\n")
    _, bounds = chapter_split.split(md, "b", out_dir=str(tmp_path / "ch"))
    assert len(bounds) == 1


def test_split_appendix_h2_promoted(tmp_path):
    md = _write(tmp_path, "# Chapter One\nbody\n\n## Appendix A. Extra stuff\nappendix body\n")
    written, bounds = chapter_split.split(md, "b", out_dir=str(tmp_path / "ch"))
    assert len(bounds) == 2
    appendix = (tmp_path / "ch" / "02-appendix-a-extra-stuff.md").read_text()
    assert "# Appendix A. Extra stuff" in appendix  # normalized to H1


def test_split_dry_run_writes_nothing(tmp_path):
    md = _write(tmp_path, "# C1\nbody\n")
    written, _ = chapter_split.split(md, "b", out_dir=str(tmp_path / "ch"), dry_run=True)
    assert written and not (tmp_path / "ch").exists()


def test_split_no_boundaries_raises(tmp_path):
    md = _write(tmp_path, "just prose, no headings\n")
    try:
        chapter_split.split(md, "b")
        assert False, "expected NoBoundariesError"
    except chapter_split.NoBoundariesError:
        pass


# ---------- symbol_pua ----------
# Fixtures use the exact shapes found in the corpus; each is annotated with the source page that
# was rendered to confirm what the book actually prints (see bug-symbol-font-pua-glyphs-dropped).

PI, SIGMA, ARROW, BULLET = "\uf070", "\uf0e5", "\uf0ae", "\uf0a1"
DIAMOND = "\uf077"  # Wingdings diamond, Advanced Algorithms p494; omega in Adobe Symbol encoding
DOT = symbol_pua.DOT  # verified inline in one book, printed as a bullet in another
SYMBOL_SPACE = symbol_pua.SPACE


def test_pua_inline_symbols_remapped():
    # Math for Programmers p504 prints "or 2π radians ... every 2π units".
    md = f"if you rotate 360 degrees or 2{PI} radians, every 2{PI} units\n"
    out, stats = symbol_pua.remap(md)
    assert out == "if you rotate 360 degrees or 2π radians, every 2π units\n"
    assert stats["remap_f070"] == 2
    assert stats["unknown"] == {}


def test_pua_sigma_is_capital_sigma_not_summation():
    # U+F0E5 is Adobe Symbol's SUMMATION slot, but Advanced Algorithms p209 prints capital Sigma.
    md = f"given an alphabet {SIGMA} with |{SIGMA}|=k symbols\n"
    out, _ = symbol_pua.remap(md)
    assert out == "given an alphabet Σ with |Σ|=k symbols\n"
    assert "∑" not in out  # NOT the summation sign


def test_pua_arrow_remapped():
    # Microservices Patterns p440.
    md = f"becomes Service {ARROW} Source Envoy {ARROW} Destination Envoy\n"
    out, _ = symbol_pua.remap(md)
    assert out == "becomes Service → Source Envoy → Destination Envoy\n"


def test_pua_math_greek_letters_remapped():
    # Math for Programmers: the book names the letter it prints, so the page is its own ground
    # truth -- p87 theta, p120 phi, p480 alpha, p654 lambda. Written as escapes: a literal PUA
    # character is invisible in this file too.
    md = (
        "the sine and cosine of an angle \uf071 (the Greek letter theta)\n"
        "we label it with the Greek letter \uf066 (phi)\n"
        "where \uf061 (the Greek letter alpha) is a number giving the magnitude of drag\n"
        "comes from the Greek letter \uf06c, written lambda\n"
    )
    out, stats = symbol_pua.remap(md)
    assert out == (
        "the sine and cosine of an angle θ (the Greek letter theta)\n"
        "we label it with the Greek letter φ (phi)\n"
        "where α (the Greek letter alpha) is a number giving the magnitude of drag\n"
        "comes from the Greek letter λ, written lambda\n"
    )
    assert stats["unknown"] == {}


def test_pua_math_operators_remapped():
    # Math for Programmers p211 (x), p182 (!=), p444 (identical-to), p86 (approx), p446 (nabla).
    md = (
        "as in a 3\uf0b43 matrix or a 3\uf0b41 matrix\n"
        "and T(0) \uf0b9 0, where 0 represents the vector\n"
        "I use the \uf0ba sign to indicate that these notations are equivalent\n"
        "tan(37 degrees) \uf0bb 3/4\n"
        "its gradient and written \uf0d1U\n"
    )
    out, stats = symbol_pua.remap(md)
    assert out == (
        "as in a 3×3 matrix or a 3×1 matrix\n"
        "and T(0) ≠ 0, where 0 represents the vector\n"
        "I use the ≡ sign to indicate that these notations are equivalent\n"
        "tan(37 degrees) ≈ 3/4\n"
        "its gradient and written ∇U\n"
    )
    assert stats["unknown"] == {}


def test_pua_two_codepoints_print_the_same_dot():
    # p80 sets the dot at 4 pt (U+F0B7) and p133 at 10 pt (U+F0D7); both print a centered
    # multiplication dot, so both map to MIDDLE DOT -- a mapping that only rendering both pages
    # produces, since the two codepoints sit in different slots of the font's encoding.
    md = "points where r\uf0b7u + s\uf0b7v, and its length is sqrt(a\uf0d7a + b\uf0d7b)\n"
    out, stats = symbol_pua.remap(md)
    assert out == "points where r·u + s·v, and its length is sqrt(a·a + b·b)\n"
    assert stats["remap_f0b7"] == 2
    assert stats["remap_f0d7"] == 2


def test_pua_symbol_font_parens_and_space_are_restored():
    # Math for Programmers p118 sets the parentheses of a radical in Symbol; p677's index line sets
    # the space after the pi. Dropping either silently rewrites the expression.
    md = "has length sqrt\uf0284^2 + 3^2\uf029 = sqrt25\n\uf070\uf020(pi) symbol 56\n"
    out, stats = symbol_pua.remap(md)
    assert out == "has length sqrt(4^2 + 3^2) = sqrt25\nπ (pi) symbol 56\n"
    assert stats["unknown"] == {}


def test_pua_checkmark_and_infinity_from_blockchain_book():
    # Mastering Blockchain p511 prints a check mark in a terminal transcript, p699 an infinity sign
    # used as a footnote marker.
    md = "\uf0fc Preparing to download box\n\uf0a5 TPS results for Hyperledger Fabric\n"
    out, stats = symbol_pua.remap(md)
    assert out == "✓ Preparing to download box\n∞ TPS results for Hyperledger Fabric\n"
    assert stats["unknown"] == {}


def test_pua_line_leading_dot_is_never_interpreted():
    # U+F0B7 is verified INLINE (Math p80, 4 pt, between two vectors). At the start of a line the
    # same glyph is what a publisher template uses for a bullet, and no rendered page in the corpus
    # settles it -- so it must be left alone, not flattened into middle-dot paragraphs.
    md = "\uf0b7 Chunked transfer encoding\n\uf0b7 Server-sent events\n"
    out, stats = symbol_pua.remap(md)
    assert out == md  # untouched — never guess
    assert stats["line_leading_dot_deferred"] == 2
    assert stats["total_changes"] == 0  # a refusal to guess is not a repair
    assert "remap_f0b7" not in stats


def test_pua_inline_dot_still_remapped_on_a_line_that_opens_with_one():
    # The deferral is positional, not a blanket opt-out: the inline dots on the same line are the
    # verified reading and must still be restored.
    md = "\uf0b7 r\uf0b7u + s\uf0b7v\n"
    out, stats = symbol_pua.remap(md)
    assert out == "\uf0b7 r·u + s·v\n"
    assert stats["line_leading_dot_deferred"] == 1
    assert stats["remap_f0b7"] == 2


def test_pua_deferral_applies_at_any_indent():
    """The refusal must not stop applying because a list is nested.

    The list reading carries CommonMark's indent limit, and the deferral copied it. A dot opening
    a line indented four spaces or more was then rewritten to a middle dot and counted as a repair —
    a nested bulleted list flattened into paragraphs, which is the one rewrite this module says it
    must never make.
    """
    for indent in ("", "  ", "    ", "\t", "        "):
        md = f"{indent}{DOT} Chunked transfer encoding\n"
        out, stats = symbol_pua.remap(md)
        assert out == md, repr(indent)
        assert stats["line_leading_dot_deferred"] == 1, repr(indent)
        assert stats["total_changes"] == 0, repr(indent)


def test_pua_report_always_carries_every_documented_key():
    # `remap()` documents these as always present so a caller needs no KeyError guard, and the CRLF
    # refusal returns its own dict, which has to keep the same shape.
    documented = {
        "list_markers",
        "heading_markers",
        "stray_markers",
        "stray_unhandled",
        "line_leading_dot_deferred",
        "line_leading_marker_deferred",
        "dropped_f020",
        "in_code",
        "unknown",
        "total_changes",
        "skipped_crlf",
    }
    for md in ("plain prose with no glyph at all\n", "a\r\nb\n"):
        _, stats = symbol_pua.remap(md)
        assert documented <= set(stats), (md, documented - set(stats))


def test_pua_symbol_space_does_not_defeat_the_bullet_pass():
    # The structural passes test for real whitespace and "\uf020".isspace() is False, so a bullet
    # separated from its text by a Symbol space used to survive into the output as an invisible
    # codepoint with its list item lost. Both books that emit \uf0a1 also emit \uf020.
    md = "\uf0a1\uf020Using built-in Keras training and evaluation loops\n"
    out, stats = symbol_pua.remap(md)
    assert out == "- Using built-in Keras training and evaluation loops\n"
    assert stats["list_markers"] == 1
    assert "\uf0a1" not in out


def test_pua_symbol_space_at_a_line_edge_is_dropped_not_spaced():
    # Two trailing spaces are a CommonMark hard break and a whitespace-only line is a blank line;
    # neither is structure the printed page has. A DELETION is counted apart from a substitution:
    # `remap_f020` would claim the step put a space where the page prints one.
    out, stats = symbol_pua.remap("the value of x\uf020\uf020\nnext line\n")
    assert out == "the value of x\nnext line\n"
    assert stats["dropped_f020"] == 2
    assert "remap_f020" not in stats
    out, stats = symbol_pua.remap("para one\n\uf020\npara two\n")
    assert out == "para one\n\npara two\n"
    assert stats["dropped_f020"] == 1


def test_glyph_table_values_are_never_private_use():
    # A replacement that is itself a PUA codepoint would break the documented "a second pass is a
    # no-op" guarantee and feed an unbounded `unknown` residue, with no other test failing.
    for key, value in symbol_pua.GLYPHS.items():
        assert not any(0xE000 <= ord(c) <= 0xF8FF for c in value), key


def test_pua_every_glyph_is_idempotent_and_fence_scoped():
    # The invariants were only ever exercised against the three original codepoints.
    for key in symbol_pua.GLYPHS:
        if key == symbol_pua.DOT:
            continue  # positional; covered by its own tests above
        md = f"prose {key} here\n\n```text\nliteral {key} inside\n```\n"
        once, _ = symbol_pua.remap(md)
        twice, stats = symbol_pua.remap(once)
        assert once == twice, key
        assert stats["total_changes"] == 0, key
        assert f"literal {key} inside" in once, key  # fence copied byte-for-byte
        assert stats["in_code"] == {f"{ord(key):04x}": 1}, key
        assert stats["unknown"] == {}, key


def test_glyph_table_keys_are_single_private_use_codepoints():
    # A key that is not a lone PUA codepoint cannot be what MinerU carried through, and would make
    # the `unknown` residue -- the signal that asks for a human -- lie.
    for key in symbol_pua.GLYPHS:
        assert len(key) == 1, key
        assert 0xE000 <= ord(key) <= 0xF8FF, key
    assert symbol_pua.BULLET not in symbol_pua.GLYPHS  # structural, handled separately


def test_pua_bullet_becomes_list_item():
    # Deep Learning with Python p197: a "This chapter covers" bulleted list.
    md = f"{BULLET} Using built-in Keras training and evaluation loops\n"
    out, stats = symbol_pua.remap(md)
    assert out == "- Using built-in Keras training and evaluation loops\n"
    assert stats["list_markers"] == 1


def test_pua_bullet_behind_stray_emphasis_opener():
    # Deep Learning with Python p71: MinerU emitted the emphasis opener before the bullet.
    md = f"*{BULLET} Dense layer with relu activation: An important observation\n"
    out, _ = symbol_pua.remap(md)
    assert out == "- Dense layer with relu activation: An important observation\n"


def test_pua_bullet_in_heading_keeps_heading_level():
    # Deep Learning with Python p399 prints these as list items, but the vault already has them as
    # headings; this step must NOT restructure the document, only drop the glyph.
    md = f"## {BULLET} With temperature=0.2\n"
    out, stats = symbol_pua.remap(md)
    assert out == "## With temperature=0.2\n"
    assert stats["heading_markers"] == 1
    assert stats["list_markers"] == 0


def test_pua_code_blocks_are_untouched_and_reported():
    md = f"prose 2{PI} here\n\n```text\n{BULLET} not a list item\n2{PI} literal\n```\n"
    out, stats = symbol_pua.remap(md)
    assert "prose 2π here" in out
    assert f"{BULLET} not a list item" in out  # byte-identical inside the fence
    assert f"2{PI} literal" in out
    # verified glyphs inside a fence are a benign residue, NOT an unknown codepoint
    assert stats["in_code"] == {"f0a1": 1, "f070": 1}
    assert stats["unknown"] == {}


def test_pua_symbol_space_after_a_deferred_dot_is_spaced_not_deleted():
    # The dot opens the line, so the line is deferred -- but the Symbol space that separates it from
    # the first word is still a space, and deleting it edits the very line the deferral leaves alone.
    md = f"{DOT}{SYMBOL_SPACE}Chunked transfer encoding\n"
    out, stats = symbol_pua.remap(md)
    assert out == f"{DOT} Chunked transfer encoding\n"
    assert stats["line_leading_dot_deferred"] == 1
    assert stats["remap_f020"] == 1
    assert "remap_f0b7" not in stats  # the dot itself is never interpreted here


def test_pua_symbol_space_before_a_leading_dot_still_defers():
    # The line-opening reading matches a `[ \t]` indent only, and a Symbol space is neither, so this
    # remap loop and had its dot rewritten. Substituting SPACE first is what makes it a line-opening
    # dot at all.
    md = f"{SYMBOL_SPACE}{DOT} Server-sent events\n"
    out, stats = symbol_pua.remap(md)
    assert out == f"{DOT} Server-sent events\n"  # the edge space is dropped, the dot left alone
    assert stats["line_leading_dot_deferred"] == 1
    assert stats["dropped_f020"] == 1  # a deletion, not "the step wrote a space here"
    assert "remap_f020" not in stats
    assert "remap_f0b7" not in stats


def test_pua_unknown_codepoint_left_alone_and_reported():
    md = "an \uf0ff unverified glyph\n"
    out, stats = symbol_pua.remap(md)
    assert out == md  # untouched — never guess
    assert stats["unknown"] == {"f0ff": 1}
    assert stats["in_code"] == {}


def test_pua_idempotent():
    md = f"{BULLET} item with 2{PI} and {ARROW}\n\n## {BULLET} Heading\n"
    once, _ = symbol_pua.remap(md)
    twice, stats = symbol_pua.remap(once)
    assert once == twice
    assert stats["total_changes"] == 0


def test_pua_clean_document_unchanged():
    md = "Ordinary prose.\n\n- a list\n\n```python\nx = 1\n```\n"
    out, stats = symbol_pua.remap(md)
    assert out == md
    assert stats["total_changes"] == 0


# --- regression tests for the review findings (all reproduced before being fixed) ---


def test_pua_stray_marker_never_joins_words():
    # BLOCKER: `BULLET + [ \t]*` ate the marker AND the only space separating two real words,
    # reporting "word next" -> "wordnext" as a successful fix.
    out, stats = symbol_pua.remap(f"word{BULLET} next\n")
    assert out == "word next\n"
    assert stats["stray_markers"] == 1


def test_pua_stray_marker_flush_between_words_is_left_alone():
    # No safe reading — was it a separator or a decoration? Don't guess; report it.
    md = f"acceptable{BULLET}unacceptable and more text\n"
    out, stats = symbol_pua.remap(md)
    assert out == md  # untouched
    assert stats["stray_unhandled"] == 1
    assert stats["stray_markers"] == 0
    assert stats["total_changes"] == 0  # leaving it in place is not a "change"


def test_pua_isolated_stray_marker_leaves_no_double_space():
    out, _ = symbol_pua.remap(f"before {BULLET} after\n")
    assert out == "before after\n"


def test_pua_double_marker_in_heading_leaves_no_double_space():
    out, _ = symbol_pua.remap(f"## {BULLET} {BULLET} text\n")
    assert out == "## text\n"


def test_pua_crlf_document_is_refused_not_corrupted():
    # fences.blocks() is LF-only, so on CRLF input it reports ZERO blocks and code would be
    # rewritten as prose. Refuse instead.
    md = f"a\r\n```text\r\n{BULLET} not a list item\r\n```\r\n"
    out, stats = symbol_pua.remap(md)
    assert out == md
    assert stats["skipped_crlf"] is True
    assert stats["total_changes"] == 0


def test_pua_glyph_unwrapped_by_caption_unbleed_is_still_remapped():
    # HIGH: symbol_pua runs first and correctly skips a glyph inside a caption-only fence, but
    # caption_unbleed then promotes that fence to prose — leaving a raw PUA byte in permanent text
    # unless the chain re-runs the step.
    md = f"prose\n\n```text\nTable 3.1 alphabet {SIGMA} notation\n```\n\nafter\n"
    once, _ = symbol_pua.remap(md)
    unwrapped, _ = caption_unbleed.unbleed(once)
    assert SIGMA in unwrapped  # the hole the second pass exists to close
    final, stats = symbol_pua.remap(unwrapped)
    assert SIGMA not in final
    assert "alphabet Σ notation" in final


# ---------- illegal_codepoints ----------
# The corpus fixture is *Modern C++ Tutorial* p55: the PDF's own text layer carries two U+FFFF
# noncharacters inside a string literal (a CJK word the font subset failed to encode, printing
# blank), and MinerU's pipeline backend writes them out as raw NUL bytes — verified in its own raw
# chunk output, base_40_79/.../txt/modern-cpp-tutorial.md. See bug-converter-maps-uffff-to-nul.

NUL = chr(0x0000)
NONCHAR_FFFF = chr(0xFFFF)
NONCHAR_FFFE = chr(0xFFFE)
NONCHAR_ARABIC = chr(0xFDD0)  # first of the U+FDD0-U+FDEF block
NONCHAR_PLANE1 = chr(0x1FFFF)  # plane-end pair, SMP


def test_pua_diamond_is_a_second_list_marker():
    # Advanced Algorithms p494 sets a bulleted list in Wingdings, not in the Wingdings2 the Keras
    # book uses, so the marker is a different codepoint printing a filled diamond.
    assert symbol_pua.DIAMOND == DIAMOND and DIAMOND in symbol_pua.BULLETS
    md = f"{DIAMOND} Shard the dataset and send the shards to mappers\n"
    out, stats = symbol_pua.remap(md)
    assert out == "- Shard the dataset and send the shards to mappers\n"
    assert stats["list_markers"] == 1
    assert stats["unknown"] == {}  # it is known now, and structurally


def test_pua_diamond_in_heading_is_kept_because_no_page_verifies_that_reading():
    # The evidence rule is per READING. Advanced Algorithms p494 shows the diamond as a list
    # bullet; no rendered page shows it promoted to a heading, so the heading path leaves it in
    # place and counts it, where the square -- Deep Learning with Python p399 -- loses its glyph.
    md = f"### {DIAMOND} Each mapper assigns points to one of the centroids\n"
    out, stats = symbol_pua.remap(md)
    assert out == md
    assert stats["heading_markers"] == 0 and stats["line_leading_marker_deferred"] == 1
    assert stats["total_changes"] == 0

    # And that is what makes the chain's SECOND pass safe: `# <D> <D> text` keeps both diamonds
    # on pass one, and pass two, which sees `# <D> ` as a heading prefix, keeps them again.
    md = f"# {DIAMOND} {DIAMOND} text\n"
    once, rep1 = symbol_pua.remap(md)
    twice, rep2 = symbol_pua.remap(once)
    assert once == md and twice == md
    assert rep1["line_leading_marker_deferred"] == 1 and rep1["marker_no_reading"] == 1
    assert rep1["total_changes"] == 0 and rep2["total_changes"] == 0


def test_pua_diamond_after_hashes_or_an_opener_is_a_line_opening_refusal_not_a_mid_line_one():
    # `###<D>text` opens the line after hashes, and `**<D> bold` after an opener the list pattern
    # does not accept. Neither is mid-line; the residue has to say so, with the same counter the
    # square raises for the hash case.
    for src in (f"### {DIAMOND}text\n", f"#{DIAMOND}x\n"):
        out, stats = symbol_pua.remap(src)
        assert out == src, src
        assert stats["line_leading_marker_deferred"] == 1 and stats["marker_no_reading"] == 0, src


def test_pua_line_opening_marker_is_not_a_bullet_when_an_operator_follows():
    """Every marker slot is also a Greek letter in Adobe Symbol encoding.

    `0x77` is *omega* and `0xA1` is *Upsilon1*. A book that sets a display formula on its own line
    would otherwise have the letter deleted and the formula turned into a list item, reported as a
    repair -- the failure class this module exists to remove, and the same ambiguity `DOT` defers.
    A bullet introduces text, so a marker followed by an OPERATOR is not read as one. It is left in
    place and counted with the other line-opening refusals.
    """
    pi = "\N{GREEK SMALL LETTER PI}"
    for marker in (DIAMOND, BULLET):
        md = f"{marker} = 2{PI}f is the angular frequency\n"
        out, stats = symbol_pua.remap(md)
        assert out == f"{marker} = 2{pi}f is the angular frequency\n", marker
        assert stats["list_markers"] == 0, marker
        assert stats["line_leading_marker_deferred"] == 1, marker  # left in place AND counted
        assert stats["remap_f070"] == 1, marker  # the verified glyph on the line is still repaired
        assert stats["total_changes"] == 1, marker  # the refusal is not a repair


def test_pua_bullet_before_a_formula_is_still_a_list_item():
    # The guard refuses an OPERATOR, never a formula. Advanced Algorithms p445 prints a Wingdings2
    # square ahead of `d*(n+k)*log(k) < n*k*d ⇔ ...`, a real list item whose text is a formula, and
    # `<`/`>` cost six real bullets in Microservices Patterns when they were in the set.
    for body in ("n*2<sup>d</sup> < n*k*d ⇔ d << k", "<sub>REST</sub> client", "x = 2"):
        out, stats = symbol_pua.remap(f"{BULLET} {body}\n")
        assert out == f"- {body}\n", body
        assert stats["list_markers"] == 1, body


def test_pua_marker_guard_is_not_defeated_by_extra_whitespace():
    """A one-character look past the marker sees a space, and a space is not an operator.

    The guard must read the first character AFTER the gap, whatever the gap's width. An earlier
    regex form of it backtracked to one space and then inspected the second, so two spaces reopened
    it while a one-space test stayed green.
    """
    for gap in ("  ", " \t", "\t ", "   "):
        md = f"{DIAMOND}{gap}= 2x\n"
        out, stats = symbol_pua.remap(md)
        assert out == md, repr(gap)
        assert stats["list_markers"] == 0, repr(gap)
        assert stats["line_leading_marker_deferred"] == 1, repr(gap)

    # A marker with nothing but whitespace after it is an empty list item, which is still one.
    out, stats = symbol_pua.remap(f"{DIAMOND}  \n")
    assert out == "- \n" and stats["list_markers"] == 1


def test_pua_heading_marker_carries_the_same_guard():
    # The heading path deletes the glyph and keeps the heading level, so it destroys a formula the
    # same way the list path would. A marker slot is a Greek letter in a heading too.
    for marker in (DIAMOND, BULLET):
        md = f"### {marker} = 2x\n"
        out, stats = symbol_pua.remap(md)
        assert out == md, marker
        assert stats["heading_markers"] == 0, marker
        assert stats["line_leading_marker_deferred"] == 1, marker

    # ...and a real bulleted heading still loses the VERIFIED marker.
    out, stats = symbol_pua.remap(f"## {BULLET} With temperature=0.2\n")
    assert out == "## With temperature=0.2\n"
    assert stats["heading_markers"] == 1


def test_pua_operator_guard_covers_the_relations_the_table_already_knows():
    # A formula whose Greek first letter is followed by an arrow, a gradient or a relation is the
    # same shape as `= 2x`. `→` is what U+F0AE becomes, and the remap runs first.
    for body in ("→ 2x", f"{ARROW} 2x", "∇f", "≤ 1", "∈ A", "∞"):
        out, stats = symbol_pua.remap(f"{DIAMOND} {body}\n")
        assert stats["list_markers"] == 0 and stats["line_leading_marker_deferred"] == 1, body
        assert out.startswith(DIAMOND), body


def test_pua_bullet_before_an_inline_dot_is_still_a_list_item():
    # `·` is what DOT becomes, and `_remap_line` runs before the positional pass. With `·` in the
    # operator set a verified inline dot after a real bullet refused the list item.
    out, stats = symbol_pua.remap(f"{BULLET} {DOT} x\n")
    assert out == "- · x\n"
    assert stats["list_markers"] == 1 and stats["line_leading_marker_deferred"] == 0


def test_pua_diamond_line_opening_refusals_match_the_square():
    # Too indented, or glued to its text: the same readings as the verified marker, never a deletion.
    for src in (f"    {DIAMOND} nested\n", f"  {DIAMOND}text\n", f"{DIAMOND}text\n"):
        out, stats = symbol_pua.remap(src)
        assert out == src, repr(src)
        assert stats["line_leading_marker_deferred"] == 1, repr(src)
        assert stats["total_changes"] == 0, repr(src)


def test_pua_diamond_mid_line_is_never_deleted():
    """Being a bullet at line START says nothing about the same codepoint mid-sentence.

    U+F077 is *omega* in Adobe Symbol encoding, and the corpus's largest PUA source emits SymbolMT
    lowercase Greek out of that very block (alpha, phi, lambda, pi, theta). Deleting one mid-line
    the way the verified U+F0A1 marker is deleted would turn a codepoint that needs a rendered page
    into a silent deletion, reported as a repair. It is left in place and counted instead -- on
    both sides of the separator-or-flush distinction, which only a strippable marker needs.
    """
    for md in (
        f"the angular velocity {DIAMOND} is measured in rad/s\n",
        f"velocity{DIAMOND}is measured\n",
        f"- item {DIAMOND} text\n",
    ):
        out, stats = symbol_pua.remap(md)
        assert out == md, md  # untouched -- never guess
        assert stats["marker_no_reading"] == 1, md  # its own residue class: render the page
        assert stats["stray_markers"] == 0 and stats["stray_unhandled"] == 0, md
        assert stats["total_changes"] == 0, md  # a refusal is not a repair

    # ...while the verified marker still IS dropped mid-line, whitespace preserved.
    out, stats = symbol_pua.remap(f"before {BULLET} after\n")
    assert out == "before after\n"
    assert stats["stray_markers"] == 1


def test_pua_second_diamond_after_an_opening_one_is_kept():
    # A line opens once. The second marker is read mid-line, and mid-line a diamond has no reading.
    out, stats = symbol_pua.remap(f"{DIAMOND} {DIAMOND} text\n")
    assert out == f"- {DIAMOND} text\n"
    assert stats["list_markers"] == 1 and stats["marker_no_reading"] == 1


def test_pua_diamond_inside_a_fence_is_reported_not_rewritten():
    md = f"prose 2{PI}\n\n```text\n{DIAMOND} not a list item\n```\n"
    out, stats = symbol_pua.remap(md)
    assert "prose 2\N{GREEK SMALL LETTER PI}" in out  # the prose glyph IS remapped
    assert f"{DIAMOND} not a list item" in out  # the fence is copied byte-for-byte
    assert stats["in_code"] == {"f077": 1}
    assert stats["unknown"] == {}


def test_pua_marker_no_reading_reaches_the_operator(tmp_path):
    # A counter no command prints reaches no human. The chain runs `symbol_pua` twice; the residue
    # line takes the high-water mark of the two, like every other refusal.
    from pdf2wiki import phase5

    md = tmp_path / "book.md"
    md.write_text(
        f"# Title\n\nvelocity {DIAMOND} in rad/s, and {DIAMOND} again\n", encoding="utf-8"
    )
    report = phase5.run_chain(str(md), "book")
    lines = phase5.residue_lines(report)
    assert any(ln.startswith("⚠ 2 list-marker codepoint(s) found AWAY FROM") for ln in lines), lines
    assert any("Render the source page" in ln for ln in lines)


def test_illegal_nul_removed_inside_a_code_fence():
    # The real defect: it sits INSIDE a ```cpp fence, which is exactly where symbol_pua refuses to
    # go — so only a step scoped to the whole document can remove it.
    md = f'```cpp\nthrow std::out_of_range("{NUL}{NUL}.");\n```\n'
    out, stats = illegal_codepoints.strip(md)
    assert out == '```cpp\nthrow std::out_of_range(".");\n```\n'
    assert NUL not in out
    assert stats["removed"] == 2
    assert stats["counts"] == {"0000": 2}
    assert stats["word_joins"] == 0  # flanked by `"` and `.`, not by letters


def test_illegal_noncharacters_removed_from_prose():
    md = f"a sentence{NONCHAR_FFFF} with{NONCHAR_FFFE} noncharacters{NONCHAR_ARABIC}\n"
    out, stats = illegal_codepoints.strip(md)
    assert out == "a sentence with noncharacters\n"
    assert stats["counts"] == {"ffff": 1, "fffe": 1, "fdd0": 1}


def test_illegal_plane_end_noncharacter_removed():
    md = f"astral{NONCHAR_PLANE1} text\n"
    out, stats = illegal_codepoints.strip(md)
    assert out == "astral text\n"
    assert stats["counts"] == {"1ffff": 1}


def test_illegal_leaves_legitimate_text_byte_identical():
    md = (
        "# Heading\n\nProse with π, Σ, → and an em-dash — plus CJK 越界.\n\n"
        "```python\nx = '\\u0000 is a literal, not a byte'\n```\n"
    )
    out, stats = illegal_codepoints.strip(md)
    assert out == md
    assert stats["removed"] == 0
    assert stats["counts"] == {}


def test_illegal_does_not_touch_private_use_area():
    # PUA glyphs belong to symbol_pua, whose table is verified against rendered pages. A blanket
    # sanitizer that ate them would silently destroy π/Σ/→ before that step ever ran.
    md = f"rotate 2{PI} radians, alphabet {SIGMA}, {BULLET} bullet\n"
    out, stats = illegal_codepoints.strip(md)
    assert out == md
    assert stats["removed"] == 0


def test_illegal_is_idempotent():
    md = f"one{NUL} two{NONCHAR_FFFF}\n"
    once, _ = illegal_codepoints.strip(md)
    twice, stats = illegal_codepoints.strip(once)
    assert twice == once
    assert stats["removed"] == 0


def test_illegal_counts_a_word_join_so_it_stays_visible():
    # Removing an illegal codepoint between two alphanumerics MERGES two words. It is still the
    # right call (the codepoint is illegal in interchange and prints nothing), but it must be
    # reported, not silent — the same failure class the symbol_pua fix once reintroduced.
    md = f"word{NUL}next and 2{NONCHAR_FFFF}3\n"
    out, stats = illegal_codepoints.strip(md)
    assert out == "wordnext and 23\n"
    assert stats["word_joins"] == 2


def test_illegal_run_of_codepoints_counts_as_one_join():
    md = f"word{NUL}{NUL}{NONCHAR_FFFF}next\n"
    out, stats = illegal_codepoints.strip(md)
    assert out == "wordnext\n"
    assert stats["removed"] == 3
    assert stats["word_joins"] == 1


def test_illegal_works_on_crlf_input():
    # This step is fence-agnostic, so unlike symbol_pua it has no LF-only dependency and must NOT
    # bail on CRLF — it runs before every fence-parsing step precisely so a NUL can never reach one.
    md = f'```cpp\r\nauto s = "{NUL}";\r\n```\r\n'
    out, stats = illegal_codepoints.strip(md)
    assert out == '```cpp\r\nauto s = "";\r\n```\r\n'
    assert stats["removed"] == 1


def test_illegal_handles_codepoint_at_string_edges():
    out, stats = illegal_codepoints.strip(f"{NUL}edge{NUL}")
    assert out == "edge"
    assert stats["removed"] == 2
    assert stats["word_joins"] == 0


def test_a_nested_pua_bullet_is_left_in_place_instead_of_deleted():
    """Shipped in 0.2.8: a PUA bullet indented four spaces or more was DELETED.

    The list and heading readings both carry CommonMark's indent limit, so a nested marker matched
    neither and fell through to the stray-marker branch, where the indent on its left IS
    whitespace. The nested list flattened into continuation text of the parent item, and it was
    counted as `stray_markers` -- the counter for a SUCCESSFUL cleanup -- so no residue counter
    moved and nothing reached the operator. A deletion is not a list-recognition rule.
    """
    src = f"- top level\n    {BULLET} nested one\n    {BULLET} nested two\n"
    assert src.count(BULLET) == 2
    out, rep = symbol_pua.remap(src)

    assert out == src  # not one character changed
    assert rep["line_leading_marker_deferred"] == 2
    assert rep["stray_markers"] == 0
    assert rep["total_changes"] == 0  # a refusal is not an edit


def test_the_marker_refusal_applies_at_every_indent_the_list_pass_declines():
    """Indents 0-3 become real list items. Four and beyond are refused, never deleted."""
    for n in (0, 1, 2, 3):
        out, rep = symbol_pua.remap(" " * n + f"{BULLET} item\n")
        assert out == " " * n + "- item\n", n
        assert rep["list_markers"] == 1 and rep["line_leading_marker_deferred"] == 0, n
    for n in (4, 5, 8):
        out, rep = symbol_pua.remap(" " * n + f"{BULLET} item\n")
        assert out == " " * n + f"{BULLET} item\n", n
        assert rep["line_leading_marker_deferred"] == 1 and rep["stray_markers"] == 0, n


def test_a_tab_indented_marker_is_measured_in_columns_and_refused():
    """Shipped in 0.2.8: the indent limit counted CHARACTERS, and CommonMark counts COLUMNS.

    A tab is one character and four columns, so `[ \\t]{0,3}` accepted a marker standing at column
    4 or beyond. `\\t<M> nested` became `\\t- nested`, which outside a list context is an indented
    CODE BLOCK -- the very structure the refusal exists to avoid -- while `     nested`, at the same
    column, was refused. One column, two answers.
    """
    for indent in ("\t", " \t", "\t ", "   \t"):
        out, rep = symbol_pua.remap(f"{indent}{BULLET} nested\n")
        assert out == f"{indent}{BULLET} nested\n", repr(indent)  # not one character changed
        assert rep["line_leading_marker_deferred"] == 1, repr(indent)
        assert rep["list_markers"] == 0 and rep["stray_markers"] == 0, repr(indent)
        assert rep["total_changes"] == 0, repr(indent)  # a refusal is not an edit


def test_the_column_count_agrees_with_commonmarks_four_column_tab_stop():
    """A tab advances to the next multiple of four, so its width depends on where it starts."""
    assert symbol_pua._columns("") == 0
    assert symbol_pua._columns("   ") == 3
    assert symbol_pua._columns("\t") == 4
    assert symbol_pua._columns(" \t") == 4  # one space then a tab still lands on the stop
    assert symbol_pua._columns("   \t") == 4
    assert symbol_pua._columns("\t ") == 5
    assert symbol_pua._columns("\t\t") == 8


def test_a_tab_indented_dot_still_defers_because_its_indent_is_unbounded():
    """The `U+F0B7` refusal never carried the limit, so the column fix must not give it one."""
    out, rep = symbol_pua.remap(f"\t{DOT} nested\n")
    assert out == f"\t{DOT} nested\n"
    assert rep["line_leading_dot_deferred"] == 1
    assert rep["total_changes"] == 0


def test_classify_reads_each_position_once():
    """The five readings are one function now, so pin what each position is called."""
    assert symbol_pua.classify("", " item") is symbol_pua.Pos.LIST
    assert symbol_pua.classify("  ", " item") is symbol_pua.Pos.LIST
    assert symbol_pua.classify("  *", " item") is symbol_pua.Pos.LIST  # opener MinerU misplaced
    assert symbol_pua.classify("## ", " item") is symbol_pua.Pos.HEADING
    assert symbol_pua.classify("    ", " item") is symbol_pua.Pos.LINE_OPEN  # over the limit
    assert symbol_pua.classify("\t", " item") is symbol_pua.Pos.LINE_OPEN  # four columns
    assert symbol_pua.classify("", "item") is symbol_pua.Pos.LINE_OPEN  # no gap after it
    assert symbol_pua.classify("* ", "item") is symbol_pua.Pos.SEPARATOR  # a REAL bullet, then it
    assert symbol_pua.classify("word ", " next") is symbol_pua.Pos.SEPARATOR
    assert symbol_pua.classify("word", "next") is symbol_pua.Pos.FLUSH


def test_a_line_opening_marker_glued_to_its_text_is_refused_not_deleted():
    """`  <M>text` has no space after it, so the list pass declines it, and the indent on its left
    used to send it to the deletion branch. Whether it is a bullet with a missing space is a
    reading of the page, not a fact about the line.
    """
    out, rep = symbol_pua.remap(f"  {BULLET}text\n")
    assert out == f"  {BULLET}text\n"
    assert rep["line_leading_marker_deferred"] == 1
    assert rep["stray_markers"] == 0


def test_the_line_opening_refusal_leaves_the_mid_line_readings_alone():
    """The two behaviors this fix must NOT change, pinned so a later widening trips here."""
    out, rep = symbol_pua.remap(f"word {BULLET} next\n")  # whitespace both sides: a safe cleanup
    assert out == "word next\n"
    assert rep["stray_markers"] == 1 and rep["line_leading_marker_deferred"] == 0

    out, rep = symbol_pua.remap(f"word{BULLET}next\n")  # flush between two words: never guess
    assert out == f"word{BULLET}next\n"
    assert rep["stray_unhandled"] == 1 and rep["line_leading_marker_deferred"] == 0


def test_the_marker_refusal_counter_is_always_present_on_both_reports():
    """A caller written against the documented return contract reads it without a KeyError guard."""
    _, plain = symbol_pua.remap("nothing to do here\n")
    assert plain["line_leading_marker_deferred"] == 0
    _, crlf = symbol_pua.remap("a line\r\nanother\r\n")
    assert crlf["skipped_crlf"] is True
    assert crlf["line_leading_marker_deferred"] == 0


def test_an_emphasis_opener_does_not_defeat_the_line_opening_refusal():
    """MinerU misplaces a `*` ahead of the marker, and both marker patterns allow one.

    The stray-marker branch did not, so `    *<BULLET> nested` fell straight past the refusal to the
    deletion branch and the nested list flattened -- the same defect one character to the left of
    where it was fixed. The `U+F0B7` sibling never had the gap, which is what showed it was an
    oversight and not a decision.
    """
    src = f"- top\n    *{BULLET} nested one\n    *{BULLET} nested two\n"
    out, rep = symbol_pua.remap(src)

    assert out == src
    assert rep["line_leading_marker_deferred"] == 2
    assert rep["stray_markers"] == 0 and rep["total_changes"] == 0
    # ...and the U+F0B7 sibling agrees, on the identical shape
    dot_src = f"- top\n    *{DOT} nested\n"
    out, rep = symbol_pua.remap(dot_src)
    assert out == dot_src and rep["line_leading_dot_deferred"] == 1


def test_a_marker_in_column_zero_is_reported_as_line_opening_not_mid_word():
    """`before` is `""` there, and `"".isspace()` is `False`.

    Behind the mid-word test, a marker that opens the line in column 0 was counted as
    `stray_unhandled`, whose report line reads "mid-word marker(s) ... inspect by hand". The
    character was left in place either way, so this is a reporting defect -- but it sends the
    operator looking for a word join that does not exist.
    """
    for src in (f"{BULLET}text\n", f"{BULLET}\n"):
        out, rep = symbol_pua.remap(src)
        assert out == src, src
        assert rep["line_leading_marker_deferred"] == 1, src
        assert rep["stray_unhandled"] == 0, src

    # the genuine mid-word reading is untouched: two real words, and no way to know
    out, rep = symbol_pua.remap(f"word{BULLET}next\n")
    assert out == f"word{BULLET}next\n"
    assert rep["stray_unhandled"] == 1 and rep["line_leading_marker_deferred"] == 0

    # and a SECOND emphasis opener closes the line again, so this is not a blanket exemption
    out, rep = symbol_pua.remap(f"**b**{BULLET}x\n")
    assert out == f"**b**{BULLET}x\n"
    assert rep["stray_unhandled"] == 1 and rep["line_leading_marker_deferred"] == 0


def test_a_real_markdown_bullet_before_the_marker_is_still_cleaned():
    """The emphasis opener that keeps a line "open" must be ADJACENT to the marker.

    The list and dot readings both require that. Allowing whitespace between them made
    `* <BULLET> item` -- a real Markdown bullet followed by a stray marker -- read as line-opening,
    so the marker stayed in the output as an invisible codepoint where it used to be removed. That
    is the failure class this module exists to remove, introduced by the guard against another one.
    """
    out, rep = symbol_pua.remap(f"* {BULLET} item\n")
    assert out == "* item\n"
    assert rep["stray_markers"] == 1 and rep["line_leading_marker_deferred"] == 0

    # the same line written with the other bullet character behaves identically
    out, _ = symbol_pua.remap(f"- {BULLET} item\n")
    assert out == "- item\n"

    # and the adjacent form is still a list item, not a deferral
    out, rep = symbol_pua.remap(f"*{BULLET} item\n")
    assert out == "- item\n" and rep["list_markers"] == 1

    # ...while the nested case the adjacency rule exists for is still refused
    src = f"- top\n    *{BULLET} nested\n"
    out, rep = symbol_pua.remap(src)
    assert out == src and rep["line_leading_marker_deferred"] == 1
