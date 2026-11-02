# Alexbed Light Media Player (ALMP)
# Copyright (C) 2026 Alexander Bediako
# SPDX-License-Identifier: GPL-3.0-or-later
"""Single instance: a second ALMP (for example a file opened from Explorer) hands its files to the
one that is already open, through a local channel that only this Windows user can use."""
import getpass
import re
import time

from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from .logsetup import log


def make_ipc_name(user=None):
    """One single-instance channel per Windows user, so two people signed in on the same PC
    (fast user switching, Remote Desktop) each get their own ALMP window."""
    if user is None:
        try:
            user = getpass.getuser()
        except Exception:          # noqa: BLE001
            user = ""
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", str(user or "user"))[:64]
    return f"ALMP-IPC-{safe}"

IPC_NAME = make_ipc_name()

def connect_with_retry(try_connect, timeout_s=10.0, interval_s=0.25, sleep=time.sleep, clock=time.monotonic):
    """Call try_connect() until it returns True or timeout_s has passed.
    Used when a second ALMP starts while the first one is still opening its window."""
    deadline = clock() + timeout_s
    while True:
        try:
            if try_connect():
                return True
        except Exception:          # noqa: BLE001
            log.exception("Single-instance connect attempt failed")
        if clock() >= deadline:
            return False
        sleep(interval_s)


class SingleInstanceServer(QObject):
    """Receives files from a second ALMP (for example several files opened from Explorer).
    It starts listening before the main window is built; files that arrive early are kept
    until the window is ready."""
    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.name = name
        self.server = QLocalServer(self)
        try:
            self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        except Exception:          # noqa: BLE001
            log.exception("Could not restrict the single-instance channel to this user")
        self._receiver = None
        self._early = []
        self.listening = False

    def listen(self):
        QLocalServer.removeServer(self.name)
        self.listening = bool(self.server.listen(self.name))
        if self.listening:
            self.server.newConnection.connect(self._on_new_connection)
        else:
            log.warning("Single-instance channel could not start: %s", self.server.errorString())
        return self.listening

    def set_receiver(self, receiver):
        self._receiver = receiver
        early, self._early = self._early, []
        for paths in early:
            receiver(paths)

    def _deliver(self, paths):
        if self._receiver is None:
            self._early.append(paths)
        else:
            self._receiver(paths)

    def _on_new_connection(self):
        while self.server.hasPendingConnections():
            sock = self.server.nextPendingConnection()
            if sock is None:
                return
            self._handle_socket(sock)

    def _handle_socket(self, sock):
        buf = bytearray()
        state = {"done": False}

        def read_more():
            try:
                buf.extend(bytes(sock.readAll()))
            except RuntimeError:
                pass

        def finish():
            if state["done"]:
                return
            state["done"] = True
            read_more()
            paths = [x for x in buf.decode("utf-8", "ignore").split("\n") if x.strip()]
            try:
                sock.deleteLater()
            except RuntimeError:
                pass
            self._deliver(paths)

        sock.readyRead.connect(read_more)
        sock.disconnected.connect(finish)
        if sock.state() != QLocalSocket.LocalSocketState.ConnectedState:
            QTimer.singleShot(0, finish)
        QTimer.singleShot(15000, finish)   # never keep a stuck connection open


def send_paths_to_running_instance(paths, name=IPC_NAME, timeout_s=10.0):
    """Client side: hand our files to the ALMP that is already running.
    Retries for up to `timeout_s` because that ALMP may still be starting up."""
    payload = "\n".join(paths).encode("utf-8")

    def try_once():
        sock = QLocalSocket()
        sock.connectToServer(name)
        if not sock.waitForConnected(500):
            sock.abort()
            return False
        if payload:
            sock.write(payload)
            sock.flush()
            sock.waitForBytesWritten(3000)
        sock.disconnectFromServer()
        if sock.state() != QLocalSocket.LocalSocketState.UnconnectedState:
            sock.waitForDisconnected(2000)
        return True          # connected and handed over; do not send twice

    return connect_with_retry(try_once, timeout_s=timeout_s)

