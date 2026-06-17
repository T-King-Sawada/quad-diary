"""初回設定ウィザード。

管理者が config.default.json で base_url / space_id を用意済みの場合は、
利用者は email と API Token だけ入力すれば動くようにする（新人社員向け）。
未用意の場合は全項目を入力できる（個人利用向け）。
"""

from __future__ import annotations

import copy

from PySide6.QtCore import QTime, Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTimeEdit,
    QVBoxLayout,
)

from . import config as config_mod
from .confluence_client import ConfluenceClient


class FirstRunWizard(QDialog):
    def __init__(self, base_config: dict, parent=None):
        super().__init__(parent)
        self._config = copy.deepcopy(base_config)
        self.setWindowTitle("4行日記 - 初回設定")
        self.setMinimumWidth(440)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)

        # 管理者デフォルトで base_url と space_id が用意済みか
        md = config_mod.managed_defaults().get("confluence", {})
        self._admin_managed = bool(md.get("base_url")) and bool(md.get("space_id"))

        conf = self._config.get("confluence", {})
        root = QVBoxLayout(self)

        intro = QLabel(
            "ようこそ。毎日決まった時刻に「4行日記」の入力を促すアプリです。\n"
            "最初に基本設定を行います（後から「設定」で変更できます）。"
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        basic = QFormLayout()
        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        hh, mm = self._parse_time(self._config.get("reminder_time", "18:30"))
        self.time_edit.setTime(QTime(hh, mm))
        basic.addRow("リマインダー時刻", self.time_edit)

        self.autostart_check = QCheckBox("Windows ログオン時に自動起動する")
        self.autostart_check.setChecked(bool(self._config.get("autostart_enabled", False)))
        basic.addRow("", self.autostart_check)
        root.addLayout(basic)

        # --- Confluence ---
        group = QGroupBox("Confluence 同期（任意）")
        group.setCheckable(True)
        group.setChecked(bool(conf.get("enabled", False)))
        self.conf_group = group
        form = QFormLayout(group)

        # 接続先は管理者デフォルトがあれば隠す。利用者は投稿先/認証情報を入力。
        self.conf_base_url = QLineEdit(conf.get("base_url", ""))
        self.conf_space_id = QLineEdit(conf.get("space_id", ""))
        self.conf_parent_id = QLineEdit(conf.get("parent_page_id", ""))
        self.conf_parent_id.setPlaceholderText("日記を置くページのID")

        if self._admin_managed:
            note = QLabel("接続先は管理者により設定済みです。あなたの投稿先と認証情報を入力してください。")
            note.setStyleSheet("color: gray;")
            note.setWordWrap(True)
            form.addRow("", note)
        else:
            form.addRow("Base URL", self.conf_base_url)
            form.addRow("Space ID", self.conf_space_id)

        # Parent Page ID は常に表示（利用者が投稿先を指定）
        form.addRow("Parent Page ID", self.conf_parent_id)

        self.conf_email = QLineEdit(conf.get("email", ""))
        self.conf_token = QLineEdit(conf.get("api_token", ""))
        self.conf_token.setEchoMode(QLineEdit.Password)
        form.addRow("Email", self.conf_email)
        form.addRow("API Token", self.conf_token)

        self.test_btn = QPushButton("接続テスト")
        self.test_btn.clicked.connect(self._on_test)
        form.addRow("", self.test_btn)

        hint = QLabel(
            "API Token は https://id.atlassian.com/manage-profile/security/api-tokens で発行。"
            "トークンは Windows 資格情報マネージャーに安全に保存されます。"
        )
        hint.setStyleSheet("color: gray;")
        hint.setWordWrap(True)
        form.addRow("", hint)
        root.addWidget(group)

        buttons = QHBoxLayout()
        ok = QPushButton("完了")
        ok.setDefault(True)
        ok.clicked.connect(self._on_finish)
        skip = QPushButton("あとで")
        skip.clicked.connect(self.reject)
        buttons.addStretch(1)
        buttons.addWidget(ok)
        buttons.addWidget(skip)
        root.addLayout(buttons)

    @staticmethod
    def _parse_time(value: str) -> tuple[int, int]:
        try:
            hh, mm = value.split(":")
            return int(hh), int(mm)
        except (ValueError, AttributeError):
            return 18, 30

    def _gather_confluence(self) -> dict:
        conf = dict(self._config.get("confluence", {}))
        conf["enabled"] = self.conf_group.isChecked()
        if not self._admin_managed:
            conf["base_url"] = self.conf_base_url.text().strip()
            conf["space_id"] = self.conf_space_id.text().strip()
        # 投稿先・認証情報は常に利用者が入力
        conf["parent_page_id"] = self.conf_parent_id.text().strip()
        conf["email"] = self.conf_email.text().strip()
        conf["api_token"] = self.conf_token.text()
        return conf

    def _on_test(self) -> None:
        conf = self._gather_confluence()
        client = ConfluenceClient(
            base_url=conf.get("base_url", ""),
            email=conf.get("email", ""),
            api_token=conf.get("api_token", ""),
            space_id=conf.get("space_id", ""),
            parent_page_id=conf.get("parent_page_id", ""),
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
        (QMessageBox.information if ok else QMessageBox.warning)(self, "接続テスト", msg)

    def _on_finish(self) -> None:
        self._config["reminder_time"] = self.time_edit.time().toString("HH:mm")
        self._config["autostart_enabled"] = self.autostart_check.isChecked()
        self._config["confluence"] = self._gather_confluence()
        self.accept()

    def result_config(self) -> dict:
        return self._config
