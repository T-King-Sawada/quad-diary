"""Confluence 同期をバックグラウンドスレッドで実行する。

UI スレッドをブロックしないよう QThread で通信し、結果はシグナルで返す。
done シグナルは（entry, SyncResult）のタプルを 1 件ずつ通知する。
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from .confluence_client import ConfluenceClient, SyncResult


class SyncWorker(QThread):
    # 1 件完了するごとに (entry, SyncResult) を通知
    one_done = Signal(dict, object)
    # 全件完了
    all_done = Signal(int, int)  # (success_count, total)

    def __init__(self, client: ConfluenceClient, entries: list[dict], parent=None):
        super().__init__(parent)
        self._client = client
        self._entries = entries

    def run(self) -> None:
        success = 0
        for entry in self._entries:
            result: SyncResult = self._client.create_diary_page(entry)
            if result.ok:
                success += 1
            self.one_done.emit(entry, result)
        self.all_done.emit(success, len(self._entries))
