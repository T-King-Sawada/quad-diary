"""本機保存(JSONL)のテスト。"""

from __future__ import annotations

from app import storage


def test_new_entry_fields():
    e = storage.new_entry("2026-06-18", "f", "d", "l", "de")
    assert e["date"] == "2026-06-18" and e["id"] == "2026-06-18"
    assert (e["fact"], e["discovery"], e["lesson"], e["declaration"]) == ("f", "d", "l", "de")
    assert e["sync_status"] == "none"
    assert e["confluence_page_id"] is None
    assert e["created_at"] and e["updated_at"]


def test_save_and_get(isolated_paths):
    e = storage.new_entry("2026-06-18", "f", "d", "l", "de")
    storage.save_entry(e)
    assert storage.is_submitted("2026-06-18")
    got = storage.get_entry("2026-06-18")
    assert got["fact"] == "f"


def test_upsert_same_date_replaces(isolated_paths):
    e1 = storage.new_entry("2026-06-18", "f", "d", "l", "de")
    storage.save_entry(e1)
    got1 = storage.get_entry("2026-06-18")
    e2 = storage.new_entry("2026-06-18", "F2", "d", "l", "de", existing=got1)
    storage.save_entry(e2)
    rows = storage.load_year(2026)
    assert len(rows) == 1                       # 重複追記されない
    assert storage.get_entry("2026-06-18")["fact"] == "F2"
    assert storage.get_entry("2026-06-18")["created_at"] == got1["created_at"]  # created保持


def test_unsynced_entries(isolated_paths):
    a = storage.new_entry("2026-06-18", "a", "", "", "")
    a["sync_status"] = "synced"
    b = storage.new_entry("2026-06-19", "b", "", "", "")
    b["sync_status"] = "failed"
    c = storage.new_entry("2026-06-20", "c", "", "", "")
    c["sync_status"] = "pending"
    for e in (a, b, c):
        storage.save_entry(e)
    dates = {e["date"] for e in storage.unsynced_entries()}
    assert dates == {"2026-06-19", "2026-06-20"}     # synced は対象外


def test_not_submitted_when_absent(isolated_paths):
    assert storage.is_submitted("2026-01-01") is False
    assert storage.get_entry("2026-01-01") is None


# ============================================================
# 宣言の検証（再浮上）
# ============================================================


def test_declaration_gets_review_pointer_for_next_day():
    e = storage.new_entry("2026-09-11", "f", "", "", "早起きする")
    assert e["review_at"] == "2026-09-12"          # 宣言＝明日やること
    assert e["review_state"] == storage.REVIEW_PENDING


def test_empty_declaration_has_no_review_pointer():
    e = storage.new_entry("2026-09-11", "f", "", "", "")
    assert e["review_at"] is None
    assert e["review_state"] is None


def test_reediting_same_declaration_keeps_review_state(isolated_paths):
    first = storage.new_entry("2026-09-11", "f", "", "", "早起きする")
    storage.save_entry(first)
    got = storage.get_entry("2026-09-11")
    got["review_state"] = storage.REVIEW_DONE

    again = storage.new_entry("2026-09-11", "F2", "", "", "早起きする", existing=got)
    assert again["review_state"] == storage.REVIEW_DONE     # 応答済みを巻き戻さない

    changed = storage.new_entry("2026-09-11", "F2", "", "", "別の宣言", existing=got)
    assert changed["review_state"] == storage.REVIEW_PENDING  # 文面が変われば作り直す


def test_due_declarations_returns_only_arrived_ones(isolated_paths):
    storage.save_entry(storage.new_entry("2026-09-11", "f", "", "", "早起きする"))
    storage.save_entry(storage.new_entry("2026-09-12", "f", "", "", "散歩する"))

    due = storage.due_declarations(today="2026-09-12")

    assert [d["date"] for d in due] == ["2026-09-11"]   # 9/12 の検証日は 9/13
    assert due[0]["days"] == 1


def test_due_declarations_are_sorted_oldest_first(isolated_paths):
    for day, text in (("09-05", "A"), ("09-09", "B"), ("09-11", "C")):
        storage.save_entry(storage.new_entry(f"2026-{day}", "f", "", "", text))

    due = storage.due_declarations(today="2026-09-12")

    assert [d["declaration"] for d in due] == ["A", "B", "C"]


def test_due_declarations_limit(isolated_paths):
    for day in ("09-05", "09-09", "09-11"):
        storage.save_entry(storage.new_entry(f"2026-{day}", "f", "", "", f"宣言{day}"))

    assert len(storage.due_declarations(today="2026-09-12", limit=2)) == 2


def test_untouched_declaration_is_auto_shelved(isolated_paths):
    """14日以上無反応なら自動で保留へ。放置してもリストが伸びない。"""
    storage.save_entry(storage.new_entry("2026-08-01", "f", "", "", "放置された宣言"))

    due = storage.due_declarations(today="2026-09-12")

    assert due == []
    assert storage.get_entry("2026-08-01")["review_state"] == storage.REVIEW_SHELVED


def test_auto_shelve_can_be_disabled(isolated_paths):
    storage.save_entry(storage.new_entry("2026-08-01", "f", "", "", "放置された宣言"))

    due = storage.due_declarations(today="2026-09-12", auto_shelve=False)

    assert len(due) == 1
    assert storage.get_entry("2026-08-01")["review_state"] == storage.REVIEW_PENDING


def test_respond_done_records_result(isolated_paths):
    storage.save_entry(storage.new_entry("2026-09-11", "f", "", "", "早起きする"))

    summary = storage.respond_to_declaration(
        "2026-09-11", storage.REVIEW_DONE, "5時に起きた", today="2026-09-12"
    )

    entry = storage.get_entry("2026-09-11")
    assert entry["review_state"] == storage.REVIEW_DONE
    assert entry["review_result"]["note"] == "5時に起きた"
    assert summary["ref"] == "2026-09-11" and summary["result"] == "done"
    assert storage.due_declarations(today="2026-09-12") == []   # 一覧から消える


def test_respond_dropped_clears_the_list(isolated_paths):
    """達成しなくてもゼロにできること（これが継続の前提）。"""
    storage.save_entry(storage.new_entry("2026-09-11", "f", "", "", "向いてなかった宣言"))

    storage.respond_to_declaration("2026-09-11", storage.REVIEW_DROPPED, today="2026-09-12")

    assert storage.get_entry("2026-09-11")["review_state"] == storage.REVIEW_DROPPED
    assert storage.due_declarations(today="2026-09-12") == []


def test_defer_pushes_review_date_and_stays_pending(isolated_paths):
    storage.save_entry(storage.new_entry("2026-09-11", "f", "", "", "早起きする"))

    storage.respond_to_declaration("2026-09-11", storage.REVIEW_PENDING, today="2026-09-12")

    entry = storage.get_entry("2026-09-11")
    assert entry["review_state"] == storage.REVIEW_PENDING
    assert entry["review_at"] == "2026-09-19"                       # +7日
    assert storage.due_declarations(today="2026-09-12") == []       # 当面は出てこない
    assert len(storage.due_declarations(today="2026-09-19")) == 1   # 期日にまた出る


def test_respond_does_not_resync_the_old_entry(isolated_paths):
    """古いページの再送を起こさない（応答内容は応答した日のページに載る）。"""
    entry = storage.new_entry("2026-09-11", "f", "", "", "早起きする")
    entry["sync_status"] = "synced"
    storage.save_entry(entry)

    storage.respond_to_declaration("2026-09-11", storage.REVIEW_DONE, today="2026-09-12")

    assert storage.get_entry("2026-09-11")["sync_status"] == "synced"


def test_respond_to_missing_entry_returns_none(isolated_paths):
    assert storage.respond_to_declaration("2026-01-01", storage.REVIEW_DONE) is None


def test_redeclaring_supersedes_the_old_one(isolated_paths):
    """同じ宣言を書き直す＝継続。専用UIを作らずに継続を表現する。"""
    storage.save_entry(storage.new_entry("2026-09-11", "f", "", "", "早起きする"))
    storage.save_entry(storage.new_entry("2026-09-12", "f", "", "", "早起きする"))

    updated = storage.supersede_declaration(
        "早起きする", exclude_date="2026-09-12", today="2026-09-12"
    )

    assert updated == ["2026-09-11"]
    assert storage.get_entry("2026-09-11")["review_state"] == storage.REVIEW_SUPERSEDED
    assert storage.get_entry("2026-09-12")["review_state"] == storage.REVIEW_PENDING
    assert len(storage.due_declarations(today="2026-09-13")) == 1   # 重複して並ばない


def test_repeat_count_reveals_habit_after_the_fact(isolated_paths):
    """習慣かどうかは書くときに決めず、回数を後から数えて発見する。"""
    for day in ("09-09", "09-10", "09-11"):
        storage.save_entry(storage.new_entry(f"2026-{day}", "f", "", "", "早起きする"))

    assert storage.declaration_repeat_count("早起きする") == 3
    assert storage.declaration_repeat_count("早起きする ") == 3    # 前後の空白は無視
    assert storage.declaration_repeat_count("書いてない宣言") == 0

    due = storage.due_declarations(today="2026-09-12", auto_shelve=False)
    assert due[0]["repeat"] == 3


def test_meta_is_merged_and_preserved(isolated_paths):
    first = storage.new_entry(
        "2026-09-11", "f", "", "", "", meta={"snooze_count": 2, "written_at": "23:41"}
    )
    storage.save_entry(first)
    got = storage.get_entry("2026-09-11")

    again = storage.new_entry(
        "2026-09-11", "f2", "", "", "", existing=got, meta={"elapsed_sec": 95}
    )

    assert again["meta"] == {"snooze_count": 2, "written_at": "23:41", "elapsed_sec": 95}


def test_old_rows_without_new_keys_are_still_readable(isolated_paths):
    """後方互換：新キーが無い既存行を読んでも壊れない（移行スクリプト不要）。"""
    import json

    path = isolated_paths / "data" / "diary_2025.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    legacy = {"id": "2025-01-01", "date": "2025-01-01", "fact": "昔の行", "declaration": "宣言"}
    path.write_text(json.dumps(legacy, ensure_ascii=False) + "\n", encoding="utf-8")

    assert storage.get_entry("2025-01-01")["fact"] == "昔の行"
    assert storage.due_declarations(today="2025-01-02") == []   # review_state が無いので対象外
