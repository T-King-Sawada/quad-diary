"""Confluence クライアントのテスト（requests はモック）。"""

from __future__ import annotations

import requests

from app import confluence_client as cc
from app.confluence_client import ConfluenceClient, render_storage_html, _page_id


class FakeResp:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def make_client(**kw):
    base = dict(
        base_url="https://x.atlassian.net/wiki",
        email="e@x.com",
        api_token="t",
        space_id="100",
    )
    base.update(kw)
    return ConfluenceClient(**base)


# ---------------- 純粋関数 ----------------
def test_render_html_escapes_and_sections():
    e = {"date": "2026-06-18", "fact": "a<b>", "discovery": "l1\nl2", "lesson": "L", "declaration": "D"}
    html = render_storage_html(e)
    assert "<h1>4行日記 - 2026-06-18</h1>" in html
    assert "a&lt;b&gt;" in html          # エスケープ
    assert "l1<br/>l2" in html           # 改行→<br/>
    assert html.count("<h2>") == 4       # 4項目


def test_page_id_normalization():
    assert _page_id("123456/2026-06") == "123456"
    assert _page_id("  789  ") == "789"
    assert _page_id("") == ""


def test_from_config_none_when_incomplete():
    assert ConfluenceClient.from_config({"confluence": {}}) is None
    ok = ConfluenceClient.from_config(
        {"confluence": {"base_url": "https://x.atlassian.net/wiki", "space_id": "1"}}
    )
    assert ok is not None


# ---------------- 通信あり（モック） ----------------
def test_connection_success(monkeypatch):
    def fake_get(url, **kw):
        if "_edge/tenant_info" in url:
            return FakeResp(200, {"cloudId": "CID"})
        if "/api/v2/spaces/" in url:
            return FakeResp(200, {"name": "MySpace"})
        return FakeResp(404, {}, "nope")

    monkeypatch.setattr(cc.requests, "get", fake_get)
    ok, msg = make_client().test_connection()
    assert ok is True and "MySpace" in msg


def test_connection_401(monkeypatch):
    def fake_get(url, **kw):
        if "_edge/tenant_info" in url:
            return FakeResp(200, {"cloudId": "CID"})
        return FakeResp(401, {}, "unauthorized")

    monkeypatch.setattr(cc.requests, "get", fake_get)
    ok, msg = make_client().test_connection()
    assert ok is False and "401" in msg


def test_upsert_creates_when_not_found(monkeypatch):
    calls = {"post": 0}

    def fake_get(url, **kw):
        if "_edge/tenant_info" in url:
            return FakeResp(200, {"cloudId": "CID"})
        if "/api/v2/pages" in url:
            return FakeResp(200, {"results": []})   # 同名ページ無し
        return FakeResp(404)

    def fake_post(url, **kw):
        calls["post"] += 1
        return FakeResp(201, {"id": "NEWID"})

    monkeypatch.setattr(cc.requests, "get", fake_get)
    monkeypatch.setattr(cc.requests, "post", fake_post)

    entry = {"date": "2026-06-18", "fact": "f", "discovery": "", "lesson": "", "declaration": ""}
    res = make_client(parent_page_id="9").create_diary_page(entry)
    assert res.ok and res.page_id == "NEWID"
    assert calls["post"] == 1


def test_upsert_updates_when_page_id_known(monkeypatch):
    calls = {"put": 0, "post": 0}

    def fake_get(url, **kw):
        if "_edge/tenant_info" in url:
            return FakeResp(200, {"cloudId": "CID"})
        if "/api/v2/pages/" in url:                  # 既存ページ取得（バージョン）
            return FakeResp(200, {"id": "P1", "title": "x", "version": {"number": 5}})
        return FakeResp(200, {"results": []})

    def fake_put(url, **kw):
        calls["put"] += 1
        return FakeResp(200, {"id": "P1", "version": {"number": 6}})

    def fake_post(url, **kw):
        calls["post"] += 1
        return FakeResp(201, {"id": "SHOULD_NOT"})

    monkeypatch.setattr(cc.requests, "get", fake_get)
    monkeypatch.setattr(cc.requests, "put", fake_put)
    monkeypatch.setattr(cc.requests, "post", fake_post)

    entry = {
        "date": "2026-06-18", "fact": "f", "discovery": "", "lesson": "", "declaration": "",
        "confluence_page_id": "P1",
    }
    res = make_client().create_diary_page(entry)
    assert res.ok and res.page_id == "P1"
    assert calls["put"] == 1 and calls["post"] == 0   # 更新のみ、新規作成しない


def test_sync_failure_returns_error(monkeypatch):
    def fake_get(url, **kw):
        if "_edge/tenant_info" in url:
            return FakeResp(200, {"cloudId": "CID"})
        return FakeResp(200, {"results": []})

    def fake_post(url, **kw):
        return FakeResp(400, {}, "bad request")

    monkeypatch.setattr(cc.requests, "get", fake_get)
    monkeypatch.setattr(cc.requests, "post", fake_post)

    entry = {"date": "2026-06-18", "fact": "f", "discovery": "", "lesson": "", "declaration": ""}
    res = make_client().create_diary_page(entry)
    assert res.ok is False and "400" in res.error
