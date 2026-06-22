"""カスタムトースト通知のテスト（オフスクリーン）。"""

from __future__ import annotations

from app.toast import Toast


def test_show_message_sets_text_and_starts_timer():
    t = Toast()
    t.show_message("保存しました。", msecs=2000)
    assert t._label.text() == "保存しました。"
    assert t._timer.isActive()
    assert t._timer.isSingleShot()


def test_timer_interval_matches_msecs():
    t = Toast()
    t.show_message("テスト", msecs=1500)
    assert t._timer.interval() == 1500
