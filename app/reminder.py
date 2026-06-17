"""定時リマインダー。QTimer で時刻を監視し、条件を満たしたら fire シグナルを出す。

判定ロジック（設計 8.3）:
    現在時刻 >= リマインダー時刻
    かつ 本日未提出
    かつ 本日まだ発火していない（または snooze 待ちが満了）
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Callable

from PySide6.QtCore import QObject, QTimer, Signal

from .logger import get_logger

log = get_logger(__name__)

CHECK_INTERVAL_MS = 20_000  # 20 秒ごと


class Reminder(QObject):
    # reason: "reminder"（定刻）/ "snooze"（再通知）
    fire = Signal(str)

    def __init__(
        self,
        get_reminder_time: Callable[[], str],
        is_submitted_today: Callable[[], bool],
    ):
        super().__init__()
        self._get_time = get_reminder_time
        self._is_submitted = is_submitted_today

        self._triggered_date: date | None = None   # 本日の定刻発火済み
        self._handled_date: date | None = None      # 本日は対応済み（保存 or 完了）
        self._snooze_until: datetime | None = None
        self._snooze_count = 0

        self._timer = QTimer(self)
        self._timer.setInterval(CHECK_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        self._tick()
        self._timer.start()

    # --- 状態遷移（コントローラから呼ばれる） ---
    def mark_done(self) -> None:
        """保存完了。本日はもう発火しない。"""
        self._handled_date = date.today()
        self._snooze_until = None

    def dismiss(self) -> None:
        """normal モードで閉じられた。本日の定刻発火は終了扱い。"""
        self._triggered_date = date.today()
        self._snooze_until = None

    def snooze(self, minutes: int) -> None:
        self._snooze_count += 1
        self._snooze_until = datetime.now() + timedelta(minutes=minutes)
        self._triggered_date = date.today()
        log.info("再通知を %d 分後に設定（本日 %d 回目）。", minutes, self._snooze_count)

    def snooze_count(self) -> int:
        return self._snooze_count

    def can_snooze(self, max_count: int) -> bool:
        return self._snooze_count < max_count

    # --- 内部 ---
    def _reset_if_new_day(self) -> None:
        today = date.today()
        last = self._triggered_date or self._handled_date
        if last is not None and last != today:
            self._triggered_date = None
            self._handled_date = None
            self._snooze_until = None
            self._snooze_count = 0
            log.info("日付が変わったためリマインダー状態をリセットしました。")

    def _tick(self) -> None:
        self._reset_if_new_day()
        today = date.today()

        if self._handled_date == today:
            return

        if self._is_submitted():
            # 既に本日分が保存済み（前回起動時など）
            self._handled_date = today
            return

        now = datetime.now()

        # snooze 待ち
        if self._snooze_until is not None:
            if now >= self._snooze_until:
                self._snooze_until = None
                log.info("再通知の時刻になりました。")
                self.fire.emit("snooze")
            return

        if self._triggered_date == today:
            return

        hh, mm = self._parse(self._get_time())
        target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if now >= target:
            self._triggered_date = today
            log.info("定刻リマインダーを発火します。")
            self.fire.emit("reminder")

    @staticmethod
    def _parse(value: str) -> tuple[int, int]:
        try:
            hh, mm = value.split(":")
            return int(hh), int(mm)
        except (ValueError, AttributeError):
            return 18, 30
