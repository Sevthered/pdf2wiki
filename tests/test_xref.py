# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The cross-reference linker (`phase5.xref`).

The caption and reference shapes in these fixtures are the ones measured on 24 converted books:
Manning italic captions under an image, bold-number listing captions above a fence, listing captions
that the converter set as a heading, O'Reilly `Figure 2-1.` captions, and prose that starts like a
caption ("Listing 6.1 shows ...").
"""

import os
import re
import sys
from urllib.parse import unquote

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pdf2wiki import cli
from pdf2wiki.phase5 import run_chain, xref

FM = '---\ntitle: "{t}"\nbook: "b"\nchapter: {n}\nsource: "b.pdf"\ntags: [book]\n---\n'


def chap(n: int, title: str, body: str) -> str:
    return FM.format(t=title, n=n) + body


CH6 = chap(
    7,
    "Introduction to Quarkus",
    "# Introduction to Quarkus\n\n"
    "The flow is in figure 6.2, and figure 6.9 does not exist.\n\n"
    "![](images/a.jpg)\n\n"
    "*Figure 6.2 Liveness check and application traffic flow*\n\n"
    "## 6.3 Getting started with MicroProfile Health\n\n"
    "Listing 6.1 shows the class.\n\n"
    "**Listing 6.1** The health check\n\n"
    "```java\nclass Health {} // see figure 6.2\n```\n\n"
    "## Listing 6.2 application.properties\n\n"
    "```\nquarkus.http.port=8080\n```\n",
)
CH7 = chap(
    8,
    "Configuring microservices",
    "# Configuring microservices\n\n"
    "Section 6.3 and listing 6.2 came in chapter 6, see figures 6.2 and 7.1.\n\n"
    "![](images/b.jpg)\n\n"
    "*Figure 7.1 Configuration sources*\n\n"
    "Use `figure 6.2` in code, and [figure 6.2](elsewhere.md) is already a link.\n\n"
    "Chapter 3 of Kubernetes in Action explains pods.\n",
)


def run(files, style="obsidian"):
    return xref.link(files, style)


def test_links_a_figure_reference_to_the_caption_in_another_file():
    out, rep = run({"07-intro.md": CH6, "08-config.md": CH7})
    assert (
        "figures [6.2](07-intro.md#^fig-6-2) and [7.1](08-config.md#^fig-7-1)"
        in out["08-config.md"]
    )
    assert (
        "*Figure 6.2 Liveness check and application traffic flow* ^fig-6-2\n" in out["07-intro.md"]
    )
    assert rep["linked"]["figure"] == 3  # one in CH6, two in CH7


def test_a_reference_in_the_same_file_still_names_the_file():
    out, _ = run({"07-intro.md": CH6, "08-config.md": CH7})
    assert "The flow is in [figure 6.2](07-intro.md#^fig-6-2)," in out["07-intro.md"]


def test_a_missing_target_is_reported_and_left_alone():
    out, rep = run({"07-intro.md": CH6, "08-config.md": CH7})
    assert "and figure 6.9 does not exist" in out["07-intro.md"]
    assert rep["not_found"]["figure"] == 1


def test_a_bold_number_caption_gets_a_block_id_and_prose_that_starts_like_a_caption_is_a_reference():
    out, _ = run({"07-intro.md": CH6, "08-config.md": CH7})
    assert "**Listing 6.1** The health check ^lst-6-1\n" in out["07-intro.md"]
    assert "[Listing 6.1](07-intro.md#^lst-6-1) shows the class." in out["07-intro.md"]


def test_a_heading_caption_and_a_numbered_section_get_heading_links():
    out, _ = run({"07-intro.md": CH6, "08-config.md": CH7})
    text = out["08-config.md"]
    assert (
        "[Section 6.3](07-intro.md#6.3%20Getting%20started%20with%20MicroProfile%20Health)" in text
    )
    assert "[listing 6.2](07-intro.md#Listing%206.2%20application.properties)" in text
    assert "## 6.3 Getting started with MicroProfile Health\n" in out["07-intro.md"]  # unchanged


def test_code_inline_code_and_existing_links_are_not_touched():
    out, _ = run({"07-intro.md": CH6, "08-config.md": CH7})
    assert "class Health {} // see figure 6.2\n" in out["07-intro.md"]
    assert (
        "Use `figure 6.2` in code, and [figure 6.2](elsewhere.md) is already a link."
        in out["08-config.md"]
    )


def test_the_chapter_number_comes_from_the_captions_when_the_title_has_none():
    out, rep = run({"07-intro.md": CH6, "08-config.md": CH7})
    assert "came in [chapter 6](07-intro.md), see" in out["08-config.md"]
    assert rep["linked"]["chapter"] == 1


def test_a_chapter_of_another_book_is_external():
    out, rep = run({"07-intro.md": CH6, "08-config.md": CH7})
    assert "Chapter 3 of Kubernetes in Action explains pods." in out["08-config.md"]
    assert rep["external"]["chapter"] == 1


def test_frontmatter_and_headings_are_never_linked():
    files = {
        "05-x.md": chap(5, "Chapter 5 Data", "# Chapter 5 Data\n\n## Compare with chapter 6\n"),
        "06-y.md": chap(6, "Chapter 6 More", "# Chapter 6 More\n\nSee chapter 5.\n"),
    }
    out, _ = run(files)
    assert out["05-x.md"] == files["05-x.md"]
    assert "See [chapter 5](05-x.md)." in out["06-y.md"]


def test_a_number_with_two_targets_is_ambiguous():
    body = "# A\n\n![](images/a.jpg)\n\n*Figure 1.1 One*\n\n![](images/b.jpg)\n\n*Figure 1.1 Two*\n\nSee figure 1.1.\n"
    out, rep = run({"01-a.md": chap(1, "A", body)})
    assert "See figure 1.1." in out["01-a.md"]
    assert "^fig-1-1" not in out["01-a.md"]
    assert rep["ambiguous"]["figure"] == 1


def test_two_files_that_claim_one_chapter_number_link_nowhere():
    a = chap(1, "A", "# A\n\n![](i/a.jpg)\n\n*Figure 2.1 x*\n\n![](i/b.jpg)\n\n*Figure 2.2 y*\n")
    b = chap(
        2,
        "B",
        "# B\n\n![](i/c.jpg)\n\n*Figure 2.3 x*\n\n![](i/d.jpg)\n\n*Figure 2.4 y*\n\nSee chapter 2.\n",
    )
    out, rep = run({"01-a.md": a, "02-b.md": b})
    assert "See chapter 2." in out["02-b.md"]
    assert rep["ambiguous"]["chapter"] == 1


def test_an_oreilly_caption_with_a_hyphen_number():
    body = "# Ch\n\nAs figure 2-1 shows.\n\n![](images/a.png)\n\nFigure 2-1. The architecture\n"
    out, _ = run({"02-c.md": chap(2, "Ch", body)})
    assert "As [figure 2-1](02-c.md#^fig-2-1) shows." in out["02-c.md"]
    assert "Figure 2-1. The architecture ^fig-2-1\n" in out["02-c.md"]


def test_a_second_run_changes_nothing():
    once, _ = run({"07-intro.md": CH6, "08-config.md": CH7})
    twice, rep = run(once)
    assert twice == once
    assert rep["anchors_added"] == 0 and sum(rep["linked"].values()) == 0


def test_markdown_style_uses_html_anchors():
    out, _ = run({"07-intro.md": CH6, "08-config.md": CH7}, style="markdown")
    assert "figures [6.2](07-intro.md#fig-6-2)" in out["08-config.md"]
    assert '<a id="fig-6-2"></a>*Figure 6.2 Liveness check' in out["07-intro.md"]
    # the heading text stays as it was: the anchor sits on its own line above it
    assert (
        '<a id="sec-6-3"></a>\n\n## 6.3 Getting started with MicroProfile Health\n'
        in out["07-intro.md"]
    )
    assert "[Section 6.3](07-intro.md#sec-6-3)" in out["08-config.md"]
    assert '<a id="lst-6-2"></a>\n\n## Listing 6.2 application.properties\n' in out["07-intro.md"]
    twice, _ = run(out, style="markdown")
    assert twice == out


def test_an_unknown_style_is_refused():
    with pytest.raises(ValueError):
        run({"a.md": "x"}, style="wiki")


def test_a_caption_shaped_line_with_no_image_fence_or_table_near_is_prose():
    body = "# A\n\nText.\n\nTable 2.1 Comparison of brokers\n\nMore text.\n"
    out, rep = run({"01-a.md": chap(1, "A", body)})
    assert "^tbl-2-1" not in out["01-a.md"]
    assert rep["anchors_added"] == 0 and rep["not_found"]["table"] == 1


def test_one_caption_is_not_enough_to_number_a_chapter():
    one = chap(1, "A", "# A\n\n![](i/a.jpg)\n\n*Figure 7.1 Sources*\n")
    other = chap(2, "B", "# B\n\nSee chapter 7.\n")
    out, rep = run({"01-a.md": one, "02-b.md": other})
    assert "See chapter 7." in out["02-b.md"]
    assert rep["chapters"] == {} and rep["not_found"]["chapter"] == 1


def test_captions_with_different_first_numbers_give_no_chapter_number():
    mixed = chap(
        1, "A", "# A\n\n![](i/a.jpg)\n\n*Figure 6.1 x*\n\n![](i/b.jpg)\n\n*Figure 7.1 y*\n"
    )
    out, rep = run({"01-a.md": mixed, "02-b.md": chap(2, "B", "# B\n\nSee chapter 6.\n")})
    assert "See chapter 6." in out["02-b.md"]
    assert rep["chapters"] == {}


def test_a_section_reference_needs_a_number_with_two_parts():
    out, rep = run(
        {"01-a.md": chap(1, "A", "# A\n\n## 1.2 Part\n\nSee section 6, then section 1.2.\n")}
    )
    assert "See section 6, then [section 1.2](01-a.md#1.2%20Part)." in out["01-a.md"]
    assert rep["not_found"]["section"] == 0


# ---------- the `link` command and the phase5 chain ----------


def _book(tmp_path, book="b"):
    d = tmp_path / "chapters"
    d.mkdir(exist_ok=True)
    (d / "07-intro.md").write_text(CH6.replace('book: "b"', f'book: "{book}"'), encoding="utf-8")
    (d / "08-config.md").write_text(CH7, encoding="utf-8")
    (d / "b-index.md").write_text(
        '---\ntitle: "B"\nbook: "b"\n---\n\nSee figure 6.2.\n', encoding="utf-8"
    )
    (d / "notes.md").write_text("figure 6.2\n", encoding="utf-8")
    return d


def test_link_is_a_dry_run_by_default(tmp_path, capsys):
    d = _book(tmp_path)
    before = {p.name: p.read_text(encoding="utf-8") for p in d.iterdir()}
    assert cli.main(["link", str(d)]) == 0
    assert {p.name: p.read_text(encoding="utf-8") for p in d.iterdir()} == before
    out = capsys.readouterr().out
    assert (
        "xref (obsidian):" in out
        and "(dry-run — would write 2 of 2 chapter files; pass --apply)" in out
    )


def test_link_apply_writes_the_chapters_only_and_a_second_run_writes_nothing(tmp_path, capsys):
    d = _book(tmp_path)
    assert cli.main(["link", str(d), "--apply"]) == 0
    assert "figures [6.2](07-intro.md#^fig-6-2)" in (d / "08-config.md").read_text(encoding="utf-8")
    assert (d / "b-index.md").read_text(encoding="utf-8").endswith("See figure 6.2.\n")
    assert (d / "notes.md").read_text(encoding="utf-8") == "figure 6.2\n"
    capsys.readouterr()
    assert cli.main(["link", str(d), "--apply"]) == 0
    assert "APPLIED — wrote 0 of 2 chapter files" in capsys.readouterr().out


def test_link_refuses_a_folder_with_two_books_or_none(tmp_path, capsys):
    d = _book(tmp_path, book="other")
    assert cli.main(["link", str(d)]) == 2
    assert "more than one book: b, other" in capsys.readouterr().err
    empty = tmp_path / "empty"
    empty.mkdir()
    assert cli.main(["link", str(empty)]) == 2
    assert "holds no chapter file" in capsys.readouterr().err


def test_link_json_reports_the_counts(tmp_path, capsys):
    import json

    d = _book(tmp_path)
    assert cli.main(["link", str(d), "--style", "markdown", "--json"]) == 0
    rep = json.loads(capsys.readouterr().out)
    assert rep["style"] == "markdown" and rep["applied"] is False
    assert rep["changed"] == ["07-intro.md", "08-config.md"] and rep["linked"]["figure"] == 3


def test_phase5_links_only_when_asked(tmp_path):
    md = tmp_path / "book.md"
    md.write_text(
        "# Chapter 1 Overview\n\n![](images/a.jpg)\n\n*Figure 1.1 The system*\n\n"
        "# Chapter 2 Data\n\nAs in figure 1.1 and chapter 1.\n",
        encoding="utf-8",
    )
    off = run_chain(str(md), "book", out_dir=str(tmp_path / "off"), apply=True)
    assert off["xref"] is None
    assert "As in figure 1.1 and chapter 1." in (
        tmp_path / "off" / "02-chapter-2-data.md"
    ).read_text(encoding="utf-8")
    on = run_chain(str(md), "book", out_dir=str(tmp_path / "on"), apply=True, links="obsidian")
    text = (tmp_path / "on" / "02-chapter-2-data.md").read_text(encoding="utf-8")
    assert (
        "As in [figure 1.1](01-chapter-1-overview.md#^fig-1-1) and [chapter 1](01-chapter-1-overview.md)."
        in text
    )
    assert on["xref"]["linked"]["figure"] == 1 and on["xref"]["linked"]["chapter"] == 1


def test_phase5_cli_prints_the_link_summary(tmp_path, capsys):
    md = tmp_path / "book.md"
    md.write_text("# Chapter 1 A\n\ntext\n\n# Chapter 2 B\n\nSee chapter 1.\n", encoding="utf-8")
    assert cli.main(["phase5", str(md), "--book", "book", "--links", "markdown"]) == 0
    assert "xref (markdown): 1 links (chapter 1)" in capsys.readouterr().out


def test_a_caption_that_wraps_gets_its_block_id_on_the_last_line_and_no_links():
    body = (
        "# A\n\n![](i/a.jpg)\n\n*Figure 3.2 The same layout as in figure 3.1,\nwith a cache in front*\n\n"
        "![](i/b.jpg)\n\n*Figure 3.1 The layout*\n\nSee figure 3.2.\n"
    )
    out, _ = run({"03-a.md": chap(3, "A", body)})
    text = out["03-a.md"]
    assert (
        "*Figure 3.2 The same layout as in figure 3.1,\nwith a cache in front* ^fig-3-2\n" in text
    )
    assert "See [figure 3.2](03-a.md#^fig-3-2)." in text


def test_a_heading_that_a_link_cannot_carry_is_unlinkable():
    body = "# A\n\n## 2.1 Use [brackets] here\n\nSee section 2.1.\n"
    out, rep = run({"02-a.md": chap(2, "A", body)})
    assert "See section 2.1." in out["02-a.md"]
    assert rep["unlinkable"]["section"] == 1
    out, rep = run({"02-a.md": chap(2, "A", body)}, style="markdown")
    assert "See [section 2.1](02-a.md#sec-2-1)." in out["02-a.md"]


def test_read_book_dir_skips_folders_other_files_and_an_unclosed_frontmatter(tmp_path):
    (tmp_path / "images").mkdir()
    (tmp_path / "a.png").write_bytes(b"\x89PNG")
    (tmp_path / "broken.md").write_text(
        "---\nbook: b\nchapter: 1\nno closing line\n", encoding="utf-8"
    )
    (tmp_path / "01-a.md").write_text(chap(1, "A", "# A\n"), encoding="utf-8")
    assert list(xref.read_book_dir(str(tmp_path))) == ["01-a.md"]


def test_a_users_own_block_id_stays_and_its_line_is_still_linked():
    body = "# A\n\nSee figure 4.1 again. ^my-note\n\n![](i/a.jpg)\n\n*Figure 4.1 Last caption,\nat the end of the file*"
    out, _ = run({"04-a.md": chap(4, "A", body)})
    assert "See [figure 4.1](04-a.md#^fig-4-1) again. ^my-note\n" in out["04-a.md"]
    assert out["04-a.md"].endswith("*Figure 4.1 Last caption,\nat the end of the file* ^fig-4-1")


# ---------- review round 1 ----------


# How Obsidian 1.14.5 follows a Markdown link to a heading, read from its app code. The link is
# internal only when it starts with ./ or ../ or has no ":". It is decoded with decodeURI, which
# keeps the escapes of ;/?:@&=+$,#. The first heading whose stripHeading text matches wins.
_OBSIDIAN_STRIP = re.compile(r'[!"#$%&()*+,.:;<=>?@^`{|}~/\[\]\\\r\n]')
_DECODE_URI_KEEPS = set(";/?:@&=+$,#")


def _decode_uri(s):
    def decode(m):
        out, run = [], []
        for esc in re.findall(r"%[0-9A-Fa-f]{2}", m.group()):
            if chr(int(esc[1:], 16)) in _DECODE_URI_KEEPS:
                out.append(unquote("".join(run), errors="strict"))
                run = []
                out.append(esc)
            else:
                run.append(esc)
        out.append(unquote("".join(run), errors="strict"))
        return "".join(out)

    return re.sub(r"(?:%[0-9A-Fa-f]{2})+", decode, s)


def _strip_heading(s):
    return " ".join(_OBSIDIAN_STRIP.sub(" ", s).split()).lower()


def _obsidian_heading_hits(target, href):
    """How many headings of `target` the link `href` (file#fragment) matches in Obsidian."""
    assert href.startswith(("./", "../")) or ":" not in href, f"Obsidian reads {href} as external"
    want = _strip_heading(_decode_uri(href.partition("#")[2]))
    heads = re.findall(r"^#{1,6}[ \t]+(.*?)[ \t]*$", target, re.M)
    return sum(_strip_heading(h) == want for h in heads)


def test_the_obsidian_model_matches_the_click_test():
    """The links clicked in Obsidian 1.14.5 (session 77) and what each one did."""
    a = (
        "## 6.3 Setup: the basics\n\n## 7.1 Memory is not enough (literally)\n\n"
        "## Listing 7.11 LFU cache get, Java version\n\n## **6.4** Bold number\n"
    )
    clicked = {
        "6.3%20Setup%3A%20the%20basics": 0,
        "6.3%20Setup%20the%20basics": 1,
        "7.1%20Memory%20is%20not%20enough%20%28literally%29": 1,
        "Listing%207.11%20LFU%20cache%20get%2C%20Java%20version": 0,
        "%2A%2A6.4%2A%2A%20Bold%20number": 1,
        "6.4%20Bold%20number": 1,
    }
    for frag, hits in clicked.items():
        assert _obsidian_heading_hits(a, f"a.md#{frag}") == hits, frag


def _anchors_resolve(out):
    """Every link to a fragment opens something that exists in the target file, the way Obsidian
    follows it: a block id or exactly one heading. A markdown-style `<a id>` also counts, for other
    viewers. A run never rewrites the links of an earlier run, so after a run in the other style
    both kinds of link are in the text."""
    for text in out.values():
        for name, frag in re.findall(r"\]\(([^)#\s]+\.md)#([^)\s]+)\)", text):
            if name not in out:
                continue
            target = out[name]
            if frag.startswith("^"):
                ok = re.search(rf"[ \t]\^{re.escape(frag[1:])}[ \t]*$", target, re.M)
            elif f'<a id="{frag}"></a>' in target:
                ok = True
            else:
                ok = _obsidian_heading_hits(target, f"{name}#{frag}") == 1
            assert ok, (name, frag)


def test_a_heading_link_drops_what_obsidian_does_not_decode():
    """A fragment with `%3A` (":") or `%2C` (",") opened nothing in Obsidian. On the vault, 84 of
    312 section links had one of these characters."""
    heads = [
        "2.2 The problem: Handling priority",
        "2.5 Under the hood: How do Bloom filters work?",
        "2.6 LFU cache get, Java version",
        "2.7 Analysis of branching factor<sup>21</sup>",
        "2.8 Q&A; a+b=c @ 5$ each",
    ]
    body = "# A\n\n" + "".join(f"## {h}\n\nText.\n\n" for h in heads)
    body += "".join(f"See section {h.split()[0]}.\n\n" for h in heads)
    out, rep = run({"02-a.md": chap(2, "A", body)})
    text = out["02-a.md"]
    assert "[section 2.2](02-a.md#2.2%20The%20problem%20Handling%20priority)" in text
    assert "[section 2.6](02-a.md#2.6%20LFU%20cache%20get%20Java%20version)" in text
    assert rep["linked"]["section"] == len(heads)
    _anchors_resolve(out)


@pytest.mark.parametrize(("first", "second"), [("obsidian", "markdown"), ("markdown", "obsidian")])
def test_a_second_run_in_the_other_style_adds_its_own_anchors(first, second):
    once, _ = run({"07-intro.md": CH6, "08-config.md": CH7}, style=first)
    twice, rep = run(once, style=second)
    _anchors_resolve(twice)
    assert rep["anchors_added"] > 0


def test_an_image_on_the_next_line_belongs_to_the_caption_paragraph():
    body = "# A\n\n*Figure 7.1 Sources*\n![](i/b.jpg)\n\nSee figure 7.1.\n"
    out, _ = run({"07-a.md": chap(7, "A", body)})
    assert "*Figure 7.1 Sources*\n![](i/b.jpg) ^fig-7-1\n" in out["07-a.md"]


def test_display_math_is_never_linked():
    body = (
        "# A\n\n![](i/a.jpg)\n\n*Figure 4.1 x*\n\n$$\n\\text{see figure 4.1}\n$$\n\n"
        "$$ \\text{inline figure 4.1} $$\n"
    )
    out, _ = run({"04-a.md": chap(4, "A", body)})
    assert "$$\n\\text{see figure 4.1}\n$$\n" in out["04-a.md"]
    assert "$$ \\text{inline figure 4.1} $$\n" in out["04-a.md"]


@pytest.mark.parametrize(
    ("line", "caption"),
    [
        ("Table 1.3 makes the point clear.", False),  # the review's case: no verb on the list
        ("Figure 14.18 shows, on a simpler graph, how it works.", False),  # a verb with a comma
        ("Figure 1.1 The (simplified) internal representation of an array.", True),
        ("Listing 5.1 Login endpoint vulnerable to brute force attacks", True),
        ("Figure 3.1 – The output of the command", True),  # Packt
    ],
)
def test_a_plain_caption_line_needs_a_capital_after_the_number(line, caption):
    body = f"# A\n\n{line}\n\n| a | b |\n|---|---|\n| 1 | 2 |\n"
    out, rep = run({"01-a.md": chap(1, "A", body)})
    assert (rep["anchors_added"] == 1) is caption


def test_numbers_compare_without_leading_zeros():
    files = {
        "05-x.md": chap(5, "Chapter 05 Data", "# Chapter 05 Data\n\ntext\n"),
        "06-y.md": chap(6, "B", "# Chapter 6 B\n\nSee chapter 5.\n"),
    }
    out, rep = run(files)
    assert "See [chapter 5](05-x.md)." in out["06-y.md"]
    assert rep["chapters"]["05-x.md"] == 5


def test_a_plural_list_takes_only_numbers_of_the_same_shape():
    body = "# A\n\n![](i/a.jpg)\n\n*Figure 6.2 x*\n\nFigures 6.2, 2019 data and more.\n"
    out, rep = run({"06-a.md": chap(6, "A", body)})
    assert "[Figures 6.2](06-a.md#^fig-6-2), 2019 data and more." in out["06-a.md"]
    assert rep["not_found"]["figure"] == 0


# ---------- review round 2 ----------


def test_two_caption_lines_in_one_paragraph_make_one_target():
    body = "# A\n\n![](a.jpg)\n*Figure 2.1 Alpha*\n*Figure 2.2 Beta*\n\nSee figure 2.1 and figure 2.2.\n"
    out, rep = run({"02-a.md": chap(2, "A", body)})
    assert out["02-a.md"].count(" ^fig-") == 1  # one block id: one paragraph, one block
    assert "*Figure 2.2 Beta* ^fig-2-1\n" in out["02-a.md"]
    assert "See [figure 2.1](02-a.md#^fig-2-1) and figure 2.2." in out["02-a.md"]


def test_a_dash_is_a_range_unless_the_book_numbers_that_kind_with_a_dash():
    sections = "# A\n\n## 2.3 Start\n\nSee sections 2-3 and listings 4-6.\n"
    out, rep = run({"02-a.md": chap(2, "A", sections)})
    assert "See sections 2-3 and listings 4-6." in out["02-a.md"]
    assert rep["not_found"]["listing"] == 0
    oreilly = "# A\n\n![](a.png)\n\nFigure 2-1. One\n\n![](b.png)\n\nFigure 2-2. Two\n\nSee figures 2-1 and 2-2.\n"
    out, _ = run({"02-b.md": chap(2, "B", oreilly)})
    assert "See figures [2-1](02-b.md#^fig-2-1) and [2-2](02-b.md#^fig-2-2)." in out["02-b.md"]


def test_an_h1_number_must_end_at_a_space_or_punctuation():
    files = {
        "03-g.md": chap(3, "3D Graphics", "# 3D Graphics\n\ntext\n"),
        "04-c.md": chap(4, "C", "# Chapter 3: Real\n\ntext\n"),
        "05-d.md": chap(5, "D", "# 5. Data\n\nSee chapter 3 and chapter 5.\n"),
    }
    out, rep = run(files)
    assert rep["chapters"] == {"04-c.md": 3, "05-d.md": 5}
    assert "See [chapter 3](04-c.md) and [chapter 5](05-d.md)." in out["05-d.md"]


def test_one_part_caption_numbers_do_not_number_a_chapter():
    pre = chap(
        1,
        "Preface",
        "# Preface\n\n![](a.jpg)\n\n*Figure 1 Something*\n\n**Listing 1** Hello\n\n```\nx\n```\n",
    )
    out, rep = run({"01-pre.md": pre, "02-x.md": chap(2, "X", "# X\n\nSee chapter 1.\n")})
    assert rep["chapters"] == {}
    assert "See chapter 1." in out["02-x.md"]


def test_prices_are_not_math():
    body = "# A\n\n![](a.jpg)\n\n*Figure 2.1 x*\n\nIt costs $5 and figure 2.1 or $6. Math $x^2$ and figure 2.1.\n"
    out, _ = run({"02-a.md": chap(2, "A", body)})
    assert "It costs $5 and [figure 2.1](02-a.md#^fig-2-1) or $6." in out["02-a.md"]
    assert "Math $x^2$ and [figure 2.1](02-a.md#^fig-2-1)." in out["02-a.md"]


def test_inline_html_at_the_line_start_does_not_hide_a_reference():
    body = "# A\n\n## 3.1 Start\n\n<kbd>Ctrl</kbd> opens it, see section 3.1.\n\n<div>see section 3.1</div>\n"
    out, _ = run({"03-a.md": chap(3, "A", body)})
    assert "<kbd>Ctrl</kbd> opens it, see [section 3.1](03-a.md#3.1%20Start)." in out["03-a.md"]
    assert "<div>see section 3.1</div>" in out["03-a.md"]


def test_of_chapter_or_part_is_this_book():
    body = "# A\n\n## 4.1 Start\n\nSee section 4.1 of Chapter 4, and section 4.1 of RFC 6749.\n"
    out, rep = run({"04-a.md": chap(4, "A", body)})
    assert (
        "See [section 4.1](04-a.md#4.1%20Start) of Chapter 4, and section 4.1 of RFC 6749."
        in out["04-a.md"]
    )
    assert rep["external"]["section"] == 1


def test_link_apply_writes_nothing_when_a_file_cannot_be_written(tmp_path, capsys, monkeypatch):
    d = _book(tmp_path)
    before = {p.name: p.read_text(encoding="utf-8") for p in d.iterdir()}
    real = os.replace

    def failing(src, dst):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "replace", failing)
    assert cli.main(["link", str(d), "--apply"]) == 2
    monkeypatch.setattr(os, "replace", real)
    assert "No space left on device" in capsys.readouterr().err
    assert {p.name: p.read_text(encoding="utf-8") for p in d.iterdir()} == before


# ---------- review round 3 ----------


def test_a_one_part_number_resolves_only_in_its_own_file():
    c = chap(3, "C", "# C\n\nAs Figure 7 shows, it works.\n\nFigure 7 The other thing\n")
    d = chap(5, "D", "# D\n\n![](a.jpg)\n\n*Figure 7 The thing*\n\nSee figure 7.\n")
    out, rep = run({"03-c.md": c, "05-d.md": d})
    assert "As Figure 7 shows, it works." in out["03-c.md"]  # its own Figure 7 is not detected
    assert "See [figure 7](05-d.md#^fig-7)." in out["05-d.md"]
    e = chap(6, "E", "# E\n\n![](b.jpg)\n\n*Figure 7 A third*\n\nSee figure 7 here.\n")
    out, _ = run({"05-d.md": d, "06-e.md": e})  # Figure 7 in two files: each links its own
    assert "See [figure 7](05-d.md#^fig-7)." in out["05-d.md"]
    assert "See [figure 7](06-e.md#^fig-7) here." in out["06-e.md"]


def test_reference_links_and_their_definitions_are_not_touched():
    body = (
        "# A\n\n![](a.jpg)\n\n*Figure 2.1 x*\n\nSee [Figure 2.1][r] and [chapter 2] too.\n\n"
        '[r]: http://x "Chapter 2 and figure 2.1"\n'
    )
    out, _ = run({"02-a.md": chap(2, "A", body)})
    assert "See [Figure 2.1][r] and [chapter 2] too." in out["02-a.md"]
    assert '[r]: http://x "Chapter 2 and figure 2.1"\n' in out["02-a.md"]


def test_markdown_anchor_lines_do_not_hide_a_caption_on_the_second_run():
    body = "# A\n\n![](a.jpg)\n\n## 1.2 Start\n\nFigure 1.1 The arch\n\nSee figure 1.1 and section 1.2.\n"
    once, rep1 = run({"01-a.md": chap(1, "A", body)}, style="markdown")
    twice, rep2 = run(once, style="markdown")
    assert twice == once
    assert rep2["not_found"]["figure"] == 0


def test_indented_code_is_not_linked():
    body = "# A\n\n![](a.jpg)\n\n*Figure 1.1 x*\n\nCode:\n\n    // see Figure 1.1\n    x = 1\n\nSee figure 1.1.\n"
    out, _ = run({"01-a.md": chap(1, "A", body)})
    assert "    // see Figure 1.1\n" in out["01-a.md"]
    assert "See [figure 1.1](01-a.md#^fig-1-1)." in out["01-a.md"]


def test_link_keeps_crlf_line_ends_symlinks_and_file_modes(tmp_path):
    d = _book(tmp_path)
    crlf = d / "08-config.md"
    crlf.write_bytes(crlf.read_text(encoding="utf-8").replace("\n", "\r\n").encode("utf-8"))
    real = tmp_path / "real-intro.md"
    real.write_text((d / "07-intro.md").read_text(encoding="utf-8"), encoding="utf-8")
    real.chmod(0o640)
    (d / "07-intro.md").unlink()
    (d / "07-intro.md").symlink_to(real)
    assert cli.main(["link", str(d), "--apply"]) == 0
    raw = crlf.read_bytes()
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")
    assert b"figures [6.2](07-intro.md#^fig-6-2)" in raw
    assert (d / "07-intro.md").is_symlink()
    assert "^fig-6-2" in real.read_text(encoding="utf-8")
    assert real.stat().st_mode & 0o777 == 0o640
    assert not list(d.glob(".*.xref-tmp")) and not list(tmp_path.glob(".*.xref-tmp"))


# Review round 4. Each test failed before its fix.


def test_a_caption_can_start_with_a_capital_preposition():
    """31 vault captions start "Figure 7.2 With ..." or "In ...". Prose goes on in lower case."""
    body = (
        "# A\n\n![](a.jpg)\n\n*Figure 7.2 With the cache, the call is fast*\n\n"
        "![](b.jpg)\n\nFigure 7.3 In-memory data grid\n\nSee figure 7.2 and figure 7.3.\n"
    )
    out, rep = run({"07-a.md": chap(7, "A", body)})
    assert rep["linked"]["figure"] == 2
    assert "*Figure 7.2 With the cache, the call is fast* ^fig-7-2" in out["07-a.md"]


def test_a_number_never_ends_inside_a_longer_number():
    body = (
        "# A\n\n![](a.jpg)\n\n*Figure 6 Overview*\n\n![](b.jpg)\n\n*Figure 6.2 Detail*\n\n"
        "See figure 6.2a, figure 9.15B and figure 6.2x1.\n"
    )
    out, _ = run({"06-a.md": chap(6, "A", body)})
    text = out["06-a.md"]
    assert "See [figure 6.2](06-a.md#^fig-6-2)a, figure 9.15B and figure 6.2x1." in text


def test_an_en_dash_range_gets_no_link():
    body = (
        "# A\n\n![](a.jpg)\n\n*Figure 2.1 x*\n\n![](b.jpg)\n\n*Figure 2.3 y*\n\n"
        "See figures 2.1\u20132.3, chapters 2 \u2014 4 and figures 2.1 - 2.3.\n"
    )
    out, _ = run({"02-a.md": chap(2, "A", body)})
    assert "See figures 2.1\u20132.3, chapters 2 \u2014 4 and figures 2.1 - 2.3." in out["02-a.md"]


def test_a_list_with_an_oxford_comma_links_its_last_number():
    body = "# A\n\n" + "".join(f"![](i{n}.jpg)\n\n*Figure 6.{n} x*\n\n" for n in (1, 2, 3))
    body += "See figures 6.1, 6.2, and 6.3.\n"
    out, rep = run({"06-a.md": chap(6, "A", body)})
    assert rep["linked"]["figure"] == 3
    assert ", and [6.3](06-a.md#^fig-6-3)." in out["06-a.md"]


def test_emphasis_after_of_is_this_book_unless_it_holds_a_capital():
    body = (
        "# A\n\n## 4.1 Start\n\nSee section 4.1 of *this* chapter, and chapter 3 of *Kubernetes*.\n"
    )
    out, rep = run({"04-a.md": chap(4, "A", body)})
    assert "See [section 4.1](04-a.md#4.1%20Start) of *this* chapter" in out["04-a.md"]
    assert rep["external"]["chapter"] == 1


def test_display_math_ends_a_caption_paragraph():
    body = "# A\n\n![](a.jpg)\n*Figure 1.1 X*\n$$\ny = x\n$$\n\nSee figure 1.1.\n"
    out, _ = run({"01-a.md": chap(1, "A", body)})
    assert "*Figure 1.1 X* ^fig-1-1\n$$\ny = x\n$$\n" in out["01-a.md"]


def test_no_target_in_indented_code_or_an_html_block():
    body = (
        "# A\n\nCode:\n\n    ![](a.jpg)\n    Figure 1.1 The thing\n\n"
        "<pre>\n![](b.jpg)\n\n*Figure 1.2 Inside*\n\nsee figure 1.1\n</pre>\n\n"
        "<!-- a note\n\nsee figure 1.2\n-->\n\nSee figure 1.1 and figure 1.2.\n"
    )
    out, rep = run({"01-a.md": chap(1, "A", body)}, style="markdown")
    assert out["01-a.md"] == chap(1, "A", body)
    assert rep["not_found"]["figure"] == 2


def test_a_caption_starts_a_paragraph():
    body = (
        "# A\n\nSome prose that wraps, and the next line\nFigure 1.1 The thing is described here.\n"
        "![](a.jpg)\n\nSee figure 1.1.\n"
    )
    out, rep = run({"01-a.md": chap(1, "A", body)}, style="markdown")
    assert out["01-a.md"] == chap(1, "A", body)
    assert rep["anchors_added"] == 0


def test_a_section_in_its_own_chapter_wins_over_a_table_of_contents():
    """Three vault books set the table of contents as headings: 16 sections were ambiguous."""
    toc = chap(0, "Contents", "# Contents\n\n## 1.1 Pods\n\n## 1.2 Nodes\n\n## 2.1 Services\n")
    ch1 = chap(1, "Pods", "# 1 Pods\n\n## 1.1 Pods\n\n## 1.2 Nodes\n\nSee section 1.2.\n")
    for style in ("obsidian", "markdown"):
        out, rep = run({"00-contents.md": toc, "01-pods.md": ch1}, style=style)
        assert "sec-1-2" not in out["00-contents.md"]  # the anchor goes to the chapter
        assert rep["linked"]["section"] == 1 and rep["ambiguous"]["section"] == 0
        assert "See [section 1.2](01-pods.md#" in out["01-pods.md"]
        _anchors_resolve(out)


def test_a_heading_with_a_hash_is_a_link_target():
    body = "# A\n\n## 3.2 Calling C# from F#\n\nSee section 3.2.\n"
    out, _ = run({"03-a.md": chap(3, "A", body)})
    assert "See [section 3.2](03-a.md#3.2%20Calling%20C%20from%20F)." in out["03-a.md"]
    _anchors_resolve(out)


def test_mixed_styles_never_give_an_anchor_twice():
    body = "# A\n\n![](a.jpg)\n*Figure 1.1 X*\n## 1.2 Foo\n\nSee figure 1.1 and section 1.2.\n"
    files = {"01-a.md": chap(1, "A", body)}
    for style in ("markdown", "obsidian", "markdown"):
        files, _ = run(files, style=style)
    assert files["01-a.md"].count('<a id="sec-1-2"></a>') == 1
    assert "*Figure 1.1 X* ^fig-1-1\n" in files["01-a.md"]
    _anchors_resolve(files)


def test_link_skips_a_note_that_is_not_utf8_and_names_a_chapter_that_is_not(tmp_path, capsys):
    d = _book(tmp_path)
    (d / "latin.md").write_bytes("caf\xe9 notes\n".encode("latin-1"))
    assert cli.main(["link", str(d)]) == 0
    (d / "09-bad.md").write_bytes(chap(9, "Bad", "caf\xe9\n").encode("latin-1"))
    assert cli.main(["link", str(d)]) == 2
    assert "09-bad.md is not UTF-8" in capsys.readouterr().err


def test_link_apply_never_follows_a_file_at_the_temporary_path(tmp_path):
    d = _book(tmp_path)
    victim = tmp_path / "victim.txt"
    victim.write_text("keep\n", encoding="utf-8")
    (d / ".07-intro.md.xref-tmp").symlink_to(victim)
    mixed = d / "08-config.md"
    mixed.write_bytes(mixed.read_bytes().replace(b"\n", b"\r\n", 1))
    assert cli.main(["link", str(d), "--apply"]) == 0
    assert victim.read_text(encoding="utf-8") == "keep\n"
    assert (
        b"\r\n" not in mixed.read_bytes()
    )  # only a file with CRLF line ends everywhere keeps them


def test_a_caption_right_under_a_fence_starts_a_paragraph():
    body = "# A\n\n```java\nclass A {}\n```\n**Listing 1.1** The class\n\nSee listing 1.1.\n"
    out, _ = run({"01-a.md": chap(1, "A", body)})
    assert "**Listing 1.1** The class ^lst-1-1\n" in out["01-a.md"]
    assert "See [listing 1.1](01-a.md#^lst-1-1)." in out["01-a.md"]
