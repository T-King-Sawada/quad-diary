"""追記ブロック（思考 / タネ）のテスト。

意図的に「検証を付けない」「再浮上させない」ことも仕様として固定する。
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from app import storage
from app.diary_dialog import DiaryDialog


# ---------------- storage ----------------


def test_new_block_has_id_and_timestamp():
    b = storage.new_block(storage.BLOCK_THOUGHT, "考えごと")
    assert b["type"] == "thought" and b["body"] == "考えごと"
    assert b["id"] and b["created_at"]


def test_unknown_kind_is_rejected():
    with pytest.raises(ValueError):
        storage.new_block("decision", "まだ Phase 3 ではない")


def test_empty_blocks_are_dropped():
    """開いたけど書かなかった追記は記録に残さない。"""
    blocks = storage.normalize_blocks(
        [
            {"type": "thought", "body": "書いた"},
            {"type": "thought", "body": "   "},
            {"type": "seed", "body": ""},
        ]
    )
    assert [b["body"] for b in blocks] == ["書いた"]


def test_unknown_kind_is_skipped_on_normalize():
    assert storage.normalize_blocks([{"type": "nope", "body": "x"}]) == []


def test_created_at_is_preserved_on_reedit():
    original = storage.new_block(storage.BLOCK_SEED, "タネ")
    kept = storage.normalize_blocks(
        [{"id": original["id"], "type": "seed", "body": "タネ（加筆）"}],
        existing=[original],
    )
    assert kept[0]["created_at"] == original["created_at"]
    assert kept[0]["body"] == "タネ（加筆）"


def test_entries_default_to_existing_when_not_passed(isolated_paths):
    """entries を渡さない保存では既存の追記を消さない。"""
    first = storage.new_entry(
        "2026-09-12", "f", "", "", "", entries=[{"type": "seed", "body": "タネ"}]
    )
    storage.save_entry(first)
    got = storage.get_entry("2026-09-12")

    again = storage.new_entry("2026-09-12", "f2", "", "", "", existing=got)

    assert [b["body"] for b in again["entries"]] == ["タネ"]


def test_blocks_can_be_removed_by_passing_fewer(isolated_paths):
    first = storage.new_entry(
        "2026-09-12", "f", "", "", "",
        entries=[{"type": "seed", "body": "残す"}, {"type": "thought", "body": "消す"}],
    )
    storage.save_entry(first)
    got = storage.get_entry("2026-09-12")
    keep = [b for b in got["entries"] if b["body"] == "残す"]

    again = storage.new_entry("2026-09-12", "f", "", "", "", existing=got, entries=keep)

    assert [b["body"] for b in again["entries"]] == ["残す"]


def test_blocks_of_filters_by_kind(isolated_paths):
    entry = storage.new_entry(
        "2026-09-12", "f", "", "", "",
        entries=[{"type": "seed", "body": "タネ"}, {"type": "thought", "body": "考え"}],
    )
    assert len(storage.blocks_of(entry)) == 2
    assert storage.blocks_of(entry, storage.BLOCK_SEED)[0]["body"] == "タネ"
    assert storage.blocks_of(None) == []


def test_all_blocks_collects_across_days(isolated_paths):
    storage.save_entry(
        storage.new_entry("2026-09-11", "f", "", "", "", entries=[{"type": "seed", "body": "A"}])
    )
    storage.save_entry(
        storage.new_entry("2026-09-12", "f", "", "", "", entries=[{"type": "thought", "body": "B"}])
    )

    everything = storage.all_blocks()
    assert [(b["date"], b["body"]) for b in everything] == [("2026-09-11", "A"), ("2026-09-12", "B")]
    assert [b["body"] for b in storage.all_blocks(storage.BLOCK_SEED)] == ["A"]


def test_blocks_never_get_a_review_pointer(isolated_paths):
    """★仕様の固定：追記ブロックには検証を付けない（第二の未処理リストを作らない）。"""
    entry = storage.new_entry(
        "2026-09-12", "f", "", "", "", entries=[{"type": "seed", "body": "タネ"}]
    )
    storage.save_entry(entry)

    assert all("review_at" not in b for b in entry["entries"])
    assert storage.due_declarations(today="2026-09-13") == []   # 再浮上もしない


# ---------------- UI ----------------


def test_no_block_fields_by_default():
    """既定では入力欄を出さない（空欄の圧を作らない）。"""
    d = DiaryDialog()
    d.prepare(None, force=False, snooze_enabled=True, snooze_minutes=10)
    assert d.blocks() == []


def test_adding_a_block_creates_one_field():
    d = DiaryDialog()
    d.prepare(None, force=False, snooze_enabled=True, snooze_minutes=10)
    row = d._add_block(storage.BLOCK_THOUGHT)
    row._edit.setPlainText("4行に収まらない考え")

    assert d.blocks() == [{"type": "thought", "body": "4行に収まらない考え"}]


def test_removing_a_block():
    d = DiaryDialog()
    d.prepare(None, force=False, snooze_enabled=True, snooze_minutes=10)
    row = d._add_block(storage.BLOCK_SEED)
    row.removed.emit(row)

    assert d.blocks() == []


def test_existing_blocks_are_loaded_for_reedit():
    d = DiaryDialog()
    d.prepare(
        {"fact": "f", "entries": [{"id": "abc12345", "type": "seed", "body": "タネ"}]},
        force=False, snooze_enabled=True, snooze_minutes=10,
    )
    assert d.blocks() == [{"type": "seed", "body": "タネ", "id": "abc12345"}]


def test_blocks_are_reset_between_openings():
    d = DiaryDialog()
    d.prepare(
        {"entries": [{"id": "abc12345", "type": "seed", "body": "タネ"}]},
        force=False, snooze_enabled=True, snooze_minutes=10,
    )
    d.prepare(None, force=False, snooze_enabled=True, snooze_minutes=10)

    assert d.blocks() == []


def test_a_block_alone_is_enough_to_save(monkeypatch):
    """★回帰テスト：4行が空でも、追記だけ書いた日は保存できる。"""
    d = DiaryDialog()
    d.prepare(None, force=False, snooze_enabled=True, snooze_minutes=10)
    d._add_block(storage.BLOCK_SEED)._edit.setPlainText("後で書きたいこと")

    warnings = []
    monkeypatch.setattr(
        "app.diary_dialog.QMessageBox.warning", lambda *args: warnings.append(args[2])
    )
    saved = []
    d.saved.connect(lambda: saved.append(True))

    d._on_save()

    assert warnings == [] and saved == [True]


def test_confluence_renders_blocks():
    from app.confluence_client import render_storage_html

    html_out = render_storage_html(
        {
            "date": "2026-09-12",
            "fact": "f", "discovery": "", "lesson": "", "declaration": "",
            "entries": [
                {"type": "thought", "body": "考え"},
                {"type": "seed", "body": "タネ"},
            ],
        }
    )
    assert "<h2>思考</h2>" in html_out and "<p>考え</p>" in html_out
    assert "<h2>タネ</h2>" in html_out and "<p>タネ</p>" in html_out
