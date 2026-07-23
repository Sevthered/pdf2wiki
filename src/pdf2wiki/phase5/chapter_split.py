"""Split a converted book .md into per-chapter files + inject YAML frontmatter.

Boundaries = fence-aware H1 lines (`# ...`), PLUS an H2 `## Appendix X. ...` line when the
converter mistagged an appendix heading one level down (a real source heading-level inconsistency
seen in the wild, not a converter bug). Fence-aware: a `# file: x.py` code COMMENT inside a fenced
code block must never be read as a chapter boundary.

Image paths are left untouched — MinerU emits `images/<hash>.ext` relative refs; every chapter
file is written into the SAME output directory as the shared `images/` folder, so the relative
path still resolves. No rewrite needed.

Everything before the first boundary becomes `00-front-matter.md` (title page, ToC, preface).
Frontmatter fields kept minimal: title, book, chapter, source, tags.
"""

import json
import os
import re

FENCE = re.compile(r"^```")
H1 = re.compile(r"^# (.+)$")
APPENDIX_H2 = re.compile(r"^## (Appendix [A-Z]\..+)$")


def find_boundaries(lines: list[str]) -> list[tuple[int, str]]:
    """Return list of (line_index, heading_text) for chapter-level boundaries, fence-aware."""
    bounds = []
    in_fence = False
    for i, ln in enumerate(lines):
        if FENCE.match(ln):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = H1.match(ln)
        if m:
            bounds.append((i, m.group(1).strip()))
            continue
        m = APPENDIX_H2.match(ln)
        if m:
            bounds.append((i, m.group(1).strip()))
    return bounds


def slugify(title: str) -> str:
    s = re.sub(r"[^\w\s-]", "", title.lower()).strip()
    s = re.sub(r"[\s_-]+", "-", s)
    return s[:60].strip("-") or "untitled"


def frontmatter(title: str, book: str, order: int, source: str) -> str:
    # json.dumps -> a valid double-quoted YAML scalar (JSON string syntax is a YAML subset).
    # Python repr()/raw interpolation broke YAML on titles with mixed quotes/backslashes and on
    # source filenames containing `: `, `#`, or a leading flow-indicator char.
    return (
        "---\n"
        f"title: {json.dumps(title)}\n"
        f"book: {json.dumps(book)}\n"
        f"chapter: {order}\n"
        f"source: {json.dumps(source)}\n"
        "tags: [book]\n"
        "---\n\n"
    )


class NoBoundariesError(RuntimeError):
    pass


def split(
    md_path: str,
    book: str,
    out_dir: str | None = None,
    source_name: str | None = None,
    dry_run: bool = False,
) -> tuple[list[str], list[tuple[int, str]]]:
    """Split md_path into chapter files. Returns (written_paths, boundaries).

    dry_run: compute boundaries and target paths, write nothing.
    source_name: value for frontmatter `source:` (pass the original PDF filename so staging
    paths don't leak into permanent frontmatter). Defaults to md_path.
    """
    source = source_name or md_path
    with open(md_path, encoding="utf-8") as f:
        text = f.read()
    lines = text.split("\n")
    bounds = find_boundaries(lines)
    if not bounds:
        raise NoBoundariesError("no chapter boundaries found")

    out = out_dir or os.path.join(os.path.dirname(md_path) or ".", "chapters")
    written: list[str] = []

    # front matter: everything before the first boundary
    front = "\n".join(lines[: bounds[0][0]]).strip("\n")
    plans: list[tuple[str, str]] = []
    if front.strip():
        plans.append(
            (
                os.path.join(out, "00-front-matter.md"),
                frontmatter("Front matter", book, 0, source) + front + "\n",
            )
        )

    # each chapter: from its boundary to the next (or EOF)
    for idx, (start, title) in enumerate(bounds, start=1):
        end = bounds[idx][0] if idx < len(bounds) else len(lines)
        chapter_lines = list(lines[start:end])
        chapter_lines[0] = f"# {title}"  # heading normalize: boundary heading is always H1 in its
        body = "\n".join(chapter_lines).strip("\n")  # own file, even when the source mistagged it
        slug = slugify(title)
        plans.append(
            (
                os.path.join(out, f"{idx:02d}-{slug}.md"),
                frontmatter(title, book, idx, source) + body + "\n",
            )
        )

    if not dry_run:
        os.makedirs(out, exist_ok=True)
        for path, content in plans:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
    written = [p for p, _ in plans]
    return written, bounds
