"""Fully-managed mineru.net Cloud converter (`--mineru-cloud`).

No GPU and no local MinerU: the PDF is uploaded to the OpenDataLab cloud (mineru.net Precision API),
parsed there, and the result Markdown + images are pulled back. Output layout matches the local
converter (`<out>/<slug>/<slug>.md` + `images/`), so phase5 consumes it unchanged.

⚠ DATA EGRESS: this uploads the source PDF to a third-party cloud. Only reachable behind the explicit
`--mineru-cloud` opt-in, and it logs the upload loudly. Do not use for material you cannot send offsite.

Uses `requests` (the `[cloud]` extra), lazy-imported so the core install stays dependency-light. It is
required here because the OSS pre-signed upload URL is signed with NO Content-Type header, and urllib
auto-adds one → SignatureDoesNotMatch; requests sends the raw body without it. Token is read from config,
then env MINERU_API_TOKEN, then a token_file; it is never written to disk or logged.
"""
import os
import time
import zipfile
from io import BytesIO


class CloudError(RuntimeError):
    """A mineru.net Cloud request failed. Raised loud (fail-fast) — never silently degraded."""


def _requests():
    try:
        import requests
    except ModuleNotFoundError as e:
        raise CloudError(
            "--mineru-cloud needs the 'requests' package: pip install 'pdf2wiki[cloud]' (or "
            "pip install requests)."
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


def _api(url, token, method="GET", body=None, timeout=60):
    """One JSON API call to mineru.net. Returns the `data` payload; raises CloudError on HTTP/API error."""
    requests = _requests()
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.request(method, url, headers=headers, json=body, timeout=timeout)
    except requests.RequestException as e:
        raise CloudError(f"{method} {url} unreachable: {e}") from e
    if r.status_code != 200:
        raise CloudError(f"{method} {url} -> HTTP {r.status_code}: {r.text[:400]}")
    payload = r.json()
    if payload.get("code") != 0:
        raise CloudError(f"{method} {url} -> API code {payload.get('code')}: {payload.get('msg')}")
    return payload["data"]


def _put_file(upload_url, pdf_path, timeout=300):
    """Upload the PDF to a mineru.net pre-signed URL. PUT with NO Content-Type (the URL is signed
    without one; adding one breaks the OSS signature)."""
    requests = _requests()
    with open(pdf_path, "rb") as f:
        try:
            r = requests.put(upload_url, data=f, timeout=timeout)
        except requests.RequestException as e:
            raise CloudError(f"upload PUT unreachable: {e}") from e
    if r.status_code != 200:
        raise CloudError(f"upload PUT -> HTTP {r.status_code}: {r.text[:200]}")


def convert_book_cloud(pdf_path: str, slug: str, out_root: str, *,
                       cfg=None, model_version: str | None = None,
                       timeout: int | None = None) -> tuple[bool, str]:
    """Convert one book via the mineru.net Cloud API. Returns (ok, log_text).

    Output: <out_root>/<slug>/<slug>.md plus <out_root>/<slug>/images/ — the same layout the local
    converter produces (mineru.net already emits `![](images/<hash>.jpg)` refs, so no path rewrite).
    """
    import pymupdf

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
        try:
            pages = pymupdf.open(pdf_path).page_count
        except Exception as e:
            raise CloudError(f"cannot open PDF '{pdf_path}': {e}") from e
        if pages > c.max_pages:
            raise CloudError(
                f"{pages} pages exceeds mineru.net's {c.max_pages}-page limit per file. Split the PDF "
                f"into <= {c.max_pages}-page parts and convert each (cloud chunking is not automated)."
            )

        name = os.path.basename(pdf_path)
        say(f"⚠ mineru.net Cloud: uploading '{name}' ({pages}p) to a THIRD-PARTY cloud "
            f"(model_version={model_version}, lang={c.language}). Data leaves this machine.")

        # Step 1: request a pre-signed upload URL for this file.
        body = {
            "files": [{"name": name, "is_ocr": False}],
            "model_version": model_version,
            "enable_formula": True,
            "enable_table": True,
            "language": c.language,
        }
        if c.extra_formats:
            body["extra_formats"] = list(c.extra_formats)
        sub = _api(f"{c.base_url}/file-urls/batch", token, method="POST", body=body)
        batch_id = sub["batch_id"]
        upload_url = sub["file_urls"][0]

        # Step 2: upload the bytes.
        _put_file(upload_url, pdf_path)
        say(f"uploaded; batch={batch_id}; polling…")

        # Step 3: poll until this file is done (or failed). Fail-fast + loud on error.
        deadline = time.monotonic() + (timeout or c.poll_timeout)
        zip_url = None
        while time.monotonic() < deadline:
            data = _api(f"{c.base_url}/extract-results/batch/{batch_id}", token)
            item = next((x for x in data.get("extract_result", []) if x.get("file_name") == name), None)
            if item:
                state = item.get("state")
                if state == "done":
                    zip_url = item["full_zip_url"]
                    break
                if state == "failed":
                    raise CloudError(f"cloud parse failed for '{name}': {item.get('err_msg')}")
                prog = item.get("extract_progress", {})
                say(f"  state={state} {prog.get('extracted_pages', '?')}/{prog.get('total_pages', '?')}")
            time.sleep(6)
        if not zip_url:
            raise CloudError(f"timed out after {timeout or c.poll_timeout}s waiting for batch {batch_id}")

        # Step 4: download the result zip and lay it out like the local converter.
        work = os.path.join(os.path.expanduser(out_root), slug)
        os.makedirs(work, exist_ok=True)
        requests = _requests()
        try:
            resp = requests.get(zip_url, timeout=300)
            resp.raise_for_status()
            zbytes = resp.content
        except requests.RequestException as e:
            raise CloudError(f"result download failed: {e}") from e
        zf = zipfile.ZipFile(BytesIO(zbytes))
        md_member = next((n for n in zf.namelist() if n == "full.md" or n.endswith("/full.md")), None)
        if not md_member:
            raise CloudError(f"result zip has no full.md (members: {zf.namelist()[:8]})")
        md_text = zf.read(md_member).decode("utf-8")
        with open(os.path.join(work, f"{slug}.md"), "w", encoding="utf-8") as f:
            f.write(md_text)
        n_img = 0
        for member in zf.namelist():
            if member.startswith("images/") and not member.endswith("/"):
                dest = os.path.join(work, "images", os.path.basename(member))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, "wb") as f:
                    f.write(zf.read(member))
                n_img += 1
        say(f"wrote {work}/{slug}.md ({len(md_text)} chars), {n_img} images")
        return True, "\n".join(lines)
    except CloudError as e:
        say(f"FAILED (mineru.net Cloud): {e}")
        return False, "\n".join(lines)
