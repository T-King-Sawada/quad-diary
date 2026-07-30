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

import math
import re
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# 4 項目の定義（キー, ラベル, プレースホルダ）
FIELDS = [
    ("fact", "事実", "今日実際に起きたこと"),
    ("discovery", "発見", "今日気づいたこと・注目したこと"),
    ("lesson", "教訓", "今日得た教訓"),
    ("declaration", "宣言", "明日からの行動宣言"),
]


def _make_list_icon(numbered: bool, color: QColor) -> QIcon:
    """ツールバー風の箇条書き／番号付きリストアイコンを描画する。"""
    pixmap = QPixmap(36, 36)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    line_pen = QPen(color, 1.2)
    line_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(line_pen)

    if numbered:
        rows = ((5.0, "1"), (13.0, "2"))
        font = painter.font()
        font.setPixelSize(7)
        painter.setFont(font)
        for y, number in rows:
            painter.drawText(
                QRectF(0, y - 4, 6, 8),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                number,
            )
            painter.drawLine(QPointF(8, y), QPointF(17, y))
    else:
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        for y in (4.0, 9.0, 14.0):
            painter.drawEllipse(QPointF(3, y), 0.9, 0.9)
        painter.setPen(line_pen)
        for y in (4.0, 9.0, 14.0):
            painter.drawLine(QPointF(8, y), QPointF(17, y))

    painter.end()
    return QIcon(pixmap)


class _AutoJumpTextEdit(QTextEdit):
    """高さの自動調整と Markdown リスト入力を備えた QTextEdit。

    表示高は 1～5 行に収め、超過分は欄内スクロールにする。
    Enter はリストを継続し、Shift+Enter は同じ項目内で改行する。
    """

    height_changed = Signal()

    _BULLET_RE = re.compile(r"^-\s?(.*)$", re.DOTALL)
    _NUMBER_RE = re.compile(r"^(\d+)\.\s?(.*)$", re.DOTALL)
    _MAX_VISIBLE_LINES = 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.document().documentLayout().documentSizeChanged.connect(self._update_height)
        QTimer.singleShot(0, self._update_height)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Down and event.modifiers() == Qt.NoModifier:
            cursor = self.textCursor()
            probe = QTextCursor(cursor)
            if not probe.movePosition(QTextCursor.MoveOperation.Down):
                cursor.movePosition(QTextCursor.MoveOperation.End)
                self.setTextCursor(cursor)
                return

        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() == Qt.ShiftModifier:
                # U+2028 は QTextDocument 内では同一段落の改行として扱われ、
                # toPlainText() では通常の改行として取得できる。
                cursor = self.textCursor()
                cursor.insertText("\u2028")
                self.setTextCursor(cursor)
                return

            if event.modifiers() == Qt.NoModifier and self._continue_or_exit_list():
                return

        super().keyPressEvent(event)

    def toggle_list(self, list_type: str) -> None:
        """選択行または現在行を bullet／番号リストへ切り替える。"""
        if list_type not in {"bullet", "number"}:
            raise ValueError(f"Unknown list type: {list_type}")

        cursor = self.textCursor()
        document = self.document()
        start_block = document.findBlock(cursor.selectionStart())
        end_block = document.findBlock(cursor.selectionEnd())
        if (
            cursor.hasSelection()
            and cursor.selectionEnd() == end_block.position()
            and end_block != start_block
        ):
            end_block = end_block.previous()

        blocks = []
        block = start_block
        while block.isValid():
            blocks.append(block)
            if block == end_block:
                break
            block = block.next()

        texts = [block.text() for block in blocks]
        meaningful = [text for text in texts if text.strip()]
        target_re = self._BULLET_RE if list_type == "bullet" else self._NUMBER_RE
        remove_target = bool(meaningful) and all(target_re.match(text) for text in meaningful)

        replacements: list[str] = []
        next_number = 1
        for text in texts:
            if not text.strip() and len(blocks) > 1:
                replacements.append(text)
                continue

            body = self._without_list_prefix(text)
            if remove_target:
                replacements.append(body)
            elif list_type == "bullet":
                replacements.append(f"- {body}")
            else:
                replacements.append(f"{next_number}. {body}")
                next_number += 1

        start_number = blocks[0].blockNumber()
        end_number = blocks[-1].blockNumber()
        for block, replacement in reversed(list(zip(blocks, replacements))):
            edit_cursor = QTextCursor(block)
            edit_cursor.movePosition(
                QTextCursor.MoveOperation.EndOfBlock,
                QTextCursor.MoveMode.KeepAnchor,
            )
            edit_cursor.insertText(replacement)

        first = document.findBlockByNumber(start_number)
        last = document.findBlockByNumber(end_number)
        restored = QTextCursor(first)
        if cursor.hasSelection():
            restored.setPosition(
                last.position() + len(last.text()),
                QTextCursor.MoveMode.KeepAnchor,
            )
        else:
            restored.setPosition(first.position() + len(first.text()))
        self.setTextCursor(restored)
        self.setFocus()

    def _continue_or_exit_list(self) -> bool:
        cursor = self.textCursor()
        text = cursor.block().text()
        bullet = self._BULLET_RE.match(text)
        numbered = self._NUMBER_RE.match(text)
        if not bullet and not numbered:
            return False

        body = (bullet.group(1) if bullet else numbered.group(2)).strip()
        if not body:
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            cursor.movePosition(
                QTextCursor.MoveOperation.EndOfBlock,
                QTextCursor.MoveMode.KeepAnchor,
            )
            cursor.removeSelectedText()
            self.setTextCursor(cursor)
            return True

        prefix = "- " if bullet else f"{int(numbered.group(1)) + 1}. "
        cursor.insertBlock()
        cursor.insertText(prefix)
        self.setTextCursor(cursor)
        return True

    @classmethod
    def _without_list_prefix(cls, text: str) -> str:
        bullet = cls._BULLET_RE.match(text)
        if bullet:
            return bullet.group(1)
        numbered = cls._NUMBER_RE.match(text)
        if numbered:
            return numbered.group(2)
        return text

    def _update_height(self, *_args) -> None:
        document_height = math.ceil(self.document().documentLayout().documentSize().height())
        frame_height = self.frameWidth() * 2
        document_margin = math.ceil(self.document().documentMargin() * 2)
        line_height = self.fontMetrics().lineSpacing()
        minimum_height = line_height + document_margin + frame_height
        maximum_height = (
            line_height * self._MAX_VISIBLE_LINES + document_margin + frame_height
        )
        target_height = max(minimum_height, min(document_height + frame_height, maximum_height))
        overflow = document_height + frame_height > maximum_height
        policy = Qt.ScrollBarAsNeeded if overflow else Qt.ScrollBarAlwaysOff

        changed = self.height() != target_height
        self.setVerticalScrollBarPolicy(policy)
        if changed:
            self.setFixedHeight(target_height)
            self.height_changed.emit()


class DiaryDialog(QDialog):
    saved = Signal()
    snoozed = Signal(int)
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._force = False
        self._snooze_minutes = 10
        self._snooze_enabled = True
        self._allow_close = False  # アプリ終了時のみ True にして強制クローズを許可
        self._edits: dict[str, QTextEdit] = {}
        self._format_buttons: dict[str, tuple[QPushButton, QPushButton]] = {}

        self.setWindowTitle("今日の4行日記")
        self.setMinimumWidth(420)
        # リマインダー窓なので常に最前面に表示する
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)

        layout = QVBoxLayout(self)

        self._yesterday_label = QLabel()
        self._yesterday_label.setWordWrap(True)
        self._yesterday_label.setStyleSheet(
            "color: #5c4400; background-color: #fff3cd; padding: 6px; border-radius: 4px;"
        )
        self._yesterday_label.setVisible(False)

        self._form_widget = QWidget()
        self._form_layout = QVBoxLayout(self._form_widget)

        for key, label, placeholder in FIELDS:
            if key == "declaration":
                # 「宣言」欄の直前に、昨日の宣言（=今日やるはずだったこと）を表示する
                self._form_layout.addWidget(self._yesterday_label)

            header = QHBoxLayout()
            header.addWidget(QLabel(label))
            header.addStretch()

            edit = _AutoJumpTextEdit()
            edit.setPlaceholderText(placeholder)
            edit.setAcceptRichText(False)
            # Tab で次の欄、Shift+Tab で前の欄へ移動（タブ文字は挿入しない）
            edit.setTabChangesFocus(True)

            bullet_btn = QPushButton()
            bullet_btn.setIcon(
                _make_list_icon(False, bullet_btn.palette().buttonText().color())
            )
            bullet_btn.setIconSize(QSize(18, 18))
            bullet_btn.setToolTip("箇条書き（Markdown: - ）")
            bullet_btn.setFocusPolicy(Qt.NoFocus)
            bullet_btn.setFixedWidth(32)
            bullet_btn.clicked.connect(
                lambda _checked=False, target=edit: target.toggle_list("bullet")
            )

            number_btn = QPushButton()
            number_btn.setIcon(
                _make_list_icon(True, number_btn.palette().buttonText().color())
            )
            number_btn.setIconSize(QSize(18, 18))
            number_btn.setToolTip("番号付きリスト（Markdown: 1. ）")
            number_btn.setFocusPolicy(Qt.NoFocus)
            number_btn.setFixedWidth(32)
            number_btn.clicked.connect(
                lambda _checked=False, target=edit: target.toggle_list("number")
            )

            header.addWidget(bullet_btn)
            header.addWidget(number_btn)
            self._edits[key] = edit
            self._format_buttons[key] = (bullet_btn, number_btn)
            self._form_layout.addLayout(header)
            self._form_layout.addWidget(edit)

        self._form_scroll = QScrollArea()
        self._form_scroll.setWidgetResizable(True)
        self._form_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._form_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._form_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._form_scroll.setSizeAdjustPolicy(
            QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents
        )
        self._form_scroll.setWidget(self._form_widget)
        layout.addWidget(self._form_scroll)

        for edit in self._edits.values():
            edit.height_changed.connect(self._schedule_form_resize)

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
        self._schedule_form_resize()

    # ---------------- 表示準備 ----------------
    def prepare(
        self,
        existing: Optional[dict],
        force: bool,
        snooze_enabled: bool,
        snooze_minutes: int,
        yesterday_declaration: str = "",
    ) -> None:
        self.update_mode(force, snooze_enabled, snooze_minutes)
        for key, _, _ in FIELDS:
            self._edits[key].setPlainText((existing or {}).get(key, "") or "")
        self._schedule_form_resize()

        if yesterday_declaration:
            self._yesterday_label.setText(f"昨日の宣言：{yesterday_declaration}")
            self._yesterday_label.setVisible(True)
        else:
            self._yesterday_label.setVisible(False)

    def update_mode(self, force: bool, snooze_enabled: bool, snooze_minutes: int) -> None:
        """入力内容には触れず、モード（Force/normal）と再通知ボタンだけ更新する。

        表示中の窓に対して設定変更を反映するために使う。
        """
        self._force = force
        self._snooze_minutes = snooze_minutes
        self._snooze_enabled = snooze_enabled
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

    @staticmethod
    def _has_meaningful_content(value: str) -> bool:
        marker_only = re.compile(r"^(?:-\s*|\d+\.\s*)$")
        return any(
            line.strip() and not marker_only.fullmatch(line.strip())
            for line in value.splitlines()
        )

    def _schedule_form_resize(self) -> None:
        QTimer.singleShot(0, self._resize_form_area)

    def _resize_form_area(self) -> None:
        self._form_layout.activate()
        natural_height = self._form_widget.sizeHint().height()
        screen = self.screen()
        available_height = screen.availableGeometry().height() if screen else 800
        maximum_form_height = max(240, int(available_height * 0.75))
        self._form_scroll.setFixedHeight(min(natural_height, maximum_form_height))
        self.adjustSize()

    # ---------------- ボタン処理 ----------------
    def _on_save(self) -> None:
        vals = self.values()
        meaningful = tuple(self._has_meaningful_content(value) for value in vals)
        if not any(meaningful):
            QMessageBox.warning(self, "確認", "少なくとも1項目は入力してください。")
            return
        if self._force and not all(meaningful):
            QMessageBox.warning(self, "確認", "Forceモードでは全項目の入力が必要です。")
            return
        self.saved.emit()
        self.hide()

    def _on_snooze(self) -> None:
        self.snoozed.emit(self._snooze_minutes)
        self.hide()

    def force_close(self) -> None:
        """アプリ終了時に、Force モードでも確認なしで確実に閉じる。"""
        self._allow_close = True
        self.close()

    def closeEvent(self, event) -> None:
        # アプリ終了による強制クローズはそのまま閉じる
        if self._allow_close:
            event.accept()
            return

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
