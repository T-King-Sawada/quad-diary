"""API Token を Windows 資格情報マネージャー（keyring）に保存する。

config.json に平文で残さないための層。keyring が使えない環境では
失敗をログに残し、トークンはメモリ上のみ（ファイルには書かない）とする。
"""

from __future__ import annotations

from .logger import get_logger

log = get_logger(__name__)

# 旧名のまま維持（リネーム後も既存の保存トークンを引き継ぐため変更しない）
SERVICE = "DailyDiary"
ACCOUNT = "confluence_api_token"

try:
    import keyring

    _available = True
except Exception as e:  # pragma: no cover
    keyring = None  # type: ignore
    _available = False
    log.warning("keyring が利用できません（トークンは保存されません）: %s", e)


def available() -> bool:
    return _available


def get_token() -> str:
    if not _available:
        return ""
    try:
        return keyring.get_password(SERVICE, ACCOUNT) or ""
    except Exception as e:
        log.error("トークンの取得に失敗: %s", e)
        return ""


def set_token(token: str) -> None:
    if not _available:
        return
    try:
        if token:
            keyring.set_password(SERVICE, ACCOUNT, token)
        else:
            clear_token()
    except Exception as e:
        log.error("トークンの保存に失敗: %s", e)


def clear_token() -> None:
    if not _available:
        return
    try:
        keyring.delete_password(SERVICE, ACCOUNT)
    except Exception:
        pass
