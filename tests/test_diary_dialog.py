"""日記ウィンドウのモード切替テスト（GUIはオフスクリーン）。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor

from app.diary_dialog import DiaryDialog


def test_tab_changes_focus_on_all_fields():
    """Tab で次の入力欄へ移動する設定になっていること。"""
    d = DiaryDialog()
    assert all(e.tabChangesFocus() for e in d._edits.values())


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


def test_prepare_shows_yesterday_declaration():
    d = DiaryDialog()
    d.prepare(None, force=False, snooze_enabled=True, snooze_minutes=10, yesterday_declaration="早起きする")
    assert d._yesterday_label.isHidden() is False
    assert "早起きする" in d._yesterday_label.text()


def test_prepare_hides_yesterday_label_when_no_declaration():
    d = DiaryDialog()
    d.prepare(None, force=False, snooze_enabled=True, snooze_minutes=10, yesterday_declaration="")
    assert d._yesterday_label.isHidden() is True


def test_down_arrow_jumps_to_end_on_last_line():
    """★回帰テスト：最終行（かつ行末より手前）で下矢印を押すと文末へジャンプする。"""
    d = DiaryDialog()
    edit = d._edits["fact"]
    edit.setPlainText("1行目\n2行目")
    cursor = edit.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)  # 最終行の先頭へ
    edit.setTextCursor(cursor)

    edit.keyPressEvent(_make_key_event(Qt.Key_Down))

    assert edit.textCursor().position() == len(edit.toPlainText())


def test_down_arrow_moves_to_next_line_when_not_last():
    """下矢印の通常動作（次の行がある場合）は維持される。"""
    d = DiaryDialog()
    edit = d._edits["fact"]
    edit.setPlainText("1行目\n2行目")
    cursor = edit.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.Start)
    edit.setTextCursor(cursor)  # 1行目の先頭

    edit.keyPressEvent(_make_key_event(Qt.Key_Down))

    assert edit.textCursor().position() != len(edit.toPlainText())
    assert edit.textCursor().blockNumber() == 1


def _make_key_event(key):
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent

    return QKeyEvent(QEvent.Type.KeyPress, key, Qt.NoModifier)


def test_force_close_closes_even_in_force_mode():
    """★回帰テスト：Forceモードでも force_close なら確認なしで閉じる（終了時用）。"""
    d = DiaryDialog()
    d.prepare(None, force=True, snooze_enabled=True, snooze_minutes=10)
    d.show()
    assert d.isVisible() is True
    d.force_close()
    assert d.isVisible() is False    # 確認ダイアログ無しで閉じる
