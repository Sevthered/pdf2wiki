#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: MIT

"""Count how well a knowledge vault covers a topic, without reading a page into the model.

    python3 vault_coverage.py <vault> <term> [<term> ...]

TERMS. Each <term> is a Python regular expression, matched without regard to case. Use `.?` where a
name can hold a space or a hyphen: 'circuit.?breaker'. Join synonyms with `|`: 'retry|backoff'.
Escape special characters: 'c\\+\\+'. Use `\\b` for a whole word: '\\bnat\\b'. `^` and `$` match at
the start and end of a line. Do not use POSIX classes such as [[:alpha:]].

COUNTS. For each term the script counts the Markdown files under <vault>/wiki/concepts and
<vault>/wiki/entities (subfolders too):

- filename: the file name (without .md) matches;
- heading:  the text of a Markdown heading (# to ######) matches. A line in the YAML frontmatter or
            in a fenced code block is never a heading (CommonMark fence rules);
- body:     the text of the file matches anywhere.

OUTPUT. One line per term, `term F/H/B VERDICT`. The verdict is COVERED (a filename or heading
match), PASSING (body matches only) or NONE. Under it, at most 15 filename and 15 heading matches,
and for a PASSING term at most 15 body matches with their first matching text. The last line,
`Coverage: ...`, joins the term lines.

The standard library only, so the plugin needs nothing installed. Exit 0 on success, 2 on a usage
error, a vault with no wiki/ folder, or an invalid regular expression (checked before any scan).
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

FOLDERS = ("concepts", "entities")
FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})")
HEADING = re.compile(r"^ {0,3}#{1,6}(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$")
MAX_LINES = 15


@dataclass
class Page:
    rel: str
    stem: str
    text: str
    headings: list[str]


def strip_frontmatter(lines: list[str]) -> list[str]:
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() in ("---", "..."):
                return lines[i + 1 :]
    return lines


def headings(text: str) -> list[str]:
    """The text of the ATX headings of a Markdown page, outside the frontmatter and the code fences.

    A fence closes only with the same character, at least as long as the opening run, and nothing
    else on the line (CommonMark). So ``` inside a ```` block, or ~~~ inside ```, stays code.
    """
    out: list[str] = []
    fence: tuple[str, int] | None = None
    for line in strip_frontmatter(text.splitlines()):
        if fence:
            char, size = fence
            stripped = line.strip()
            indent = len(line) - len(line.lstrip(" "))
            if indent <= 3 and len(stripped) >= size and set(stripped) == {char}:
                fence = None
            continue
        m = FENCE_OPEN.match(line)
        if m:
            run = m.group(1)
            if run[0] == "~" or "`" not in line[m.end() :]:  # a ``` info string has no backtick
                fence = (run[0], len(run))
                continue
        h = HEADING.match(line)
        if h:
            out.append(h.group(1) or "")
    return out


def load(vault: Path) -> list[Page]:
    wiki = vault / "wiki"
    found: list[Page] = []
    for folder in FOLDERS:
        if not (wiki / folder).is_dir():
            continue
        for path in sorted(p for p in (wiki / folder).rglob("*.md") if p.is_file()):
            text = path.read_text(encoding="utf-8", errors="replace")
            found.append(Page(path.relative_to(wiki).as_posix(), path.stem, text, headings(text)))
    return found


def snippet(text: str, rx: re.Pattern[str]) -> str:
    m = rx.search(text)
    if not m:
        return ""
    start = text.rfind("\n", 0, m.start()) + 1
    end = text.find("\n", m.end())
    line = " ".join(text[start : end if end != -1 else len(text)].split())
    return line if len(line) <= 120 else line[:117] + "..."


def capped(lines: list[str], label: str) -> list[str]:
    out = lines[:MAX_LINES]
    if len(lines) > MAX_LINES:
        out.append(f"{label}: ... {len(lines) - MAX_LINES} more")
    return out


def count(pages: list[Page], term: str, rx: re.Pattern[str]) -> tuple[str, list[str]]:
    """The summary `term F/H/B VERDICT` and the detail lines for one term."""
    by_name = [p.rel for p in pages if rx.search(p.stem)]
    by_heading = []
    for p in pages:
        hit = next((h for h in p.headings if rx.search(h)), None)
        if hit is not None:
            by_heading.append(f"{p.rel}: # {hit}")
    by_body = [p for p in pages if rx.search(p.text)]
    if by_name or by_heading:
        verdict = "COVERED"
    elif by_body:
        verdict = "PASSING"
    else:
        verdict = "NONE"
    summary = f"{term} {len(by_name)}/{len(by_heading)}/{len(by_body)} {verdict}"
    detail = capped([f"filename: {r}" for r in by_name], "filename")
    detail += capped([f"heading: {h}" for h in by_heading], "heading")
    if verdict == "PASSING":
        detail += capped([f"body: {p.rel}: {snippet(p.text, rx)}" for p in by_body], "body")
    return summary, detail


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] in ("-h", "--help"):
        print((__doc__ or "").strip(), file=sys.stderr)
        return 2
    vault = Path(argv[0]).expanduser()
    if not (vault / "wiki").is_dir():
        print(f"error: {vault}/wiki is not a folder", file=sys.stderr)
        return 2
    compiled = []
    for term in argv[1:]:
        try:
            compiled.append((term, re.compile(term, re.IGNORECASE | re.MULTILINE)))
        except re.error as e:
            print(f"error: {term!r} is not a valid regular expression: {e}", file=sys.stderr)
            return 2
    pages = load(vault)
    summaries = []
    for term, rx in compiled:
        summary, detail = count(pages, term, rx)
        print(summary)
        for line in detail:
            print(f"  {line}")
        summaries.append(summary)
    print("Coverage: " + "; ".join(summaries))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
