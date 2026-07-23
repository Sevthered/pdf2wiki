"""Render converter block records (blocks.json entries) to markdown snippets.

Single shared implementation — the converter's full renderer and the QA review renderer must not
drift apart (historically this logic existed in three copies)."""

from .convert.block import Block


def render_block(b: Block) -> str:
    # The typed accessors coerce BOTH a missing key and an explicit JSON null to "" (the converter
    # can emit either), so `None.strip()` / `"# " + None` can't crash and qa.review's join stays str.
    t = b.type
    if t == "text":
        lvl = b.text_level
        return ("#" * int(lvl) + " " if lvl else "") + (b.text or "")
    if t == "code":
        return f"```{b.sub_type}\n{b.code_body}\n```"
    if t == "list":
        return "\n".join("- " + str(x) for x in b.list_items)
    if t == "equation":
        return b.text or ""
    if t == "chart":
        cap = " ".join(b.chart_caption)
        out = f"[CHART {b.img_path or ''}]" + (f" — {cap}" if cap else "")
        if b.content.strip():
            out += "\n[+DATA]\n" + b.content
        return out
    if t == "table":
        cap = " ".join(b.table_caption)
        return (b.table_body or "") + (f"\n*{cap}*" if cap else "")
    if t == "image":
        cap = " ".join(b.image_caption)
        out = f"[IMAGE {b.img_path or ''}]" + (f" — {cap}" if cap else "")
        if "mermaid" in b.content:
            out += "\n[+MERMAID]\n" + b.content
        return out
    return ""
