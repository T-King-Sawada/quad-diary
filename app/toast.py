"""画面右下に出る自前の軽量通知（トースト）。

Windows 標準通知は表示時間を OS が制御し「2秒で消す」が効かないため、
自前で描画して指定ミリ秒後に自動で閉じる。フォーカスは奪わない。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget


class Toast(QWidget):
    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._label = QLabel(self)
        self._label.setWordWrap(True)
        self._label.setMaximumWidth(340)
        self._label.setStyleSheet(
            "background: rgba(40,40,40,235); color: white;"
            "padding: 12px 16px; border-radius: 10px; font-size: 13px;"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_message(self, text: str, msecs: int = 2000) -> None:
        self._label.setText(text)
        self.adjustSize()
        self._reposition()
        self.show()
        self.raise_()
        self._timer.start(msecs)

    def _reposition(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        margin = 16
        self.move(geo.right() - self.width() - margin, geo.bottom() - self.height() - margin)
