"""トレイ用アイコンをコード内で描画して生成する（外部画像ファイル不要）。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap


def app_icon() -> QIcon:
    size = 64
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)

    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)

    # 角丸の背景
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#2d6cdf"))
    p.drawRoundedRect(4, 4, size - 8, size - 8, 12, 12)

    # 4 本の線（= 4 行日記）
    pen = QPen(QColor("white"))
    pen.setWidth(5)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    for i, y in enumerate((18, 30, 42, 54)):
        right = size - 14 if i < 3 else size - 26  # 最後の行は少し短く
        p.drawLine(16, y, right, y)

    p.end()
    return QIcon(pm)
