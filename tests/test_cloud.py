"""Tests for the mineru.net Cloud converter (--mineru-cloud). No live API — HTTP is mocked."""
import io
import os
import sys
import zipfile

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
    assert load_config().mineru_cloud.model_version == "pipeline"   # default (code-safe)
    (tmp_path / "pdf2wiki.toml").write_text(
        "[mineru_cloud]\nmodel_version = \"pipeline\"\nlanguage = \"en\"\nmax_pages = 50\n")
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
            return {"extract_result": [{"file_name": "book.pdf", "state": "done",
                                        "full_zip_url": "https://cdn/z.zip"}]}
        raise AssertionError(url)

    def fake_put(upload_url, pdf_path, timeout=300):
        calls["put"] += 1

    class FakeZipResp:
        content = _fake_zip()
        def raise_for_status(self): pass

    class FakeRequests:
        RequestException = Exception
        @staticmethod
        def get(url, timeout=0): return FakeZipResp()

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
    assert "THIRD-PARTY cloud" in log      # egress warning surfaced


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
    last = {}
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
    cloud._put_file("https://upload/x", str(pdf))       # must not raise, must send bytes
    assert _FakeRequests.last["has_data"] is True
    _FakeRequests._resp = _FakeResp(403, text="SignatureDoesNotMatch")
    with pytest.raises(cloud.CloudError, match="HTTP 403"):
        cloud._put_file("https://upload/x", str(pdf))


def test_resolve_token_ignores_whitespace(monkeypatch):
    cfg = load_config()
    monkeypatch.delenv("MINERU_API_TOKEN", raising=False)
    cfg.mineru_cloud.token = "   "                       # whitespace-only -> not a token
    with pytest.raises(cloud.CloudError, match="no mineru.net token"):
        cloud._resolve_token(cfg)


def test_convert_cloud_bad_pdf(tmp_path):
    cfg = load_config()
    cfg.mineru_cloud.token = "t"
    ok, log = cloud.convert_book_cloud(str(tmp_path / "nope.pdf"), "x", str(tmp_path / "out"), cfg=cfg)
    assert ok is False
    assert "cannot open PDF" in log


def _convert_args(**over):
    from types import SimpleNamespace
    base = dict(pdf="b.pdf", name="slug", out=None, remote=None,
                hybrid_server_url=None, mineru_cloud=False, cloud_model=None)
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
    assert seen["called"] == ("b.pdf", "slug", "pipeline")   # flag overrode model_version
