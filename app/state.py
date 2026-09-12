"""日付単位の軽い実行時状態（data/state.json）。

設定でも日記でもない、「その日もう定刻リマインダーに応答したか」だけを覚える。
プロセスをまたいで残す必要があるのはこれだけなので、意図的に小さく保つ。

なぜ必要か
----------
以前は「本日1件でも保存済み＝定刻リマインダーは不要」と判定していたため、
昼に先に書いて保存すると 18:30 の窓が出ず、その日の残りを書き損ねていた。
判定を「保存したか」から「定刻リマインダーに応答したか」へ移すために、
応答の事実だけを永続化する。

保存しないもの（意図的）
------------------------
キャンセル（dismiss）は永続化しない。未応答のまま再起動したら、その日のうちは
もう一度出したほうが「書き忘れ」を防げるため。
"""

from __future__ import annotations

import json
from typing import Any, Optional

from . import paths
from .logger import get_logger

log = get_logger(__name__)


def _path():
    return paths.data_dir() / "state.json"


def load() -> dict[str, Any]:
    path = _path()
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError) as e:
        # 壊れていても致命的ではない（リマインダーが1回多く出るだけ）
        log.warning("state.json を読めませんでした（無視します）: %s", e)
        return {}


def save(state: dict[str, Any]) -> None:
    path = _path()
    tmp = path.with_suffix(".json.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        tmp.replace(path)
    except OSError as e:
        log.warning("state.json を保存できませんでした（無視します）: %s", e)


def reminder_handled_on() -> Optional[str]:
    """定刻リマインダーに応答した日付（YYYY-MM-DD）。未応答なら None。"""
    value = load().get("reminder_handled_on")
    return value if isinstance(value, str) else None


def set_reminder_handled(date_str: str) -> None:
    state = load()
    state["reminder_handled_on"] = date_str
    save(state)
    log.info("定刻リマインダーに応答済みとして記録しました: %s", date_str)
