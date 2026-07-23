# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Repair VLM-transcribed Mermaid blocks so they render (and stay searchable).

The hybrid/VLM pass stuffs request/response JSON into node labels, producing parse-breakers:
literal `\\n`, `&quot;` entities, quotes-inside-quoted-labels, JSON `[]{}` brackets that collide
with mermaid shape syntax, and unclosed labels. We sanitize each node label while preserving its
text (the searchable value):
  - `\\n` -> `<br>` (mermaid line break); collapse repeats
  - `&quot;` and any inner `"` -> `'`
  - inner `[] {}` -> `()` (avoid shape-delimiter collision)
  - close an unclosed `["...` label at segment end
Lines are split on arrow ops first so each node is isolated (greedy inner-label match is then safe
even when a label contains stray quotes/brackets). Never changes non-mermaid fences.
Validation is a parse-breaker score (proxy), not a real mermaid parse.
"""

import re

MERBLOCK = re.compile(r"^(```mermaid\n)(.*?)^(```)", re.S | re.M)
ARROW = re.compile(r"(\s*(?:-\.->|--[>x]|==>|===|-\.-|---|~~~)\s*)")  # keep arrows as separators
# id (or `subgraph name`) + shape-open + "label" + close. Prefix allows a `subgraph name ` lead-in.
NODE = re.compile(r'^([\w&;\s]*?)([\[\{\(])"(.*)"([\]\}\)])(.*)$')
OPEN_ONLY = re.compile(r'^([\w&;\s]*?)([\[\{\(])["\'](.*)$')  # unclosed / mismatched-quote label
CLOSE = {"[": "]", "{": "}", "(": ")"}
ORPHAN_TAIL = re.compile(
    r"([\]\}\)])[\s\}\]\)]*(?:<br>[\s\}\]\)]*)*$"
)  # stray brackets/br after a close


def _san_inner(s: str) -> str:
    s = s.replace("\\", "")  # drop stray backslashes (\' escape noise)
    s = s.replace('"', "'").replace("[", "(").replace("]", ")").replace("{", "(").replace("}", ")")
    s = re.sub(r"(<br>\s*)+", "<br>", s)
    return s.strip("<br> ").strip()


def _fix_segment(seg: str) -> str:
    m = NODE.match(seg)
    if m:
        pre, op, inner, _cl, post = m.groups()
        return f'{pre}{op}"{_san_inner(inner)}"{CLOSE[op]}{post}'  # emit close MATCHING the opener
    m = OPEN_ONLY.match(seg)  # unclosed label -> close it with a matching bracket
    if m:
        pre, op, inner = m.groups()
        return f'{pre}{op}"{_san_inner(inner)}"{CLOSE[op]}'
    return seg


def _fix_line(ln: str) -> str:
    ln = ln.replace("&quot;", "'").replace("\\n", "<br>")
    parts = ARROW.split(ln)
    for i in range(0, len(parts), 2):  # even indices = node segments
        parts[i] = _fix_segment(parts[i])
    ln = "".join(parts)
    ln = ORPHAN_TAIL.sub(r"\1", ln)  # drop orphan braces/br leaked from multi-line JSON labels
    return ln


def _fix_block(body: str) -> str:
    return "\n".join(_fix_line(l) for l in body.split("\n"))


def issues(body: str) -> int:
    """Count parse-breakers in a block (validation proxy)."""
    n = 0
    n += body.count("\\n") + body.count("&quot;")
    n += sum(l.count('"') % 2 for l in body.split("\n"))
    n += abs(body.count("[") - body.count("]")) + abs(body.count("{") - body.count("}"))
    return n


def repair(md: str) -> tuple[str, dict[str, int]]:
    """Return (new_md, stats dict: blocks_changed, score_before, score_after)."""
    state = {"blocks_changed": 0, "score_before": 0, "score_after": 0}

    def repl(mo: re.Match[str]) -> str:
        body = mo.group(2)
        b0 = issues(body)
        nb = _fix_block(body)
        b1 = issues(nb)
        state["score_before"] += b0
        state["score_after"] += b1
        if nb != body:
            state["blocks_changed"] += 1
        return mo.group(1) + nb + mo.group(3)

    out = MERBLOCK.sub(repl, md)
    return out, state
