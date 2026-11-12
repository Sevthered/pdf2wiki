# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Check that a code block is valid in a language: the parser checks of `pdf2wiki listings --check`.

`judge` sorts one block into `ok`, `fragment`, `error` or `not-checked` for one language. See the
`listings` module docstring for what each class means, and for the measurements on a vault.
`other_language` tells whether a block that is an `error` for its tag passes as another language.
`listings --check` uses it to report `wrong-language?`, and `lang_retag` uses it to replace a wrong
tag that the converter gave. The caller supplies the guess (`lang_retag.heuristic`), so this module
does not import `lang_retag`.
"""

from __future__ import annotations

import ast
import json
import re
import textwrap
import tomllib
import warnings
import xml.etree.ElementTree as ET
from collections.abc import Callable

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
UNCHECKED_HINTS = frozenset({"pseudocode", "html", "http"})
_REPL = re.compile(r"^[ \t]*>>>(?: |$)", re.M)
_ELLIPSIS = chr(0x2026)  # the one-character `…` that typesetting puts in place of `...`
# An elision in JSON: `...` or `…` outside a string. A string is blanked first, so "Loading..." in a
# value does not hide a real defect elsewhere in the block.
_JSON_STRING = re.compile(r'"(?:\\.|[^"\\\n])*"')
_JSON_ELISION = re.compile(r"\.\.\.|" + chr(0x2026))


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
    except RecursionError:  # very deep nesting: phase 5 runs this check on each `toml` block
        return "RecursionError"
    return None


def _xml_error(body: str) -> str | None:
    # S314: ElementTree is not hardened against hostile XML. The input is a chapter file of the
    # user's own book on the local disk, which the user chose to check, and `defusedxml` would be a
    # new dependency. Expat (>= 2.4.1, bundled with every supported Python) limits entity expansion.
    try:
        ET.fromstring(body)  # noqa: S314
    except ET.ParseError as e:
        return str(e)
    except RecursionError:  # very deep nesting: phase 5 runs this check on each `xml` block
        return "RecursionError"
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


def checker(lang: str) -> str | None:
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


def judge(lang: str, body: str) -> tuple[str, str | None]:
    """Check `body` as canonical `lang`, without the other-language test: (class, message)."""
    kind = checker(lang)
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


# A statement line that only Python writes. A `python` block with one is Python, also when it fails
# `ast.parse` and the detector names another language: in a vault of 24 books, two such blocks were
# Python with a lost indent (FastAPI `async def`, Keras `import tensorflow as tf`). Each form ends
# its line, so Scala `def f(a: Int): Int = a` and Swift `class C: UIViewController {` do not match.
# A bare `import x` is not here: Swift and Kotlin write it too.
PY_ONLY = re.compile(
    r"^[ \t]*(?:(?:async[ \t]+)?def[ \t]+\w+[ \t]*\(.*\)[ \t]*(?:->[^:\n]*)?:"
    r"|class[ \t]+\w+(?:\(.*\))?:"  # no space before `:`: C++ writes `class D :` above its bases
    r"|from[ \t]+[\w.]+[ \t]+import[ \t]+[\w.*(), \t]+"
    r"|import[ \t]+[\w.]+[ \t]+as[ \t]+\w+)[ \t]*(?:#.*)?$",
    re.M,
)
# The strings and the comments of Python text, strings first: in `s ← '#'` the `#` is in a string.
_PY_STRING = re.compile(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"[^"\n]*"|\'[^\'\n]*\'')
_PY_COMMENT = re.compile(r"#[^\n]*")


def _py_code_only(body: str) -> str:
    """`body` without its Python strings and comments: the text that a pseudocode marker in a
    docstring, a string or a comment does not reach."""
    return _PY_COMMENT.sub("", _PY_STRING.sub('""', body))


def other_language(lang: str, body: str, guess_of: Callable[[str], str]) -> tuple[str, str] | None:
    """`(guess, why)` when `body`, an `error` for canonical `lang`, is code in another language.

    `guess_of` is the detector (`lang_retag.heuristic`), passed in so that this module does not
    import `lang_retag`. Its guess counts when `body` passes the check of the guess as `ok` or as a
    `fragment`. A guess that runs the same check as `lang` proves nothing. A guess with no check
    here (`UNCHECKED_HINTS`) counts when the detector names it only on its own markers, and for a
    `python` block also without the strings and comments: `# x ← 0` is a comment, not pseudocode. A
    `python` block with a `PY_ONLY` line is Python.
    """
    if lang == "python" and PY_ONLY.search(body):
        return None
    guess = guess_of(body)
    if guess in UNCHECKED_HINTS:
        if lang == "python" and guess_of(_py_code_only(body)) != guess:
            return None
        return guess, f"looks like {guess}"
    if checker(guess) not in (None, checker(lang)):
        other, _ = judge(guess, body)
        if other == "ok":
            return guess, f"parses as {guess}"
        if other == "fragment":
            return guess, f"a {guess} fragment"
    return None
