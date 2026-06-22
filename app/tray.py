"""システムトレイ常駐アイコンとメニュー。"""

from __future__ import annotations

from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .icon import app_icon
from .toast import Toast

NOTIFY_MSECS = 2000  # 通知の表示時間（約2秒で自動的に閉じる）


class Tray(QSystemTrayIcon):
    def __init__(self, on_write, on_settings, on_sync, on_quit, on_check_update=None, parent=None):
        super().__init__(app_icon(), parent)
        self.setToolTip("4行日記")

        menu = QMenu()
        menu.addAction("今日を書く", on_write)
        menu.addAction("設定", on_settings)
        self._sync_action = menu.addAction("同期する", on_sync)
        if on_check_update is not None:
            menu.addAction("更新を確認", on_check_update)
        menu.addSeparator()
        menu.addAction("終了", on_quit)
        self.setContextMenu(menu)

        self._toast = Toast()

        # トレイアイコンのダブルクリックでも「今日を書く」
        self.activated.connect(
            lambda reason: on_write() if reason == QSystemTrayIcon.DoubleClick else None
        )

    def set_sync_enabled(self, enabled: bool) -> None:
        self._sync_action.setEnabled(enabled)

    def notify(self, title: str, message: str) -> None:
        # OS標準通知は表示時間を制御できないため、自前トーストで約2秒だけ表示
        self._toast.show_message(message, NOTIFY_MSECS)
