"""日記の本機保存（JSONL）。年ごとに data/diary_YYYY.jsonl へ保存する。

1 行 = 1 件の DiaryEntry。同じ日付は upsert（追記ではなく置換）する。
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from typing import Any, Optional

from . import paths
from .logger import get_logger

log = get_logger(__name__)


def today_str() -> str:
    return date.today().isoformat()


def _file_for_year(year: int):
    return paths.data_dir() / f"diary_{year}.jsonl"


def load_year(year: int) -> list[dict]:
    path = _file_for_year(year)
    if not path.exists():
        return []
    entries: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                log.warning("%s の %d 行目を JSON として読めませんでした（スキップ）。", path.name, i)
    return entries


def all_entries() -> list[dict]:
    """全年の日記を日付順で返す。"""
    result: list[dict] = []
    for path in sorted(paths.data_dir().glob("diary_*.jsonl")):
        try:
            year = int(path.stem.split("_")[1])
        except (IndexError, ValueError):
            continue
        result.extend(load_year(year))
    result.sort(key=lambda e: e.get("date", ""))
    return result


def unsynced_entries() -> list[dict]:
    """未同期（pending / failed）の日記を返す。"""
    return [e for e in all_entries() if e.get("sync_status") in ("pending", "failed")]


def get_entry(date_str: str) -> Optional[dict]:
    year = int(date_str[:4])
    for e in load_year(year):
        if e.get("date") == date_str:
            return e
    return None


def is_submitted(date_str: str) -> bool:
    return get_entry(date_str) is not None


def new_entry(
    date_str: str,
    fact: str,
    discovery: str,
    lesson: str,
    declaration: str,
    existing: Optional[dict] = None,
) -> dict[str, Any]:
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    created = existing.get("created_at") if existing else now
    return {
        "id": date_str,
        "date": date_str,
        "fact": fact,
        "discovery": discovery,
        "lesson": lesson,
        "declaration": declaration,
        "created_at": created or now,
        "updated_at": now,
        "sync_status": (existing or {}).get("sync_status", "none"),
        "confluence_page_id": (existing or {}).get("confluence_page_id"),
        "sync_error": (existing or {}).get("sync_error"),
    }


def save_entry(entry: dict) -> None:
    """date が一致する行を置換、無ければ追記して全件を書き直す。"""
    year = int(entry["date"][:4])
    path = _file_for_year(year)

    entries = load_year(year)
    replaced = False
    for i, e in enumerate(entries):
        if e.get("date") == entry["date"]:
            entries[i] = entry
            replaced = True
            break
    if not replaced:
        entries.append(entry)

    tmp = path.with_suffix(".jsonl.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    os.replace(tmp, path)
    log.info("日記を保存しました: %s (%s)", entry["date"], "更新" if replaced else "新規")
