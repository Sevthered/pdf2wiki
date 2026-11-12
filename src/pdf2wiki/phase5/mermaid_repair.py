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
even when a label contains stray quotes/brackets). An arrow inside a complete quoted label is label
text, not a split point, unless a node with a quoted shape follows it. Never changes non-mermaid
fences. Validation is a parse-breaker score (proxy), not a real mermaid parse: a line or a block
whose score a repair raises stays as it was. The score does not count `(` and `)`, so this guard
cannot see a lost parenthesis.
"""

import re

from . import fences

ARROW = re.compile(r"(\s*(?:-\.->|--[>x]|==>|===|-\.-|---|~~~)\s*)")  # keep arrows as separators
# id (or `subgraph name`) + shape-open + "label" + close. Prefix allows a `subgraph name ` lead-in.
NODE = re.compile(r'^([\w&;\s]*?)([\[\{\(])"(.*)"([\]\}\)])(.*)$')
OPEN_ONLY = re.compile(r'^([\w&;\s]*?)([\[\{\(])["\'](.*)$')  # unclosed / mismatched-quote label
CLOSE = {"[": "]", "{": "}", "(": ")"}
ORPHAN_TAIL = re.compile(
    r"([\]\}\)])[\s\}\]\)]*(?:<br>[\s\}\]\)]*)*$"
)  # stray brackets/br after a close
OPENER = {c: o for o, c in CLOSE.items()}
# A complete quoted label: an opener, a quoted text without `"`, and a closer. An arrow inside
# one is label text, such as `G["If valid --> vote"]`, and is not an edge.
QUOTED_LABEL = re.compile(r'[\[\{\(]"[^"]*"[\]\}\)]')
# But an arrow to a node with a quoted shape is an edge also inside such a label: the VLM joins two
# lines into one label, such as `F["PATCH /orders<br>  F --> G[&quot;API server"]`. The quote
# (`"` or `&quot;`, before the `&quot;` -> `'` step) keeps `x --> next(it)` and `x --> f('a')` in
# the label. A single `(` is a call, such as `x --> print(&quot;hi&quot;)`: in 25 books, each of the
# 34 arrows to a quoted node in a label went to `[`.
NODE_AHEAD = re.compile(r'(?:\|[^|]*\|\s*)?\w+\s*(?:[\[\{][\[\{\(]?|\(\()(?:"|&quot;)')
TAIL_FILL = re.compile(r"(?:\s|<br>)+$")


BR_EDGE = re.compile(r"^(?:\s*<br>)+|(?:<br>\s*)+$")


def _san_inner(s: str) -> str:
    s = s.replace("\\", "")  # drop stray backslashes (\' escape noise)
    s = s.replace('"', "'").replace("[", "(").replace("]", ")").replace("{", "(").replace("}", ")")
    s = re.sub(r"(<br>\s*)+", "<br>", s)
    # Strip a leading/trailing <br> TOKEN. `str.strip("<br> ")` was a character set: it ate the
    # final letters of every label ending in b/r/</>/space ("Load Balancer" -> "Load Balance",
    # "Web" -> "We"), silently truncating node text in shipped books.
    return BR_EDGE.sub("", s).strip()


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


def _split_arrows(ln: str) -> list[str]:
    """Split on the arrows, as `ARROW.split` does, but not on an arrow inside a complete quoted
    label that is not followed by a node with a shape. A split there cut `G["If valid --> vote"]`
    into a closed label and loose text."""
    labels = [m.span() for m in QUOTED_LABEL.finditer(ln)]
    parts, last = [], 0
    for m in ARROW.finditer(ln):
        in_label = any(a < m.start() < b for a, b in labels)
        if in_label and not NODE_AHEAD.match(ln, m.end()):
            continue
        parts += [ln[last : m.start()], m.group(1)]
        last = m.end()
    parts.append(ln[last:])
    return parts


def _drop_orphan_tail(ln: str, node: str) -> str:
    """Drop the brackets and `<br>` that a multi-line JSON label leaks after a close. `node` is the
    last node of `ln`, which holds the tail. A bracket is an orphan only when `node`, outside its
    quoted labels, has more of it than of its opener: the `]` of `subgraph LB [Load balancer (LB)]`
    closes the `[`, and it stays. The `)` of `A[Step 1)]` in an earlier node, and the `(` of
    `F["f(x"]))` in label text, do not change the count."""
    m = ORPHAN_TAIL.search(ln)
    if not m:
        return ln
    head, tail = ln[: m.start(1) + 1], ln[m.start(1) + 1 :]
    shape = QUOTED_LABEL.sub(lambda q: q.group(0)[0] + q.group(0)[-1], node)
    excess = {c: shape.count(c) - shape.count(o) for c, o in OPENER.items()}
    kept = []
    for ch in reversed(tail):
        if ch in excess and excess[ch] > 0:
            excess[ch] -= 1
            continue
        kept.append(ch)
    return head + TAIL_FILL.sub("", "".join(reversed(kept)))


def _fix_line(ln: str) -> str:
    parts = _split_arrows(ln)  # before the `&quot;` step, so NODE_AHEAD can tell `&quot;` from `'`
    for i in range(0, len(parts), 2):  # even indices = node segments
        parts[i] = _fix_segment(parts[i].replace("&quot;", "'").replace("\\n", "<br>"))
    return _drop_orphan_tail("".join(parts), parts[-1])


def _fix_line_or_keep(ln: str) -> str:
    """A line whose own score the repair raises stays as it was. The block guard in `repair` alone
    let one line get worse when another line of the block got better."""
    new = _fix_line(ln)
    return ln if issues(new) > issues(ln) else new


def _fix_block(body: str) -> str:
    return "\n".join(_fix_line_or_keep(l) for l in body.split("\n"))


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

    def repl(blk: fences.Block) -> str | None:
        if not blk.is_mermaid:
            return None
        body = blk.body
        b0 = issues(body)
        nb = _fix_block(body)
        b1 = issues(nb)
        if b1 > b0:  # a repair must never make a block worse: keep it as it was (#123)
            nb, b1 = body, b0
        state["score_before"] += b0
        state["score_after"] += b1
        if nb == body:
            return None
        state["blocks_changed"] += 1
        return blk.rebuild(body=nb)

    out = fences.transform(md, repl)
    return out, state
