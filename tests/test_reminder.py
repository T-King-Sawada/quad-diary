"""リマインダーの状態遷移テスト。

今回見つかった「時刻を変更しても発火状態がリセットされず再通知されない」バグの
回帰テストを含む。時刻は固定クロックで決定的に制御する。
"""

from __future__ import annotations

import datetime as _dt

import pytest

from app import reminder as reminder_mod
from app.reminder import Reminder


class _Clock:
    def __init__(self, now: _dt.datetime):
        self.now_val = now

    def set(self, now: _dt.datetime):
        self.now_val = now


@pytest.fixture
def clock(monkeypatch):
    c = _Clock(_dt.datetime(2026, 6, 18, 12, 0, 0))

    class FakeDateTime(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return c.now_val

    class FakeDate(_dt.date):
        @classmethod
        def today(cls):
            return c.now_val.date()

    monkeypatch.setattr(reminder_mod, "datetime", FakeDateTime)
    monkeypatch.setattr(reminder_mod, "date", FakeDate)
    return c


def make_reminder(time_str="09:00", submitted=False):
    state = {"time": time_str, "submitted": submitted}
    r = Reminder(lambda: state["time"], lambda: state["submitted"])
    fires: list[str] = []
    r.fire.connect(lambda reason: fires.append(reason))
    return r, state, fires


def test_fires_when_time_passed(clock):
    r, state, fires = make_reminder("09:00")  # now=12:00 > 09:00
    r._tick()
    assert fires == ["reminder"]


def test_not_fire_before_time(clock):
    r, state, fires = make_reminder("15:00")  # now=12:00 < 15:00
    r._tick()
    assert fires == []


def test_fires_once_per_day(clock):
    r, state, fires = make_reminder("09:00")
    r._tick()
    r._tick()
    r._tick()
    assert fires == ["reminder"]  # 何度 tick しても1日1回


def test_dismiss_then_no_refire(clock):
    """normal モードでキャンセル(dismiss)した後は同じ日に再発火しない。"""
    r, state, fires = make_reminder("09:00")
    r._tick()           # 発火
    r.dismiss()         # キャンセル
    fires.clear()
    r._tick()
    assert fires == []


def test_rearm_refires_after_time_change(clock):
    """★回帰テスト：時刻変更後に rearm すると、その日でも再発火する。"""
    r, state, fires = make_reminder("09:00")
    r._tick()
    r.dismiss()
    fires.clear()
    # 時刻を変更（過去のまま）→ rearm で再評価 → 発火するはず
    state["time"] = "10:00"  # now=12:00 > 10:00
    r.rearm()
    assert fires == ["reminder"]


def test_rearm_no_fire_if_submitted(clock):
    """既に本日分を保存済みなら rearm しても発火しない（催促しない）。"""
    r, state, fires = make_reminder("09:00", submitted=True)
    r.rearm()
    assert fires == []


def test_new_day_resets(clock):
    r, state, fires = make_reminder("09:00")
    r._tick()
    r.dismiss()
    fires.clear()
    # 翌日へ
    clock.set(_dt.datetime(2026, 6, 19, 9, 30, 0))
    r._tick()
    assert fires == ["reminder"]


def test_snooze_schedules_and_refires(clock):
    r, state, fires = make_reminder("09:00")
    r._tick()
    fires.clear()
    r.snooze(10)                 # now=12:00 → 12:10 に再通知予約
    r._tick()
    assert fires == []           # まだ 12:00
    clock.set(_dt.datetime(2026, 6, 18, 12, 11, 0))
    r._tick()
    assert fires == ["snooze"]


def test_can_snooze_limit(clock):
    r, state, fires = make_reminder("09:00")
    assert r.can_snooze(3) is True
    r.snooze(5)
    r.snooze(5)
    r.snooze(5)
    assert r.can_snooze(3) is False
