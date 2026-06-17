"""多重起動防止。2 回目以降の起動は、既存インスタンスに「表示して」と通知する。

QLocalServer/QLocalSocket（名前付きパイプ）で実装。
* 最初の起動 … サーバを listen する。
* 2 回目以降 … サーバに接続できる → "show" を送って自分は終了。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from .logger import get_logger

log = get_logger(__name__)

KEY = "DailyDiary_singleinstance_v1"


class SingleInstance(QObject):
    # 既存インスタンスが「表示して」と依頼されたとき発火
    activated = Signal()

    def __init__(self):
        super().__init__()
        self._server: QLocalServer | None = None

    def is_already_running(self) -> bool:
        sock = QLocalSocket()
        sock.connectToServer(KEY)
        if sock.waitForConnected(300):
            sock.write(b"show")
            sock.waitForBytesWritten(300)
            sock.disconnectFromServer()
            return True
        # 自分が最初のインスタンス → サーバを起動
        self._start_server()
        return False

    def _start_server(self) -> None:
        # 前回クラッシュ時に残ったソケット名を掃除してから listen
        QLocalServer.removeServer(KEY)
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_new_connection)
        if not self._server.listen(KEY):
            log.warning("単一インスタンス用サーバの listen に失敗: %s", self._server.errorString())

    def _on_new_connection(self) -> None:
        conn = self._server.nextPendingConnection() if self._server else None
        if conn is None:
            return
        conn.waitForReadyRead(300)
        conn.readAll()
        conn.disconnectFromServer()
        log.info("別の起動要求を受信。日記ウィンドウを表示します。")
        self.activated.emit()
