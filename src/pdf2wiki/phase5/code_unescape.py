# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Strip spurious markdown-punctuation backslash-escapes INSIDE code blocks of a converted book .md.

MinerU's markdown emitter escapes bare special chars from the text/VLM layer (`$`->`\\$`, `*`->`\\*`,
`~`->`\\~`, backtick, `#`, `_`). Inside a fenced code block these render literally (the backslash is
visible) and corrupt shell prompts, pointers, and config. We unescape ONLY a conservative set of
punctuation that is (a) markdown-special and (b) essentially never a real string/regex escape, so real
escapes (`\\n \\t \\d \\s \\w \\"`, escaped-backslash `\\\\`) and regex-structural metachars
(`. ( ) [ ] { } + ? | ^`) are preserved.

Fixes ONLY within ``` code blocks (never prose, where markdown escaping is correct) and never inside
```mermaid. Idempotent. See bug-backslash-escape-stripped (the `\\_`-only fix was incomplete: it left
`\\$ \\* \\~` on both the flagged pipeline path and the hybrid path).
"""

import re

from . import fences

# Unescape \X -> X for X in this set. `(?<!\\)` keeps a real escaped-backslash (\\X) intact.
UNESCAPE = r"$*~_`#@%&!"
_PAT = re.compile(r"(?<!\\)\\([" + re.escape(UNESCAPE) + r"])")


def _fix_body(body: str) -> tuple[str, list[tuple[str, str]]]:
    changes: list[tuple[str, str]] = []
    out_lines = []
    for ln in body.split("\n"):
        nl = _PAT.sub(r"\1", ln)
        if nl != ln:
            changes.append((ln.strip(), nl.strip()))
        out_lines.append(nl)
    return "\n".join(out_lines), changes


def unescape(md: str) -> tuple[str, list[tuple[str, str, str]]]:
    """Return (new_md, list of (fence_tag, old_line, new_line))."""
    allchanges: list[tuple[str, str, str]] = []

    def repl(blk: fences.Block) -> str | None:
        if blk.is_mermaid:
            return None
        newbody, ch = _fix_body(blk.body)
        allchanges.extend((blk.lang, o, n) for o, n in ch)
        return blk.rebuild(body=newbody)

    return fences.transform(md, repl), allchanges
