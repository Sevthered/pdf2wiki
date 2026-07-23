"""Tests for the mineru.net Cloud converter (--mineru-cloud). No live API — HTTP is mocked."""

import io
import os
import sys
import zipfile
from typing import ClassVar

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pdf2wiki.config import load_config
from pdf2wiki.convert import cloud


def _make_pdf(path, pages=1):
    import pymupdf

    doc = pymupdf.open()
    for _ in range(pages):
        doc.new_page()
    doc.save(path)
    doc.close()


def _fake_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("full.md", "# Book\n\n![](images/a.jpg)\n\n```java\nint x = 1;\n```\n")
        z.writestr("images/a.jpg", b"\xff\xd8\xff\xe0jpeg")
        z.writestr("layout.json", "{}")
    return buf.getvalue()


def test_config_reads_mineru_cloud(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert load_config().mineru_cloud.model_version == "pipeline"  # default (code-safe)
    (tmp_path / "pdf2wiki.toml").write_text(
        '[mineru_cloud]\nmodel_version = "pipeline"\nlanguage = "en"\nmax_pages = 50\n'
    )
    c = load_config().mineru_cloud
    assert c.model_version == "pipeline"
    assert c.language == "en"
    assert c.max_pages == 50


def test_resolve_token_precedence(tmp_path, monkeypatch):
    cfg = load_config()
    monkeypatch.delenv("MINERU_API_TOKEN", raising=False)
    # none configured -> clear error
    with pytest.raises(cloud.CloudError, match="no mineru.net token"):
        cloud._resolve_token(cfg)
    # token_file
    tf = tmp_path / "tok"
    tf.write_text("file-tok\n")
    cfg.mineru_cloud.token_file = str(tf)
    assert cloud._resolve_token(cfg) == "file-tok"
    # env beats token_file
    monkeypatch.setenv("MINERU_API_TOKEN", "env-tok")
    assert cloud._resolve_token(cfg) == "env-tok"
    # explicit config token beats all
    cfg.mineru_cloud.token = "cfg-tok"
    assert cloud._resolve_token(cfg) == "cfg-tok"


def test_convert_cloud_happy_path(tmp_path, monkeypatch):
    pdf = tmp_path / "book.pdf"
    _make_pdf(pdf, pages=2)
    cfg = load_config()
    cfg.mineru_cloud.token = "t"

    calls = {"put": 0}

    def fake_api(url, token, method="GET", body=None, timeout=60):
        if url.endswith("/file-urls/batch"):
            assert method == "POST" and body["model_version"] == "pipeline"
            return {"batch_id": "B1", "file_urls": ["https://upload/x"]}
        if "/extract-results/batch/" in url:
            return {
                "extract_result": [
                    {"file_name": "book.pdf", "state": "done", "full_zip_url": "https://cdn/z.zip"}
                ]
            }
        raise AssertionError(url)

    def fake_put(upload_url, pdf_path, timeout=300):
        calls["put"] += 1

    class FakeZipResp:
        status_code = 200
        content = _fake_zip()

        def raise_for_status(self):
            pass

    class FakeRequests:
        RequestException = Exception

        @staticmethod
        def get(url, timeout=0):
            return FakeZipResp()

    monkeypatch.setattr(cloud, "_api", fake_api)
    monkeypatch.setattr(cloud, "_put_file", fake_put)
    monkeypatch.setattr(cloud, "_requests", lambda: FakeRequests)

    ok, log = cloud.convert_book_cloud(str(pdf), "book", str(tmp_path / "out"), cfg=cfg)
    assert ok is True
    assert calls["put"] == 1
    md = tmp_path / "out" / "book" / "book.md"
    img = tmp_path / "out" / "book" / "images" / "a.jpg"
    assert md.exists() and "int x = 1;" in md.read_text()
    assert img.exists()
    assert "THIRD-PARTY cloud" in log  # egress warning surfaced


def test_convert_cloud_page_guard(tmp_path, monkeypatch):
    pdf = tmp_path / "big.pdf"
    _make_pdf(pdf, pages=3)
    cfg = load_config()
    cfg.mineru_cloud.token = "t"
    cfg.mineru_cloud.max_pages = 2
    ok, log = cloud.convert_book_cloud(str(pdf), "big", str(tmp_path / "out"), cfg=cfg)
    assert ok is False
    assert "exceeds mineru.net" in log
    assert not (tmp_path / "out" / "big" / "big.md").exists()


class _FakeResp:
    def __init__(self, status=200, payload=None, text="", content=b""):
        self.status_code = status
        self._payload = payload
        self.text = text
        self.content = content

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code != 200:
            raise _FakeRequests.RequestException(f"HTTP {self.status_code}")


class _FakeRequests:
    RequestException = type("RequestException", (Exception,), {})
    last: ClassVar[dict] = {}

    @classmethod
    def request(cls, method, url, headers=None, json=None, timeout=0):
        cls.last = {"method": method, "url": url, "headers": headers, "json": json}
        return cls._resp

    @classmethod
    def put(cls, url, data=None, timeout=0):
        cls.last = {"put_url": url, "has_data": data is not None, "headers_sent": None}
        return cls._resp


def test_api_returns_data_and_raises(monkeypatch):
    monkeypatch.setattr(cloud, "_requests", lambda: _FakeRequests)
    _FakeRequests._resp = _FakeResp(200, {"code": 0, "data": {"batch_id": "B"}})
    assert cloud._api("http://x/y", "tok", method="POST", body={"a": 1})["batch_id"] == "B"
    # Authorization header carries the token; body sent as json (not form-encoded)
    assert _FakeRequests.last["headers"]["Authorization"] == "Bearer tok"
    assert _FakeRequests.last["json"] == {"a": 1}
    # non-200 -> CloudError
    _FakeRequests._resp = _FakeResp(401, text="unauthorized")
    with pytest.raises(cloud.CloudError, match="HTTP 401"):
        cloud._api("http://x/y", "tok")
    # API code != 0 -> CloudError
    _FakeRequests._resp = _FakeResp(200, {"code": -60005, "msg": "too big"})
    with pytest.raises(cloud.CloudError, match="code -60005"):
        cloud._api("http://x/y", "tok")


def test_put_file_no_content_type_header(tmp_path, monkeypatch):
    pdf = tmp_path / "f.pdf"
    _make_pdf(pdf, 1)
    monkeypatch.setattr(cloud, "_requests", lambda: _FakeRequests)
    _FakeRequests._resp = _FakeResp(200)
    cloud._put_file("https://upload/x", str(pdf))  # must not raise, must send bytes
    assert _FakeRequests.last["has_data"] is True
    _FakeRequests._resp = _FakeResp(403, text="SignatureDoesNotMatch")
    with pytest.raises(cloud.CloudError, match="HTTP 403"):
        cloud._put_file("https://upload/x", str(pdf))


def test_resolve_token_ignores_whitespace(monkeypatch):
    cfg = load_config()
    monkeypatch.delenv("MINERU_API_TOKEN", raising=False)
    cfg.mineru_cloud.token = "   "  # whitespace-only -> not a token
    with pytest.raises(cloud.CloudError, match="no mineru.net token"):
        cloud._resolve_token(cfg)


def test_convert_cloud_bad_pdf(tmp_path):
    cfg = load_config()
    cfg.mineru_cloud.token = "t"
    ok, log = cloud.convert_book_cloud(
        str(tmp_path / "nope.pdf"), "x", str(tmp_path / "out"), cfg=cfg
    )
    assert ok is False
    assert "cannot open PDF" in log


def _write_content_list(dest_dir, blocks):
    import json

    os.makedirs(dest_dir, exist_ok=True)
    with open(os.path.join(dest_dir, "u_content_list.json"), "w", encoding="utf-8") as f:
        json.dump(blocks, f)


def test_convert_cloud_merge_two_passes(tmp_path, monkeypatch):
    """--cloud-model merge: runs BOTH cloud passes and splices with our local merge — pipeline supplies
    byte-clean code tokens, vlm supplies indentation. Mocks the fetch; real merge() runs."""
    pdf = tmp_path / "book.pdf"
    _make_pdf(pdf, pages=1)
    cfg = load_config()
    cfg.mineru_cloud.token = "t"

    # same code block on page 0, same bbox in both passes: pipeline = flat clean tokens,
    # vlm = indented (correct) — merge must keep pipeline tokens with vlm indentation.
    pipe_blocks = [
        {
            "type": "code",
            "sub_type": "code",
            "bbox": [10, 10, 200, 80],
            "page_idx": 0,
            "code_body": "def f():\nreturn 1",
        },
        {"type": "text", "bbox": [10, 90, 200, 100], "page_idx": 0, "text": "hello"},
    ]
    vlm_blocks = [
        {
            "type": "code",
            "sub_type": "code",
            "bbox": [10, 10, 200, 79],
            "page_idx": 0,
            "code_body": "def f():\n    return 1",
        },
        {"type": "text", "bbox": [10, 90, 200, 100], "page_idx": 0, "text": "hello"},
    ]
    seen = []

    def fake_pass(pdf_path, model_version, token, cfg, dest_dir, say, timeout=None):
        seen.append(model_version)
        _write_content_list(dest_dir, pipe_blocks if model_version == "pipeline" else vlm_blocks)
        return dest_dir

    monkeypatch.setattr(cloud, "_run_cloud_pass", fake_pass)
    ok, log = cloud.convert_book_cloud_merge(str(pdf), "book", str(tmp_path / "out"), cfg=cfg)
    assert ok is True
    assert seen == ["pipeline", "vlm"]  # both passes, in order
    md = (tmp_path / "out" / "book" / "book.md").read_text()
    assert "def f():" in md and "return 1" in md
    assert "\n    return 1" in md  # vlm indentation preserved
    assert "graft stats" in log
    assert (tmp_path / "out" / "book" / "blocks.json").exists()


def test_convert_cloud_merge_page_guard(tmp_path, monkeypatch):
    pdf = tmp_path / "big.pdf"
    _make_pdf(pdf, pages=3)
    cfg = load_config()
    cfg.mineru_cloud.token = "t"
    cfg.mineru_cloud.max_pages = 2
    called = []
    monkeypatch.setattr(cloud, "_run_cloud_pass", lambda *a, **k: called.append(1))
    ok, log = cloud.convert_book_cloud_merge(str(pdf), "big", str(tmp_path / "out"), cfg=cfg)
    assert ok is False
    assert "exceeds mineru.net" in log
    assert not called  # never hit the API past the guard


def test_load_cloud_content_list_injects_abs_page(tmp_path):
    _write_content_list(
        str(tmp_path), [{"type": "text", "bbox": [0, 0, 1, 1], "page_idx": 4, "text": "x"}]
    )
    blocks = cloud._load_cloud_content_list(str(tmp_path))
    assert blocks[0]["abs_page"] == 4  # abs_page = page_idx (already absolute)
    assert blocks[0]["_imgdir"] == str(tmp_path)


def test_cli_cloud_merge_routes(monkeypatch):
    from pdf2wiki import cli
    from pdf2wiki import convert as convmod

    seen = {}

    def fake_merge(pdf, slug, out, cfg=None):
        seen["called"] = (pdf, slug)
        return True, "ok"

    monkeypatch.setattr(convmod, "convert_book_cloud_merge", fake_merge)
    rc = cli._cmd_convert(_convert_args(mineru_cloud=True, cloud_model="merge"), load_config())
    assert rc == 0
    assert seen["called"] == ("b.pdf", "slug")


def _convert_args(**over):
    from types import SimpleNamespace

    base = dict(
        pdf="b.pdf",
        name="slug",
        out=None,
        remote=None,
        hybrid_server_url=None,
        mineru_cloud=False,
        cloud_model=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_cli_cloud_mutually_exclusive_with_remote(capsys):
    from pdf2wiki import cli

    rc = cli._cmd_convert(_convert_args(mineru_cloud=True, remote="gpu-box"), load_config())
    assert rc == 2
    assert "cannot combine" in capsys.readouterr().err


def test_cli_cloud_routes_to_cloud(monkeypatch):
    from pdf2wiki import cli
    from pdf2wiki import convert as convmod

    seen = {}

    def fake_cloud(pdf, slug, out, cfg=None):
        seen["called"] = (pdf, slug, cfg.mineru_cloud.model_version)
        return True, "ok"

    monkeypatch.setattr(convmod, "convert_book_cloud", fake_cloud)
    rc = cli._cmd_convert(_convert_args(mineru_cloud=True, cloud_model="pipeline"), load_config())
    assert rc == 0
    assert seen["called"] == ("b.pdf", "slug", "pipeline")  # flag overrode model_version


# ---------- resilience + security hardening (tech-books review port) ----------


def test_transient_status_classification():
    assert (
        cloud._transient_status(429)
        and cloud._transient_status(500)
        and cloud._transient_status(503)
    )
    assert (
        not cloud._transient_status(400)
        and not cloud._transient_status(401)
        and not cloud._transient_status(404)
    )


def test_retry_retries_transient_then_succeeds(monkeypatch):
    monkeypatch.setattr(cloud.time, "sleep", lambda *_: None)
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] == 1:
            raise cloud.CloudError("blip", transient=True)
        return "ok"

    assert cloud._retry("x", fn, tries=3, base_delay=0.01, say=lambda *_: None) == "ok"
    assert calls["n"] == 2  # retried once, then succeeded


def test_retry_reraises_permanent_immediately(monkeypatch):
    monkeypatch.setattr(cloud.time, "sleep", lambda *_: None)
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise cloud.CloudError("nope", transient=False)

    with pytest.raises(cloud.CloudError, match="nope"):
        cloud._retry("x", fn, tries=3, base_delay=0.01, say=lambda *_: None)
    assert calls["n"] == 1  # permanent error is NOT retried


def test_retry_gives_up_after_tries(monkeypatch):
    monkeypatch.setattr(cloud.time, "sleep", lambda *_: None)
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise cloud.CloudError("blip", transient=True)

    with pytest.raises(cloud.CloudError):
        cloud._retry("x", fn, tries=3, base_delay=0.01, say=lambda *_: None)
    assert calls["n"] == 3  # bounded: exactly `tries` attempts


def test_require_https_rejects_http():
    assert cloud._require_https("https://mineru.net/x", "up").startswith("https")
    with pytest.raises(cloud.CloudError, match="non-HTTPS"):
        cloud._require_https("http://mineru.net/x", "up")


def test_safe_extract_blocks_zip_slip(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("../evil.txt", "pwned")  # member escapes dest_dir
    with pytest.raises(cloud.CloudError, match="unsafe zip member"):
        cloud._safe_extract(buf.getvalue(), str(tmp_path / "d"))
    assert not (tmp_path / "evil.txt").exists()  # nothing written outside dest


def test_safe_extract_allows_benign_zip(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("ok/full.md", "hi")
    cloud._safe_extract(buf.getvalue(), str(tmp_path / "d2"))
    assert (tmp_path / "d2" / "ok" / "full.md").read_text() == "hi"


def test_run_cloud_pass_resumes_from_done(tmp_path, monkeypatch):
    cfg = load_config()
    cfg.mineru_cloud.token = "t"
    dest = tmp_path / "_cloud_pipeline"
    dest.mkdir()
    (dest / ".done").write_text("ok\n")
    (dest / "full.md").write_text("cached")

    def boom(*a, **k):
        raise AssertionError("must not touch the network on resume")

    monkeypatch.setattr(cloud, "_api", boom)
    monkeypatch.setattr(cloud, "_put_file", boom)
    monkeypatch.setattr(cloud, "_requests", boom)
    said = []
    out = cloud._run_cloud_pass(
        str(tmp_path / "book.pdf"), "pipeline", "t", cfg, str(dest), said.append
    )
    assert out == str(dest)
    assert any("reusing cached" in s for s in said)
