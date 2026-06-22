"""同期先プロバイダのレジストリ。

新しいプロバイダを追加するときは、SyncProvider を実装して
_provider_classes() に足すだけ。
"""

from __future__ import annotations

from .base import SyncProvider, SyncResult


def _provider_classes() -> list[type[SyncProvider]]:
    # 循環 import を避けるため遅延 import する
    from ..confluence_client import ConfluenceClient

    return [ConfluenceClient]


def enabled_providers(config: dict) -> list[SyncProvider]:
    """config 上で有効かつ設定が揃っているプロバイダのインスタンス一覧。"""
    result: list[SyncProvider] = []
    for cls in _provider_classes():
        conf = config.get(cls.KEY, {})
        if not conf.get("enabled"):
            continue
        provider = cls.from_config(config)
        if provider is not None:
            result.append(provider)
    return result


__all__ = ["SyncProvider", "SyncResult", "enabled_providers"]
