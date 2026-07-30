"""日記ウィンドウのモード切替テスト（GUIはオフスクリーン）。"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication

from app.diary_dialog import DiaryDialog, _AutoJumpTextEdit


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


def _make_key_event(key, modifiers=Qt.NoModifier):
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent

    return QKeyEvent(QEvent.Type.KeyPress, key, modifiers)


def test_force_close_closes_even_in_force_mode():
    """★回帰テスト：Forceモードでも force_close なら確認なしで閉じる（終了時用）。"""
    d = DiaryDialog()
    d.prepare(None, force=True, snooze_enabled=True, snooze_minutes=10)
    d.show()
    assert d.isVisible() is True
    d.force_close()
    assert d.isVisible() is False    # 確認ダイアログ無しで閉じる


def test_text_edit_grows_from_one_to_five_lines_and_then_stops():
    edit = _AutoJumpTextEdit()
    edit.resize(320, edit.height())
    edit.show()

    edit.setPlainText("1行")
    QApplication.processEvents()
    one_line_height = edit.height()

    edit.setPlainText("1\n2\n3\n4\n5")
    QApplication.processEvents()
    five_line_height = edit.height()

    edit.setPlainText("1\n2\n3\n4\n5\n6")
    QApplication.processEvents()

    assert five_line_height > one_line_height
    assert edit.height() == five_line_height
    assert edit.verticalScrollBarPolicy() == Qt.ScrollBarAsNeeded


def test_text_edit_grows_for_visual_word_wrap():
    edit = _AutoJumpTextEdit()
    edit.resize(120, edit.height())
    edit.show()
    edit.setPlainText("長い文章を自動折り返しさせます。" * 8)
    QApplication.processEvents()

    assert edit.document().documentLayout().documentSize().height() > edit.fontMetrics().lineSpacing()
    assert edit.height() > edit.fontMetrics().lineSpacing()


def test_prepare_recalculates_height_for_multiline_existing_value():
    d = DiaryDialog()
    edit = d._edits["fact"]
    d.prepare(
        {"fact": "1\n2\n3\n4"},
        force=False,
        snooze_enabled=True,
        snooze_minutes=10,
    )
    d.show()
    QApplication.processEvents()

    assert edit.height() > edit.fontMetrics().lineSpacing() * 2


def test_each_field_has_independent_markdown_buttons():
    d = DiaryDialog()
    fact = d._edits["fact"]
    discovery = d._edits["discovery"]
    fact.setPlainText("できたこと")
    discovery.setPlainText("気づき")

    bullet_btn, _ = d._format_buttons["fact"]
    bullet_btn.click()

    assert fact.toPlainText() == "- できたこと"
    assert discovery.toPlainText() == "気づき"


def test_markdown_buttons_use_compact_list_icons():
    d = DiaryDialog()

    for bullet_btn, number_btn in d._format_buttons.values():
        assert bullet_btn.text() == ""
        assert number_btn.text() == ""
        assert bullet_btn.icon().isNull() is False
        assert number_btn.icon().isNull() is False
        assert bullet_btn.iconSize() == QSize(18, 18)
        assert number_btn.iconSize() == QSize(18, 18)


def test_selected_lines_can_switch_between_bullet_and_numbered_lists():
    edit = _AutoJumpTextEdit()
    edit.setPlainText("一つ目\n二つ目")
    edit.selectAll()

    edit.toggle_list("bullet")
    assert edit.toPlainText() == "- 一つ目\n- 二つ目"

    edit.toggle_list("number")
    assert edit.toPlainText() == "1. 一つ目\n2. 二つ目"

    edit.toggle_list("number")
    assert edit.toPlainText() == "一つ目\n二つ目"


def test_enter_continues_bullet_and_empty_item_exits_list():
    edit = _AutoJumpTextEdit()
    edit.setPlainText("- 一つ目")
    cursor = edit.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    edit.setTextCursor(cursor)

    edit.keyPressEvent(_make_key_event(Qt.Key_Return))
    assert edit.toPlainText() == "- 一つ目\n- "

    edit.keyPressEvent(_make_key_event(Qt.Key_Return))
    assert edit.toPlainText() == "- 一つ目\n"


def test_enter_increments_numbered_list():
    edit = _AutoJumpTextEdit()
    edit.setPlainText("3. 三つ目")
    cursor = edit.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    edit.setTextCursor(cursor)

    edit.keyPressEvent(_make_key_event(Qt.Key_Return))

    assert edit.toPlainText() == "3. 三つ目\n4. "


def test_shift_enter_adds_soft_line_break_then_enter_continues_list():
    edit = _AutoJumpTextEdit()
    edit.setPlainText("- 一つ目")
    cursor = edit.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    edit.setTextCursor(cursor)

    edit.keyPressEvent(_make_key_event(Qt.Key_Return, Qt.ShiftModifier))
    cursor = edit.textCursor()
    cursor.insertText("同じ項目の続き")
    edit.setTextCursor(cursor)
    assert edit.toPlainText() == "- 一つ目\n同じ項目の続き"

    edit.keyPressEvent(_make_key_event(Qt.Key_Return))
    assert edit.toPlainText() == "- 一つ目\n同じ項目の続き\n- "


def test_shift_enter_is_plain_line_break_outside_list():
    edit = _AutoJumpTextEdit()
    edit.setPlainText("普通の文章")
    cursor = edit.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    edit.setTextCursor(cursor)

    edit.keyPressEvent(_make_key_event(Qt.Key_Return, Qt.ShiftModifier))
    cursor = edit.textCursor()
    cursor.insertText("続き")
    edit.setTextCursor(cursor)

    assert edit.toPlainText() == "普通の文章\n続き"


def test_marker_only_lines_do_not_count_as_meaningful_content(monkeypatch):
    d = DiaryDialog()
    d.prepare(
        {"fact": "- ", "discovery": "1. "},
        force=False,
        snooze_enabled=True,
        snooze_minutes=10,
    )
    warnings = []
    monkeypatch.setattr(
        "app.diary_dialog.QMessageBox.warning",
        lambda *args: warnings.append(args[2]),
    )

    d._on_save()

    assert warnings == ["少なくとも1項目は入力してください。"]


def test_values_preserve_markdown_and_multiline_plain_text():
    d = DiaryDialog()
    value = "- 一つ目\n同じ項目の続き\n- 二つ目"
    d.prepare(
        {"fact": value},
        force=False,
        snooze_enabled=True,
        snooze_minutes=10,
    )

    assert d.values()[0] == value
