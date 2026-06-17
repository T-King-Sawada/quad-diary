"""システムトレイ常駐アイコンとメニュー。"""

from __future__ import annotations

from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .icon import app_icon


class Tray(QSystemTrayIcon):
    def __init__(self, on_write, on_settings, on_sync, on_quit, parent=None):
        super().__init__(app_icon(), parent)
        self.setToolTip("4行日記")

        menu = QMenu()
        menu.addAction("今日を書く", on_write)
        menu.addAction("設定", on_settings)
        self._sync_action = menu.addAction("同期する", on_sync)
        menu.addSeparator()
        menu.addAction("終了", on_quit)
        self.setContextMenu(menu)

        # トレイアイコンのダブルクリックでも「今日を書く」
        self.activated.connect(
            lambda reason: on_write() if reason == QSystemTrayIcon.DoubleClick else None
        )

    def set_sync_enabled(self, enabled: bool) -> None:
        self._sync_action.setEnabled(enabled)

    def notify(self, title: str, message: str) -> None:
        self.showMessage(title, message, app_icon())
