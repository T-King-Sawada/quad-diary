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
