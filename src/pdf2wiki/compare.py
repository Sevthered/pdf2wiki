# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Compare two output folders of `phase5`, file by file (`pdf2wiki compare OLD NEW`).

**Why.** The release gate of 0.3.0 ran `phase5` from the last tag and from `main` on 8 books into two
folders and compared them with `diff -r -I '^source: '`. That pattern also hides a body line that
starts with `source:`, and `diff` cannot say how many files were the same. This module does the same
check and nothing more. It reads two folders. It never runs `phase5` and never writes a file.

**Pairs.** Both folders are walked with `os.walk` and its default `followlinks=False`, and a file
pairs with the file at the same relative path. A file symlink is followed. A directory symlink is
not entered, so a link back to a parent folder cannot loop, and it pairs like a file. Only Markdown
files (`.md` and `.markdown`, in any case) are read. Every other file is paired and not read: the
`.log` files of a batch differ by design. A file of any kind on one side only is a difference, so a
version that stops writing the images of a chapter does not pass the gate.

**Ignored keys.** Before two files are compared, the top-level frontmatter lines whose key is in
`ignore_keys` are removed. The default is `source`, because `phase5` writes the staging path of the
book there. A multi-line value goes with its key: the lines below it that start with a space, a tab
or `- ` are removed too. A line in the body is never removed.

**One matcher.** The line counts and the hunks come from one `SequenceMatcher` with autojunk off.
`difflib.unified_diff` turns autojunk on, and on a file of 251 lines that only moved one line it
gave 250 removed and 250 added where the counts said 1 and 1. A hunk names the line numbers of the
real files, not of the text without its ignored lines.

**Line ends count.** A file is read as bytes and decoded as UTF-8. Lines split at `\\n` only, and each
line keeps its `\\r`, so a CRLF file differs from the same LF file. `str.splitlines()` would also
split at U+2028 and form feed, which can occur in book text. A file that is not valid UTF-8 is
compared as bytes: same or different, with no line counts and no diff.
"""

import difflib
import itertools
import os
from collections.abc import Iterator
from typing import Any

DEFAULT_IGNORE_KEYS = ("source",)
MARKDOWN_SUFFIXES = (".md", ".markdown")

# `diff` uses the same three exit codes
EXIT_SAME, EXIT_DIFFERENT, EXIT_ERROR = 0, 1, 2


def _lines(text: str) -> list[str]:
    """Split at "\\n" only, keep each line end, and keep a last line that has no "\\n"."""
    parts = text.split("\n")
    lines = [p + "\n" for p in parts[:-1]]
    if parts[-1]:
        lines.append(parts[-1])
    return lines


def _bare(line: str) -> str:
    return line.removesuffix("\n").removesuffix("\r")


def _continues(bare: str) -> bool:
    """True for a line that belongs to the value above it: indented, or a `- ` list item."""
    return bare[:1] in (" ", "\t") or bare == "-" or bare.startswith("- ")


def _kept(lines: list[str], keys: list[str] | tuple[str, ...]) -> list[int]:
    """The indexes of the lines that stay when the top-level frontmatter `keys` are removed.

    The frontmatter is the block between a first line `---` and the next line `---` or `...`. Text
    with no closed block at its start keeps every line. A removed key takes its value with it: the
    indented lines, `- ` items and indented comments below it. A blank line inside a block scalar
    (`source: |`) goes too when the next line that is not blank still continues the value. A blank
    line before the next top-level key stays.
    """
    every = list(range(len(lines)))
    if not keys or not lines or _bare(lines[0]) != "---":
        return every
    end = next((i for i in range(1, len(lines)) if _bare(lines[i]) in ("---", "...")), None)
    if end is None:
        return every
    prefixes = tuple(f"{k}:" for k in keys)
    kept = [0]
    dropping = False
    for i in range(1, end):
        bare = _bare(lines[i])
        if dropping:
            if not bare.strip():
                nxt = next(
                    (_bare(lines[j]) for j in range(i + 1, end) if _bare(lines[j]).strip()), ""
                )
                if _continues(nxt):
                    continue
            elif _continues(bare):
                continue
        dropping = bare.startswith(prefixes)
        if not dropping:
            kept.append(i)
    return kept + every[end:]


def strip_keys(text: str, keys: list[str] | tuple[str, ...]) -> str:
    """Remove the top-level frontmatter lines of `keys`, with the value lines of each key."""
    lines = _lines(text)
    return "".join(lines[i] for i in _kept(lines, keys))


def _is_markdown(path: str) -> bool:
    return path.lower().endswith(MARKDOWN_SUFFIXES)


def _walk(root: str) -> set[str]:
    """The relative paths of every file under `root`, and of every directory symlink in it."""
    found: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(root):
        # a directory symlink is listed but not entered (followlinks=False)
        names = [d for d in dirnames if os.path.islink(os.path.join(dirpath, d))] + filenames
        for name in names:
            rel = os.path.relpath(os.path.join(dirpath, name), root)
            found.add(rel.replace(os.sep, "/"))
    return found


def _check_dirs(old: str, new: str) -> None:
    for d in (old, new):
        if not os.path.isdir(d):
            raise ValueError(f"{d} is not a folder")
    # samefile, not a compare of path strings: on a case-insensitive file system (APFS, NTFS)
    # `old` and `OLD` are one folder with two spellings
    if os.path.samefile(old, new):
        raise ValueError(f"OLD and NEW are the same folder: {old}, {new}")
    if _inside(old, new) or _inside(new, old):
        raise ValueError(f"one folder is inside the other: {old}, {new}")


def _inside(child: str, parent: str) -> bool:
    """True when a folder above `child` is the folder `parent`."""
    path = os.path.realpath(child)
    up = os.path.dirname(path)
    while up != path:
        if os.path.samefile(up, parent):
            return True
        path, up = up, os.path.dirname(up)
    return False


def _check_keys(keys: list[str]) -> None:
    for k in keys:
        if not k or ":" in k or any(c.isspace() for c in k):
            raise ValueError(f"{k!r} is not a frontmatter key")


def _compare_file(
    old_path: str, new_path: str, rel: str, keys: list[str], n: int
) -> dict[str, Any]:
    with open(old_path, "rb") as fh:
        a_bytes = fh.read()
    with open(new_path, "rb") as fh:
        b_bytes = fh.read()
    try:
        a_text, b_text = a_bytes.decode("utf-8"), b_bytes.decode("utf-8")
    except UnicodeDecodeError:
        status = "same" if a_bytes == b_bytes else "different"
        return {"path": rel, "status": status, "utf8": False, "added": None, "removed": None}
    a_all, b_all = _lines(a_text), _lines(b_text)
    a_map, b_map = _kept(a_all, keys), _kept(b_all, keys)
    a, b = [a_all[i] for i in a_map], [b_all[i] for i in b_map]
    if a == b:
        return {"path": rel, "status": "same", "utf8": True, "added": 0, "removed": 0}
    # ONE matcher, with autojunk off, gives both the counts and the hunks. With autojunk on, a
    # line in over 1% of a 200+ line file is junk: a blank line or a `---` in a long chapter.
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    added = removed = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            removed += i2 - i1
            added += j2 - j1
    entry: dict[str, Any] = {
        "path": rel,
        "status": "different",
        "utf8": True,
        "added": added,
        "removed": removed,
        "line_ends_only": [_bare(x) for x in a] == [_bare(x) for x in b],
    }
    if n:
        hunks = _unified(matcher, a, b, a_map, b_map, rel)
        entry["diff"] = list(itertools.islice(hunks, n))
    return entry


def _range(start: int, stop: int, real: list[int]) -> str:
    """A unified-diff range of lines `start`..`stop` of the compared text, in real line numbers.

    `real[i]` is the 0-based line of the file that compared line `i` came from. The range spans the
    real file, so an ignored line inside a hunk counts in its length but is not shown.
    """
    if start == stop:
        # an empty range names the line after which the lines go (difflib's convention)
        return f"{real[start - 1] + 1 if start else 0},0"
    first, length = real[start] + 1, real[stop - 1] - real[start] + 1
    return str(first) if length == 1 else f"{first},{length}"


def _unified(
    matcher: difflib.SequenceMatcher[str],
    a: list[str],
    b: list[str],
    a_map: list[int],
    b_map: list[int],
    rel: str,
) -> Iterator[str]:
    """The unified diff of `matcher`, with `@@` line numbers of the real files.

    A line keeps its "\r", so a CRLF line differs visibly in JSON. Only the "\n" is dropped.
    """
    yield f"--- old/{rel}"
    yield f"+++ new/{rel}"
    for group in matcher.get_grouped_opcodes(3):
        i1, i2 = group[0][1], group[-1][2]
        j1, j2 = group[0][3], group[-1][4]
        yield f"@@ -{_range(i1, i2, a_map)} +{_range(j1, j2, b_map)} @@"
        for tag, x1, x2, y1, y2 in group:
            if tag == "equal":
                yield from (" " + line.removesuffix("\n") for line in a[x1:x2])
                continue
            yield from ("-" + line.removesuffix("\n") for line in a[x1:x2])
            yield from ("+" + line.removesuffix("\n") for line in b[y1:y2])


def compare_dirs(
    old: str,
    new: str,
    ignore_keys: list[str] | None = None,
    diff_lines: int = 0,
) -> dict[str, Any]:
    """Compare the `.md` files of two folders and return the report as a JSON-ready dict.

    `ignore_keys` None means the default (`source`). An empty list ignores no key. `diff_lines` > 0
    keeps the first that many lines of the unified diff of each different UTF-8 file. Raises
    `ValueError` for a bad folder or key, and `OSError` when a file cannot be read.
    """
    keys = list(DEFAULT_IGNORE_KEYS) if ignore_keys is None else list(ignore_keys)
    _check_keys(keys)
    _check_dirs(old, new)
    old_set, new_set = _walk(old), _walk(new)
    files: list[dict[str, Any]] = []
    for rel in sorted(old_set | new_set):
        if rel not in new_set:
            files.append({"path": rel, "status": "only_in_old"})
        elif rel not in old_set:
            files.append({"path": rel, "status": "only_in_new"})
        elif _is_markdown(rel) and not (
            os.path.isdir(os.path.join(old, rel)) or os.path.isdir(os.path.join(new, rel))
        ):  # a directory symlink named "x.md" is paired like any other directory symlink
            files.append(
                _compare_file(os.path.join(old, rel), os.path.join(new, rel), rel, keys, diff_lines)
            )
        else:
            # paired, not read: a .log of a batch differs by design
            files.append({"path": rel, "status": "not_compared"})
    count = {
        s: sum(f["status"] == s for f in files)
        for s in ("same", "different", "only_in_old", "only_in_new", "not_compared")
    }
    totals = {
        "compared": count["same"] + count["different"],
        "same": count["same"],
        "different": count["different"],
        "not_utf8": sum(f.get("utf8") is False for f in files),
        "only_in_old": count["only_in_old"],
        "only_in_new": count["only_in_new"],
        "not_compared": count["not_compared"],
    }
    differs = count["different"] or count["only_in_old"] or count["only_in_new"]
    return {
        "old": old,
        "new": new,
        "ignore_keys": keys,
        "files": files,
        "totals": totals,
        "exit_code": EXIT_DIFFERENT if differs else EXIT_SAME,
    }


def render_human(report: dict[str, Any]) -> str:
    """The report as text: one line for each file that is not the same, then the totals.

    A same file gets no line: on 8 books there are 232 of them, and the totals count them.
    """
    keys = ", ".join(report["ignore_keys"]) or "none"
    out = [f"compare {report['old']} -> {report['new']} (frontmatter keys ignored: {keys})"]
    for f in report["files"]:
        if f["status"] == "only_in_old":
            out.append(f"only in OLD  {f['path']}")
        elif f["status"] == "only_in_new":
            out.append(f"only in NEW  {f['path']}")
        elif f["status"] == "different":
            if not f["utf8"]:
                out.append(f"different    {f['path']}  (not UTF-8: the bytes differ)")
                continue
            note = " (line ends only)" if f["line_ends_only"] else ""
            out.append(f"different    {f['path']}  +{f['added']} -{f['removed']}{note}")
            # a terminal shows no "\r": a line-ends-only diff would look like two equal lines
            out.extend(f"    {line.replace(chr(13), '␍')}" for line in f.get("diff", []))
    t = report["totals"]
    not_utf8 = f" ({t['not_utf8']} not UTF-8)" if t["not_utf8"] else ""
    other = "other file" if t["not_compared"] == 1 else "other files"
    out.append(
        f"{t['compared']} compared{not_utf8}: {t['same']} same, {t['different']} different. "
        f"{t['only_in_old']} only in OLD, {t['only_in_new']} only in NEW. "
        f"{t['not_compared']} {other} in both folders, not read."
    )
    return "\n".join(out)
