from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtNetwork import QLocalServer, QLocalSocket

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "AniDesk"


def resource_path(name: str) -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS")) / "resources" / name
    return Path(__file__).resolve().parents[4] / "src-tauri" / "icons" / name


def open_external(url: str) -> bool:
    parsed = QUrl(url)
    if parsed.scheme().lower() not in {"http", "https"} or not parsed.host():
        raise ValueError("仅支持有效的 HTTP/HTTPS 地址")
    return QDesktopServices.openUrl(parsed)


def _autostart_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    executable = pythonw if pythonw.is_file() else Path(sys.executable)
    return f'"{executable}" -m anidesk'


def set_autostart(enabled: bool) -> None:
    if os.name != "nt":
        return
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ, _autostart_command())
        else:
            try:
                winreg.DeleteValue(key, RUN_NAME)
            except FileNotFoundError:
                pass


def autostart_enabled() -> bool:
    if os.name != "nt":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_QUERY_VALUE) as key:
            value, _ = winreg.QueryValueEx(key, RUN_NAME)
            return bool(value)
    except FileNotFoundError:
        return False


class SingleInstance:
    def __init__(self, name: str = "com.anidesk.desktop") -> None:
        self.name = name
        self.server = QLocalServer()

    def acquire(self, activate_callback) -> bool:
        if self.server.listen(self.name):
            self.server.newConnection.connect(lambda: self._receive(activate_callback))
            return True
        socket = QLocalSocket()
        socket.connectToServer(self.name)
        if socket.waitForConnected(500):
            socket.write(b"activate")
            socket.waitForBytesWritten(500)
            socket.disconnectFromServer()
            return False
        QLocalServer.removeServer(self.name)
        if not self.server.listen(self.name):
            raise RuntimeError("无法建立 AniDesk 单实例服务")
        self.server.newConnection.connect(lambda: self._receive(activate_callback))
        return True

    def _receive(self, activate_callback) -> None:
        socket = self.server.nextPendingConnection()
        if socket:
            socket.waitForReadyRead(100)
            socket.readAll()
            socket.disconnectFromServer()
        activate_callback()
