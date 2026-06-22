"""プロバイダ抽象（汎用同期インターフェイス）のテスト。"""

from __future__ import annotations

from app import providers
from app.confluence_client import ConfluenceClient
from app.providers.base import SyncProvider


def test_confluence_implements_provider():
    assert issubclass(ConfluenceClient, SyncProvider)
    assert ConfluenceClient.KEY == "confluence"
    assert ConfluenceClient.LABEL == "Confluence"
    assert hasattr(ConfluenceClient, "upsert_entry")


def test_enabled_providers_empty():
    assert providers.enabled_providers({}) == []
    # enabled でも設定不足なら除外
    assert providers.enabled_providers({"confluence": {"enabled": True}}) == []


def test_enabled_providers_confluence():
    cfg = {
        "confluence": {
            "enabled": True,
            "base_url": "https://x.atlassian.net/wiki",
            "space_id": "1",
        }
    }
    ps = providers.enabled_providers(cfg)
    assert len(ps) == 1
    assert ps[0].KEY == "confluence"


def test_disabled_provider_excluded():
    cfg = {
        "confluence": {
            "enabled": False,
            "base_url": "https://x.atlassian.net/wiki",
            "space_id": "1",
        }
    }
    assert providers.enabled_providers(cfg) == []
