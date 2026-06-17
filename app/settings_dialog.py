"""設定ダイアログ。MVP では提醒時間・ポップアップ強度・再通知・自動起動を扱う。

Confluence 欄は Phase 3 連携のために用意するが、接続テスト等は未実装。
"""

from __future__ import annotations

import copy

from PySide6.QtCore import QTime, Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
)

from .confluence_client import ConfluenceClient


class SettingsDialog(QDialog):
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self._config = copy.deepcopy(config)
        self.setWindowTitle("設定")
        self.setMinimumWidth(420)
        # 日記窓が常時最前面のため、設定画面も最前面にしてその上に出す
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)

        root = QVBoxLayout(self)

        # --- 基本設定 ---
        basic = QFormLayout()

        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        hh, mm = self._parse_time(config.get("reminder_time", "18:30"))
        self.time_edit.setTime(QTime(hh, mm))
        basic.addRow("リマインダー時刻", self.time_edit)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["normal", "force"])
        idx = self.mode_combo.findText(config.get("popup_mode", "normal"))
        self.mode_combo.setCurrentIndex(idx if idx >= 0 else 0)
        basic.addRow("ポップアップ強度", self.mode_combo)

        self.snooze_spin = QSpinBox()
        self.snooze_spin.setRange(0, 10)
        self.snooze_spin.setValue(int(config.get("max_snooze_count", 3)))
        basic.addRow("1日の最大再通知回数", self.snooze_spin)

        self.autostart_check = QCheckBox("Windows ログオン時に自動起動する")
        self.autostart_check.setChecked(bool(config.get("autostart_enabled", False)))
        basic.addRow("", self.autostart_check)

        root.addLayout(basic)

        # --- Confluence（Phase 3 用・保存のみ） ---
        conf = config.get("confluence", {})
        group = QGroupBox("Confluence 同期")
        group.setCheckable(True)
        group.setChecked(bool(conf.get("enabled", False)))
        self.conf_group = group
        conf_form = QFormLayout(group)

        self.conf_base_url = QLineEdit(conf.get("base_url", ""))
        self.conf_space_id = QLineEdit(conf.get("space_id", ""))
        self.conf_parent_id = QLineEdit(conf.get("parent_page_id", ""))
        self.conf_parent_id.setPlaceholderText("日記を置くページのID")
        self.conf_email = QLineEdit(conf.get("email", ""))
        self.conf_token = QLineEdit(conf.get("api_token", ""))
        self.conf_token.setEchoMode(QLineEdit.Password)

        conf_form.addRow("Base URL", self.conf_base_url)
        conf_form.addRow("Space ID", self.conf_space_id)
        conf_form.addRow("Parent Page ID", self.conf_parent_id)
        conf_form.addRow("Email", self.conf_email)
        conf_form.addRow("API Token", self.conf_token)

        self.conf_monthly = QCheckBox("年→月の親ページ(YYYY / YYYY-MM)を自動作成する")
        self.conf_monthly.setChecked(bool(conf.get("monthly_parent", False)))
        self.conf_monthly.setToolTip(
            "ON: Parent Page ID をルートとして、その下に年・月ページを自動作成し、"
            "日記を月ページの下にぶら下げます。\n"
            "OFF: 日記を Parent Page ID の直下に作成します。"
        )
        conf_form.addRow("", self.conf_monthly)

        self.test_btn = QPushButton("接続テスト")
        self.test_btn.clicked.connect(self._on_test)
        conf_form.addRow("", self.test_btn)

        note = QLabel("※ 日記内容を Confluence に送信します。API Token は Windows 資格情報マネージャーに保存されます。")
        note.setStyleSheet("color: gray;")
        note.setWordWrap(True)
        conf_form.addRow("", note)

        root.addWidget(group)

        # --- ボタン ---
        buttons = QHBoxLayout()
        save_btn = QPushButton("保存")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._on_save)
        cancel_btn = QPushButton("キャンセル")
        cancel_btn.clicked.connect(self.reject)
        buttons.addStretch(1)
        buttons.addWidget(save_btn)
        buttons.addWidget(cancel_btn)
        root.addLayout(buttons)

    @staticmethod
    def _parse_time(value: str) -> tuple[int, int]:
        try:
            hh, mm = value.split(":")
            return int(hh), int(mm)
        except (ValueError, AttributeError):
            return 18, 30

    def _on_test(self) -> None:
        client = ConfluenceClient(
            base_url=self.conf_base_url.text().strip(),
            email=self.conf_email.text().strip(),
            api_token=self.conf_token.text(),
            space_id=self.conf_space_id.text().strip(),
            parent_page_id=self.conf_parent_id.text().strip(),
        )
        self.test_btn.setEnabled(False)
        self.test_btn.setText("テスト中…")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            ok, msg = client.test_connection()
        finally:
            QApplication.restoreOverrideCursor()
            self.test_btn.setEnabled(True)
            self.test_btn.setText("接続テスト")
        if ok:
            QMessageBox.information(self, "接続テスト", msg)
        else:
            QMessageBox.warning(self, "接続テスト", msg)

    def _on_save(self) -> None:
        self._config["reminder_time"] = self.time_edit.time().toString("HH:mm")
        self._config["popup_mode"] = self.mode_combo.currentText()
        self._config["max_snooze_count"] = self.snooze_spin.value()
        self._config["autostart_enabled"] = self.autostart_check.isChecked()
        self._config["confluence"] = {
            "enabled": self.conf_group.isChecked(),
            "base_url": self.conf_base_url.text().strip(),
            "space_id": self.conf_space_id.text().strip(),
            "parent_page_id": self.conf_parent_id.text().strip(),
            "email": self.conf_email.text().strip(),
            "api_token": self.conf_token.text(),
            "monthly_parent": self.conf_monthly.isChecked(),
        }
        self.accept()

    def result_config(self) -> dict:
        return self._config
