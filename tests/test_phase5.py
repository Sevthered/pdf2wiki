# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Golden-file style tests for the Phase 5 fixers. All fixtures are synthetic."""

import os
import sys
import textwrap

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

PI, SIGMA, ARROW, BULLET = "", "", "", ""


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


def test_pua_unknown_codepoint_left_alone_and_reported():
    md = "an  unverified glyph\n"
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
