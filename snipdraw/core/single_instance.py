"""单实例：第二个进程只把指令转发给已运行的实例，然后退出。"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class SingleInstance(QObject):
    commandReceived = Signal(str)

    def __init__(self, key: str = "snipdraw-single", parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.key = key
        self._server: QLocalServer | None = None

    def notify_existing(self, command: str, timeout_ms: int = 800) -> bool:
        """连上已有实例、转发指令、并等到对方回 "ok" 才认为它真的活着。

        只靠 connectToServer 成功是不够的：socket 文件残留时连接可能假装成功，
        结果第二个进程误以为已有实例而直接退出，用户看到的就是“点了没反应”。
        """
        socket = QLocalSocket(self)
        socket.connectToServer(self.key)
        if not socket.waitForConnected(timeout_ms):
            return False
        socket.write(command.encode("utf-8"))
        socket.flush()
        socket.waitForBytesWritten(500)
        ack = socket.waitForReadyRead(600) and bytes(socket.readAll().data()).strip() == b"ok"
        socket.disconnectFromServer()
        return ack

    def listen(self) -> bool:
        # 上一个实例崩溃时 socket 文件会残留，先清掉
        QLocalServer.removeServer(self.key)
        server = QLocalServer(self)
        if not server.listen(self.key):
            return False
        server.newConnection.connect(self._on_new_connection)
        self._server = server
        return True

    def _on_new_connection(self) -> None:
        if self._server is None:
            return
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            if socket is None:
                return
            buffer = {"data": b""}
            socket.readyRead.connect(lambda s=socket, b=buffer: self._read(s, b))
            socket.disconnected.connect(socket.deleteLater)

    def _read(self, socket: QLocalSocket, buffer: dict[str, bytes]) -> None:
        buffer["data"] += bytes(socket.readAll().data())
        try:
            text = buffer["data"].decode("utf-8").strip()
        except UnicodeDecodeError:
            return
        if text:
            buffer["data"] = b""
            self.commandReceived.emit(text)
            # 回执：让第二个进程确认“指令真的被活着的实例收到了”
            try:
                socket.write(b"ok")
                socket.flush()
            except RuntimeError:
                pass
