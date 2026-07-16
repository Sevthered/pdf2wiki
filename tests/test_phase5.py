"""Golden-file style tests for the Phase 5 fixers. All fixtures are synthetic."""
import os
import sys
import textwrap

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pdf2wiki.phase5 import caption_unbleed, chapter_split, dash_normalize, lang_retag, mermaid_repair


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
    assert "public class Widget {}" in out           # real code untouched
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
    assert "book: testbook" in ch1
    assert "# Chapter One" in ch1


def test_split_fence_aware(tmp_path):
    md = _write(tmp_path, "# Real Chapter\n```python\n# file: not_a_chapter.py\nx=1\n```\n")
    _, bounds = chapter_split.split(md, "b", out_dir=str(tmp_path / "ch"))
    assert len(bounds) == 1


def test_split_appendix_h2_promoted(tmp_path):
    md = _write(tmp_path, "# Chapter One\nbody\n\n## Appendix A. Extra stuff\nappendix body\n")
    written, bounds = chapter_split.split(md, "b", out_dir=str(tmp_path / "ch"))
    assert len(bounds) == 2
    appendix = (tmp_path / "ch" / "02-appendix-a-extra-stuff.md").read_text()
    assert "# Appendix A. Extra stuff" in appendix   # normalized to H1


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
