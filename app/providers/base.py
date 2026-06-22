"""同期先プロバイダの共通インターフェイス。

新しい連携先（Notion / Google Docs / Google Sheets 等）を追加するときは、
この SyncProvider を実装したクラスを作り、providers/__init__.py の
PROVIDER_CLASSES に登録するだけでよい。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class SyncResult:
    ok: bool
    page_id: Optional[str] = None
    error: Optional[str] = None


class SyncProvider(ABC):
    KEY: str = ""      # config 内のキー（例 "confluence"）
    LABEL: str = ""    # 表示名（例 "Confluence"）

    @classmethod
    @abstractmethod
    def from_config(cls, config: dict) -> "Optional[SyncProvider]":
        """config から生成。設定不足なら None を返す。"""

    @abstractmethod
    def test_connection(self) -> tuple[bool, str]:
        """接続テスト。(成功か, メッセージ) を返す。"""

    @abstractmethod
    def upsert_entry(self, entry: dict) -> SyncResult:
        """日記 1 件を連携先へ作成/更新する。"""
