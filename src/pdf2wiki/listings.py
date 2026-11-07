# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Export the code blocks of one converted book, and check whether each one parses.

A book's code is the part a reader most wants to run, and the part a conversion most often breaks:
a curly quote typeset into a string, an indent lost at a page break, a callout label pulled into the
code, a wrong fence tag. `pdf2wiki listings` finds every code block of one book with the shared
lexer (`phase5/fences.py`: backtick fences only, an unclosed opener is not a block), counts them,
writes each one to its own file with `--out`, and with `--check` runs a standard-library parser over
each one.

**Why a failure is not an error.** A book shows code in pieces. Measured on a vault of 24 converted
books (11,544 blocks in chapter files), a plain `ast.parse` fails for 725 of 1,314 `python` blocks,
and the bracket check fails for 389 of 1,163 `go` blocks. Most of those pieces are intended: a REPL
session, an elided body, a method shown without its class, the last part of a function. So each
failure goes into ONE class, and `--check` always exits 0:

- `fragment`: the block is a piece of a program by design. Python: a REPL session (`>>>` prompts),
  an elision (`…`), or an indented excerpt, when the block parses after the prompts come off, after
  `…` becomes `...`, after `textwrap.dedent`, or inside an `if 1:` body (which also takes a comment
  at column 0 above indented code). `ast.parse` accepts `return`, `await` and `break` at the top
  level, so a function-body wrap adds nothing. Brace languages: the brackets nest correctly, and some
  only open before the block or close after it. JSON: an elision, a member list without its braces,
  several documents in a row, or a cut as for a brace language. XML: several top-level elements.
- `wrong-language?`: the block fails for its tag, and the detector of `phase5/lang_retag.py`
  (`heuristic`) names another language whose check it passes, or of which it is a fragment. A
  bracket balance alone is too weak a signal, but the detector only names a language on that
  language's own markers (`package main`, `func (s *S)`, `public class`, `console.log`). It also
  counts when the detector names a language with no check here on a marker that the tag cannot
  have: pseudocode (a `←` arrow), html (the block opens with an HTML element) or http (the block
  opens with a request or status line).
- `error`: everything else, with the parser's message.

Measured on the same vault: of 4,803 blocks in a checked language, 2,883 are `ok`, 1,157 are a
`fragment`, 354 are `wrong-language?` and 409 are an `error`. In a random sample, 20 of 20
`wrong-language?` blocks had a wrong tag (Go and Java under `python`, and pseudocode). 10 of 10 `error` blocks were broken: 6 in the code (a lost indent, callout text
in the code, a string broken over two lines), 4 a wrong tag that the detector does not name.

A Python block that ends inside an open bracket stays an `error`. The Python parser knows the
statements, so an excerpt cut between statements already passes as an indented excerpt. A cut inside
a call is a block that the converter split at a page break. The bracket check of a brace language
cannot tell these two apart, so there every cut is a fragment.

**Captions.** A "Listing 4.1" caption sits above its fence in converter output, often with blank
lines and a `<!-- code-verify ... -->` comment between them. So a caption is attached when the
paragraph directly above the opener (blank lines and one-line HTML comments skipped) is a listing
caption by the rules of `link` (`phase5/xref.py`): the same paragraph breaks, the same rejection of
prose such as "Listing 4.1 shows", and the fence within two non-blank lines. Measured on the vault:
`link` finds 529 listing captions, and 474 of them attach. Of the other 55, 40 have a code line, a
callout or prose before the next block, 9 have a table or an image next (the converter did not keep
the code as code), and 6 sit below a fence.
"""

from __future__ import annotations

import ast
import collections
import json
import os
import re
import textwrap
import tomllib
import warnings
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

from .phase5 import fences, lang_retag, xref

CLASSES = ("ok", "fragment", "wrong-language?", "error", "not-checked")
# Tags that name one of the checked languages but are in neither alias table of lang_retag.
_ALIASES = {"python3": "python", "golang": "go"}
_BRACE = frozenset(
    {
        "go", "c", "cpp", "java", "javascript", "typescript", "rust",
        "csharp", "kotlin", "swift", "scala", "php", "dart", "groovy",
    }
)  # fmt: skip
# A `'` starts a character literal, not a string, in these languages. A Rust lifetime (`<'a>`) or a
# C++ digit separator (`1'000`) must not open a string that swallows the rest of the line.
_CHAR_LITERAL = frozenset(
    {"go", "c", "cpp", "java", "csharp", "kotlin", "rust", "scala", "swift", "json"}
)
_CHAR = re.compile(r"'(?:\\[^'\n]{1,10}|[^'\\\n]{1,2})'")
# A backtick string can hold newlines and brackets in Go (raw string) and JS/TS (template literal).
_BACKTICK = frozenset({"go", "javascript", "typescript"})
_PAIRS = {"(": ")", "[": "]", "{": "}"}
# Detector results with no check here, which the detector reaches only on a marker that no checked
# language has: a `←` arrow or a brace-less `function f(x)` header (pseudocode), a block that opens
# with an HTML element (html), or one that opens with an HTTP request or status line (http).
_UNCHECKED_HINTS = frozenset({"pseudocode", "html", "http"})
_REPL = re.compile(r"^[ \t]*>>>(?: |$)", re.M)
_ELLIPSIS = chr(0x2026)  # the one-character `…` that typesetting puts in place of `...`
# An elision in JSON: `...` or `…` outside a string. A string is blanked first, so "Loading..." in a
# value does not hide a real defect elsewhere in the block.
_JSON_STRING = re.compile(r'"(?:\\.|[^"\\\n])*"')
_JSON_ELISION = re.compile(r"\.\.\.|" + chr(0x2026))
# One line at a time, so re.S changes nothing here. It keeps CodeQL py/bad-tag-filter quiet, which
# flags a comment pattern whose `.` cannot cross a newline. A browser also ends a comment at --!>.
_COMMENT = re.compile(r"^[ \t]*<!--.*--!?>[ \t]*$", re.S)
# Emphasis on the "Listing X.Y" label, a `*word*` run (not inside a word), and a code span.
_LABEL_EM = re.compile(r"^(\*\*|__|\*|_)(Listing[ \t]+[^\s*_]+)\1(?=[\s.:]|$)")
_STAR_EM = re.compile(r"(?<![\w*\\])(\*\*|\*)(?=[^\s*])(.+?)(?<=[^\s*])\1(?![\w*])")
_CODE_SPAN = re.compile(r"(`+[^`]*`+)")
# A CommonMark backslash escape of ASCII punctuation: MinerU writes `kafka\_cluster.yml`.
_ESCAPE = re.compile(r"\\([!-/:-@\[-`{-~])")
_ANCHOR = re.compile(r'<a id="[^"]*"></a>')
# One extension per language: the first file extension lang_retag.EXT maps to it ("py", not "pyw").
_EXT: dict[str, str] = {}
for _ext, _lang in lang_retag.EXT.items():
    _EXT.setdefault(_lang, _ext)


class OutDirError(Exception):
    """`--out` names a directory that is not empty, or a file."""


@dataclass(frozen=True)
class Listing:
    """One code block of one chapter file."""

    chapter: str  # the chapter file name, such as `07-chapter-4.md`
    index: int  # 1-based position of the block in its chapter
    line: int  # 1-based line of the opening fence
    lang: str  # the fence tag as `fences.Block.lang` reads it, `""` when there is none
    caption: str | None  # the caption text without markup, such as `Listing 4.1 The class`
    number: str | None  # the listing number of the caption, such as `4.1`
    body: str  # the text between the fences, as the chapter text holds it


@dataclass(frozen=True)
class Check:
    """The result of `--check` for one block."""

    cls: str  # one of CLASSES
    language: str  # the language the check ran for (the canonical tag), `""` when none
    message: str | None  # the parser message, or why the block is a fragment or another language


def canonical(tag: str) -> str:
    """The canonical language name of a fence tag: `py` and `python3` are `python`."""
    tag = tag.lower()
    tag = _ALIASES.get(tag, tag)
    return lang_retag.CANON.get(tag, lang_retag.EXT.get(tag, tag))


def extension(tag: str) -> str:
    """The file extension for a fence tag, from lang_retag's alias table. Unknown: `txt`."""
    return _EXT.get(canonical(tag), "txt")


def _caption(f: xref._File, opener: int) -> tuple[str, str] | None:
    """The (caption text, number) of the "Listing X.Y" caption directly above line `opener`.

    The paragraph rules are `link`'s (`xref._File`), so both commands find the same captions: a
    paragraph starts after a blank line, a heading, an image, a fence or an HTML block, and a
    heading, a list item, a table row or a fence ends one. A caption that is not a heading needs
    the fence within two non-blank lines, as `link` needs an image, a fence or a table there.
    """
    j = opener - 1
    while j >= f.start and (not f.lines[j].strip() or _COMMENT.match(f.lines[j])):
        j -= 1
    if j < f.start or not f.is_text(j) or j in f.opaque:
        return None  # the frontmatter, a fence, display math or an HTML block is directly above
    i = j
    while not f.starts_paragraph(i) and not xref._INTERRUPT.match(f.lines[i]):
        i -= 1  # up to the first line of the paragraph that ends directly above the fence
    line = f.lines[i]
    h = xref._HEADING.match(line)
    text = h.group("text") if h else line
    m = xref._CAPTION.match(text)
    if m is None or m.group("kind") != "Listing" or not xref._is_caption(text, m, bool(h)):
        return None
    if not h and not f.near_block(i):
        return None
    return _clean_caption(text), m.group("num")


def _clean_caption(text: str) -> str:
    """The caption text without anchors, emphasis and backslash escapes. `__init__` stays.

    Converters set emphasis on the label (`**Listing 4.1** Title`) or on the whole caption
    (`*Listing 4.1 Title*`), and an author can set a word in `*...*`. Only those markers come off:
    a `_` inside the caption text is an identifier far more often than emphasis.
    """
    text = xref._BLOCK_ID.sub("", _ANCHOR.sub("", text)).strip()
    text = _LABEL_EM.sub(r"\2", text)
    for d in ("**", "__", "*", "_"):  # emphasis on the whole caption; the label is done above
        if text.startswith(d) and text.endswith(d) and len(text) > 2 * len(d):
            text = text[len(d) : -len(d)]
            break
    parts = _CODE_SPAN.split(text)  # a code span keeps its asterisks and backslashes: `*ptr`
    return "".join(
        p if p.startswith("`") else _ESCAPE.sub(r"\1", _STAR_EM.sub(r"\2", p)) for p in parts
    )


def scan(files: dict[str, str]) -> list[Listing]:
    """Every code block of every chapter file, in file-name order, then document order."""
    out: list[Listing] = []
    for name in sorted(files):
        f = xref._File(name, files[name])
        for n, blk in enumerate(fences.blocks(files[name]), 1):
            cap = _caption(f, blk.start)
            out.append(
                Listing(
                    chapter=name,
                    index=n,
                    line=blk.start + 1,
                    lang=blk.lang,
                    caption=cap[0] if cap else None,
                    number=cap[1] if cap else None,
                    body=blk.body,
                )
            )
    return out


# --- the checks ----------------------------------------------------------------------------------
# Each returns None when the text passes, or the parser's message. Line numbers in a message count
# from the first line of the block body.


def _python_error(body: str) -> str | None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # SyntaxWarning: invalid escape sequence, and the like
        try:
            ast.parse(body)
        except SyntaxError as e:
            return f"{e.msg} (line {e.lineno})"
        except (ValueError, RecursionError) as e:  # a NUL byte before 3.12; very deep nesting
            return str(e) or type(e).__name__
    return None


def _json_error(body: str) -> str | None:
    # Plain ValueError too: a number over Python's 4,300-digit limit for int() is not a
    # JSONDecodeError, and must be a finding, not a crash of --check.
    try:
        json.loads(body)
    except (ValueError, RecursionError) as e:
        return str(e) or type(e).__name__
    return None


def _toml_error(body: str) -> str | None:
    # The result follows the running Python: measured, the tomllib of 3.15 accepts an inline table
    # over two lines (TOML 1.1) that the tomllib of 3.13 rejects.
    try:
        tomllib.loads(body)
    except ValueError as e:  # TOMLDecodeError, and the int() digit limit
        return str(e)
    return None


def _xml_error(body: str) -> str | None:
    # S314: ElementTree is not hardened against hostile XML. The input is a chapter file of the
    # user's own book on the local disk, which the user chose to check, and `defusedxml` would be a
    # new dependency. Expat (>= 2.4.1, bundled with every supported Python) limits entity expansion.
    try:
        ET.fromstring(body)  # noqa: S314
    except ET.ParseError as e:
        return str(e)
    return None


def _xml_elements(body: str) -> int:
    """How many top-level elements `body` holds when it parses inside one root element, else 0.

    Text alone (`mvn clean install`) parses inside a root too, so the count must be checked.
    """
    try:
        return len(ET.fromstring(f"<_>{body}</_>"))  # noqa: S314  # see _xml_error
    except ET.ParseError:
        return 0


def _brace_error(body: str, lang: str) -> tuple[str | None, bool]:
    """Check that `()[]{}` balance outside strings and comments: (message, crossed).

    `crossed` is True when a bracket closes an opener of another kind, such as `(` closed by `}`.
    Without a crossed pair, the block is a contiguous piece of a balanced program: the missing
    openers come before it and the missing closers after it.
    """
    stack: list[tuple[str, int]] = []
    unmatched: tuple[str, int] | None = None
    i, n, line = 0, len(body), 1

    def skip_to(end: str, start: int) -> int:
        """Index after the next `end` from `start` (the end of the body when there is none)."""
        nonlocal line
        j = body.find(end, start)
        stop = n if j < 0 else j + len(end)
        line += body.count("\n", i, stop)
        return stop

    while i < n:
        ch = body[i]
        if body.startswith("//", i):
            j = body.find("\n", i)
            i = n if j < 0 else j  # the newline itself is counted below
        elif body.startswith("/*", i):
            i = skip_to("*/", i + 2)
        elif body.startswith('"""', i):  # Kotlin, Scala, Swift, Groovy, Dart, Java text blocks
            i = skip_to('"""', i + 3)
        elif ch == "`" and lang in _BACKTICK:
            i = skip_to("`", i + 1)
        elif ch == '"' or (ch == "'" and lang not in _CHAR_LITERAL):
            # A string ends at its quote or at the end of the line: a quote the converter lost
            # must not swallow the rest of the block.
            j = i + 1
            while j < n and body[j] not in (ch, "\n"):
                if body.startswith("\\\n", j):
                    line += 1  # a C line continuation keeps the string open on the next line
                j += 2 if body[j] == "\\" else 1
            i = j + 1 if j < n and body[j] == ch else j
        elif ch == "'":
            m = _CHAR.match(body, i)
            i = m.end() if m else i + 1
        else:
            if ch == "\n":
                line += 1
            elif ch in _PAIRS:
                stack.append((ch, line))
            elif ch in ")]}":
                if not stack:
                    unmatched = unmatched or (ch, line)
                else:
                    o, oline = stack.pop()
                    if _PAIRS[o] != ch:
                        return f"'{o}' at line {oline} closed by '{ch}' at line {line}", True
            i += 1
    if unmatched:
        return f"unmatched '{unmatched[0]}' at line {unmatched[1]}", False
    if stack:
        return f"unclosed '{stack[0][0]}' from line {stack[0][1]}", False
    return None, False


def _checker(lang: str) -> str | None:
    """The name of the check that runs for a canonical language, or None when there is none."""
    if lang in ("python", "json", "toml", "xml"):
        return lang
    return "brace" if lang in _BRACE else None


def _python_fragment(body: str) -> str | None:
    """Why a failing Python block is a fragment, or None when it is not one."""
    why = "an indented excerpt"
    if _REPL.search(body):
        # Keep the code of a session and blank its output, so line numbers stay the same.
        kept = []
        for ln in body.split("\n"):
            s = ln.lstrip()
            if s.startswith((">>> ", "... ")) or s in (">>>", "..."):
                kept.append(s[4:])
            else:
                kept.append("")
        body = "\n".join(kept)
        why = "a REPL session"
    if _ELLIPSIS in body:
        body = body.replace(_ELLIPSIS, "...")
        why = why if why == "a REPL session" else "an elision"
    flat = textwrap.dedent(body)
    for text in (body, flat, "if 1:\n" + textwrap.indent(flat, " ")):
        if _python_error(text) is None:
            return why
    return None


def _judge(lang: str, body: str) -> tuple[str, str | None]:
    """Check `body` as canonical `lang`, without the other-language test: (class, message)."""
    kind = _checker(lang)
    if kind is None:
        return "not-checked", None
    if kind == "brace":
        msg, crossed = _brace_error(body, lang)
        if msg is None:
            return "ok", None
        return ("error", msg) if crossed else ("fragment", f"a cut excerpt: {msg}")
    if kind == "python":
        msg = _python_error(body)
        if msg is None:
            return "ok", None
        why = _python_fragment(body)
        return ("fragment", why) if why else ("error", msg)
    if kind == "json":
        msg = _json_error(body)
        if msg is None:
            return "ok", None
        if _JSON_ELISION.search(_JSON_STRING.sub('""', body)):
            return "fragment", "an elision"
        if _json_error("{" + body.strip().rstrip(",") + "}") is None:
            return "fragment", "a member list without its braces"
        if _json_documents(body) > 1:
            return "fragment", "several JSON documents"
        cut, crossed = _brace_error(body, "json")
        if cut and not crossed:
            return "fragment", f"a cut excerpt: {cut}"
        return "error", msg
    if kind == "toml":
        msg = _toml_error(body)
        return ("ok", None) if msg is None else ("error", msg)
    msg = _xml_error(body)
    if msg is None:
        return "ok", None
    if _xml_elements(body) > 1:
        return "fragment", "several top-level elements"
    return "error", msg


def _json_documents(body: str) -> int:
    """How many JSON values follow each other in `body`; 0 when any of them does not parse."""
    dec = json.JSONDecoder()
    i, n, count = 0, len(body), 0
    while True:
        while i < n and body[i].isspace():
            i += 1
        if i == n:
            return count
        try:
            _, i = dec.raw_decode(body, i)
        except (ValueError, RecursionError):
            return 0
        count += 1


def check(tag: str, body: str) -> Check:
    """Check one block. See the module docstring for the classes."""
    lang = canonical(tag)
    cls, msg = _judge(lang, body)
    if cls in ("ok", "fragment", "not-checked"):
        return Check(cls, lang if cls != "not-checked" else "", msg)
    guess = lang_retag.heuristic(body)
    if guess in _UNCHECKED_HINTS:
        return Check("wrong-language?", lang, f"looks like {guess}")
    if _checker(guess) not in (None, _checker(lang)):
        other, _ = _judge(guess, body)
        if other == "ok":
            return Check("wrong-language?", lang, f"parses as {guess}")
        if other == "fragment":
            return Check("wrong-language?", lang, f"a {guess} fragment")
    return Check("error", lang, msg)


# --- the report and the export -------------------------------------------------------------------


def report(found: list[Listing], checks: list[Check] | None) -> dict[str, Any]:
    """Counts by language and chapter, and with `checks` the classes and the findings."""
    langs = collections.Counter(x.lang or "(none)" for x in found)
    chapters = collections.Counter(x.chapter for x in found)
    rep: dict[str, Any] = {
        "blocks": len(found),
        "captions": sum(1 for x in found if x.caption),
        "languages": dict(langs.most_common()),
        "chapters": dict(sorted(chapters.items())),
    }
    if checks is not None:
        classes: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
        findings = []
        for x, c in zip(found, checks, strict=True):
            if c.cls == "not-checked":
                continue
            classes[c.language][c.cls] += 1
            if c.cls in ("error", "wrong-language?"):
                findings.append(
                    {
                        "chapter": x.chapter,
                        "line": x.line,
                        "lang": x.lang,
                        "class": c.cls,
                        "message": c.message,
                    }
                )
        order = sorted(classes, key=lambda k: (-sum(classes[k].values()), k))
        rep["checked"] = sum(sum(classes[k].values()) for k in order)
        rep["classes"] = {k: {c: classes[k][c] for c in CLASSES if classes[k][c]} for k in order}
        rep["findings"] = findings
    return rep


def summary_lines(rep: dict[str, Any]) -> list[str]:
    """The report as text lines for a terminal."""
    langs: dict[str, int] = rep["languages"]
    chapters: dict[str, int] = rep["chapters"]
    out = [
        f"listings: {rep['blocks']} code blocks in {len(chapters)} chapter files, "
        f"{rep['captions']} with a Listing caption",
        "by language:",
    ]
    out += [f"  {k:<16} {v:>5}" for k, v in langs.items()]
    out.append("by chapter file:")
    out += [f"  {k:<60} {v:>5}" for k, v in chapters.items()]
    if "classes" in rep:
        classes: dict[str, dict[str, int]] = rep["classes"]
        out.append(f"check: {rep['checked']} blocks in a checked language")
        for lang, counts in classes.items():
            out.append(f"  {lang:<16} " + "  ".join(f"{c} {n}" for c, n in counts.items()))
        findings: list[dict[str, Any]] = rep["findings"]
        if findings:
            out.append("error and wrong-language? blocks:")
            out += [
                f"  {f['chapter']}:{f['line']} {f['lang']} {f['class']}: {f['message']}"
                for f in findings
            ]
    if "out" in rep:
        out.append(f"wrote {rep['written']} files and index.json to {rep['out']}")
    return out


def _file_name(x: Listing, width: int) -> str:
    suffix = f"-listing-{xref._key(x.number).replace('.', '-')}" if x.number else ""
    return f"{x.index:0{width}d}{suffix}.{extension(x.lang)}"


def export(found: list[Listing], out_dir: str, checks: list[Check] | None) -> int:
    """Write each block to `out_dir/<chapter stem>/<NN>[-listing-X-Y].<ext>`, and `index.json`.

    `out_dir` must not exist or must be empty: the export never mixes with older files. Every file
    is created exclusively, so nothing is ever overwritten. A body is written as `scan` got it, with
    no newline translation. `read_book_dir` reads a chapter as text with LF line ends, so a block of
    a CRLF chapter file is written with LF. Returns the number of block files.
    """
    try:
        os.makedirs(out_dir, exist_ok=True)
    except FileExistsError as e:  # a file of that name
        raise OutDirError(f"{out_dir} exists and is not a directory") from e
    if os.listdir(out_dir):
        raise OutDirError(f"{out_dir} is not empty: name a new or empty directory")
    per_chapter = collections.Counter(x.chapter for x in found)
    index = []
    for n, x in enumerate(found):
        stem = os.path.splitext(x.chapter)[0]
        width = max(2, len(str(per_chapter[x.chapter])))
        rel = f"{stem}/{_file_name(x, width)}"
        if x.index == 1:
            os.mkdir(os.path.join(out_dir, stem))
        _write_new(os.path.join(out_dir, rel), x.body)
        entry: dict[str, object] = {
            "chapter": x.chapter,
            "line": x.line,
            "lang": x.lang,
            "caption": x.caption,
            "path": rel,
        }
        if checks is not None:
            c = checks[n]
            entry["check"] = {"class": c.cls, "message": c.message}
        index.append(entry)
    _write_new(
        os.path.join(out_dir, "index.json"), json.dumps(index, indent=1, ensure_ascii=False) + "\n"
    )
    return len(found)


def _write_new(path: str, text: str) -> None:
    """Create `path` and write `text` as UTF-8 with no newline translation. Never overwrites."""
    with open(path, "x", encoding="utf-8", newline="") as fh:
        fh.write(text)
