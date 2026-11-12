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
text, not a split point, unless a node with a quoted shape follows it. A label delimited by
`&quot;` is a quoted label also. A quoted label can continue on the next lines, as mermaid allows:
those lines are one logical line for the repair and for the score. Never changes non-mermaid
fences. Validation is a parse-breaker score (proxy), not a real mermaid parse: a line or a block
whose score a repair raises stays as it was. The score does not count `(` and `)`, so this guard
cannot see a lost parenthesis.
"""

import re

from . import fences

ARROW = re.compile(r"(\s*(?:-\.->|--[>x]|==>|===|-\.-|---|~~~)\s*)")  # keep arrows as separators
# id (or `subgraph name`) + shape-open + "label" + close. Prefix allows a `subgraph name ` lead-in.
# A label delimiter is `"` or `&quot;` (#126): `C[&quot;k&quot;]` is the label `k`. Only a label
# that `&quot;` opens can close with `&quot;`: in `F["a {&quot;b&quot;}"]`, `&quot;}` is text. A
# label that `'` opens closes with `'` or `"`: `A['x']` and `A['x"]` are the label `x`.
NODE = re.compile(
    r"^(?P<pre>[\w&;\s]*?)(?P<op>[\[\{\(])"
    r'(?:"(?P<q>.*)"|&quot;(?P<e>.*)(?:"|&quot;)|\'(?P<s>.*)["\'])[\]\}\)](?P<post>.*)$'
)
# An unclosed label, or one with a mismatched quote.
OPEN_ONLY = re.compile(r'^([\w&;\s]*?)([\[\{\(])(?:["\']|&quot;)(.*)$')
CLOSE = {"[": "]", "{": "}", "(": ")"}
ORPHAN_TAIL = re.compile(
    r"([\]\}\)])[\s\}\]\)]*(?:<br>[\s\}\]\)]*)*$"
)  # stray brackets/br after a close
OPENER = {c: o for o, c in CLOSE.items()}
# A complete quoted label: an opener, a quoted text without `"`, and a closer. An arrow inside
# one is label text, such as `G["If valid --> vote"]`, and is not an edge.
QUOTED_LABEL = re.compile(r'[\[\{\(](?:"[^"]*"|&quot;(?:(?!&quot;)[^"])*(?:&quot;|"))[\]\}\)]')
# But an arrow to a node with a quoted shape is an edge also inside such a label: the VLM joins two
# lines into one label, such as `F["PATCH /orders<br>  F --> G[&quot;API server"]`. The quote
# (`"` or `&quot;`, before the `&quot;` -> `'` step) keeps `x --> next(it)` and `x --> f('a')` in
# the label. A single `(` is a call, such as `x --> print(&quot;hi&quot;)`: in 25 books, each of the
# 34 arrows to a quoted node in a label went to `[`.
NODE_AHEAD = re.compile(r'(?:\|[^|]*\|\s*)?\w+\s*(?:[\[\{][\[\{\(]?|\(\()(?:"|&quot;)')
TAIL_FILL = re.compile(r"(?:\s|<br>)+$")


BR_EDGE = re.compile(r"^(?:\s*<br>)+|(?:<br>\s*)+$")
# A text whose last `"` opens a label, and a line whose first `"` closes one with only label text
# before it (#126): no bracket here, and no arrow (checked in `_logical_lines`). A line between
# them must look like label text, not like a statement.
OPENS_LABEL = re.compile(r'[\[\{\(]"[^"]*$')
CLOSES_LABEL = re.compile(r'^[^"\[\]\{\}\(\)]*"[\]\}\)]')
STATEMENT = re.compile(
    r'[\[\]\{\}\(\)"]|^\s*(?:%%|(?:end|subgraph|style|classDef|class|click|linkStyle|direction)\b)'
)
SEP = "\x00"  # stands for a newline inside a logical line while `_fix_line` runs


def _quot(s: str) -> str:
    return s.replace("&quot;", "'")


def _san_inner(s: str) -> str:
    s = _quot(s).replace("\\", "")  # drop stray backslashes (\' escape noise)
    s = s.replace('"', "'").replace("[", "(").replace("]", ")").replace("{", "(").replace("}", ")")
    s = re.sub(r"(<br>\s*)+", "<br>", s)
    # Strip a leading/trailing <br> TOKEN. `str.strip("<br> ")` was a character set: it ate the
    # final letters of every label ending in b/r/</>/space ("Load Balancer" -> "Load Balance",
    # "Web" -> "We"), silently truncating node text in shipped books.
    return BR_EDGE.sub("", s).strip()


def _fix_segment(seg: str) -> str:
    m = NODE.match(seg)
    if m:
        pre, op, post = m["pre"], m["op"], m["post"]
        inner = next(m[g] for g in "qes" if m[g] is not None)
        # emit close MATCHING the opener
        return f'{_quot(pre)}{op}"{_san_inner(inner)}"{CLOSE[op]}{_quot(post)}'
    m = OPEN_ONLY.match(seg)  # unclosed label -> close it with a matching bracket
    if m:
        pre, op, inner = m.groups()
        return f'{_quot(pre)}{op}"{_san_inner(inner)}"{CLOSE[op]}'
    return _quot(seg)


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
        parts[i] = _fix_segment(parts[i].replace("\\n", "<br>"))
    return _drop_orphan_tail("".join(parts), parts[-1])


def _fix_line_or_keep(ln: str) -> str:
    """A line whose own score the repair raises stays as it was. The block guard in `repair` alone
    let one line get worse when another line of the block got better. `ln` is a logical line: a
    newline in it is part of a quoted label."""
    if "\n" not in ln:
        new = _fix_line(ln)
    elif SEP in ln:
        return ln
    else:
        new = _fix_line(ln.replace("\n", SEP)).replace(SEP, "\n")
    return ln if issues(new) > issues(ln) else new


def _logical_lines(body: str) -> list[str]:
    """Split `body` into lines, but keep a quoted label that continues on the next lines in one
    logical line (#126): `A["foo` and `bar"] --> B` are one label. A line between them must have no
    arrow, no bracket, no `"` and no keyword, and the last line must close the label at its first
    `"`, with no arrow and no bracket before it. Then the logical line can open the next label, as `two"] --> B["three` does. Otherwise,
    each line stays alone, and the repair closes the label on its own line. A wrong join puts
    nodes into a label, so the rule joins only what is clearly label text."""
    lines = body.split("\n")
    out, i = [], 0
    while i < len(lines):
        end, quotes = i, lines[i].count('"')
        while quotes % 2 and OPENS_LABEL.search(lines[end]):
            k = end + 1
            while k < len(lines) and not ARROW.search(lines[k]) and not STATEMENT.search(lines[k]):
                k += 1
            if k == len(lines):
                break
            close = CLOSES_LABEL.match(lines[k])
            if not close or ARROW.search(close.group(0)):
                break
            end, quotes = k, quotes + lines[k].count('"')
        out.append("\n".join(lines[i : end + 1]))
        i = end + 1
    return out


def _fix_block(body: str) -> str:
    return "\n".join(_fix_line_or_keep(l) for l in _logical_lines(body))


def issues(body: str) -> int:
    """Count parse-breakers in a block (validation proxy)."""
    n = 0
    n += body.count("\\n") + body.count("&quot;")
    n += sum(l.count('"') % 2 for l in _logical_lines(body))
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
