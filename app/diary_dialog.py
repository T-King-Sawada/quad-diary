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
import time
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import storage

# 4 項目の定義（キー, ラベル, プレースホルダ）
# ラベルは同期先の見出しにも使うので、素の名前のままにしておく。
FIELDS = [
    ("fact", "事実", "今日実際に起きたこと"),
    ("discovery", "発見", "今日気づいたこと・注目したこと"),
    ("lesson", "教訓", "今日得た教訓"),
    (
        "declaration",
        "宣言",
        "明日やること。1つだけ。習慣にするかどうかは考えなくていい",
    ),
]

#: 入力画面でだけ「（任意）」を添える項目。必須は「少なくとも1項目」だけ。
OPTIONAL_FIELDS = {"discovery", "lesson", "declaration"}

# 追記ブロックの種別（キー, ラベル, プレースホルダ）
# 4 行に収まらない日の受け皿。既定では入力欄を出さず、押したときだけ増える。
BLOCK_TYPES = [
    (storage.BLOCK_THOUGHT, "思考", "4行に収まらない考え"),
    (storage.BLOCK_SEED, "タネ", "後で書きたいこと。一言でいい"),
]
BLOCK_LABELS = {key: label for key, label, _ in BLOCK_TYPES}
BLOCK_PLACEHOLDERS = {key: placeholder for key, _, placeholder in BLOCK_TYPES}


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


class _ClickableLabel(QLabel):
    """クリックで checkbox をトグルできる、折り返し対応の宣言ラベル。"""

    clicked = Signal()

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class _ReviewRow(QWidget):
    """未応答の宣言 1 件。チェックが主操作で、一言はチェック後に開く任意欄。"""

    changed = Signal()

    def __init__(self, item: dict, parent=None):
        super().__init__(parent)
        self._date: str = item["date"]
        self._result: Optional[str] = None  # None / done / dropped / pending(=あとで)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 2, 0, 2)
        outer.setSpacing(2)

        row = QHBoxLayout()
        row.setSpacing(6)

        self._check = QCheckBox()
        self._check.setToolTip("できた")
        self._check.toggled.connect(self._on_toggled)

        self._label = _ClickableLabel(item["declaration"])
        self._label.clicked.connect(self._check.toggle)

        # 経過日数は中立表示（警告色や記号は使わない）
        self._meta = QLabel(self._meta_text(item))
        self._meta.setStyleSheet("color: #71717a;")

        self._menu_btn = QToolButton()
        self._menu_btn.setText("⋯")
        self._menu_btn.setAutoRaise(True)
        self._menu_btn.setFocusPolicy(Qt.NoFocus)
        self._menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self._menu_btn)
        menu.addAction("もう降りる", lambda: self._set_result(storage.REVIEW_DROPPED))
        menu.addAction(
            f"あとで（+{storage.DEFER_DAYS}日）",
            lambda: self._set_result(storage.REVIEW_PENDING),
        )
        self._menu_btn.setMenu(menu)

        row.addWidget(self._check, 0)
        row.addWidget(self._label, 1)
        row.addWidget(self._meta, 0)
        row.addWidget(self._menu_btn, 0)
        outer.addLayout(row)

        self._note = QLineEdit()
        self._note.setPlaceholderText("一言（任意・空でも保存できます）")
        self._note.setVisible(False)
        outer.addWidget(self._note)

    @staticmethod
    def _meta_text(item: dict) -> str:
        month_day = item["date"][5:].replace("-", "/")
        parts = [month_day]
        days = item.get("days", 0)
        if days > 0:
            parts.append(f"{days}日前")
        repeat = item.get("repeat", 1)
        if repeat > 1:
            parts.append(f"{repeat}回目")
        return " ・ ".join(parts)

    # ---- 操作 ----
    def _on_toggled(self, checked: bool) -> None:
        self._result = storage.REVIEW_DONE if checked else None
        self._note.setVisible(checked)
        if not checked:
            self._note.clear()
        self.changed.emit()

    def _set_result(self, result: str) -> None:
        """メニュー経由の確定（降りる／あとで）。行を淡くして操作を締める。"""
        self._result = result
        self._check.setEnabled(False)
        self._label.setEnabled(False)
        self._menu_btn.setEnabled(False)
        self._note.setVisible(False)
        self._note.clear()

        font = self._label.font()
        font.setStrikeOut(result == storage.REVIEW_DROPPED)
        self._label.setFont(font)
        self._label.setStyleSheet("color: #a1a1aa;")
        self._meta.setText(
            "降りた" if result == storage.REVIEW_DROPPED else f"+{storage.DEFER_DAYS}日"
        )
        self.changed.emit()

    def response(self) -> Optional[dict]:
        if self._result is None:
            return None
        return {
            "date": self._date,
            "result": self._result,
            "note": self._note.text().strip(),
        }


class _ReviewList(QFrame):
    """入力画面の先頭に出す「未応答の宣言」リスト。0 件なら自分を隠す。

    設計上の要点:
        - 追加の入力時間をゼロにする（読んで押すだけ。テキストは押した後の任意欄）
        - 一度に出すのは最大 MAX_VISIBLE_REVIEWS 件。残りは「他N件」に畳む
        - 出口が「できた」だけではないので、リストは必ずゼロに到達できる
    """

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("reviewList")
        self.setStyleSheet(
            "#reviewList { background-color: #fafafa; border: 1px solid #e4e4e7;"
            " border-radius: 6px; }"
        )
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(10, 8, 10, 8)
        self._layout.setSpacing(2)

        self._header = QLabel()
        self._header.setStyleSheet("color: #52525b; font-weight: bold;")
        self._layout.addWidget(self._header)

        self._rows: list[_ReviewRow] = []
        self._hidden_rows: list[_ReviewRow] = []
        self._more_btn = QPushButton()
        self._more_btn.setFlat(True)
        self._more_btn.setFocusPolicy(Qt.NoFocus)
        self._more_btn.setStyleSheet("color: #52525b; text-align: left;")
        self._more_btn.setVisible(False)
        self._more_btn.clicked.connect(self._reveal_rest)
        self._layout.addWidget(self._more_btn)

    def set_items(self, items: list[dict]) -> None:
        for row in self._rows:
            row.setParent(None)
            row.deleteLater()
        self._rows = []
        self._hidden_rows = []

        if not items:
            self._more_btn.setVisible(False)
            self.setVisible(False)
            return

        self._header.setText(f"宣言 {len(items)}件")
        insert_at = self._layout.indexOf(self._more_btn)
        for index, item in enumerate(items):
            row = _ReviewRow(item)
            row.changed.connect(self.changed)
            self._layout.insertWidget(insert_at + index, row)
            self._rows.append(row)
            if index >= storage.MAX_VISIBLE_REVIEWS:
                row.setVisible(False)
                self._hidden_rows.append(row)

        if self._hidden_rows:
            self._more_btn.setText(f"他 {len(self._hidden_rows)}件 ▾")
            self._more_btn.setVisible(True)
        else:
            self._more_btn.setVisible(False)

        self.setVisible(True)

    def _reveal_rest(self) -> None:
        for row in self._hidden_rows:
            row.setVisible(True)
        self._hidden_rows = []
        self._more_btn.setVisible(False)
        self.changed.emit()

    def responses(self) -> list[dict]:
        return [r for r in (row.response() for row in self._rows) if r is not None]


class _BlockRow(QWidget):
    """追記ブロック 1 件（思考 / タネ）。空のまま保存すると捨てられる。"""

    removed = Signal(object)
    height_changed = Signal()

    def __init__(self, kind: str, body: str = "", block_id: Optional[str] = None, parent=None):
        super().__init__(parent)
        self._kind = kind
        self._id = block_id

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(2)

        header = QHBoxLayout()
        label = QLabel(BLOCK_LABELS.get(kind, kind))
        label.setStyleSheet("color: #52525b;")
        header.addWidget(label)
        header.addStretch()

        remove_btn = QToolButton()
        remove_btn.setText("×")
        remove_btn.setAutoRaise(True)
        remove_btn.setFocusPolicy(Qt.NoFocus)
        remove_btn.setToolTip("この追記を消す")
        remove_btn.clicked.connect(lambda: self.removed.emit(self))
        header.addWidget(remove_btn)
        layout.addLayout(header)

        self._edit = _AutoJumpTextEdit()
        self._edit.setPlaceholderText(BLOCK_PLACEHOLDERS.get(kind, ""))
        self._edit.setAcceptRichText(False)
        self._edit.setTabChangesFocus(True)
        self._edit.setPlainText(body)
        self._edit.height_changed.connect(self.height_changed)
        layout.addWidget(self._edit)

    def focus(self) -> None:
        self._edit.setFocus()

    def value(self) -> dict:
        block = {"type": self._kind, "body": self._edit.toPlainText().strip()}
        if self._id:
            block["id"] = self._id
        return block


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
        self._opened_at: Optional[float] = None
        self._edits: dict[str, QTextEdit] = {}
        self._format_buttons: dict[str, tuple[QPushButton, QPushButton]] = {}

        self.setWindowTitle("今日の4行日記")
        self.setMinimumWidth(420)
        # リマインダー窓なので常に最前面に表示する
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)

        layout = QVBoxLayout(self)

        # 未応答の宣言を最上部に再浮上させる（0 件なら自動で隠れる）
        self._review_list = _ReviewList()
        self._review_list.setVisible(False)
        self._review_list.changed.connect(self._schedule_form_resize)
        layout.addWidget(self._review_list)

        self._form_widget = QWidget()
        self._form_layout = QVBoxLayout(self._form_widget)

        for key, label, placeholder in FIELDS:
            header = QHBoxLayout()
            header.addWidget(
                QLabel(f"{label}（任意）" if key in OPTIONAL_FIELDS else label)
            )
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

        # --- 追記ブロック（任意）---
        # 既定では入力欄を出さない。押したときだけ増えるので、空欄の圧が生まれない。
        self._blocks: list[_BlockRow] = []
        self._blocks_container = QWidget()
        self._blocks_layout = QVBoxLayout(self._blocks_container)
        self._blocks_layout.setContentsMargins(0, 0, 0, 0)
        self._blocks_layout.setSpacing(2)
        self._form_layout.addWidget(self._blocks_container)

        add_row = QHBoxLayout()
        add_row.setSpacing(6)
        for kind, label, _placeholder in BLOCK_TYPES:
            btn = QPushButton(f"＋ {label}")
            btn.setFlat(True)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setStyleSheet("color: #52525b; text-align: left;")
            btn.setToolTip(BLOCK_PLACEHOLDERS[kind])
            btn.clicked.connect(lambda _checked=False, k=kind: self._add_block(k, focus=True))
            add_row.addWidget(btn)
        add_row.addStretch()
        self._form_layout.addLayout(add_row)

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
        reviews: Optional[list[dict]] = None,
    ) -> None:
        self.update_mode(force, snooze_enabled, snooze_minutes)
        for key, _, _ in FIELDS:
            self._edits[key].setPlainText((existing or {}).get(key, "") or "")
        self._review_list.set_items(reviews or [])
        self._load_blocks((existing or {}).get("entries") or [])
        self._opened_at = time.monotonic()
        self._schedule_form_resize()

    # ---------------- 追記ブロック ----------------
    def _load_blocks(self, blocks: list[dict]) -> None:
        for row in list(self._blocks):
            self._remove_block(row)
        for block in blocks:
            kind = block.get("type")
            if kind in BLOCK_LABELS:
                self._add_block(kind, body=block.get("body", ""), block_id=block.get("id"))

    def _add_block(
        self,
        kind: str,
        body: str = "",
        block_id: Optional[str] = None,
        focus: bool = False,
    ) -> "_BlockRow":
        row = _BlockRow(kind, body=body, block_id=block_id)
        row.removed.connect(self._remove_block)
        row.height_changed.connect(self._schedule_form_resize)
        self._blocks_layout.addWidget(row)
        self._blocks.append(row)
        self._schedule_form_resize()
        if focus:
            row.focus()
        return row

    def _remove_block(self, row: "_BlockRow") -> None:
        if row in self._blocks:
            self._blocks.remove(row)
        row.setParent(None)
        row.deleteLater()
        self._schedule_form_resize()

    def blocks(self) -> list[dict]:
        """追記ブロックの内容（空欄は保存側で捨てられる）。"""
        return [row.value() for row in self._blocks]

    def review_responses(self) -> list[dict]:
        """検証リストで応答された宣言（date / result / note）を返す。"""
        return self._review_list.responses()

    def elapsed_seconds(self) -> int:
        """画面を開いてから経過した秒数（meta の自己観測用）。"""
        if self._opened_at is None:
            return 0
        return int(time.monotonic() - self._opened_at)

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
        # 追記ブロックだけ書いた日も保存できる
        meaningful += tuple(
            self._has_meaningful_content(block["body"]) for block in self.blocks()
        )
        if not any(meaningful):
            QMessageBox.warning(self, "確認", "少なくとも1項目は入力してください。")
            return
        # Force モードでも全項目は要求しない。1 行だけで保存できることが継続の前提。
        # Force の意味は「未保存のまま黙って閉じさせない」（closeEvent 側）に限定する。
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
