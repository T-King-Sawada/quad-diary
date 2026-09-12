"""定刻リマインダーの応答状態（data/state.json）のテスト。"""

from __future__ import annotations

from app import state


def test_no_state_file_means_never_handled(isolated_paths):
    assert state.reminder_handled_on() is None


def test_set_and_read_back(isolated_paths):
    state.set_reminder_handled("2026-09-12")
    assert state.reminder_handled_on() == "2026-09-12"


def test_overwrites_previous_day(isolated_paths):
    state.set_reminder_handled("2026-09-11")
    state.set_reminder_handled("2026-09-12")
    assert state.reminder_handled_on() == "2026-09-12"


def test_broken_state_file_is_ignored(isolated_paths):
    """壊れていても致命的ではない（リマインダーが1回多く出るだけ）。"""
    from app import paths

    (paths.data_dir() / "state.json").write_text("{ broken", encoding="utf-8")

    assert state.reminder_handled_on() is None
    state.set_reminder_handled("2026-09-12")          # 上書きして復旧できる
    assert state.reminder_handled_on() == "2026-09-12"


def test_other_keys_are_preserved(isolated_paths):
    state.save({"something_else": 1})
    state.set_reminder_handled("2026-09-12")

    assert state.load() == {"something_else": 1, "reminder_handled_on": "2026-09-12"}
