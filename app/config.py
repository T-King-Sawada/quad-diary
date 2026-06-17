"""config.json の読み書き。デフォルト値の補完と、壊れたファイルの退避を行う。"""

from __future__ import annotations

import copy
import json
import time
from typing import Any

from . import paths
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
        "parent_page_id": "",
        "email": "",
        "api_token": "",
        "monthly_parent": False,  # True なら YYYY-MM 月次親ページを自動作成
    },
}


def _deep_merge(default: dict, loaded: dict) -> dict:
    """default をベースに loaded で上書き。未知キーは無視せず残す。"""
    result = copy.deepcopy(default)
    for key, value in loaded.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load() -> dict:
    path = paths.config_path()
    if not path.exists():
        log.info("config.json が無いためデフォルトで新規作成します。")
        save(DEFAULT_CONFIG)
        return copy.deepcopy(DEFAULT_CONFIG)

    try:
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if not isinstance(loaded, dict):
            raise ValueError("config.json のトップレベルが object ではありません。")
        return _deep_merge(DEFAULT_CONFIG, loaded)
    except (json.JSONDecodeError, ValueError, OSError) as e:
        # 14.3 設定ファイル破損：退避してデフォルト再生成
        backup = path.with_name(f"config.broken.{int(time.time())}.json")
        try:
            path.rename(backup)
            log.error("config.json が壊れていたため %s に退避しました: %s", backup.name, e)
        except OSError:
            log.error("config.json が壊れています（退避にも失敗）: %s", e)
        save(DEFAULT_CONFIG)
        return copy.deepcopy(DEFAULT_CONFIG)


def save(config: dict) -> None:
    path = paths.config_path()
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    tmp.replace(path)
    log.info("config を保存しました。")
