"""4 行日記の入力ウィンドウ。

アプリ起動中はインスタンスを 1 つだけ使い回す（非モーダル）。
モーダル exec() を使わないことで、再表示要求が重なってもウィンドウが
積み重なったり、閉じた後に裏の窓が出てきたりしない。

ボタン操作は Qt シグナルで通知する：
    saved      … 保存ボタン（入力検証 OK）
    snoozed(int) … 「N分後に再通知」
    cancelled  … キャンセル／×ボタン
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

# 4 項目の定義（キー, ラベル, プレースホルダ）
FIELDS = [
    ("fact", "事実", "今日実際に起きたこと"),
    ("discovery", "発見", "今日気づいたこと・注目したこと"),
    ("lesson", "教訓", "今日得た教訓"),
    ("declaration", "宣言", "明日からの行動宣言"),
]


class DiaryDialog(QDialog):
    saved = Signal()
    snoozed = Signal(int)
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._force = False
        self._snooze_minutes = 10
        self._snooze_enabled = True
        self._edits: dict[str, QTextEdit] = {}

        self.setWindowTitle("今日の4行日記")
        self.setMinimumWidth(420)
        # リマインダー窓なので常に最前面に表示する
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)

        layout = QVBoxLayout(self)

        for key, label, placeholder in FIELDS:
            layout.addWidget(QLabel(label))
            edit = QTextEdit()
            edit.setPlaceholderText(placeholder)
            edit.setFixedHeight(60)
            edit.setAcceptRichText(False)
            self._edits[key] = edit
            layout.addWidget(edit)

        buttons = QHBoxLayout()
        self._save_btn = QPushButton("保存")
        self._save_btn.setDefault(True)
        self._save_btn.clicked.connect(self._on_save)

        self._snooze_btn = QPushButton("10分後に再通知")
        self._snooze_btn.clicked.connect(self._on_snooze)

        self._cancel_btn = QPushButton("キャンセル")
        self._cancel_btn.clicked.connect(self.close)

        buttons.addWidget(self._save_btn)
        buttons.addWidget(self._snooze_btn)
        buttons.addWidget(self._cancel_btn)
        layout.addLayout(buttons)

    # ---------------- 表示準備 ----------------
    def prepare(
        self,
        existing: Optional[dict],
        force: bool,
        snooze_enabled: bool,
        snooze_minutes: int,
    ) -> None:
        self._force = force
        self._snooze_minutes = snooze_minutes
        self._snooze_enabled = snooze_enabled
        for key, _, _ in FIELDS:
            self._edits[key].setPlainText((existing or {}).get(key, "") or "")
        self._snooze_btn.setText(f"{snooze_minutes}分後に再通知")
        self._snooze_btn.setEnabled(snooze_enabled)
        self._snooze_btn.setToolTip(
            "" if snooze_enabled else "本日の再通知回数の上限に達しました。"
        )

    def bring_to_front(self) -> None:
        """最小化を解除し、確実に最前面・アクティブにする。"""
        self.setWindowState(
            (self.windowState() & ~Qt.WindowMinimized) | Qt.WindowActive
        )
        self.show()
        self.raise_()
        self.activateWindow()

    def values(self) -> tuple[str, str, str, str]:
        return tuple(self._edits[key].toPlainText().strip() for key, _, _ in FIELDS)  # type: ignore[return-value]

    # ---------------- ボタン処理 ----------------
    def _on_save(self) -> None:
        vals = self.values()
        if all(not v for v in vals):
            QMessageBox.warning(self, "確認", "少なくとも1項目は入力してください。")
            return
        if self._force and any(not v for v in vals):
            QMessageBox.warning(self, "確認", "Forceモードでは全項目の入力が必要です。")
            return
        self.saved.emit()
        self.hide()

    def _on_snooze(self) -> None:
        self.snoozed.emit(self._snooze_minutes)
        self.hide()

    def closeEvent(self, event) -> None:
        # × ボタン／キャンセルボタン経由。閉じずに隠して再利用する。
        event.ignore()

        if self._force:
            # Force モードでは未保存のまま黙って閉じさせない（設計 10.2）
            if self._snooze_enabled:
                ret = QMessageBox.question(
                    self,
                    "確認",
                    "まだ保存していません。\n後で再通知しますか？",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if ret == QMessageBox.Yes:
                    self.snoozed.emit(self._snooze_minutes)
                    self.hide()
                # No のときは入力に戻る（隠さない）
            else:
                QMessageBox.warning(
                    self,
                    "確認",
                    "本日の再通知回数の上限です。保存してください。",
                )
            return

        # normal モード：キャンセル扱いで隠す
        self.cancelled.emit()
        self.hide()
