"""Confluence Cloud REST API v2 クライアント。

日記 1 件につき 1 ページを作成する（設計 F-101 / 12.1）。
認証は Atlassian の email + API Token による Basic 認証。

base_url は wiki を含む形を想定：
    https://your-domain.atlassian.net/wiki
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import requests
from requests.auth import HTTPBasicAuth

from .diary_dialog import FIELDS
from .logger import get_logger

log = get_logger(__name__)

TIMEOUT = 20

# スコープ付き API Token はサイト直 URL では 401 になり、この
# ゲートウェイ + cloudId 経由でのみ Basic 認証が通る。
GATEWAY = "https://api.atlassian.com/ex/confluence"


@dataclass
class SyncResult:
    ok: bool
    page_id: Optional[str] = None
    error: Optional[str] = None


def _page_id(value) -> str:
    """ページIDを数値部分だけに正規化（URL の "/slug" を除去）。"""
    return str(value or "").strip().split("/")[0].strip()


def render_storage_html(entry: dict) -> str:
    """Confluence storage format(HTML) を生成する（設計 F-101）。"""
    date = entry.get("date", "")
    parts = [f"<h1>4行日記 - {html.escape(date)}</h1>"]
    for key, label, _ in FIELDS:
        text = entry.get(key, "") or ""
        # 改行を <br/> に、本文は HTML エスケープ
        body = html.escape(text).replace("\n", "<br/>")
        parts.append(f"<h2>{html.escape(label)}</h2>")
        parts.append(f"<p>{body}</p>")
    return "\n".join(parts)


class ConfluenceClient:
    def __init__(
        self,
        base_url: str,
        email: str,
        api_token: str,
        space_id: str,
        parent_page_id: str = "",
        monthly_parent: bool = False,
    ):
        self.base_url = (base_url or "").rstrip("/")
        self.auth = HTTPBasicAuth(email, api_token)
        self.space_id = str(space_id or "").strip()
        # ページIDは数値のみ（URL の "/2026" などが混ざっても先頭の数値を採用）
        self.parent_page_id = _page_id(parent_page_id)
        self.monthly_parent = bool(monthly_parent)
        self._cloud_id: Optional[str] = None

    def _site_root(self) -> str:
        """base_url から サイトのルート(scheme://host)を取り出す。"""
        p = urlparse(self.base_url)
        return f"{p.scheme}://{p.netloc}"

    def _resolve_cloud_id(self) -> str:
        if self._cloud_id:
            return self._cloud_id
        r = requests.get(
            f"{self._site_root()}/_edge/tenant_info", timeout=TIMEOUT
        )
        r.raise_for_status()
        self._cloud_id = r.json()["cloudId"]
        return self._cloud_id

    def _api_root(self) -> str:
        return f"{GATEWAY}/{self._resolve_cloud_id()}"

    @classmethod
    def from_config(cls, config: dict) -> Optional["ConfluenceClient"]:
        conf = config.get("confluence", {})
        if not conf.get("base_url") or not conf.get("space_id"):
            return None
        return cls(
            base_url=conf.get("base_url", ""),
            email=conf.get("email", ""),
            api_token=conf.get("api_token", ""),
            space_id=conf.get("space_id", ""),
            parent_page_id=conf.get("parent_page_id", ""),
            monthly_parent=conf.get("monthly_parent", False),
        )

    def test_connection(self) -> tuple[bool, str]:
        if not self.base_url or not self.space_id:
            return False, "Base URL と Space ID を入力してください。"
        try:
            url = f"{self._api_root()}/api/v2/spaces/{self.space_id}"
            r = requests.get(
                url,
                auth=self.auth,
                headers={"Accept": "application/json"},
                timeout=TIMEOUT,
            )
            if r.status_code == 200:
                name = r.json().get("name", "")
                return True, f"接続成功（Space: {name}）"
            if r.status_code in (401, 403):
                return False, f"認証エラー (HTTP {r.status_code})。Email / API Token を確認してください。"
            if r.status_code == 404:
                return False, "Space が見つかりません (HTTP 404)。Space ID と Base URL を確認してください。"
            return False, f"接続失敗: HTTP {r.status_code} {r.text[:200]}"
        except (requests.RequestException, KeyError, ValueError) as e:
            return False, f"接続エラー: {e}"

    def _find_page_by_title(self, title: str) -> Optional[str]:
        """スペース内で完全一致するタイトルのページIDを返す（無ければ None）。"""
        r = requests.get(
            f"{self._api_root()}/api/v2/pages",
            params={"space-id": self.space_id, "title": title, "limit": 5},
            auth=self.auth,
            headers={"Accept": "application/json"},
            timeout=TIMEOUT,
        )
        if r.status_code == 200:
            for p in r.json().get("results", []):
                if p.get("title") == title:
                    return str(p.get("id"))
        return None

    def _create_page(self, title: str, parent: Optional[str]) -> str:
        payload = {
            "spaceId": self.space_id,
            "status": "current",
            "title": title,
            "body": {
                "representation": "storage",
                "value": f"<p>4行日記 {html.escape(title)}</p>",
            },
        }
        if parent:
            payload["parentId"] = parent
        r = requests.post(
            f"{self._api_root()}/api/v2/pages",
            json=payload,
            auth=self.auth,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        page_id = str(r.json()["id"])
        log.info("親ページを作成しました: %s (id=%s)", title, page_id)
        return page_id

    def _update_page(self, page_id: str, title: str, value: str) -> None:
        """既存ページの本文を更新する（バージョンを +1）。"""
        get = requests.get(
            f"{self._api_root()}/api/v2/pages/{page_id}",
            auth=self.auth,
            headers={"Accept": "application/json"},
            timeout=TIMEOUT,
        )
        get.raise_for_status()
        current_version = get.json().get("version", {}).get("number", 1)

        payload = {
            "id": str(page_id),
            "status": "current",
            "title": title,
            "body": {"representation": "storage", "value": value},
            "version": {"number": current_version + 1},
        }
        put = requests.put(
            f"{self._api_root()}/api/v2/pages/{page_id}",
            json=payload,
            auth=self.auth,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=TIMEOUT,
        )
        put.raise_for_status()

    def _ensure_monthly_page(self, year_month: str) -> str:
        """年→月の2階層を保証し、月ページのIDを返す。

        ルート（parent_page_id）の下に YYYY 年ページ、その下に YYYY-MM 月ページ。
        既存ページがあれば再利用し、無いものだけ作成する。
        """
        year = year_month[:4]
        # 1) 年ページ
        year_id = self._find_page_by_title(year)
        if not year_id:
            year_id = self._create_page(year, self.parent_page_id or None)
        # 2) 月ページ（年ページの下）
        month_id = self._find_page_by_title(year_month)
        if not month_id:
            month_id = self._create_page(year_month, year_id)
        return month_id

    def create_diary_page(self, entry: dict) -> SyncResult:
        """日記ページを作成、既に同名ページがあれば更新する（upsert）。"""
        title = f"4行日記 - {entry.get('date', '')}"
        value = render_storage_html(entry)
        try:
            # 既存ページの特定：保存済みID → 無ければ同名タイトル検索
            page_id = _page_id(entry.get("confluence_page_id") or "")
            if not page_id:
                page_id = self._find_page_by_title(title)

            if page_id:
                # 既存ページを更新（重複作成を回避）
                self._update_page(page_id, title, value)
                log.info("Confluence ページを更新しました: %s (id=%s)", title, page_id)
                return SyncResult(ok=True, page_id=page_id)

            # 新規作成（親ページを決定）
            if self.monthly_parent:
                parent = self._ensure_monthly_page(entry.get("date", "")[:7])
            else:
                parent = self.parent_page_id or None
            payload = {
                "spaceId": self.space_id,
                "status": "current",
                "title": title,
                "body": {"representation": "storage", "value": value},
            }
            if parent:
                payload["parentId"] = parent

            r = requests.post(
                f"{self._api_root()}/api/v2/pages",
                json=payload,
                auth=self.auth,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                timeout=TIMEOUT,
            )
            if r.status_code in (200, 201):
                new_id = str(r.json().get("id"))
                log.info("Confluence ページを作成しました: %s (id=%s)", title, new_id)
                return SyncResult(ok=True, page_id=new_id)
            msg = f"HTTP {r.status_code}: {r.text[:300]}"
            log.error("Confluence 同期失敗: %s", msg)
            return SyncResult(ok=False, error=msg)
        except (requests.RequestException, KeyError, ValueError) as e:
            log.error("Confluence 同期エラー: %s", e)
            return SyncResult(ok=False, error=str(e))
