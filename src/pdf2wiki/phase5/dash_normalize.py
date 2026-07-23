"""Normalize typographic dashes INSIDE code blocks of a converted book .md.

Books typeset CLI `--flag` as an en-dash ligature (`uv add –dev` should be `uv add --dev`), and a
math minus as U+2212. These are wrong inside code. We fix ONLY within ``` code blocks (never prose,
where en/em-dashes are legitimate punctuation) and never inside ```mermaid. Conservative:
  - en/em-dash used as a flag prefix (space/start before, letter after)  -> `--`
  - lone minus sign U+2212                                               -> `-`
Idempotent.
"""

import re

FENCE = re.compile(r"^(```)([a-zA-Z]*)\n(.*?)^```", re.S | re.M)
FLAG_DASH = re.compile(r"(?<=\s)[–—](?=[A-Za-z])")  # en/em dash as a long-flag prefix
MINUS = "−"


def _fix_body(body: str) -> tuple[str, list[tuple[str, str]]]:
    changes: list[tuple[str, str]] = []
    out_lines = []
    for ln in body.split("\n"):
        nl = FLAG_DASH.sub("--", ln)
        nl = nl.replace(MINUS, "-")
        if nl != ln:
            changes.append((ln.strip(), nl.strip()))
        out_lines.append(nl)
    return "\n".join(out_lines), changes


def normalize(md: str) -> tuple[str, list[tuple[str, str, str]]]:
    """Return (new_md, list of (fence_tag, old_line, new_line))."""
    allchanges: list[tuple[str, str, str]] = []

    def repl(mo):
        tag, body = mo.group(2), mo.group(3)
        if tag == "mermaid":
            return mo.group(0)
        newbody, ch = _fix_body(body)
        allchanges.extend((tag, o, n) for o, n in ch)
        return f"```{tag}\n{newbody}```"

    return FENCE.sub(repl, md), allchanges
