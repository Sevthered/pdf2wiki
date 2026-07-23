"""Dual-pass production converter — pipeline skeleton + hybrid table/image graft.

The MinerU pipeline pass over the whole range gives byte-perfect code/text/structure from the
PDF's embedded text layer (the skeleton). The hybrid/VLM pass runs ONLY on 'rich' pages
(tables/figures/code), grouped into contiguous runs, and its table/image blocks are grafted into
the skeleton by page + bbox (IoU, with a containment fallback). Mermaid diagram transcriptions
ride inside hybrid image blocks' `content`.

Fidelity rules learned from real books:
- pipeline tokens are the truth for code — a VLM re-OCR of native text hallucinates tokens;
- hybrid wins for table grids (the text stream cannot reconstruct grid geometry) and LaTeX;
- code blocks where the two passes diverge are flagged with an HTML comment for downstream
  reconciliation, never silently trusted.
"""

import ast
import difflib
import glob
import itertools
import json
import os
import re
import shutil
import signal
import subprocess
import textwrap
from collections import Counter, defaultdict

from .block import Block

# ---------- environment ----------


def _mineru_env():
    env = dict(os.environ, MINERU_MODEL_SOURCE=os.environ.get("MINERU_MODEL_SOURCE", "huggingface"))
    # WSL2: GPU userspace libs live here and must be visible to non-interactive subprocesses
    if os.path.isdir("/usr/lib/wsl/lib"):
        env["PATH"] = "/usr/lib/wsl/lib:" + env.get("PATH", "")
    return env


def _clean_cwd(workdir: str) -> str:
    """Clean cwd for all MinerU subprocesses: prevents any local helper .py (e.g. profile.py,
    inspect.py) from shadowing a stdlib module that vllm/torch import at runtime — that failure
    mode is cryptic and costs hours."""
    d = os.path.expanduser(workdir)
    os.makedirs(d, exist_ok=True)
    return d


# ---------- helpers ----------


def bbox(b):
    v = b.get("bbox")
    if isinstance(v, str):
        v = json.loads(v)
    return [float(x) for x in v] if v else None


def iou(a, b):
    if not a or not b:
        return 0.0
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    inter = (x1 - x0) * (y1 - y0)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua else 0.0


def overlap_coef(a, b):
    """Intersection / smaller-box-area. Unlike IoU, insensitive to one box being much wider than
    the other: pipeline's code bbox often includes a right-margin annotation-callout column that
    hybrid's tighter code-only crop excludes, so true matches can sit at IoU~0.2-0.29 (just under
    the 0.3 threshold) despite hybrid's box being fully inside pipeline's."""
    if not a or not b:
        return 0.0
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    inter = (x1 - x0) * (y1 - y0)
    aa = (a[2] - a[0]) * (a[3] - a[1])
    ab = (b[2] - b[0]) * (b[3] - b[1])
    small = min(aa, ab)
    return inter / small if small else 0.0


def detect_watermarks(base, npages):
    """Book-adaptive: find short text lines that repeat on most pages (per-page DRM watermark).
    No assumption about wording; returns an empty set for books without a watermark."""
    pages_of = defaultdict(set)
    for b in base:
        t = b.get("text")
        if isinstance(t, str):
            s = t.strip()
            if 0 < len(s) < 200:
                # bucket by ABSOLUTE page: page_idx is chunk-relative (resets every pipeline
                # segment), so on a multi-chunk book distinct-page counts capped at the seg size
                # and never met the 60% threshold -> the DRM footer survived on every page.
                pages_of[s].add(b.get("abs_page"))
    thresh = max(3, int(0.6 * npages))  # must appear on >=60% of pages
    return {s for s, pgs in pages_of.items() if len(pgs) >= thresh}


def prescan(pdf, start, end):
    import pymupdf

    d = pymupdf.open(pdf)
    rich = []
    for i in range(start, end + 1):
        p = d[i]
        try:
            nt = len(p.find_tables().tables)
        except Exception:
            nt = 0
        fig = len(p.get_images()) > 0 or len(p.get_drawings()) > 20
        if nt > 0 or fig:
            rich.append(i)
    return rich


def group_runs(pages, gap):
    if not pages:
        return []
    runs, a, prev = [], pages[0], pages[0]
    for pg in pages[1:]:
        if pg - prev <= gap + 1:
            prev = pg
        else:
            runs.append((a, prev))
            a = prev = pg
    runs.append((a, prev))
    return runs


def cap_runs(runs, maxlen):
    """Split any run longer than maxlen pages so a single VLM pass can't grow unbounded (OOM/time)
    and so a failure's blast radius + resume granularity stay small."""
    out = []
    for a, b in runs:
        while b - a + 1 > maxlen:
            out.append((a, a + maxlen - 1))
            a += maxlen
        out.append((a, b))
    return out


def coverage_gaps(pdf, start, end, base):
    """Return pages in [start,end] that have real text in the PDF but produced ZERO base blocks —
    i.e. silently dropped by the scrape. Genuinely blank pages (no text) are not gaps."""
    import pymupdf

    d = pymupdf.open(pdf)
    covered = {b.get("abs_page") for b in base}
    gaps = []
    for p in range(start, end + 1):
        if p in covered:
            continue
        if len(d[p].get_text().strip()) > 50:  # had text, produced nothing -> dropped
            gaps.append(p)
    return gaps


# ---------- MinerU passes ----------


class PassFailed(RuntimeError):
    pass


def run_mineru(
    mineru_bin, pdf, a, b, backend, extra, outdir, clean_cwd, env, label="", timeout=None
):
    """Run a MinerU pass (cached). Returns (content_list, images_dir) with page_idx made ABSOLUTE.

    Cache is guarded by a `.done` sentinel written only after the subprocess exits 0 AND a
    content_list.json exists — so a pass that crashed mid-write is NEVER reused as complete
    (safe resume). On failure: report the exact pass + pages + log path, then abort (hard-stop);
    already-completed passes stay cached, so a fixed re-run resumes past them.
    MinerU stderr is never suppressed — it goes to the per-pass log file.
    """
    tag = label or backend
    done = f"{outdir}/.done"
    cl = glob.glob(f"{outdir}/*/*/*content_list.json")
    if not (os.path.exists(done) and cl):
        os.makedirs(outdir, exist_ok=True)
        # MinerU runs with cwd=clean_cwd (stdlib-shadow-safe), NOT pdf2wiki's cwd — so any relative path
        # handed to it resolves against the wrong directory and its output lands where our glob can't see
        # it (remote mode passes a home-relative --out). Absolutize the paths MinerU receives; abspath is
        # idempotent for already-absolute (local) paths. See bug-pdf2wiki-remote-relative-outdir.
        cmd = [
            mineru_bin,
            "-p",
            os.path.abspath(pdf),
            "-o",
            os.path.abspath(outdir),
            "-b",
            backend,
            "-s",
            str(a),
            "-e",
            str(b),
            *extra,
        ]
        print("  run:", " ".join(cmd[3:]))
        with open(f"{outdir}.log", "w", encoding="utf-8") as log:
            # start_new_session=True puts MinerU in its own process group so a timeout can SIGKILL the
            # WHOLE group. MinerU spawns vllm/torch workers; a bare child-kill would orphan them and an
            # orphaned worker pins GPU VRAM, so the resumed pass OOMs (Timeouts-Pattern [!warning]: a
            # timeout must kill the underlying work, not just the wrapper).
            proc = subprocess.Popen(
                cmd,
                env=env,
                cwd=clean_cwd,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                rc = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired as e:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                proc.wait()
                raise PassFailed(
                    f"FAILED pass [{tag}] pages {a}-{b}: timed out after {timeout}s (process group killed). "
                    f"log: {outdir}.log — completed passes are cached; re-run to resume from here."
                ) from e
            if rc != 0:
                raise PassFailed(
                    f"FAILED pass [{tag}] pages {a}-{b} (exit {rc}). log: {outdir}.log — "
                    f"completed passes are cached; fix root cause and re-run to resume from here."
                )
        cl = glob.glob(f"{outdir}/*/*/*content_list.json")
        if not cl:
            raise PassFailed(
                f"FAILED pass [{tag}] pages {a}-{b}: exited 0 but produced no content_list.json. "
                f"log: {outdir}.log"
            )
        with open(done, "w", encoding="utf-8") as f:
            f.write("ok\n")  # mark complete only now — guards partial-write reuse
    path = sorted(cl)[0]
    imgdir = os.path.dirname(path)
    with open(path, encoding="utf-8") as f:
        blocks = json.load(f)
    for blk in blocks:  # 0-based within run -> absolute page
        blk["abs_page"] = int(blk.get("page_idx", 0)) + a
        blk["_imgdir"] = imgdir  # per-pass images dir (pipeline is chunked -> dirs differ)
    return blocks, imgdir


def run_pipeline_chunks(mineru_bin, pdf, start, end, work, clean_cwd, env, seg=40, timeout=None):
    """Pipeline skeleton over [start,end] in fixed segments. A crash loses only the current
    segment; completed segments stay cached (.done) and resume on re-run. Blocks carry their own
    absolute page + images dir (set in run_mineru), so concatenation is order-independent."""
    base, first_img = [], None
    a = start
    while a <= end:
        b = min(a + seg - 1, end)
        blk, img = run_mineru(
            mineru_bin,
            pdf,
            a,
            b,
            "pipeline",
            ["-m", "txt"],
            f"{work}/base_{a}_{b}",
            clean_cwd,
            env,
            label=f"pipeline {a}-{b}",
            timeout=timeout,
        )
        base += blk
        first_img = first_img or img
        a = b + 1
    return base, first_img


# ---------- code fidelity ----------

RICH_TYPES = ("table", "image", "chart", "equation", "code")  # pages needing the hybrid/VLM pass

CALLOUT = re.compile(r"[①-⑳❶-❿⓪]")  # circled-digit code callouts used by some tech publishers


def strip_callouts(s):
    """Remove code-callout markers. Trailing standalone letters (e.g. " B") are ALSO callout
    markers in books that use circled digits — but in books that don't, a trailing bare letter is
    real code (Go's wrapped `..., r` parameter, `return b`, `package a`). So the letter strip is
    GATED on the block showing the circled-digit signature; circled digits themselves are never
    valid code and are always removed."""
    has_circled = bool(CALLOUT.search(s or ""))
    lines = []
    for ln in (s or "").split("\n"):
        ln = CALLOUT.sub("", ln)
        if has_circled:
            ln = re.sub(r"\s+[A-Za-z]\s*$", "", ln)  # trailing letter marker (e.g. " B")
        lines.append(ln.rstrip())
    return "\n".join(lines)


LINENUM = re.compile(r"^\s*(\d{1,4})(?:\s(.*))?$")


def strip_listing_numbers(s):
    """Remove publisher-printed listing line numbers (some publishers typeset them; the text
    layer captures them, the VLM omits them — polluting output and causing false divergence
    flags). Evidence-gated: strips ONLY when the leading integers cover most non-blank lines AND
    form a non-decreasing sequence — i.e. they demonstrably ARE line numbers, not code (a data
    matrix like `1 2 3` / `4 5 6` has too few rows or breaks monotonicity). Wrapped continuation
    lines (unnumbered) are preserved as-is."""
    lines = (s or "").split("\n")
    nums, nonblank = [], 0
    for ln in lines:
        if not ln.strip():
            continue
        nonblank += 1
        m = LINENUM.match(ln)
        if m:
            nums.append(int(m.group(1)))
    if len(nums) < 3 or nonblank == 0 or len(nums) < 0.6 * nonblank:
        return s
    if any(b < a for a, b in itertools.pairwise(nums)):
        return s
    out = []
    for ln in lines:
        m = LINENUM.match(ln) if ln.strip() else None
        out.append((m.group(2) or "") if m else ln)
    return "\n".join(out)


CAPTION = re.compile(r"^\s*(Listing|Figure|Table)\s+\d")  # caption line bled into a code block


def norm_code(s):
    """Whitespace-insensitive normal form for comparing pipeline vs hybrid code. Removes the
    noise that causes false divergence flags: fences, merged captions, markdown-escaped `\\_`,
    and long base64/JWT/key blobs (collapsed to a placeholder so OCR l/1 O/0 confusions in
    illustrative tokens don't flag)."""
    s = re.sub(r"```\w*", "", s or "")
    s = strip_listing_numbers(s)  # printed listing numbers: text layer has them, VLM omits them
    s = "\n".join(l for l in s.split("\n") if not CAPTION.match(l))
    s = strip_callouts(s).replace("\\", "")
    # collapse long base64/JWT/key blobs — but NOT `.` (dotted code identifiers like
    # `serialization.load_pem_private_key` must stay comparable so a `_`->`.` hallucination still flags).
    s = re.sub(r"[A-Za-z0-9_+/=\-]{30,}", "§B64§", s)
    return re.sub(r"\s+", "", s)


PLACEHOLDER = re.compile(r"\[\s*\.\.\.\s*\]|<[A-Za-z_][A-Za-z0-9_]*>")  # book elisions/placeholders
RUBY_MARK = re.compile(r"params\[:|=>|\.each do\b")
PY_MARK = re.compile(r"\b(def|class|import|from|async\s+def|lambda)\b")


def strip_fence(s):
    return re.sub(r"```\w*\n?", "", s or "")


def indent_suspect(body):
    """Hybrid's indentation is trusted unconditionally on a token match, but hybrid occasionally
    mis-indents even when tokens agree (e.g. dedents a try-body). Heuristic: for blocks that look
    like real (not illustrative/placeholder, not Ruby-with-`def`) Python, ast.parse after dedent
    must succeed — Python's grammar makes a wrong dedent/indent a SyntaxError far more often than
    not. Skips illustrative snippets (`[...]`, `<placeholder>`) and Ruby, which produced the only
    false positives seen in testing. Returns True only when the check is confidently meaningful
    AND fails — not a general "is this valid Python" linter."""
    b = strip_fence(body)
    if RUBY_MARK.search(b) or not PY_MARK.search(b) or PLACEHOLDER.search(b):
        return False
    try:
        ast.parse(textwrap.dedent(b))
        return False
    except (SyntaxError, ValueError):
        # ValueError: ast.parse raises "source code string cannot contain null bytes" on a NUL
        # in the code body — uncaught it escaped convert_book's handler and crashed the whole book.
        return True


def transplant_indent(hybrid_body, pipe_body):
    """Genuine divergence -> pipeline TOKENS are the truth (hybrid VLM hallucinates). Display
    pipeline content re-indented with hybrid's per-line leading whitespace when the two line up
    1:1; otherwise fall back to pipeline verbatim (correct tokens, flat).
    Returns (display_body, reindented_bool)."""
    hy = [l for l in (hybrid_body or "").split("\n") if not l.strip().startswith("```")]
    pi = []
    for l in strip_listing_numbers(re.sub(r"```\w*", "", pipe_body or "")).split("\n"):
        if CAPTION.match(l):
            continue
        # Unescape MARKDOWN-punct escapes ($ * ~ _ ` # @ % & !) — pipeline's md emitter escapes bare
        # specials from the text layer; inside code they render literally. A blanket backslash strip
        # corrupts real code escapes (`\n`->`n`), so keep `\n \t \d \s \" \\` etc.; the negative
        # lookbehind keeps a real `\\X`. Regex-structural metachars (. ( ) [ ] { } + ? | ^) left alone.
        # Mirrors phase5 code_unescape (universal net). See bug-backslash-escape-stripped.
        pi.append(re.sub(r"(?<!\\)\\([$*~_`#@%&!])", r"\1", strip_callouts(l)))
    hy_ne = [l for l in hy if l.strip()]
    pi_ne = [l for l in pi if l.strip()]
    if pi_ne and len(hy_ne) == len(pi_ne):  # 1:1 -> hybrid indent + pipeline tokens
        it = iter(pi_ne)
        out = []
        for l in hy:
            if l.strip():
                indent = l[: len(l) - len(l.lstrip())]
                out.append(indent + next(it).strip())
            else:
                out.append("")
        return "\n".join(out).strip("\n"), True
    # Line counts differ (e.g. hybrid dropped a REPL-echo line): the strict 1:1 path would fall
    # through to the flat pipeline body, which is fine for brace languages but BREAKS Python.
    # Fuzzy-align the pipeline tokens to hybrid's (correct) indentation and keep it only when the
    # result is valid Python structure; otherwise flat fallback (no regression).
    # See bug-python-indent-lost-diverge.
    if pi_ne and hy_ne:
        recovered = _recover_hybrid_indent(hy_ne, pi_ne)
        if recovered is not None:
            return recovered, True
    return "\n".join(pi).strip("\n"), False  # fallback: pipeline verbatim


def _recover_hybrid_indent(hy_ne, pi_ne):
    """Diverged block, mismatched line counts: align pipeline token lines (correct tokens) to
    hybrid lines (correct indentation) with difflib, re-apply hybrid's per-line leading
    whitespace, and accept the result ONLY if it is valid Python structure -- parseable either as
    a top-level snippet or as a function body (book code blocks are often a bare function body
    split off from their `def` header, so a lone `return`/`yield` must not disqualify it).
    Brace-language and unrecoverable blocks fail the parse gate -> None -> caller keeps the flat
    fallback. hy_ne/pi_ne are the non-empty lines."""
    hy_indent = [l[: len(l) - len(l.lstrip())] for l in hy_ne]
    hy_strip = [l.strip() for l in hy_ne]
    pi_strip = [l.strip() for l in pi_ne]
    out = [None] * len(pi_ne)
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
        None, pi_strip, hy_strip, autojunk=False
    ).get_opcodes():
        if tag in ("equal", "replace"):  # paired lines -> hybrid indent + pipeline tokens
            for k in range(min(i2 - i1, j2 - j1)):
                out[i1 + k] = hy_indent[j1 + k] + pi_strip[i1 + k]
    for idx in range(len(pi_ne)):  # pipeline-only lines (no hybrid match): infer from context
        if out[idx] is None:
            prev = out[idx - 1] if idx and out[idx - 1] is not None else ""
            ind = prev[: len(prev) - len(prev.lstrip())]
            if prev.rstrip().endswith(":"):
                ind += "    "
            out[idx] = ind + pi_strip[idx]
    body = "\n".join(out)

    def parses(src):
        try:
            ast.parse(src)
            return True
        except (SyntaxError, ValueError):
            return False

    if parses(textwrap.dedent(body)) or parses("def _f():\n" + textwrap.indent(body, "    ")):
        return body
    return None


# ---------- merge ----------
# Base (pipeline) is the authoritative skeleton: perfect code/text, best figure detection +
# captions (from the text layer). Hybrid contributes ONLY (a) correct table_body for tables,
# (b) Mermaid for diagrams, (c) cleaner LaTeX, (d) chart data, (e) code indentation when tokens
# verify. We never replace a base image with a hybrid one, never insert hybrid-only images.
DROP = ("header", "page_number", "footer")  # footer = per-page DRM watermark


def merge(base, hybrid, wm, tiny_px2=2500):
    base = [Block.from_dict(b) for b in base]
    hybrid = [Block.from_dict(h) for h in hybrid]
    hy = {
        "table": {},
        "image": {},
        "equation": {},
        "chart": {},
        "code": {},
    }  # type -> {page: [blocks]}
    for h in hybrid:
        t = h.type
        if t == "table":
            hy["table"].setdefault(h.abs_page, []).append(h)
        elif t == "image" and "mermaid" in h.content:
            hy["image"].setdefault(h.abs_page, []).append(h)
        elif t == "equation" and h.text:
            hy["equation"].setdefault(h.abs_page, []).append(h)
        elif t == "chart" and h.content.strip():
            hy["chart"].setdefault(h.abs_page, []).append(h)
        elif t == "code" and h.code_body:
            hy["code"].setdefault(h.abs_page, []).append(h)

    def best(cands, b, contain_ok=False):
        m = max(cands, key=lambda h: iou(b.bbox, h.bbox), default=None)
        if m and iou(b.bbox, m.bbox) > 0.3:
            return m
        if contain_ok and cands:  # fallback: near-full containment, not just IoU
            m2 = max(cands, key=lambda h: overlap_coef(b.bbox, h.bbox), default=None)
            if m2 and overlap_coef(b.bbox, m2.bbox) > 0.8:
                return m2
        return None

    final = []
    st = dict(
        table_swapped=0,
        table_kept=0,
        mermaid_attached=0,
        images=0,
        eq_swapped=0,
        eq_kept=0,
        chart_enriched=0,
        charts=0,
        noise_dropped=0,
        code_verified=0,
        code_flagged=0,
        code_pipeline_only=0,
        code_indent_flagged=0,
    )
    for b in base:
        t = b.type
        if t in DROP:
            continue
        bt = b.text
        if isinstance(bt, str) and bt.strip() in wm:
            st["noise_dropped"] += 1
            continue  # per-page watermark (auto-detected)
        b = b.copy()
        b.src = "base"  # _imgdir already set per-pass in run_mineru
        if t == "table":
            m = best(hy["table"].get(b.abs_page, []), b)
            if m:
                b.table_body = m.raw.get("table_body", b.table_body)
                st["table_swapped"] += 1
            else:
                st["table_kept"] += 1
        elif t == "equation":
            m = best(hy["equation"].get(b.abs_page, []), b)  # hybrid LaTeX is cleaner
            if m:
                b.text = m.raw["text"]
                st["eq_swapped"] += 1
            else:
                st["eq_kept"] += 1
        elif t == "code":
            # base `b` = pipeline block (byte-correct tokens); `m` = hybrid match (correct indentation).
            m = best(hy["code"].get(b.abs_page, []), b, contain_ok=True)
            if m:
                hy_body = m.code_body
                pi_body = b.code_body
                b.sub_type = m.raw.get("sub_type", b.raw.get("sub_type"))
                if norm_code(pi_body) == norm_code(hy_body):
                    b.code_body = hy_body
                    b.code_path = "verified"
                    if indent_suspect(hy_body):  # tokens agree but hybrid indent may be wrong
                        b.indent_flag = True  # no reliable auto-repair -> flag only
                        st["code_indent_flagged"] += 1
                    st["code_verified"] += 1  # agree -> hybrid (keeps indentation)
                else:
                    # genuine divergence -> pipeline tokens win (hybrid VLM hallucinates: _->., dropped chars).
                    disp, reindented = transplant_indent(hy_body, pi_body)
                    b.code_body = disp
                    b.code_flag = True
                    b.reindented = reindented
                    b.code_path = "flagged"
                    st["code_flagged"] += 1
            else:  # no hybrid on this page: pipeline only, strip noise
                b.code_body = strip_callouts(strip_listing_numbers(b.code_body))
                b.code_path = "pipeline_only"
                st["code_pipeline_only"] += 1
        elif t == "chart":
            m = best(hy["chart"].get(b.abs_page, []), b)  # hybrid transcribes chart data
            if m:
                b.content = m.content
                st["chart_enriched"] += 1
            st["charts"] += 1
        elif t == "image":
            bb = b.bbox
            area = (bb[2] - bb[0]) * (bb[3] - bb[1]) if bb else 0
            cap = b.image_caption
            if not any(cap) and area < tiny_px2:  # caption-less tiny image = decorative noise
                st["noise_dropped"] += 1
                continue
            m = best(hy["image"].get(b.abs_page, []), b)
            if m:
                b.content = m.content
                st["mermaid_attached"] += 1
            st["images"] += 1
        final.append(b.to_dict())
    return final, st


# ---------- chapter normalization from the PDF's own ToC ----------


def _norm_title(s):
    """Normal form for matching a ToC title against a rendered heading: case/punct-insensitive,
    ignoring a leading 'Chapter N:'/'Appendix A.'/'Part I' prefix (books often print the bare
    title on the chapter page while the ToC carries the prefixed form)."""
    s = re.sub(r"^(chapter|appendix|part)\s+[\divxlc]+\s*[:.\-]?\s*", "", (s or "").strip().lower())
    return re.sub(r"[^a-z0-9]+", "", s)


def toc_level1(doc):
    """Level-1 ToC entries as (title, 0-based page). Drops destination-less bookmarks:
    get_toc() returns page=-1 for them, and the -1-1=-2 that results would slip past the
    page-match window and inject/promote a synthetic H1 at the document top, corrupting the
    chapter split."""
    return [(t, p - 1) for lvl, t, p in doc.get_toc() if lvl == 1 and p >= 1]


def normalize_chapters_from_toc(final, toc_l1):
    """Fix heading levels using the PDF's own table of contents (level-1 bookmarks) — the ground
    truth for chapter boundaries. Layout models mistag chapter headings (real chapters come out
    H2 or plain text; section headings get promoted to H1), which breaks any downstream
    H1-boundary chapter split.

    For each ToC level-1 entry (title, 0-based page):
      - a text block near that page whose title matches -> promoted to level 1 and given the
        canonical ToC title (stable, prefixed filenames downstream);
      - no matching block, but the page produced text -> a synthetic level-1 heading is inserted
        (the layout model dropped the heading entirely);
      - a bare cover/image page with no text -> skipped.
    Evidence gate: only when >=3 entries matched are the remaining unmatched level-1 text blocks
    demoted to level 2 (kills spurious H1s) — a garbage/missing ToC changes nothing.
    Returns (final, stats)."""
    matched_ids = set()
    matched = 0
    inserts = []
    for title, page in toc_l1:
        want = _norm_title(title)
        if not want:
            continue
        hit = None
        for b in final:
            if id(b) in matched_ids or b.get("type") != "text":
                continue
            ap = int(b.get("abs_page", -99))
            if page - 1 <= ap <= page + 2 and _norm_title(b.get("text")) == want:
                hit = b
                break
        if hit is not None:
            hit["text_level"] = 1
            hit["text"] = title.strip()
            matched_ids.add(id(hit))
            matched += 1
        else:
            has_text = any(
                b.get("type") == "text" and int(b.get("abs_page", -99)) == page for b in final
            )
            idx = next(
                (i for i, b in enumerate(final) if int(b.get("abs_page", -99)) >= page), None
            )
            if has_text and idx is not None:
                inserts.append(
                    (
                        idx,
                        {
                            "type": "text",
                            "text": title.strip(),
                            "text_level": 1,
                            "abs_page": page,
                            "_src": "toc",
                            "_imgdir": "",
                        },
                    )
                )
    for idx, blk in sorted(inserts, key=lambda x: -x[0]):
        final.insert(idx, blk)
    if matched >= 3:
        for b in final:
            if (
                b.get("type") == "text"
                and b.get("text_level") == 1
                and id(b) not in matched_ids
                and b.get("_src") != "toc"
            ):
                b["text_level"] = 2
    return final, {"toc_matched": matched, "toc_inserted": len(inserts)}


# ---------- render ----------


def render(b: Block) -> str:
    t = b.type
    if t == "text":
        lvl = b.text_level
        return ("#" * int(lvl) + " " if lvl else "") + (b.text or "")
    if t == "code":
        body = b.code_body
        flag = ""
        if b.code_flag:  # divergence: displayed body is now the pipeline (correct) tokens
            how = (
                "re-indented from hybrid" if b.reindented else "verbatim (indentation approximate)"
            )
            flag = f"<!-- code-verify: hybrid VLM diverged from text layer; showing pipeline tokens {how}. -->\n"
        elif (
            b.indent_flag
        ):  # tokens matched, but hybrid indentation looks broken (ast-parse failed)
            flag = "<!-- code-verify: hybrid indentation may be broken (failed a Python indent sanity check); verify manually. -->\n"
        if body.lstrip().startswith("```"):  # MinerU already fenced it (with a language)
            return flag + body
        return flag + f"```{b.sub_type}\n{body}\n```"
    if t == "list":
        return "\n".join("- " + str(x) for x in b.list_items)
    if t == "equation":
        return b.text or ""  # already $$...$$ LaTeX
    if t == "chart":
        cap = " ".join(b.chart_caption)
        out = f"![]({b.img_path or ''})" + (f"\n\n*{cap}*" if cap else "")
        c = b.content
        if c and c.strip():
            out += f"\n\n<details><summary>chart data</summary>\n\n{c}\n\n</details>"
        return out
    if t == "table":
        cap = " ".join(b.table_caption)
        return (b.table_body or "") + (f"\n\n*{cap}*" if cap else "")
    if t == "image":
        cap = " ".join(b.image_caption)
        out = f"![]({b.img_path or ''})" + (f"\n\n*{cap}*" if cap else "")
        c = b.content
        if c and "mermaid" in c:
            out += f"\n\n<details><summary>diagram (mermaid)</summary>\n\n{c}\n\n</details>"
        return out
    return ""


def collect_images(final, outdir):
    imgdir = os.path.join(outdir, "images")
    os.makedirs(imgdir, exist_ok=True)
    for b in final:
        ip = b.get("img_path")
        if not ip:
            continue
        src = os.path.join(b["_imgdir"], ip)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(imgdir, os.path.basename(ip)))
            b["img_path"] = "images/" + os.path.basename(ip)


# ---------- entry point ----------


class CoverageError(RuntimeError):
    pass


def convert_book(
    pdf_path: str,
    slug: str,
    out_root: str,
    *,
    start: int | None = None,
    end: int | None = None,
    timeout: int | None = None,
    cfg=None,
) -> tuple[bool, str]:
    """Convert one book. Returns (ok, log_text). Resumable: completed MinerU passes are cached
    under the output dir (`.done` sentinels) and skipped on re-run."""
    import pymupdf

    from ..config import load_config

    cfg = cfg or load_config()

    lines: list[str] = []

    def say(msg):
        print(msg)
        lines.append(str(msg))

    try:
        mineru_bin = cfg.mineru.resolve_binary()
        env = _mineru_env()
        clean_cwd = _clean_cwd(cfg.convert.workdir)
        start = start or 0
        end = end if end is not None else pymupdf.open(pdf_path).page_count - 1
        work = os.path.join(os.path.expanduser(out_root), slug)
        os.makedirs(work, exist_ok=True)

        say("pipeline pass (skeleton, chunked):")
        base, _ = run_pipeline_chunks(
            mineru_bin,
            pdf_path,
            start,
            end,
            work,
            clean_cwd,
            env,
            seg=cfg.convert.seg,
            timeout=timeout,
        )
        total = end - start + 1

        # coverage gate: no page with real text may be silently dropped (hard-stop, zero-fail scrape)
        gaps = coverage_gaps(pdf_path, start, end, base)
        covered = len({b.get("abs_page") for b in base})
        say(f"coverage: {covered}/{total} pages produced blocks; text-bearing gaps={len(gaps)}")
        if gaps:
            raise CoverageError(
                f"FAILED coverage: {len(gaps)} text-bearing page(s) produced no blocks: {gaps} — "
                f"these were dropped by the pipeline scrape; investigate before trusting output."
            )

        # rich pages = where pipeline detected content needing the VLM. Derived from pipeline
        # output (not pymupdf) so CODE pages are included — pipeline mangles code indentation.
        rich = sorted({b["abs_page"] for b in base if b.get("type") in RICH_TYPES})
        runs = cap_runs(group_runs(rich, cfg.convert.gap), cfg.convert.maxrun)
        say(
            f"[{slug}] pages {start}-{end} ({total}); rich={len(rich)} "
            f"({100 * len(rich) // total if total else 0}%); hybrid runs={len(runs)}"
        )

        hybrid = []
        # Hybrid backend: local GPU (hybrid-engine) by default, or offload the VLM pass to a remote
        # OpenAI-compatible MinerU server (hybrid-http-client -u URL) when a URL is configured. The
        # layout runs client-side; only the VLM inference is remote, so --effort (image-analysis /
        # Mermaid / chart transcription) is preserved. Pipeline always stays local.
        # See decision-pdf2wiki-api-hybrid-offload.
        hy_url = (cfg.mineru.hybrid_server_url or "").strip()
        if hy_url:
            hy_backend = "hybrid-http-client"
            hy_extra = ["--effort", cfg.mineru.effort, "-u", hy_url]
            say(f"hybrid pass offloaded to remote MinerU server: {hy_url}")
        else:
            hy_backend = "hybrid-engine"
            hy_extra = ["--effort", cfg.mineru.effort]
        for i, (ra, rb) in enumerate(runs):
            say(f"hybrid pass {i + 1}/{len(runs)} pages {ra}-{rb}:")
            try:
                hb, _ = run_mineru(
                    mineru_bin,
                    pdf_path,
                    ra,
                    rb,
                    hy_backend,
                    hy_extra,
                    f"{work}/hy_{ra}_{rb}",
                    clean_cwd,
                    env,
                    label=f"hybrid {ra}-{rb}",
                    timeout=timeout,
                )
            except PassFailed as e:
                if not hy_url:
                    raise
                # Fail fast, loud: never fall back to local hybrid (assumes the GPU we offloaded
                # away) or pipeline-only (loses tables/diagrams/Mermaid). Cached passes resume.
                raise PassFailed(
                    f"{e}\nhybrid pass was offloaded to server '{hy_url}' (pages {ra}-{rb}); it must "
                    f"be reachable and serving an OpenAI-compatible MinerU endpoint. Not falling back "
                    f"to local hybrid or pipeline-only. Fix the server and re-run — completed passes "
                    f"are cached and resume."
                ) from e
            hybrid += hb  # only table/mermaid/latex/chart/code-indent used

        wm = detect_watermarks(base, total)
        if wm:
            say(f"watermark(s) auto-detected: {[w[:50] for w in wm]}")
        final, stats = merge(base, hybrid, wm, tiny_px2=cfg.convert.tiny_px2)
        toc_l1 = toc_level1(pymupdf.open(pdf_path))
        if toc_l1:
            final, toc_stats = normalize_chapters_from_toc(final, toc_l1)
            say(f"chapter normalize from ToC: {toc_stats}")
        collect_images(final, work)
        md = "\n\n".join(render(Block.from_dict(b)) for b in final)
        for w in wm:  # scrub watermark embedded in captions/merged text
            md = md.replace(w, " ")
        with open(f"{work}/{slug}.md", "w", encoding="utf-8") as f:
            f.write(md)
        with open(f"{work}/blocks.json", "w", encoding="utf-8") as f:
            json.dump(final, f, indent=1, default=str)
        say(f"graft stats: {stats}")
        say(f"final types: {dict(Counter(b['type'] for b in final))}")
        say(f"wrote {work}/{slug}.md ({len(md)} chars)")
        return True, "\n".join(lines)
    except (PassFailed, CoverageError, FileNotFoundError) as e:
        say(f"FAILED: {e}")
        return False, "\n".join(lines)
