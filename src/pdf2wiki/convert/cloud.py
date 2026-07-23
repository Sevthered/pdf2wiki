"""Fully-managed mineru.net Cloud converter (`--mineru-cloud`).

No GPU and no local MinerU: the PDF is uploaded to the OpenDataLab cloud (mineru.net Precision API),
parsed there, and the result Markdown + images are pulled back. Output layout matches the local
converter (`<out>/<slug>/<slug>.md` + `images/`), so phase5 consumes it unchanged.

Two shapes:
  * single-backend (`convert_book_cloud`): one cloud pass; accept its `full.md` verbatim. `--cloud-model
    pipeline` (default, code-safe) | `vlm` (indent/tables but corrupts code) | `MinerU-HTML`.
  * dual-pass merge (`convert_book_cloud_merge`, `--cloud-model merge`): run BOTH `pipeline` and `vlm` in
    the cloud, pull back each `content_list.json`, and feed them into our existing pure-Python `merge()`
    locally — clean code (pipeline tokens) AND indentation/tables/Mermaid (vlm), fully GPU-less. Gate-
    verified 2026-07-23 (research/2026-07-23-cloud-dual-merge-architecture, decision-pdf2wiki-cloud-dual-merge).

⚠ DATA EGRESS: this uploads the source PDF to a third-party cloud. Only reachable behind the explicit
`--mineru-cloud` opt-in, and it logs the upload loudly. Do not use for material you cannot send offsite.

Uses `requests` (a core dependency), lazy-imported only to keep import time low. It is required here
because the OSS pre-signed upload URL is signed with NO Content-Type header, and urllib auto-adds one
→ SignatureDoesNotMatch; requests sends the raw body without it. Token is read from config, then env
MINERU_API_TOKEN, then a token_file; it is never written to disk or logged.
"""

import glob
import json
import os
import random
import time
import zipfile
from io import BytesIO
from urllib.parse import urlparse


class CloudError(RuntimeError):
    """A mineru.net Cloud request failed. Raised loud (fail-fast) — never silently degraded.

    `transient` marks a failure worth retrying (network drop, HTTP 429/5xx) vs a permanent one
    (4xx, API error code, page-limit) that must fail fast — Backoff-Retries: classify, don't blindly
    retry every error.
    """

    def __init__(self, msg, *, transient=False):
        super().__init__(msg)
        self.transient = transient


def _redact_url(u: str) -> str:
    """Drop the query string from a URL before logging it — a mineru.net presigned upload/download
    URL carries its signature there and is itself a capability credential (Log-Redaction)."""
    try:
        p = urlparse(u)
        return f"{p.scheme}://{p.netloc}{p.path}"
    except Exception:
        return "<url>"


def _require_https(u: str, what: str) -> str:
    """Refuse a non-HTTPS URL before we send the Bearer token or the PDF over it. A config override
    or a MITM'd/poisoned API response could downgrade to http:// and leak the credential/data
    (JSON-Web-Token: token is only Base64, must travel over TLS; SSRF-in-APIs: don't blindly follow
    a server-supplied URL)."""
    scheme = urlparse(u).scheme
    if scheme != "https":
        raise CloudError(
            f"refusing to use non-HTTPS {what} URL ({scheme or 'no'}-scheme): the "
            f"Bearer token / PDF must not travel unencrypted"
        )
    return u


def _safe_extract(zbytes: bytes, dest_dir: str) -> None:
    """Extract a mineru.net result ZIP, rejecting any member whose path escapes dest_dir (zip-slip).
    The archive is downloaded from a server-supplied URL — untrusted input (Unsafe-Consumption-of-APIs);
    `extractall` on a `../`-prefixed or absolute member would otherwise overwrite arbitrary files."""
    os.makedirs(dest_dir, exist_ok=True)
    dest_real = os.path.realpath(dest_dir)
    with zipfile.ZipFile(BytesIO(zbytes)) as z:
        for name in z.namelist():
            target = os.path.realpath(os.path.join(dest_dir, name))
            if target != dest_real and not target.startswith(dest_real + os.sep):
                raise CloudError(
                    f"refusing to extract unsafe zip member '{name}' (escapes {dest_dir})"
                )
        z.extractall(dest_dir)


def _retry(what: str, fn, *, tries: int, base_delay: float, say):
    """Call fn(); on a *transient* CloudError retry up to `tries` times with exponential backoff +
    full jitter. Permanent CloudErrors re-raise immediately. Backoff-Retries + MicroProfile-Fault-
    Tolerance (jitter so parallel retries don't synchronize; retry can worsen an outage → bounded)."""
    for attempt in range(1, tries + 1):
        try:
            return fn()
        except CloudError as e:
            if not (getattr(e, "transient", False) and attempt < tries):
                raise
            delay = min(30.0, base_delay * (2 ** (attempt - 1)))
            delay = random.uniform(0, delay)  # full jitter
            say(
                f"  transient {what} error (attempt {attempt}/{tries}), retrying in {delay:.1f}s: {e}"
            )
            time.sleep(delay)


def _requests():
    try:
        import requests
    except ModuleNotFoundError as e:
        raise CloudError(
            "the 'requests' package is missing (it is a pdf2wiki dependency) — reinstall pdf2wiki, "
            "or: pip install requests."
        ) from e
    return requests


def _resolve_token(cfg) -> str:
    c = cfg.mineru_cloud
    if c.token.strip():
        return c.token.strip()
    env = os.environ.get("MINERU_API_TOKEN", "")
    if env.strip():
        return env.strip()
    if c.token_file:
        with open(os.path.expanduser(c.token_file), encoding="utf-8") as f:
            tok = f.read().strip()
        if tok:
            return tok
    raise CloudError(
        "no mineru.net token: set [mineru_cloud].token, or env MINERU_API_TOKEN, or "
        "[mineru_cloud].token_file. Create one at https://mineru.net/apiManage/token"
    )


def _transient_status(code: int) -> bool:
    """HTTP 429 (rate limit) and 5xx are worth retrying; other 4xx are permanent (Backoff-Retries)."""
    return code == 429 or 500 <= code < 600


def _api(url, token, method="GET", body=None, timeout=60):
    """One JSON API call to mineru.net. Returns the `data` payload; raises CloudError on HTTP/API error.
    Network drops and 429/5xx are flagged transient (retryable); other errors are permanent."""
    requests = _requests()
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.request(method, url, headers=headers, json=body, timeout=timeout)
    except requests.RequestException as e:
        raise CloudError(f"{method} {url} unreachable: {e}", transient=True) from e
    if r.status_code != 200:
        raise CloudError(
            f"{method} {url} -> HTTP {r.status_code}: {r.text[:200].replace(chr(10), ' ')}",
            transient=_transient_status(r.status_code),
        )
    payload = r.json()
    if payload.get("code") != 0:  # API-level error (bad request, quota) = permanent
        raise CloudError(f"{method} {url} -> API code {payload.get('code')}: {payload.get('msg')}")
    return payload["data"]


def _put_file(upload_url, pdf_path, timeout=300):
    """Upload the PDF to a mineru.net pre-signed URL. PUT with NO Content-Type (the URL is signed
    without one; adding one breaks the OSS signature)."""
    requests = _requests()
    _require_https(upload_url, "upload")
    with open(pdf_path, "rb") as f:
        try:
            r = requests.put(upload_url, data=f, timeout=timeout)
        except requests.RequestException as e:
            raise CloudError(
                f"upload PUT to {_redact_url(upload_url)} unreachable: {e}", transient=True
            ) from e
    if r.status_code != 200:
        raise CloudError(
            f"upload PUT -> HTTP {r.status_code}: {r.text[:200].replace(chr(10), ' ')}",
            transient=_transient_status(r.status_code),
        )


def _run_cloud_pass(pdf_path, model_version, token, cfg, dest_dir, say, timeout=None) -> str:
    """Run ONE cloud parse pass (submit → presigned PUT → poll → download → unzip). Extracts the whole
    result ZIP (full.md + *_content_list.json + images/ + *.json) into `dest_dir` and returns it.
    Raises CloudError on any failure (fail-fast, loud)."""
    c = cfg.mineru_cloud
    name = os.path.basename(pdf_path)

    # Step 0: resume — a completed pass writes a `.done` sentinel; skip the whole upload/poll/download
    # if it and the extracted artifacts are already present (Idempotent-Message-Handling: check before
    # doing work). Cheap and avoids re-uploading + re-paying for a pass that already succeeded.
    done_marker = os.path.join(dest_dir, ".done")
    existing = (
        glob.glob(f"{dest_dir}/full.md")
        + glob.glob(f"{dest_dir}/*/full.md")
        + glob.glob(f"{dest_dir}/*_content_list.json")
        + glob.glob(f"{dest_dir}/*/*_content_list.json")
    )
    if os.path.exists(done_marker) and existing:
        say(
            f"[{model_version}] reusing cached cloud pass in {dest_dir} (.done present) — no re-upload"
        )
        return dest_dir

    _require_https(c.base_url, "API base")
    say(
        f"⚠ mineru.net Cloud: uploading '{name}' to a THIRD-PARTY cloud "
        f"(model_version={model_version}, lang={c.language}). Data leaves this machine."
    )

    # Step 1: request a pre-signed upload URL for this file (retry transient network/5xx).
    body = {
        "files": [{"name": name, "is_ocr": False}],
        "model_version": model_version,
        "enable_formula": True,
        "enable_table": True,
        "language": c.language,
    }
    if c.extra_formats:
        body["extra_formats"] = list(c.extra_formats)
    sub = _retry(
        "submit",
        lambda: _api(f"{c.base_url}/file-urls/batch", token, method="POST", body=body),
        tries=c.retries,
        base_delay=c.retry_base_delay,
        say=say,
    )
    try:  # treat the API response as untrusted input
        batch_id = sub["batch_id"]
        upload_url = sub["file_urls"][0]
    except (KeyError, IndexError, TypeError) as e:
        raise CloudError(f"unexpected submit response shape ({model_version}): {e}") from e

    # Step 2: upload the bytes (retry transient; _put_file enforces https on the presigned URL).
    _retry(
        "upload",
        lambda: _put_file(upload_url, pdf_path),
        tries=c.retries,
        base_delay=c.retry_base_delay,
        say=say,
    )
    say(f"[{model_version}] uploaded; batch={batch_id}; polling…")

    # Step 3: poll until this file is done (or failed). Tolerate a bounded run of transient poll
    # errors (a network blip mid-poll must NOT fail an otherwise-healthy parse) — Backoff-Retries.
    deadline = time.monotonic() + (timeout or c.poll_timeout)
    zip_url = None
    transient_fails = 0
    while time.monotonic() < deadline:
        try:
            data = _api(f"{c.base_url}/extract-results/batch/{batch_id}", token)
        except CloudError as e:
            if e.transient and transient_fails < c.poll_max_transient:
                transient_fails += 1
                say(
                    f"  [{model_version}] transient poll error ({transient_fails}/{c.poll_max_transient}), "
                    f"backing off: {e}"
                )
                time.sleep(min(30, 6 * transient_fails))
                continue
            raise
        transient_fails = 0
        item = next((x for x in data.get("extract_result", []) if x.get("file_name") == name), None)
        if item:
            state = item.get("state")
            if state == "done":
                zip_url = item.get("full_zip_url")
                if not zip_url:
                    raise CloudError(f"cloud reported done but no full_zip_url ({model_version})")
                break
            if state == "failed":
                raise CloudError(
                    f"cloud parse failed for '{name}' ({model_version}): {item.get('err_msg')}"
                )
            prog = item.get("extract_progress", {})
            say(
                f"  [{model_version}] state={state} {prog.get('extracted_pages', '?')}/{prog.get('total_pages', '?')}"
            )
        time.sleep(6)
    if not zip_url:
        raise CloudError(
            f"timed out after {timeout or c.poll_timeout}s waiting for batch {batch_id} ({model_version})"
        )
    _require_https(zip_url, "result-download")

    # Step 4: download the result ZIP (retry transient) and extract it with zip-slip guarding.
    def _download():
        requests = _requests()
        try:
            resp = requests.get(zip_url, timeout=300)
        except requests.RequestException as e:
            raise CloudError(
                f"result download from {_redact_url(zip_url)} failed ({model_version}): {e}",
                transient=True,
            ) from e
        if resp.status_code != 200:
            raise CloudError(
                f"result download -> HTTP {resp.status_code} ({model_version})",
                transient=_transient_status(resp.status_code),
            )
        return resp.content

    zbytes = _retry("download", _download, tries=c.retries, base_delay=c.retry_base_delay, say=say)
    _safe_extract(zbytes, dest_dir)
    with open(done_marker, "w", encoding="utf-8") as f:
        f.write("ok\n")  # mark complete only after a successful extract — guards partial reuse
    return dest_dir


def _check_pages(pdf_path, max_pages) -> int:
    import pymupdf

    try:
        pages = pymupdf.open(pdf_path).page_count
    except Exception as e:
        raise CloudError(f"cannot open PDF '{pdf_path}': {e}") from e
    if pages > max_pages:
        raise CloudError(
            f"{pages} pages exceeds mineru.net's {max_pages}-page limit per file. Split the PDF "
            f"into <= {max_pages}-page parts and convert each (cloud chunking is not automated)."
        )
    return pages


def convert_book_cloud(
    pdf_path: str,
    slug: str,
    out_root: str,
    *,
    cfg=None,
    model_version: str | None = None,
    timeout: int | None = None,
) -> tuple[bool, str]:
    """Convert one book via a SINGLE mineru.net Cloud pass. Returns (ok, log_text).

    Accepts the cloud's `full.md` verbatim. Output: <out_root>/<slug>/<slug>.md plus images/ — the same
    layout the local converter produces (mineru.net already emits `![](images/<hash>.jpg)` refs).
    For dual-backend merge quality see convert_book_cloud_merge (`--cloud-model merge`).
    """
    from ..config import load_config

    cfg = cfg or load_config()
    c = cfg.mineru_cloud
    model_version = model_version or c.model_version

    lines: list[str] = []

    def say(msg):
        print(msg)
        lines.append(str(msg))

    try:
        token = _resolve_token(cfg)
        pages = _check_pages(pdf_path, c.max_pages)
        work = os.path.join(os.path.expanduser(out_root), slug)
        say(f"single cloud pass ({pages}p, model_version={model_version})")
        pass_dir = _run_cloud_pass(
            pdf_path, model_version, token, cfg, os.path.join(work, "_cloud"), say, timeout=timeout
        )

        md_member = next(
            (n for n in (glob.glob(f"{pass_dir}/full.md") + glob.glob(f"{pass_dir}/*/full.md"))),
            None,
        )
        if not md_member:
            raise CloudError(f"result has no full.md under {pass_dir}")
        with open(md_member, encoding="utf-8") as f:
            md_text = f.read()
        os.makedirs(work, exist_ok=True)
        with open(os.path.join(work, f"{slug}.md"), "w", encoding="utf-8") as f:
            f.write(md_text)
        n_img = 0
        for img in glob.glob(f"{pass_dir}/**/images/*", recursive=True):
            if os.path.isfile(img):
                dest = os.path.join(work, "images", os.path.basename(img))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, "wb") as out, open(img, "rb") as src:
                    out.write(src.read())
                n_img += 1
        say(f"wrote {work}/{slug}.md ({len(md_text)} chars), {n_img} images")
        return True, "\n".join(lines)
    except CloudError as e:
        say(f"FAILED (mineru.net Cloud): {e}")
        return False, "\n".join(lines)


def _load_cloud_content_list(pass_dir: str):
    """Load a cloud pass's `*_content_list.json` and adapt it to what merge() consumes:
    inject `abs_page` (cloud page_idx is already whole-doc absolute — no per-chunk offset) and
    `_imgdir` (this pass's extraction dir, for collect_images). Returns the block list."""
    cl = glob.glob(f"{pass_dir}/*_content_list.json") + glob.glob(
        f"{pass_dir}/*/*_content_list.json"
    )
    cl = [p for p in cl if not p.endswith("_content_list_v2.json")]
    if not cl:
        raise CloudError(f"no *_content_list.json under {pass_dir}")
    with open(cl[0], encoding="utf-8") as f:
        blocks = json.load(f)
    imgdir = os.path.dirname(cl[0])
    for b in blocks:
        b["abs_page"] = int(b.get("page_idx", 0))
        b["_imgdir"] = imgdir
    return blocks


def convert_book_cloud_merge(
    pdf_path: str, slug: str, out_root: str, *, cfg=None, timeout: int | None = None
) -> tuple[bool, str]:
    """Convert one book via TWO mineru.net Cloud passes (pipeline + vlm) merged locally with our
    base-driven merge. Returns (ok, log_text). GPU-less, no local MinerU — full dual-backend quality
    (clean code from pipeline tokens, indentation/tables/Mermaid from vlm). See
    decision-pdf2wiki-cloud-dual-merge / research/2026-07-23-cloud-dual-merge-architecture.
    """
    import pymupdf

    from ..config import load_config
    from .block import Block
    from .merge import (
        collect_images,
        detect_watermarks,
        merge,
        normalize_chapters_from_toc,
        render,
        toc_level1,
    )

    cfg = cfg or load_config()
    c = cfg.mineru_cloud

    lines: list[str] = []

    def say(msg):
        print(msg)
        lines.append(str(msg))

    try:
        token = _resolve_token(cfg)
        pages = _check_pages(pdf_path, c.max_pages)
        work = os.path.join(os.path.expanduser(out_root), slug)
        say(f"cloud dual-pass merge ({pages}p): 2 API calls (pipeline + vlm) + local merge")

        # Two cloud passes, kept in separate extraction dirs (distinct image hashes, distinct content_list).
        base_dir = _run_cloud_pass(
            pdf_path,
            "pipeline",
            token,
            cfg,
            os.path.join(work, "_cloud_pipeline"),
            say,
            timeout=timeout,
        )
        hyb_dir = _run_cloud_pass(
            pdf_path, "vlm", token, cfg, os.path.join(work, "_cloud_vlm"), say, timeout=timeout
        )

        base = _load_cloud_content_list(base_dir)  # code tokens (byte-clean, flat)
        hybrid = _load_cloud_content_list(hyb_dir)  # indentation + tables/Mermaid (corrupts code)

        wm = detect_watermarks(base, pages)
        if wm:
            say(f"watermark(s) auto-detected: {[w[:50] for w in wm]}")
        final, stats = merge(base, hybrid, wm, tiny_px2=cfg.convert.tiny_px2)

        toc_l1 = toc_level1(pymupdf.open(pdf_path))  # PDF is local (we uploaded it) → ToC available
        if toc_l1:
            final, toc_stats = normalize_chapters_from_toc(final, toc_l1)
            say(f"chapter normalize from ToC: {toc_stats}")

        os.makedirs(work, exist_ok=True)
        collect_images(
            final, work
        )  # copies base(pipeline) images; rewrites img_path -> images/<hash>.jpg
        md = "\n\n".join(render(Block.from_dict(b)) for b in final)
        for w in wm:
            md = md.replace(w, " ")
        with open(os.path.join(work, f"{slug}.md"), "w", encoding="utf-8") as f:
            f.write(md)
        with open(os.path.join(work, "blocks.json"), "w", encoding="utf-8") as f:
            json.dump(final, f, indent=1, default=str)
        say(f"graft stats: {stats}")
        say(f"wrote {work}/{slug}.md ({len(md)} chars)")
        return True, "\n".join(lines)
    except CloudError as e:
        say(f"FAILED (mineru.net Cloud merge): {e}")
        return False, "\n".join(lines)
