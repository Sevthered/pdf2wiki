"""Un-bleed figure/listing captions that MinerU wrapped in their own code fence.

MinerU sometimes emits a bare caption line as a *caption-only* code fence, separate from the real
code fence right below it, e.g.

    ```text
    Listing 3.17 ExampleConfig.java: defining properties
    ```

    ```java
    @ConfigProperties(prefix="example")
    ...

This renders the caption as a code block. Fix: any fence whose ENTIRE body is a single
`Listing|Figure|Table|Example N.M ...` line is unwrapped into a bold caption line:

    **Listing 3.17** ExampleConfig.java: defining properties

Precision-first: only single-line caption-only fences are touched (a fence with a caption line PLUS
code is left alone, so real code is never stripped). Never touches ```mermaid. Bold text, NOT a
heading, so chapter-split boundaries / ToC are unaffected. Idempotent (an unwrapped caption is
plain text and no longer matches the fence regex).
"""

import re

FENCE = re.compile(r"^(```)([a-zA-Z]*)\n(.*?)^```[ \t]*$", re.S | re.M)
CAPTION = re.compile(r"^(Listing|Figure|Table|Example)\s+(\d+(?:\.\d+)*)\s+(.+?)\s*$")


def unbleed(md: str) -> tuple[str, list[str]]:
    """Return (new_md, list of unwrapped caption labels)."""
    changes: list[str] = []

    def repl(mo):
        tag, body = mo.group(2), mo.group(3)
        if tag == "mermaid":
            return mo.group(0)
        raw = body.split("\n")
        nonempty = [l for l in raw if l.strip()]
        if not nonempty:
            return mo.group(0)
        m = CAPTION.match(nonempty[0].strip())
        if not m:  # first content line isn't a caption -> leave alone
            return mo.group(0)
        label, num, rest = m.group(1), m.group(2), m.group(3)
        cap = f"**{label} {num}** {rest}"
        changes.append(f"{label} {num}")
        if len(nonempty) == 1:  # caption-ONLY fence -> drop the fence entirely
            return f"{cap}\n"
        # caption is line 1 with real code below -> lift caption out, keep the code fence intact
        out_lines, removed = [], False
        for l in raw:
            if not removed and l.strip() == nonempty[0].strip():
                removed = True  # drop exactly the caption line
                continue
            out_lines.append(l)
        new_body = "\n".join(out_lines).lstrip("\n")
        if not new_body.endswith("\n"):
            new_body += "\n"
        return f"{cap}\n\n```{tag}\n{new_body}```"

    out = FENCE.sub(repl, md)
    return out, changes
