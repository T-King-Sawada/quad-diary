"""境界条件・バグ探し用テスト。"""

from __future__ import annotations

import requests

from app import confluence_client as cc, storage
from app.confluence_client import ConfluenceClient


class FakeResp:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            err = requests.HTTPError(f"HTTP {self.status_code}")
            resp = requests.Response()
            resp.status_code = self.status_code
            err.response = resp
            raise err


def make_client(**kw):
    base = dict(base_url="https://x.atlassian.net/wiki", email="e@x.com", api_token="t", space_id="100")
    base.update(kw)
    return ConfluenceClient(**base)


# ---------------- storage ----------------
def test_storage_cross_year(isolated_paths):
    storage.save_entry(storage.new_entry("2025-12-31", "a", "", "", ""))
    storage.save_entry(storage.new_entry("2026-01-01", "b", "", "", ""))
    assert (isolated_paths / "data" / "diary_2025.jsonl").exists()
    assert (isolated_paths / "data" / "diary_2026.jsonl").exists()
    dates = [e["date"] for e in storage.all_entries()]
    assert dates == ["2025-12-31", "2026-01-01"]   # 日付順


def test_storage_skips_corrupt_line(isolated_paths):
    p = isolated_paths / "data"
    p.mkdir(parents=True, exist_ok=True)
    (p / "diary_2026.jsonl").write_text(
        '{"date":"2026-06-18","fact":"ok"}\nTHIS IS BROKEN\n{"date":"2026-06-19","fact":"ok2"}\n',
        encoding="utf-8",
    )
    rows = storage.load_year(2026)
    assert len(rows) == 2   # 壊れた行はスキップ


# ---------------- confluence: 月次親の自動作成 ----------------
def test_monthly_parent_creates_year_then_month(monkeypatch):
    posted = []

    def fake_get(url, **kw):
        if "_edge/tenant_info" in url:
            return FakeResp(200, {"cloudId": "CID"})
        if "/api/v2/pages" in url:
            return FakeResp(200, {"results": []})    # 年・月とも未存在
        return FakeResp(404)

    def fake_post(url, **kw):
        title = kw.get("json", {}).get("title")
        posted.append(title)
        return FakeResp(201, {"id": f"id-{title}"})

    monkeypatch.setattr(cc.requests, "get", fake_get)
    monkeypatch.setattr(cc.requests, "post", fake_post)

    entry = {"date": "2026-06-18", "fact": "f", "discovery": "", "lesson": "", "declaration": ""}
    res = make_client(parent_page_id="root", monthly_parent=True).create_diary_page(entry)
    assert res.ok
    # 年(2026) → 月(2026-06) → 日記 の順に作成される
    assert posted == ["2026", "2026-06", "4行日記 - 2026-06-18"]


# ---------------- confluence: 削除済みページIDの扱い（バグ探し） ----------------
def test_stale_page_id_falls_back_to_create(monkeypatch):
    """保存済み page_id が指すページが削除済み(404)でも、再作成できるべき。"""
    def fake_get(url, **kw):
        if "_edge/tenant_info" in url:
            return FakeResp(200, {"cloudId": "CID"})
        if "/api/v2/pages/" in url:          # 既存ページ取得 → 404（削除済み）
            return FakeResp(404, {}, "not found")
        if "/api/v2/pages" in url:           # タイトル検索 → 無し
            return FakeResp(200, {"results": []})
        return FakeResp(404)

    def fake_post(url, **kw):
        return FakeResp(201, {"id": "NEW"})

    monkeypatch.setattr(cc.requests, "get", fake_get)
    monkeypatch.setattr(cc.requests, "post", fake_post)

    entry = {
        "date": "2026-06-18", "fact": "f", "discovery": "", "lesson": "", "declaration": "",
        "confluence_page_id": "DELETED_ID",
    }
    res = make_client().create_diary_page(entry)
    assert res.ok is True and res.page_id == "NEW"   # 再作成にフォールバックしてほしい
