"""同期をバックグラウンドスレッドで実行する。

UI スレッドをブロックしないよう QThread で通信し、結果はシグナルで返す。
プロバイダ非依存：SyncProvider.upsert_entry を呼ぶだけ。
one_done シグナルは（entry, SyncResult）のタプルを 1 件ずつ通知する。
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from .providers.base import SyncProvider, SyncResult


class SyncWorker(QThread):
    # 1 件完了するごとに (entry, SyncResult) を通知
    one_done = Signal(dict, object)
    # 全件完了
    all_done = Signal(int, int)  # (success_count, total)

    def __init__(self, provider: SyncProvider, entries: list[dict], parent=None):
        super().__init__(parent)
        self._provider = provider
        self._entries = entries

    def run(self) -> None:
        success = 0
        for entry in self._entries:
            result: SyncResult = self._provider.upsert_entry(entry)
            if result.ok:
                success += 1
            self.one_done.emit(entry, result)
        self.all_done.emit(success, len(self._entries))
