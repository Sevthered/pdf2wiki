"""Render converter block records (blocks.json entries) to markdown snippets.

Single shared implementation — the converter's full renderer and the QA review renderer must not
drift apart (historically this logic existed in three copies)."""


def render_block(b: dict) -> str:
    # `(b.get(k) or "")` not `b.get(k, "")`: .get's default covers a MISSING key, but the
    # converter can emit an explicit JSON null -> b.get(k, "") returns None -> None.strip()/
    # "# " + None crash. `or ""` coerces both missing and null to "".
    t = b.get("type")
    if t == "text":
        lvl = b.get("text_level")
        return ("#" * int(lvl) + " " if lvl else "") + (b.get("text") or "")
    if t == "code":
        return f"```{b.get('sub_type') or ''}\n{b.get('code_body') or ''}\n```"
    if t == "list":
        return "\n".join("- " + str(x) for x in (b.get("list_items") or []))
    if t == "equation":
        return b.get("text") or ""
    if t == "chart":
        cap = " ".join(b.get("chart_caption") or [])
        out = f"[CHART {b.get('img_path') or ''}]" + (f" — {cap}" if cap else "")
        if (b.get("content") or "").strip():
            out += "\n[+DATA]\n" + (b.get("content") or "")
        return out
    if t == "table":
        cap = " ".join(b.get("table_caption") or [])
        return (b.get("table_body") or "") + (f"\n*{cap}*" if cap else "")
    if t == "image":
        cap = " ".join(b.get("image_caption") or [])
        out = f"[IMAGE {b.get('img_path') or ''}]" + (f" — {cap}" if cap else "")
        if "mermaid" in str(b.get("content") or ""):
            out += "\n[+MERMAID]\n" + (b.get("content") or "")
        return out
    return ""
