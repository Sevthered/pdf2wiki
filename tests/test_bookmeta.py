# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Book metadata, chapter page ranges, the enriched frontmatter and the index page.

The copyright-page fixtures copy the shapes of three publishers in the converted corpus: Packt
(`Copyright © 2023 Packt Publishing`, `Published by Packt Publishing Ltd.`, a hyphenated ISBN),
Manning (`©2021 by Manning Publications Co.`, a company-name line, `ISBN: 978...`) and O'Reilly
(`Published by O’Reilly Media, Inc., <address>`, the ISBN only inside an errata URL).
"""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pdf2wiki.cli as cli
from pdf2wiki import bookmeta
from pdf2wiki.bookmeta import BookMeta
from pdf2wiki.phase5 import book_index, chapter_split, run_chain

PACKT = """# Copyright

## 50 Algorithms Every Programmer Should Know Second Edition

Copyright © 2023 Packt Publishing

Senior Publishing Product Manager: Denim Pinto

First published: June 2020

Published by Packt Publishing Ltd.

Livery Place

ISBN 978-1-80324-776-2
"""

MANNING = """Manning Publications Co.

©2021 by Manning Publications Co. All rights reserved.

ISBN: 9781617296864
"""

OREILLY = """Copyright © 2020 Google LLC. All rights reserved.

Published by O’Reilly Media, Inc., 1005 Gravenstein Highway North, Sebastopol, CA 95472.

March 2020: First Edition

See https://oreilly.com/catalog/errata.csp?isbn=9781492083122 for release details.
"""


# ---------- ISBN ----------


@pytest.mark.parametrize(
    "text, isbn",
    [
        ("ISBN 978-1-80324-776-2", "9781803247762"),
        ("ISBN: 9781617296864", "9781617296864"),
        ("errata.csp?isbn=9781492083122 for", "9781492083122"),
        ("ISBN-10: 0-306-40615-2", "0306406152"),
        ("ISBN 0-8044-2957-X", "080442957X"),
        ("ISBN 9781617295485 2021", "9781617295485"),  # the next number on the line is cut off
        ("ISBN 1491950358 2010", "1491950358"),  # an ISBN-10 is not read as a 13-digit run
    ],
)
def test_find_isbn_reads_each_printed_shape(text, isbn):
    assert bookmeta.find_isbn(text) == isbn


def test_find_isbn_rejects_a_bad_checksum_and_takes_the_next_valid_one():
    assert bookmeta.find_isbn("ISBN 978-1-80324-776-3") is None
    assert bookmeta.find_isbn("ISBN 9781803247763\nISBN 9781617296864") == "9781617296864"


def test_find_isbn_needs_the_word_isbn():
    assert bookmeta.find_isbn("Order number 9781803247762") is None


# ---------- year ----------


@pytest.mark.parametrize(
    "text, year",
    [(PACKT, 2023), (MANNING, 2021), (OREILLY, 2020), ("Copyright (c) 2019 Someone", 2019)],
)
def test_find_year_reads_the_copyright_line(text, year):
    assert bookmeta.find_year(text) == year


def test_find_year_ignores_a_first_edition_date_and_loose_years():
    assert bookmeta.find_year("First published: June 2020\nIn 1999 we wrote code.") is None
    assert bookmeta.find_year("email copyright@packtpub.com about 2021") is None


def test_find_year_takes_the_latest_year_of_a_reprint():
    assert bookmeta.find_year("© 2019 A.\nCopyright © 2022 A.") == 2022


# ---------- publisher ----------


@pytest.mark.parametrize(
    "text, publisher, how",
    [
        (PACKT, "Packt Publishing Ltd.", "published-by"),
        (MANNING, "Manning Publications Co.", "publisher-line"),
        (OREILLY, "O’Reilly Media, Inc.", "published-by"),
        (
            "Published by Packt Publishing Ltd. Livery Place 35",
            "Packt Publishing Ltd.",
            "published-by",
        ),
        ("**Manning Publications Co.**", "Manning Publications Co.", "publisher-line"),
    ],
)
def test_find_publisher(text, publisher, how):
    assert bookmeta.find_publisher(text) == (publisher, how)


@pytest.mark.parametrize(
    "text",
    [
        "# Social Media",  # a heading in chapter 1 names a topic
        "## Manning Publications Co.",  # a heading, even with a company suffix
        "Bench Press",  # no company suffix: not a publisher line
        "No Starch Press",  # the cost of that rule: left empty rather than guessed
    ],
)
def test_find_publisher_needs_a_company_line_that_is_not_a_heading(text):
    assert bookmeta.find_publisher(text) == (None, "")


def test_find_publisher_ignores_prose_and_job_titles():
    text = (
        "This book was first published by a small press in 2010.\n"
        "Senior Publishing Product Manager: Denim Pinto\n"
    )
    assert bookmeta.find_publisher(text) == (None, "")


# ---------- title and authors ----------


@pytest.mark.parametrize(
    "raw, title",
    [
        (
            "50 Algorithms Every Programmer Should Know",
            "50 Algorithms Every Programmer Should Know",
        ),
        ("  Deep   Learning with Python ", "Deep Learning with Python"),
        ("Untitled", None),
        ("Microsoft Word - draft7.docx", None),
        ("9781617294549_final.indd", None),
        ("", None),
        (None, None),
    ],
)
def test_clean_title(raw, title):
    assert bookmeta.clean_title(raw) == title


def test_split_authors():
    assert bookmeta.split_authors("Heather Adkins, Betsy Beyer; Paul Blankinship & Ana Oprea") == [
        "Heather Adkins",
        "Betsy Beyer",
        "Paul Blankinship",
        "Ana Oprea",
    ]
    assert bookmeta.split_authors("Unknown") == []
    # a comma inside one name is not a separator
    assert bookmeta.split_authors("Richardson, Chris") == ["Richardson, Chris"]
    assert bookmeta.split_authors("John Smith, Jr.; Jane Doe, PhD") == [
        "John Smith, Jr.",
        "Jane Doe, PhD",
    ]
    assert bookmeta.split_authors("Chris Richardson and Chris Richardson") == ["Chris Richardson"]


# ---------- from_text, from_pdf, book.json ----------


def test_from_text_records_each_source():
    meta = bookmeta.from_text(PACKT)
    assert (meta.isbn, meta.year, meta.publisher) == (
        "9781803247762",
        2023,
        "Packt Publishing Ltd.",
    )
    assert meta.sources == {"isbn": "text", "year": "copyright-line", "publisher": "published-by"}
    assert meta.title is None and meta.authors == []  # never guessed from text


def test_from_text_ignores_code_fences():
    # a license header in a chapter-1 sample must not win the year, nor give an ISBN
    text = PACKT + "\n```go\n// Copyright 2025 Google LLC\n// ISBN 9781617296864\n```\n"
    meta = bookmeta.from_text(text)
    assert (meta.year, meta.isbn) == (2023, "9781803247762")
    assert bookmeta.from_text("```\nCopyright 2025 X\n```\n").year is None


def test_from_text_reads_only_the_front_of_the_book():
    back_matter = "x" * bookmeta.FRONT_CHARS + "\nISBN: 9781801073448\n"
    assert bookmeta.from_text(back_matter).isbn is None  # another book's ISBN, at the back


def _pdf(tmp_path, title="Real Title", author="Ann Author, Bob Writer", body=PACKT, pages=3):
    import pymupdf

    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), body if i == 1 else f"Page {i}", fontsize=9)
    doc.set_metadata({"title": title, "author": author})
    path = tmp_path / "book.pdf"
    doc.save(str(path))
    return str(path)


def test_from_pdf_reads_the_metadata_and_the_first_pages(tmp_path):
    meta = bookmeta.from_pdf(_pdf(tmp_path))
    assert meta.title == "Real Title"
    assert meta.authors == ["Ann Author", "Bob Writer"]
    assert (meta.isbn, meta.year, meta.publisher) == (
        "9781803247762",
        2023,
        "Packt Publishing Ltd.",
    )
    assert meta.page_count == 3
    assert meta.sources["title"] == "pdf-metadata" and meta.sources["authors"] == "pdf-metadata"


def test_from_pdf_drops_a_template_title(tmp_path):
    meta = bookmeta.from_pdf(_pdf(tmp_path, title="Microsoft Word - book.docx", author=""))
    assert meta.title is None and meta.authors == [] and "title" not in meta.sources


def test_book_json_round_trips_and_drops_wrong_types(tmp_path):
    meta = bookmeta.from_pdf(_pdf(tmp_path))
    path = str(tmp_path / "book.json")
    bookmeta.write(meta, path)
    assert bookmeta.load(path) == meta

    (tmp_path / "bad.json").write_text(
        json.dumps({"title": 7, "authors": "Ann", "year": "2023", "isbn": "", "sources": []}),
        encoding="utf-8",
    )
    assert bookmeta.load(str(tmp_path / "bad.json")) == BookMeta()


@pytest.mark.parametrize("content", ["{not json", "[1, 2]", ""])
def test_load_gives_none_for_a_file_that_is_not_a_json_object(tmp_path, content):
    (tmp_path / "book.json").write_text(content, encoding="utf-8")
    assert bookmeta.load(str(tmp_path / "book.json")) is None
    assert bookmeta.load(str(tmp_path / "missing.json")) is None


def test_fill_keeps_own_values_and_takes_only_empty_fields():
    own = BookMeta(
        title="T", year=2020, sources={"title": "pdf-metadata", "year": "copyright-line"}
    )
    other = BookMeta(
        title="X", year=2023, isbn="9781617296864", sources={"isbn": "text", "year": "y"}
    )
    got = own.fill(other)
    assert (got.title, got.year, got.isbn) == ("T", 2020, "9781617296864")
    assert got.sources == {"title": "pdf-metadata", "year": "copyright-line", "isbn": "text"}
    assert own.isbn is None  # fill returns a copy


def test_write_for_pdf_never_fails_a_conversion(tmp_path):
    said = []
    (tmp_path / "book.json").write_text('{"title": "an earlier run"}', encoding="utf-8")
    bookmeta.write_for_pdf(str(tmp_path / "missing.pdf"), str(tmp_path), said.append)
    assert not (tmp_path / "book.json").exists()  # a stale book.json would lie about this book
    assert said and said[0].startswith("book metadata: not written")

    said.clear()
    bookmeta.write_for_pdf(_pdf(tmp_path), str(tmp_path), said.append)
    assert bookmeta.load(str(tmp_path / "book.json")).isbn == "9781803247762"
    assert said == [f"book metadata: title, authors, year, isbn, publisher -> {tmp_path}/book.json"]


# ---------- chapter page ranges ----------


def _h(text, page, level=1):
    return {"type": "text", "text": text, "text_level": level, "abs_page": page}


BLOCKS = [
    {"type": "text", "text": "cover art credit", "abs_page": 0},
    _h("Copyright", 2),
    _h("Chapter 1: Overview", 10),
    {"type": "text", "text": "body", "abs_page": 11},
    _h("Summary", 20, level=2),
    _h("Chapter 2: Data", 30),
    _h("Appendix A. Tools", 50, level=2),
    {"type": "code", "code_body": "x", "abs_page": 60},
]


def test_chapter_page_ranges_are_1_based_and_end_before_the_next_chapter():
    front, ranges = bookmeta.chapter_page_ranges(
        BLOCKS, ["Copyright", "Chapter 1: Overview", "Chapter 2: Data", "Appendix A. Tools"]
    )
    assert front == (1, 2)
    assert ranges == [(3, 10), (11, 30), (31, 50), (51, 61)]


def test_chapter_page_ranges_leave_a_gap_rather_than_guess():
    # "Chapter 2" is not in the blocks: chapter 1 then has no known end, and must not swallow it
    _, ranges = bookmeta.chapter_page_ranges(
        BLOCKS, ["Chapter 1: Overview", "Chapter 2 renamed", "Appendix A. Tools"]
    )
    assert ranges == [None, None, (51, 61)]


def test_chapter_page_ranges_match_a_repeated_title_in_order():
    blocks = [_h("Introduction", 1), _h("Part", 5), _h("Introduction", 9), _h("End", 12)]
    _, ranges = bookmeta.chapter_page_ranges(blocks, ["Introduction", "Introduction", "End"])
    assert ranges == [(2, 9), (10, 12), (13, 13)]


def test_chapter_page_ranges_ignore_markdown_escapes_and_case():
    _, ranges = bookmeta.chapter_page_ranges(
        [_h("Using `std::vector`", 4)], ["using std\\:\\:vector"]
    )
    assert ranges == [(5, 5)]


def test_chapter_page_ranges_without_headings_give_nothing():
    assert bookmeta.chapter_page_ranges([], ["A"]) == (None, [None])


# ---------- frontmatter ----------

META = BookMeta(
    title='A "Quoted" Book',
    authors=["Ann Author", "Bob Writer"],
    year=2023,
    isbn="9781803247762",
    publisher="Packt Publishing Ltd.",
    page_count=61,
)


def test_frontmatter_without_metadata_is_unchanged():
    assert chapter_split.frontmatter("T", "b", 1, "s.pdf") == (
        '---\ntitle: "T"\nbook: "b"\nchapter: 1\nsource: "s.pdf"\ntags: [book]\n---\n\n'
    )


def test_frontmatter_round_trips_any_title():
    yaml = pytest.importorskip("yaml")
    for title in ["Fun 😀", "O’Reilly", "𝔸lgebra", 'a "b" \\ c', "x\u0085y"]:
        fm = chapter_split.frontmatter(title, "b", 1, "s.pdf")
        assert yaml.safe_load(fm.split("---\n")[1])["title"] == title


def test_frontmatter_with_metadata_is_valid_yaml():
    fm = chapter_split.frontmatter("T", "b", 3, "s.pdf", META, (11, 30))
    assert "pdf_pages: [11, 30]" in fm
    assert 'isbn: "9781803247762"' in fm  # a string, not an int
    yaml = pytest.importorskip("yaml")
    data = yaml.safe_load(fm.split("---\n")[1])
    assert data == {
        "title": "T",
        "book": "b",
        "book_title": 'A "Quoted" Book',
        "authors": ["Ann Author", "Bob Writer"],
        "year": 2023,
        "isbn": "9781803247762",
        "publisher": "Packt Publishing Ltd.",
        "chapter": 3,
        "pdf_pages": [11, 30],
        "source": "s.pdf",
        "tags": ["book"],
    }


# ---------- the index page ----------


def test_index_escapes_titles_and_links_each_file():
    text = book_index.render(
        "slug",
        "s.pdf",
        META,
        [
            (0, "Front matter", "00-front-matter.md", (1, 2)),
            (1, "Generics <T> | [Part] *one*", "01-generics-t-part-one.md", None),
        ],
    )
    assert '# A "Quoted" Book' in text
    assert "By Ann Author, Bob Writer · Packt Publishing Ltd. · 2023 · ISBN 9781803247762" in text
    assert "| 0 | [Front matter](00-front-matter.md) | 1–2 |" in text
    row = "| 1 | [Generics \\<T\\> \\| \\[Part\\] \\*one\\*](01-generics-t-part-one.md) |  |"
    assert row in text
    assert "tags: [book-index]" in text and "pdf_page_count: 61" in text


def test_index_falls_back_to_the_slug_with_no_metadata():
    text = book_index.render("my-book", "s.pdf", None, [(1, "One", "01-one.md", None)])
    assert '\ntitle: "my-book"\n' in text and "\n# my-book\n" in text and "By " not in text


def test_index_rendering_is_valid_commonmark():
    cmark = pytest.importorskip("cmarkgfm")
    text = book_index.render(
        "s", "s.pdf", META, [(1, "Generics <T> | [x]", "01-generics-t-x.md", (3, 9))]
    )
    html = cmark.github_flavored_markdown_to_html(text.split("---\n", 2)[2])
    assert '<a href="01-generics-t-x.md">Generics &lt;T&gt; | [x]</a>' in html
    assert "<td>3–9</td>" in html


# ---------- the chain, end to end ----------

# the copyright page without its heading, so it lands in the front matter
CHAIN_MD = (
    PACKT.replace("# Copyright\n", "")
    + "\n# Chapter 1: Overview\n\nbody one\n\n# Chapter 2: Data\n\nbody two\n"
)


def _book_dir(tmp_path, with_json=True, with_blocks=True):
    d = tmp_path / "out" / "slug"
    d.mkdir(parents=True)
    (d / "slug.md").write_text(CHAIN_MD, encoding="utf-8")
    if with_json:
        bookmeta.write(
            BookMeta(
                title="Real Title",
                authors=["Ann Author"],
                page_count=61,
                sources={"title": "pdf-metadata", "authors": "pdf-metadata"},
            ),
            str(d / "book.json"),
        )
    if with_blocks:
        (d / "blocks.json").write_text(json.dumps(BLOCKS), encoding="utf-8")
    return d


def _frontmatter(path):
    return Path(path).read_text(encoding="utf-8").split("---\n")[1]


def test_run_chain_writes_enriched_chapters_and_an_index(tmp_path):
    d = _book_dir(tmp_path)
    report = run_chain(str(d / "slug.md"), "slug", source_name="b.pdf", apply=True)

    files = report["chapter_split"]["files"]
    assert [os.path.basename(f) for f in files] == [
        "00-front-matter.md",
        "01-chapter-1-overview.md",
        "02-chapter-2-data.md",
    ]
    ch1 = _frontmatter(files[1])
    assert 'book_title: "Real Title"' in ch1 and 'authors: ["Ann Author"]' in ch1
    assert "year: 2023" in ch1 and 'isbn: "9781803247762"' in ch1  # filled from the text
    assert "pdf_pages: [11, 30]" in ch1
    assert "pdf_pages: [1, 10]" in _frontmatter(files[0])
    index = (d / "chapters" / "slug-index.md").read_text(encoding="utf-8")
    assert "| 0 | [Front matter](00-front-matter.md) | 1–10 |" in index
    assert "| 1 | [Chapter 1: Overview](01-chapter-1-overview.md) | 11–30 |" in index
    assert "| 2 | [Chapter 2: Data](02-chapter-2-data.md) | 31–61 |" in index  # to the last page
    bi = report["book_index"]
    assert bi["meta_from"] == "book.json" and bi["pages_matched"] == 2 and bi["chapters"] == 2
    assert bi["file"] == str(d / "chapters" / "slug-index.md")


def test_run_chain_without_sidecars_keeps_the_old_frontmatter_shape(tmp_path):
    d = _book_dir(tmp_path, with_json=False, with_blocks=False)
    (d / "slug.md").write_text("# Chapter One\n\nbody\n", encoding="utf-8")
    report = run_chain(str(d / "slug.md"), "slug", source_name="b.pdf", apply=True)

    assert _frontmatter(report["chapter_split"]["files"][0]) == (
        'title: "Chapter One"\nbook: "slug"\nchapter: 1\nsource: "b.pdf"\ntags: [book]\n'
    )
    assert (d / "chapters" / "slug-index.md").exists()
    assert (
        report["book_index"]["meta_from"] == "text" and report["book_index"]["blocks"] == "absent"
    )


def test_run_chain_dry_run_writes_no_index(tmp_path):
    d = _book_dir(tmp_path)
    report = run_chain(str(d / "slug.md"), "slug", apply=False)
    assert report["book_index"]["file"] and not (d / "chapters").exists()


def test_run_chain_survives_a_cut_off_blocks_json(tmp_path):
    d = _book_dir(tmp_path)
    (d / "blocks.json").write_text('[{"type": "text", "abs_pa', encoding="utf-8")
    report = run_chain(str(d / "slug.md"), "slug", apply=True)
    assert report["book_index"]["blocks"] == "unreadable"
    assert "pdf_pages" not in _frontmatter(report["chapter_split"]["files"][1])


def test_run_chain_prefers_an_explicit_pdf_over_book_json(tmp_path):
    d = _book_dir(tmp_path)
    pdf = _pdf(tmp_path, title="From The PDF", author="Pdf Person")
    report = run_chain(str(d / "slug.md"), "slug", apply=False, pdf_path=pdf)
    assert report["book_index"]["meta_from"] == "pdf"
    assert report["book_index"]["meta"]["title"] == "From The PDF"


def test_cli_phase5_reports_the_metadata_and_the_page_match(tmp_path, capsys):
    d = _book_dir(tmp_path)
    assert cli.main(["phase5", str(d / "slug.md"), "--book", "slug"]) == 0
    out = capsys.readouterr().out
    assert (
        "book_index: metadata from book.json: title (pdf-metadata), authors (pdf-metadata)," in out
    )
    assert "year (copyright-line), isbn (text), publisher (published-by)" in out
    assert "pdf_pages: 2/2 chapters matched in blocks.json" in out
    assert "(dry-run — would write 3 chapter files and slug-index.md; pass --apply)" in out


def test_yaml_str_keeps_printable_text_and_escapes_the_rest():
    assert chapter_split.yaml_str("O’Reilly Média") == '"O’Reilly Média"'
    assert chapter_split.yaml_str("a\u0085b\u00a0c\u2028d") == '"a\\u0085b\\u00a0c\\u2028d"'
    assert chapter_split.yaml_str('say "hi"\\') == '"say \\"hi\\"\\\\"'
    yaml = pytest.importorskip("yaml")
    for s in ["O’Reilly", "a\u0085b", "x\u00a0y", "😀 emoji", 'q"uote\\']:
        assert yaml.safe_load("v: " + chapter_split.yaml_str(s))["v"] == s


def test_index_name_is_unique_per_book_and_never_overwrites_a_chapter(tmp_path):
    assert book_index.index_name("50-algorithms") == "50-algorithms-index.md"
    assert book_index.index_name("Sample Book") == "sample-book-index.md"
    files, _ = chapter_split.plan(str(tmp_path / "b.md"), "01", text="# Foo Index\n\nbody\n")
    assert files[0].path.endswith("01-foo-index.md")
    assert book_index.build(files, "01-foo", "s.pdf", None) is None  # same name: no index


# ---------- review round 2 ----------


@pytest.mark.parametrize(
    "text, year",
    [
        ("Copyright © 2015, 2021 Author", 2021),  # a reprint run: the latest year wins
        ("Copyright © 2017-2023 Some Press", 2023),
        ("© 2019 and 2022 A. Author", 2022),
        ("Copyright (c) 2020 Someone", 2020),
    ],
)
def test_find_year_reads_a_whole_reprint_run(text, year):
    assert bookmeta.find_year(text) == year


def test_find_year_ignores_a_bare_c_and_code_comments():
    assert bookmeta.find_year("(c) 2048 bytes of buffer") is None  # item (c) of a list
    pdf_page = "// Copyright 2025 Google LLC\n# Copyright 2024 The Kubernetes Authors\n"
    assert bookmeta.from_text(pdf_page + "Copyright © 2023 Packt", markdown=False).year == 2023
    assert bookmeta.from_text(pdf_page, markdown=False).year is None


def test_markdown_keeps_a_copyright_heading():
    # in Markdown a "#" opens a heading, not a comment
    assert bookmeta.from_text("## Copyright © 2020 Google LLC\n").year == 2020


@pytest.mark.parametrize(
    "text",
    [
        "ISBN 13: 978-1-492-08312-2",
        "ISBN (ebook): 9781492083122",
        "eISBN: 9781492083122",
        "e-ISBN 978-1-492-08312-2",
        "ISBN-13 (PDF) 9781492083122",
    ],
)
def test_find_isbn_reads_labelled_shapes(text):
    assert bookmeta.find_isbn(text) == "9781492083122"


def test_index_escapes_obsidian_inline_syntax():
    got = book_index.escape("Pricing: $5 vs $10, ==x==, ~~y~~, &amp; and ![z]")
    assert got == "Pricing: \\$5 vs \\$10, \\=\\=x\\=\\=, \\~\\~y\\~\\~, \\&amp; and \\!\\[z\\]"


def test_a_bare_appendix_heading_is_not_a_boundary_for_page_ranges():
    # chapter_split needs a title after "Appendix A."; page matching uses the same rule
    blocks = [_h("Appendix A.", 3, level=2), _h("Appendix A. Tools", 7, level=2)]
    _, ranges = bookmeta.chapter_page_ranges(blocks, ["Appendix A. Tools"])
    assert ranges == [(8, 8)]


def test_cli_phase5_with_an_unreadable_pdf_stops_cleanly(tmp_path, capsys):
    d = _book_dir(tmp_path)
    rc = cli.main(
        [
            "phase5",
            str(d / "slug.md"),
            "--book",
            "slug",
            "--pdf",
            str(tmp_path / "typo.pdf"),
            "--apply",
        ]
    )
    assert rc == 2
    assert "error: cannot read --pdf" in capsys.readouterr().err
    assert not (d / "chapters").exists()  # nothing written


# ---------- review round 3 ----------


@pytest.mark.parametrize(
    "md",
    [
        "**©2021 by Manning Publications Co. All rights reserved.**",
        "*Copyright © 2021 Packt Publishing*",
        "- Copyright © 2021 Someone",
    ],
)
def test_markdown_emphasis_or_list_keeps_its_copyright_year(md):
    assert bookmeta.from_text(md).year == 2021


def test_pdf_text_skips_a_javadoc_comment_line():
    page = "/*\n * Copyright 2025 Example Inc.\n */\nCopyright © 2021 Packt"
    assert bookmeta.from_text(page, markdown=False).year == 2021


def test_a_copyright_marker_at_a_line_end_reads_the_year_below():
    assert bookmeta.find_year("Copyright ©\n2023 Packt Publishing") == 2023
    assert bookmeta.find_year("Copyright ©\n\n2023") is None  # a blank line ends the statement


@pytest.mark.parametrize(
    "text, isbn",
    [
        ("ISBN 1098108302 (paperback)", "1098108302"),  # an ISBN-10 that starts with 10
        ("ISBN 1098108302 2021", "1098108302"),
        ("ISBN 1300000007", "1300000007"),  # ... and one that starts with 13
        ("ISBN-10 1098108302", "1098108302"),
        ("ISBN10: 1098108302", "1098108302"),
        ("ISBN: 978\u20101\u201080324\u2010776\u20102", "9781803247762"),  # U+2010 hyphens
        ("ISBN 978\u20131\u201380324\u2013776\u20132", "9781803247762"),  # en dashes
    ],
)
def test_find_isbn_keeps_leading_10_or_13_and_unicode_hyphens(text, isbn):
    assert bookmeta.find_isbn(text) == isbn


def test_find_publisher_takes_the_first_candidate_and_never_a_year():
    manning = (
        "Manning Publications Co.\n\nPreface\n\nPublished by Google in 2018, BERT changed NLP.\n"
    )
    assert bookmeta.find_publisher(manning) == ("Manning Publications Co.", "publisher-line")
    assert bookmeta.find_publisher("Published by Google in 2018, BERT changed NLP.") == (None, "")


def test_page_matching_never_jumps_over_a_heading_a_later_title_needs():
    # the blocks say A, B, Summary, C; the Markdown says A, Summary, B, C
    blocks = [_h("A", 1), _h("B", 5), _h("Summary", 40), _h("C", 41)]
    _, ranges = bookmeta.chapter_page_ranges(blocks, ["A", "Summary", "B", "C"])
    assert ranges[0] is None  # A's end is unknown: no range that swallows chapter B
    assert ranges[1] is None and ranges[2] == (6, 41) and ranges[3] == (42, 42)


# ---------- review round 4 ----------


def test_find_year_reads_the_first_statement_not_a_later_license_header():
    page = "Copyright © 2021 Packt Publishing\n" + "body\n" * 40
    header = "/*\nCopyright 2024 The Kubernetes Authors.\n*/\n"  # unfenced, unmarked line
    assert bookmeta.find_year(page + header) == 2021
    # a reprint line close below the first one still wins
    assert bookmeta.find_year("© 2019 A.\n\nCopyright © 2022 A.\n") == 2022


def test_from_pdf_refuses_a_file_that_is_not_a_pdf(tmp_path):
    md = tmp_path / "book.md"
    md.write_text(PACKT, encoding="utf-8")
    with pytest.raises(ValueError, match="is not a PDF"):
        bookmeta.from_pdf(str(md))


def test_page_match_survives_a_pua_glyph_that_symbol_pua_turned_into_a_letter():
    # the block keeps the Symbol-font glyph; the repaired Markdown title holds π
    blocks = [_h("Chapter 3: The \uf070 Constant", 9)]
    _, ranges = bookmeta.chapter_page_ranges(blocks, ["Chapter 3: The π Constant"])
    assert ranges == [(10, 10)]


def test_titles_in_another_script_do_not_all_match_each_other():
    blocks = [_h("Введение", 1), _h("Заключение", 5)]
    _, ranges = bookmeta.chapter_page_ranges(blocks, ["Введение", "Заключение"])
    assert ranges == [(2, 5), (6, 6)]


@pytest.mark.parametrize(
    "content, state",
    [
        (None, "absent"),
        ('[{"type": "te', "unreadable"),
        ('{"a": 1}', "unreadable"),
        ("[]", "empty"),
    ],
)
def test_load_blocks_names_its_state(tmp_path, content, state):
    path = tmp_path / "blocks.json"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    assert bookmeta.load_blocks(str(path)) == (None, state)


def test_cli_says_when_blocks_json_is_there_but_empty(tmp_path, capsys):
    d = _book_dir(tmp_path)
    (d / "blocks.json").write_text("[]", encoding="utf-8")
    assert cli.main(["phase5", str(d / "slug.md"), "--book", "slug"]) == 0
    assert "pdf_pages: blocks.json beside the md holds no blocks" in capsys.readouterr().out


# ---------- final combined review ----------


def test_split_authors_reads_a_serial_comma_list():
    got = bookmeta.split_authors("Brendan Burns, Joe Beda, and Kelsey Hightower")
    assert got == ["Brendan Burns", "Joe Beda", "Kelsey Hightower"]


def test_find_isbn_reads_a_bare_13_label_before_an_isbn13():
    assert bookmeta.find_isbn("ISBN 13 978-0-306-40615-7") == "9780306406157"


def test_non_latin_titles_with_the_same_number_do_not_match():
    blocks = [_h("Часть 1", 3), _h("Глава 1", 9), _h("Глава 2", 20)]
    _, ranges = bookmeta.chapter_page_ranges(blocks, ["Глава 1", "Глава 2"])
    assert ranges == [(10, 20), (21, 21)]


def test_a_chapter_ends_before_the_next_start_even_with_its_material_on_that_page():
    # Packt prints a big "8" above the chapter title; the converter puts it before the heading in
    # reading order. It belongs to chapter 8, so chapter 7 must not take that page.
    blocks = [
        _h("Chapter 7", 197),
        {"type": "text", "text": "body", "abs_page": 228},
        {"type": "text", "text": "8", "abs_page": 229},
        _h("Chapter 8", 229),
    ]
    _, ranges = bookmeta.chapter_page_ranges(blocks, ["Chapter 7", "Chapter 8"])
    assert ranges == [(198, 229), (230, 230)]


def test_clear_sidecars_removes_only_the_sidecars(tmp_path):
    for name in ("blocks.json", "book.json", "slug.md"):
        (tmp_path / name).write_text("x", encoding="utf-8")
    bookmeta.clear_sidecars(str(tmp_path))
    assert sorted(p.name for p in tmp_path.iterdir()) == ["slug.md"]


def test_an_index_page_that_cannot_be_written_does_not_fail_the_chapters(tmp_path):
    d = _book_dir(tmp_path)
    (d / "chapters" / "slug-index.md").mkdir(parents=True)  # a directory where the file goes
    report = run_chain(str(d / "slug.md"), "slug", apply=True)
    assert report["book_index"]["error"] and report["book_index"]["file"] is None
    assert len(report["chapter_split"]["files"]) == 3
    assert all(Path(f).is_file() for f in report["chapter_split"]["files"])
