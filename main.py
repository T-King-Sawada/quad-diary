"""DailyDiary エントリポイント。

PySide6 のトレイ常駐アプリ。定刻に 4 行日記の入力を促し、本機（JSONL）へ保存する。
Phase 1（本機 MVP）：トレイ常駐 / 定時リマインダー / 4 行入力 / JSONL 保存 /
設定画面 / 自動起動設定。
"""

from __future__ import annotations

import sys
from datetime import date

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QSystemTrayIcon

from app import autostart, config as config_mod, logger, storage
from app.confluence_client import ConfluenceClient
from app.diary_dialog import DiaryDialog
from app.reminder import Reminder
from app.settings_dialog import SettingsDialog
from app.single_instance import SingleInstance
from app.sync_worker import SyncWorker
from app.tray import Tray

log = logger.get_logger("main")


class AppController:
    def __init__(self, app: QApplication):
        self.app = app
        self.config = config_mod.load()

        # 日記ウィンドウは 1 つだけ使い回す（非モーダル）
        self.diary = DiaryDialog()
        self.diary.saved.connect(self._on_diary_saved)
        self.diary.snoozed.connect(self._on_diary_snoozed)
        self.diary.cancelled.connect(self._on_diary_cancelled)
        self._diary_reason = "manual"
        self._diary_existing: dict | None = None
        self._prompting = False
        self._sync_workers: set = set()

        self.reminder = Reminder(
            get_reminder_time=lambda: self.config.get("reminder_time", "18:30"),
            is_submitted_today=lambda: storage.is_submitted(storage.today_str()),
        )
        self.reminder.fire.connect(self.on_fire)

        self.tray = Tray(
            on_write=self.open_diary_manual,
            on_settings=self.open_settings,
            on_sync=self.on_sync,
            on_quit=self.quit,
        )
        self._refresh_tray_state()
        self.tray.show()

        # 起動時に config と実際の自動起動状態を合わせる
        self._sync_autostart_state()

    # ---------------- リマインダー ----------------
    def on_fire(self, reason: str) -> None:
        self.open_diary(reason)

    def open_diary_manual(self) -> None:
        self.open_diary("manual")

    def open_diary(self, reason: str) -> None:
        # 既に表示中、または確認ダイアログ表示中なら前面に出すだけ
        if self.diary.isVisible():
            self.diary.bring_to_front()
            return
        if self._prompting:
            return

        today = storage.today_str()
        existing = storage.get_entry(today)

        # F-103：定刻発火で既に保存済みなら再編集確認
        if reason == "reminder" and existing is not None:
            self._prompting = True
            try:
                ans = QMessageBox.question(
                    None,
                    "確認",
                    "今日の4行日記は既に保存されています。\n再編集しますか？",
                )
            finally:
                self._prompting = False
            if ans != QMessageBox.Yes:
                self.reminder.mark_done()
                return

        mode = self.config.get("popup_mode", "normal")
        max_snooze = int(self.config.get("max_snooze_count", 3))
        snooze_minutes = int(self.config.get("snooze_minutes", 10))

        self._diary_reason = reason
        self._diary_existing = existing
        self.diary.prepare(
            existing=existing,
            force=(mode == "force"),
            snooze_enabled=self.reminder.can_snooze(max_snooze),
            snooze_minutes=snooze_minutes,
        )
        self.diary.show()
        self.diary.bring_to_front()

    # 日記ウィンドウからのシグナル
    def _on_diary_saved(self) -> None:
        self._save_entry(storage.today_str(), self.diary.values(), self._diary_existing)

    def _on_diary_snoozed(self, minutes: int) -> None:
        self.reminder.snooze(minutes)
        self.tray.notify("4行日記", f"{minutes}分後に再通知します。")

    def _on_diary_cancelled(self) -> None:
        if self._diary_reason in ("reminder", "snooze"):
            self.reminder.dismiss()

    def _save_entry(self, today: str, values, existing) -> None:
        fact, discovery, lesson, declaration = values
        conf_enabled = bool(self.config.get("confluence", {}).get("enabled", False))
        try:
            entry = storage.new_entry(
                today, fact, discovery, lesson, declaration, existing=existing
            )
            # 同期有効なら pending、無効なら none（設計 12.2）
            entry["sync_status"] = "pending" if conf_enabled else "none"
            # まず本機保存（設計 6.4：先に本機、後で同期）
            storage.save_entry(entry)
            self.reminder.mark_done()
            self.tray.notify("4行日記", "保存しました。")
        except OSError as e:
            log.exception("本機保存に失敗しました。")
            QMessageBox.critical(
                None, "保存エラー", f"日記の保存に失敗しました。\n{e}"
            )
            return

        if conf_enabled:
            self._start_sync([entry], announce=False)

    # ---------------- Confluence 同期 ----------------
    def _start_sync(self, entries: list[dict], announce: bool) -> None:
        client = ConfluenceClient.from_config(self.config)
        if client is None:
            log.warning("Confluence 設定が不完全なため同期をスキップします。")
            return
        if not entries:
            if announce:
                self.tray.notify("4行日記", "同期対象はありません。")
            return

        worker = SyncWorker(client, entries)
        worker.one_done.connect(self._on_sync_one)
        worker.all_done.connect(self._on_sync_all)
        worker.finished.connect(lambda: self._sync_workers.discard(worker))
        self._sync_workers.add(worker)
        worker.start()

    def _on_sync_one(self, entry: dict, result) -> None:
        if result.ok:
            entry["sync_status"] = "synced"
            entry["confluence_page_id"] = result.page_id
            entry["sync_error"] = None
        else:
            entry["sync_status"] = "failed"
            entry["sync_error"] = result.error
        try:
            storage.save_entry(entry)
        except OSError:
            log.exception("同期状態の保存に失敗しました。")

    def _on_sync_all(self, success: int, total: int) -> None:
        if success == total:
            self.tray.notify("4行日記", f"Confluence へ同期しました（{success}件）。")
        else:
            failed = total - success
            self.tray.notify(
                "4行日記 同期失敗",
                f"{failed}件の同期に失敗しました。本機には保存済みです。"
                "後で「同期する」で再試行できます。",
            )

    # ---------------- 設定 ----------------
    def open_settings(self) -> None:
        dlg = SettingsDialog(self.config)
        if dlg.exec() != SettingsDialog.Accepted:
            return
        new_config = dlg.result_config()

        autostart_changed = new_config.get("autostart_enabled") != self.config.get(
            "autostart_enabled"
        )
        time_changed = new_config.get("reminder_time") != self.config.get("reminder_time")
        self.config = new_config
        config_mod.save(self.config)

        # リマインダー時刻が変わったら、その日の発火状態をリセットして再評価
        if time_changed:
            self.reminder.rearm()

        # 日記ウィンドウ表示中なら、ポップアップ強度などの変更を即反映
        if self.diary.isVisible():
            max_snooze = int(self.config.get("max_snooze_count", 3))
            self.diary.update_mode(
                force=(self.config.get("popup_mode", "normal") == "force"),
                snooze_enabled=self.reminder.can_snooze(max_snooze),
                snooze_minutes=int(self.config.get("snooze_minutes", 10)),
            )

        if autostart_changed:
            ok = autostart.apply(self.config.get("autostart_enabled", False))
            if not ok:
                QMessageBox.warning(
                    None, "自動起動", "自動起動設定の変更に失敗しました。ログを確認してください。"
                )

        self._refresh_tray_state()
        log.info("設定を更新しました。")

    def _refresh_tray_state(self) -> None:
        self.tray.set_sync_enabled(
            bool(self.config.get("confluence", {}).get("enabled", False))
        )

    def _sync_autostart_state(self) -> None:
        """config と実レジストリの自動起動状態を一致させる。"""
        want = bool(self.config.get("autostart_enabled", False))
        if want != autostart.is_enabled():
            autostart.apply(want)

    # ---------------- 同期（手動リトライ） ----------------
    def on_sync(self) -> None:
        if not self.config.get("confluence", {}).get("enabled", False):
            QMessageBox.information(
                None, "同期", "Confluence 同期が無効です。設定で有効にしてください。"
            )
            return
        pending = storage.unsynced_entries()
        if not pending:
            self.tray.notify("4行日記", "同期対象はありません。")
            return
        self.tray.notify("4行日記", f"{len(pending)}件を同期しています…")
        self._start_sync(pending, announce=True)

    # ---------------- 終了 ----------------
    def quit(self) -> None:
        log.info("アプリを終了します。")
        # 実行中の同期スレッドの完了を少し待つ
        for w in list(self._sync_workers):
            w.wait(3000)
        self.tray.hide()
        self.app.quit()

    def run_startup(self, show_diary: bool = False) -> None:
        self.reminder.start()
        # トレイが隠れていても起動が分かるよう通知を出す
        self.tray.notify(
            "4行日記",
            "タスクトレイに常駐しました。アイコンが見えない場合はタスクバー右の「∧」を確認してください。",
        )
        if show_diary:
            # 手動起動時は起動直後に日記を開く（イベントループ開始後に実行）
            QTimer.singleShot(0, self.open_diary_manual)
        log.info("DailyDiary を起動しました（reminder_time=%s）。", self.config.get("reminder_time"))


def _install_excepthook() -> None:
    """未処理例外をログに残し、利用者に通知する（設計 15）。"""

    def hook(exctype, value, tb):
        log.critical("Unexpected error", exc_info=(exctype, value, tb))
        try:
            QMessageBox.critical(
                None,
                "エラー",
                f"予期しないエラーが発生しました。\n{value}\n\n"
                "詳細は logs/app.log を確認してください。",
            )
        except Exception:
            pass

    sys.excepthook = hook


def main() -> int:
    logger.setup()
    _install_excepthook()
    log.info("==== App start ====")

    app = QApplication(sys.argv)
    app.setApplicationName("DailyDiary")
    app.setQuitOnLastWindowClosed(False)  # 窓を閉じても常駐し続ける

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "エラー", "システムトレイが利用できません。")
        return 1

    # 多重起動防止：既に起動済みなら既存インスタンスに表示を依頼して終了
    single = SingleInstance()
    if single.is_already_running():
        log.info("既に起動済み。既存インスタンスに表示を依頼して終了します。")
        return 0

    # 初回起動なら設定ウィザードを表示
    if config_mod.is_first_run():
        from app.first_run import FirstRunWizard

        base_cfg = config_mod.load()  # 管理者デフォルト
        wizard = FirstRunWizard(base_cfg)
        if wizard.exec() == QDialog.Accepted:
            config_mod.save(wizard.result_config())
        else:
            config_mod.save(base_cfg)  # スキップでも保存して次回からは初回扱いにしない
        log.info("初回設定ウィザードを完了しました。")

    controller = AppController(app)
    single.activated.connect(controller.open_diary_manual)
    controller.run_startup(show_diary="--show" in sys.argv)

    exit_code = app.exec()
    log.info("==== App exit (%d) ====", exit_code)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
