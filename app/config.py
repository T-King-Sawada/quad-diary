"""設定の読み書き（2層構成）。

レイヤの優先順位（後ほど上書き）:
    1. DEFAULT_CONFIG          … コード内の既定値
    2. config.default.json     … 管理者用デフォルト（配布物・任意・非秘密）
    3. config.json             … 個人の上書き（差分のみ保存・非秘密）
    4. Windows 資格情報マネージャー … API Token（平文で保存しない）

config.json には DEFAULT/管理者デフォルトと異なる項目だけを保存する（疎）。
API Token はファイルに書かず、keyring に保存して読み込み時に注入する。
"""

from __future__ import annotations

import copy
import json
import time
from typing import Any

from . import paths, secrets_store
from .logger import get_logger

log = get_logger(__name__)

DEFAULT_CONFIG: dict[str, Any] = {
    "reminder_time": "18:30",
    "popup_mode": "normal",          # normal | force（初版は normal / force のみ）
    "max_snooze_count": 3,
    "snooze_minutes": 10,            # 「N分後に再通知」ボタンの分数
    "autostart_enabled": False,
    "confluence": {
        "enabled": False,
        "base_url": "",
        "space_id": "",
        "parent_page_id": "",    # 利用者が指定する投稿先ページ
        "email": "",
        "api_token": "",
        "monthly_parent": False,  # True なら YYYY-MM 月次親ページを自動作成
    },
}


def _deep_merge(default: dict, loaded: dict) -> dict:
    """default をベースに loaded で上書き。"""
    result = copy.deepcopy(default)
    for key, value in loaded.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _deep_diff(full: dict, base: dict) -> dict:
    """full のうち base と異なる項目だけを返す（疎な差分）。"""
    diff: dict[str, Any] = {}
    for key, value in full.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            sub = _deep_diff(value, base[key])
            if sub:
                diff[key] = sub
        elif base.get(key) != value:
            diff[key] = value
    return diff


def managed_defaults() -> dict:
    """DEFAULT_CONFIG に config.default.json（あれば）を重ねた管理者デフォルト。"""
    merged = copy.deepcopy(DEFAULT_CONFIG)
    path = paths.default_config_path()
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                merged = _deep_merge(merged, data)
        except (json.JSONDecodeError, OSError) as e:
            log.error("config.default.json の読み込みに失敗（無視します）: %s", e)
    # API Token は決してファイル由来にしない（管理者デフォルトに誤って入っていても無視）
    merged.setdefault("confluence", {})["api_token"] = ""
    return merged


def is_first_run() -> bool:
    """個人設定ファイルがまだ無い＝初回起動。"""
    return not paths.config_path().exists()


def _read_personal() -> dict:
    path = paths.config_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if not isinstance(loaded, dict):
            raise ValueError("config.json のトップレベルが object ではありません。")
        return loaded
    except (json.JSONDecodeError, ValueError, OSError) as e:
        # 14.3 設定ファイル破損：退避
        backup = path.with_name(f"config.broken.{int(time.time())}.json")
        try:
            path.rename(backup)
            log.error("config.json が壊れていたため %s に退避しました: %s", backup.name, e)
        except OSError:
            log.error("config.json が壊れています（退避にも失敗）: %s", e)
        return {}


def load() -> dict:
    """管理者デフォルト ⊕ 個人設定 をマージし、トークンを注入して返す。"""
    base = managed_defaults()
    personal = _read_personal()
    cfg = _deep_merge(base, personal)

    # API Token は資格情報マネージャーから注入
    token = secrets_store.get_token()
    if token:
        cfg["confluence"]["api_token"] = token
    else:
        # 旧バージョンが config.json に平文保存していた場合は移行
        legacy = (personal.get("confluence") or {}).get("api_token", "")
        if legacy:
            log.info("config.json の平文トークンを資格情報マネージャーへ移行します。")
            secrets_store.set_token(legacy)
            cfg["confluence"]["api_token"] = legacy
            save(cfg)  # ファイルからトークンを除去して書き直し

    return cfg


def save(config: dict) -> None:
    """API Token は keyring へ、その他の差分のみ config.json へ保存する。"""
    # 1) トークンは資格情報マネージャーへ
    token = config.get("confluence", {}).get("api_token", "")
    secrets_store.set_token(token)

    # 2) 管理者デフォルトとの差分だけをファイルへ（トークンは除外）
    to_write = _deep_diff(config, managed_defaults())
    if "confluence" in to_write:
        to_write["confluence"].pop("api_token", None)
        if not to_write["confluence"]:
            to_write.pop("confluence")

    path = paths.config_path()
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(to_write, f, ensure_ascii=False, indent=2)
    tmp.replace(path)
    log.info("config を保存しました（個人差分のみ／トークンは資格情報マネージャー）。")
