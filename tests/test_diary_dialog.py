"""日記ウィンドウのモード切替テスト（GUIはオフスクリーン）。"""

from __future__ import annotations

from app.diary_dialog import DiaryDialog


def test_prepare_sets_force_and_fields():
    d = DiaryDialog()
    d.prepare({"fact": "A"}, force=True, snooze_enabled=True, snooze_minutes=10)
    assert d._force is True
    assert d.values()[0] == "A"


def test_update_mode_changes_force_without_clearing_input():
    """★回帰テスト：表示中にForce→normalへ変えても入力は消えず、モードだけ変わる。"""
    d = DiaryDialog()
    d.prepare({"fact": "keep", "discovery": "me"}, force=True, snooze_enabled=True, snooze_minutes=10)
    # 表示中にモード変更（normalへ）
    d.update_mode(force=False, snooze_enabled=True, snooze_minutes=30)
    assert d._force is False                      # normal に切り替わる
    assert d.values()[:2] == ("keep", "me")       # 入力は保持
    assert d._snooze_btn.text() == "30分後に再通知"


def test_update_mode_snooze_button_disabled():
    d = DiaryDialog()
    d.prepare(None, force=False, snooze_enabled=True, snooze_minutes=10)
    d.update_mode(force=True, snooze_enabled=False, snooze_minutes=10)
    assert d._snooze_btn.isEnabled() is False
