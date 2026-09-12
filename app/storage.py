"""日記の本機保存（JSONL）。年ごとに data/diary_YYYY.jsonl へ保存する。

1 行 = 1 件の DiaryEntry。同じ日付は upsert（追記ではなく置換）する。

宣言の検証（再浮上）
--------------------
「宣言」は *明日やること* として扱う。宣言を書くと検証ポインタが付き、
翌日以降の入力画面の先頭に「まだ応答していない宣言」として再浮上する。

    review_at     … 検証予定日（既定＝宣言を書いた翌日）。宣言が空なら None
    review_state  … pending / done / dropped / shelved / superseded
    review_result … 応答の内容（result・note・reviewed_on）

リストが「達成」以外でもゼロになるよう、出口を 4 つ用意する：
    done        できた
    dropped     もう降りる（＝有効な結果。向いていなかったという発見）
    superseded  同じ宣言を書き直した（＝継続の意思表示）
    shelved     AUTO_SHELVE_DAYS 日間無反応で自動保留（放置してもリストが伸びない）

習慣かどうかは *書くときに決めない*。同じ宣言が何回書かれたかを後から数える
（declaration_repeat_count）ことで、習慣化を事実として発見する。
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Optional

from . import paths
from .logger import get_logger

log = get_logger(__name__)

# 宣言の検証状態
REVIEW_PENDING = "pending"
REVIEW_DONE = "done"
REVIEW_DROPPED = "dropped"
REVIEW_SHELVED = "shelved"
REVIEW_SUPERSEDED = "superseded"

#: これ以上放置された宣言は自動で保留にする（リストを伸ばし続けない）
AUTO_SHELVE_DAYS = 14

#: 入力画面に一度に出す宣言の最大件数（残りは「他N件」に畳む）
MAX_VISIBLE_REVIEWS = 3

#: 「あとで」を押したときに検証日を延ばす日数
DEFER_DAYS = 7

#: 追記ブロックの種別（Phase 2）。検証は付けない＝溜めるだけ。
BLOCK_THOUGHT = "thought"   # 4行に収まらない考え
BLOCK_SEED = "seed"         # 「後で書きたい」だけのメモ（書けない日の逃げ道）
BLOCK_KINDS = (BLOCK_THOUGHT, BLOCK_SEED)


def today_str() -> str:
    return date.today().isoformat()


def _shift(date_str: str, days: int) -> str:
    return (date.fromisoformat(date_str) + timedelta(days=days)).isoformat()


def _days_between(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def _normalize(text: str) -> str:
    """宣言の同一判定用。前後の空白と行末の差異を無視する。"""
    return "\n".join(line.strip() for line in (text or "").splitlines()).strip()


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
    reviews: Optional[list[dict]] = None,
    meta: Optional[dict] = None,
    entries: Optional[list[dict]] = None,
) -> dict[str, Any]:
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    created = existing.get("created_at") if existing else now
    entry: dict[str, Any] = {
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

    # --- 宣言の検証ポインタ ---
    # 同じ日を再編集しても、宣言の文面が変わっていなければ検証状態を引き継ぐ。
    prev_declaration = _normalize((existing or {}).get("declaration", ""))
    keeps_state = (
        existing is not None
        and prev_declaration == _normalize(declaration)
        and existing.get("review_state") is not None
    )
    if not _normalize(declaration):
        entry["review_at"] = None
        entry["review_state"] = None
        entry["review_result"] = None
    elif keeps_state:
        entry["review_at"] = existing.get("review_at")
        entry["review_state"] = existing.get("review_state")
        entry["review_result"] = existing.get("review_result")
    else:
        # 宣言＝「明日やること」なので、既定の検証日は翌日。
        entry["review_at"] = _shift(date_str, 1)
        entry["review_state"] = REVIEW_PENDING
        entry["review_result"] = None

    # --- 過去の宣言への応答（この日に記録したもの）---
    entry["reviews"] = list(reviews or (existing or {}).get("reviews") or [])

    # --- 自己観測用メタ（入力ゼロで貯まる客観データ）---
    entry["meta"] = {**((existing or {}).get("meta") or {}), **(meta or {})}

    # --- 追記ブロック（任意・0〜N件）---
    # entries を渡さなければ既存の内容をそのまま保持する（再編集で消さない）。
    if entries is None:
        entry["entries"] = list((existing or {}).get("entries") or [])
    else:
        entry["entries"] = normalize_blocks(entries, existing=(existing or {}).get("entries"))

    return entry


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


# ============================================================
# 宣言の検証（再浮上）
# ============================================================


def declaration_repeat_count(declaration: str, upto: Optional[str] = None) -> int:
    """同じ文面の宣言が過去に何回書かれたかを数える。

    習慣かどうかを *書くときに決めさせない* ための後追い計測。
    「この宣言は5回目です」と後から見せるためだけに使う。
    """
    target = _normalize(declaration)
    if not target:
        return 0
    count = 0
    for e in all_entries():
        if upto is not None and e.get("date", "") > upto:
            continue
        if _normalize(e.get("declaration", "")) == target:
            count += 1
    return count


def due_declarations(
    today: Optional[str] = None,
    limit: Optional[int] = None,
    auto_shelve: bool = True,
) -> list[dict]:
    """検証待ちの宣言を、古い順に返す。

    返す各要素:
        date        宣言を書いた日
        declaration 宣言の文面
        review_at   検証予定日
        days        宣言を書いた日からの経過日数（中立表示用）
        repeat      同じ宣言が書かれた回数（1 なら初回）

    auto_shelve=True なら、検証日を AUTO_SHELVE_DAYS 日超えて放置された宣言を
    「保留」へ移して一覧から外す。放置してもリストが伸びないための安全弁。
    """
    today = today or today_str()
    pending: list[dict] = []

    for e in all_entries():
        if e.get("review_state") != REVIEW_PENDING:
            continue
        declaration = _normalize(e.get("declaration", ""))
        review_at = e.get("review_at")
        entry_date = e.get("date")
        if not declaration or not review_at or not entry_date:
            continue
        if review_at > today:
            continue  # まだ検証日が来ていない

        if auto_shelve and _days_between(review_at, today) > AUTO_SHELVE_DAYS:
            e["review_state"] = REVIEW_SHELVED
            e["review_result"] = {
                "result": REVIEW_SHELVED,
                "note": "",
                "reviewed_on": today,
                "auto": True,
            }
            try:
                save_entry(e)
            except OSError:
                log.exception("宣言の自動保留の保存に失敗しました: %s", entry_date)
            log.info("%s の宣言を自動保留にしました（%d日以上無反応）。", entry_date, AUTO_SHELVE_DAYS)
            continue

        pending.append(
            {
                "date": entry_date,
                "declaration": e.get("declaration", ""),
                "review_at": review_at,
                "days": _days_between(entry_date, today),
                "repeat": declaration_repeat_count(declaration, upto=today),
            }
        )

    pending.sort(key=lambda item: item["date"])
    return pending if limit is None else pending[:limit]


def respond_to_declaration(
    date_str: str,
    result: str,
    note: str = "",
    today: Optional[str] = None,
) -> Optional[dict]:
    """過去の宣言に応答して状態を確定する（できた／降りる／あとで）。

    返り値はその日の日記へ記録するための要約（Confluence 同期にも乗る）。
    対象エントリ自体は sync_status を変えない（古いページの再送を起こさないため。
    応答内容は応答した日のエントリ側に載る）。
    """
    if result not in (REVIEW_DONE, REVIEW_DROPPED, REVIEW_PENDING):
        raise ValueError(f"unknown review result: {result}")

    today = today or today_str()
    entry = get_entry(date_str)
    if entry is None:
        log.warning("応答対象の日記が見つかりません: %s", date_str)
        return None

    declaration = entry.get("declaration", "")
    if result == REVIEW_PENDING:
        # 「あとで」＝検証日を延ばすだけ。状態は pending のまま。
        entry["review_at"] = _shift(today, DEFER_DAYS)
    else:
        entry["review_state"] = result
        entry["review_result"] = {
            "result": result,
            "note": note,
            "reviewed_on": today,
        }

    try:
        save_entry(entry)
    except OSError:
        log.exception("宣言への応答の保存に失敗しました: %s", date_str)
        return None

    log.info("%s の宣言に応答しました: %s", date_str, result)
    return {
        "ref": date_str,
        "declaration": declaration,
        "result": result,
        "note": note,
        "reviewed_on": today,
    }


def supersede_declaration(
    declaration: str,
    exclude_date: str,
    today: Optional[str] = None,
) -> list[str]:
    """同じ文面を書き直した＝継続の意思表示。古い同一宣言を superseded にする。

    「継続」のための専用 UI を作らず、*今日また宣言を書く* ことを継続操作にする。
    戻り値は superseded にした日付のリスト。
    """
    target = _normalize(declaration)
    if not target:
        return []
    today = today or today_str()
    updated: list[str] = []

    for e in all_entries():
        if e.get("date") == exclude_date:
            continue
        if e.get("review_state") != REVIEW_PENDING:
            continue
        if _normalize(e.get("declaration", "")) != target:
            continue
        e["review_state"] = REVIEW_SUPERSEDED
        e["review_result"] = {
            "result": REVIEW_SUPERSEDED,
            "note": "",
            "reviewed_on": today,
            "superseded_by": exclude_date,
        }
        try:
            save_entry(e)
        except OSError:
            log.exception("宣言の再宣言処理の保存に失敗しました: %s", e.get("date"))
            continue
        updated.append(e["date"])

    if updated:
        log.info("再宣言により %d 件を superseded にしました。", len(updated))
    return updated


# ============================================================
# 追記ブロック（Phase 2）
# ============================================================
#
# 4 行に収まらない日の受け皿。必須ではなく、書ける日だけ増やす。
# 意図的に「検証を付けない」「再浮上させない」：宣言リストと並ぶ第二の
# 未処理リストを作ると、ゼロにできないリストが残って続かなくなるため。


def new_block(
    kind: str,
    body: str,
    block_id: Optional[str] = None,
    created_at: Optional[str] = None,
) -> dict[str, Any]:
    if kind not in BLOCK_KINDS:
        raise ValueError(f"unknown block kind: {kind}")
    return {
        "id": block_id or uuid.uuid4().hex[:8],
        "type": kind,
        "body": body,
        "created_at": created_at or datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def normalize_blocks(
    blocks: list[dict],
    existing: Optional[list[dict]] = None,
) -> list[dict]:
    """保存用に整える：空のブロックは捨て、id と created_at を補う。

    空欄を捨てるので「開いたけど書かなかった」が記録に残らない。
    既存ブロックの created_at は id で引き当てて保持する。
    """
    previous = {b.get("id"): b for b in (existing or []) if b.get("id")}
    result: list[dict] = []
    for block in blocks or []:
        body = (block.get("body") or "").strip()
        if not body:
            continue  # 空のブロックは保存しない
        kind = block.get("type")
        if kind not in BLOCK_KINDS:
            continue
        block_id = block.get("id")
        before = previous.get(block_id) if block_id else None
        result.append(
            new_block(
                kind,
                body,
                block_id=block_id,
                created_at=(before or {}).get("created_at") or block.get("created_at"),
            )
        )
    return result


def blocks_of(entry: Optional[dict], kind: Optional[str] = None) -> list[dict]:
    """日記から追記ブロックを取り出す（kind 指定で絞り込み）。"""
    blocks = (entry or {}).get("entries") or []
    if kind is None:
        return list(blocks)
    return [b for b in blocks if b.get("type") == kind]


def all_blocks(kind: Optional[str] = None) -> list[dict]:
    """全期間の追記ブロックを日付付きで返す（月次のまとめ出力用）。

    再浮上はさせない。見たいときに見るためだけの読み出し口。
    """
    result: list[dict] = []
    for e in all_entries():
        for block in blocks_of(e, kind):
            result.append({**block, "date": e.get("date", "")})
    return result
