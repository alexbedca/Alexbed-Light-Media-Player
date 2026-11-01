# Alexbed Light Media Player (ALMP)
# Copyright (C) 2026 Alexander Bediako
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

__version__ = "7.5.2"

import os
import sys
import random
import subprocess
import json
import threading
import time
from pathlib import Path

# --- Cross-Platform Import Handling ---
if sys.platform == "win32":
    import ctypes
    import winreg

# --- Linux: embed mpv through X11 ---
if sys.platform.startswith("linux") and "QT_QPA_PLATFORM" not in os.environ and os.environ.get("DISPLAY"):
    os.environ["QT_QPA_PLATFORM"] = "xcb"

# --- Nuitka & PyInstaller Resource Path Engine ---
def get_resource_path(relative_path):
    if hasattr(sys, "_MEIPASS"):
        base_path = sys._MEIPASS
    elif hasattr(sys, "frozen") or "__compiled__" in globals():
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

def get_app_icon_path():
    names = ["icon.ico"] if sys.platform == "win32" else ["icon.png", "icon.ico"]
    for n in names:
        p = get_resource_path(n)
        if os.path.exists(p):
            return p
    return ""

# --- Real location of ALMP.exe (portable-safe) ---
def _resolve_app_exe_path():
    def _ok(path):
        return bool(path) and os.path.isfile(path) and os.path.basename(path).lower() not in ("python.exe", "pythonw.exe")

    candidates = []
    try:
        if sys.platform == "win32":
            buf = ctypes.create_unicode_buffer(32768)
            ctypes.windll.kernel32.GetModuleFileNameW(None, buf, 32768)
            candidates.append(buf.value)
        else:
            candidates.append(os.path.realpath("/proc/self/exe"))
    except Exception:
        pass
    candidates.append(os.environ.get("NUITKA_ONEFILE_BINARY", ""))
    candidates.append(sys.argv[0] if sys.argv else "")
    try:
        candidates.append(os.path.join(__compiled__.containing_dir, "ALMP.exe"))
    except Exception:
        pass
    candidates.append(sys.executable)

    for c in candidates:
        try:
            c = os.path.abspath(c) if c else c
            if _ok(c):
                if sys.platform == "win32":
                    out = ctypes.create_unicode_buffer(32768)
                    if ctypes.windll.kernel32.GetLongPathNameW(c, out, 32768):
                        c = out.value
                return os.path.normpath(c)
        except Exception:
            continue
    return None

APP_EXE_PATH = _resolve_app_exe_path()

# --- Inject Local MPV DLL Dependency (Windows) ---
try:
    runtime_dir = get_resource_path("runtime")
    if os.path.exists(runtime_dir):
        os.environ["PATH"] = runtime_dir + os.pathsep + os.environ["PATH"]
except Exception:
    pass

from PyQt6.QtCore import Qt, QSize, QPoint, QPointF, QRectF, QObject, pyqtSignal, QThread, QTimer, QEvent, QLockFile, QStandardPaths
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtGui import QCursor, QColor, QPainter, QPen, QPolygonF, QFontMetrics, QIcon, QPixmap, QImage, QShortcut, QKeySequence
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QListWidget, QListWidgetItem, QFileDialog, QLabel,
    QCheckBox, QMessageBox, QSplitter, QSlider, QComboBox, QDialog,
    QGridLayout, QSizePolicy, QLineEdit, QMenu, QAbstractItemView
)

import mpv

AUDIO_EXTENSIONS = {
    ".mp3", ".flac", ".wav", ".aac", ".m4a", ".ogg", ".oga", ".opus", ".wma",
    ".aiff", ".aif", ".aifc", ".ape", ".alac", ".amr", ".awb", ".mp2", ".mp1",
    ".mpa", ".ac3", ".eac3", ".dts", ".wv", ".mka", ".mpc", ".tta", ".spx",
    ".caf", ".au", ".snd", ".m4r", ".m4b", ".weba", ".ra", ".dsf", ".dff",
}
VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".mpeg", ".mpg", ".mpe",
    ".m4v", ".3gp", ".3g2", ".ts", ".m2ts", ".mts", ".m2t", ".tp", ".trp",
    ".vob", ".ogv", ".ogm", ".flv", ".f4v", ".rm", ".rmvb", ".asf", ".divx",
    ".xvid", ".dv", ".mxf", ".qt", ".wtv", ".dvr-ms", ".amv", ".nsv", ".ivf",
}
SUPPORTED_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
PLAYLIST_EXTENSIONS = {".m3u", ".m3u8", ".pls"}
IPC_NAME = "ALMP-OpenFile-IPC"

def read_playlist_file(path):
    out = []
    base = os.path.dirname(path)
    is_pls = path.lower().endswith(".pls")
    try:
        with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if is_pls:
                    if not line.lower().startswith("file"):
                        continue
                    line = line.split("=", 1)[-1].strip()
                entry = line if os.path.isabs(line) else os.path.join(base, line)
                entry = os.path.normpath(entry)
                if os.path.isfile(entry) and Path(entry).suffix.lower() in SUPPORTED_EXTENSIONS:
                    out.append(entry)
    except Exception:
        pass
    return out

APP_NAME = "AlexbedLightMediaPlayer"
REGISTRY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
LINUX_AUTOSTART_DIR = Path.home() / ".config" / "autostart"
LINUX_DESKTOP_FILE = LINUX_AUTOSTART_DIR / "almp.desktop"
WIN_STARTUP_DIR = Path(os.getenv('APPDATA') or Path.home()) / r"Microsoft\Windows\Start Menu\Programs\Startup"
WIN_SHORTCUT = WIN_STARTUP_DIR / "ALMP.lnk"
STARTUP_MARKER = Path(os.getenv("APPDATA") or Path.home()) / "ALMP" / "startup_target.txt"

SETTINGS_PATH = Path(os.getenv("APPDATA") or (Path.home() / ".config")) / "ALMP" / "settings.json"
RESUME_PATH = Path(os.getenv("APPDATA") or (Path.home() / ".config")) / "ALMP" / "resume.json"
SCALE_CHOICES = [("Normal (100%)", 1.0), ("Large (125%)", 1.25), ("Extra large (150%)", 1.5), ("Huge (200%)", 2.0)]

def load_settings():
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_settings(data):
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass

def load_resume():
    try:
        return json.loads(RESUME_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_resume(data):
    try:
        RESUME_PATH.parent.mkdir(parents=True, exist_ok=True)
        RESUME_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass

# --- Crisp vector icons ---
_ICON_CACHE = {}

def make_icon(kind, color="#e6e6e6", px=20):
    key = (kind, color, px)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]
    from PyQt6.QtGui import QPixmap
    dpr = 1.0
    try:
        dpr = float(QApplication.primaryScreen().devicePixelRatio())
    except Exception:
        pass
    big = 96
    pm = QPixmap(big, big)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    u = big / 24.0
    col = QColor(color)
    pen = QPen(col)
    pen.setWidthF(2.2 * u)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

    def pt(x, y):
        return QPointF(x * u, y * u)

    def poly(points):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawPolygon(QPolygonF([pt(x, y) for x, y in points]))

    def line(*points):
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for a, b in zip(points, points[1:]):
            p.drawLine(pt(*a), pt(*b))

    def bar(x, y, w, h):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawRoundedRect(QRectF(x * u, y * u, w * u, h * u), 1.2 * u, 1.2 * u)

    if kind == "play":
        poly([(7, 4.5), (20, 12), (7, 19.5)])
    elif kind == "pause":
        bar(6.5, 4.5, 4, 15); bar(13.5, 4.5, 4, 15)
    elif kind == "prev":
        poly([(19, 5), (9, 12), (19, 19)]); bar(4.5, 5, 3, 14)
    elif kind == "next":
        poly([(5, 5), (15, 12), (5, 19)]); bar(16.5, 5, 3, 14)
    elif kind == "fullscreen":
        line((4, 9), (4, 4), (9, 4)); line((15, 4), (20, 4), (20, 9))
        line((4, 15), (4, 20), (9, 20)); line((20, 15), (20, 20), (15, 20))
    elif kind == "exitfullscreen":
        line((9, 4), (9, 9), (4, 9)); line((15, 4), (15, 9), (20, 9))
        line((4, 15), (9, 15), (9, 20)); line((20, 15), (15, 15), (15, 20))
    elif kind == "close":
        line((6, 6), (18, 18)); line((18, 6), (6, 18))
    elif kind == "playlist":
        line((4, 6), (20, 6)); line((4, 12), (20, 12)); line((4, 18), (13, 18))
    elif kind == "search":
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(4 * u, 4 * u, 12 * u, 12 * u)); line((14.5, 14.5), (20, 20))
    elif kind == "volume":
        poly([(3.5, 9), (8, 9), (13, 4.8), (13, 19.2), (8, 15), (3.5, 15)])
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(10 * u, 7.5 * u, 9 * u, 9 * u), -50 * 16, 100 * 16)
    elif kind == "settings":
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(9 * u, 9 * u, 6 * u, 6 * u))
        for i in range(8):
            angle = i * 45
            p.save()
            p.translate(12 * u, 12 * u)
            p.rotate(angle)
            p.drawLine(pt(0, -7), pt(0, -10))
            p.restore()
    p.end()

    pm = pm.scaled(int(px * dpr), int(px * dpr), Qt.AspectRatioMode.KeepAspectRatio,
                   Qt.TransformationMode.SmoothTransformation)
    pm.setDevicePixelRatio(dpr)
    icon = QIcon(pm)
    _ICON_CACHE[key] = icon
    return icon

class FullscreenTitlePill(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowTransparentForInput | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._text = ""

    def setText(self, text):
        self._text = text
        self.update()

    def text(self):
        return self._text

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = rect.height() / 2.0
        painter.setPen(QPen(QColor(255, 255, 255, 45), 1))
        painter.setBrush(QColor(18, 18, 18, 225))
        painter.drawRoundedRect(rect, radius, radius)
        font = self.font()
        font.setPixelSize(18)
        painter.setFont(font)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._text)
        painter.end()

class PlayerEventBridge(QObject):
    end_file = pyqtSignal(str)

def get_mpv_end_reason(event):
    reason = None
    try:
        data = getattr(event, "data", None)
        if isinstance(data, dict):
            reason = data.get("reason")
        elif data is not None:
            reason = getattr(data, "reason", None)
        if reason is None:
            reason = getattr(event, "reason", None)
        if reason is None:
            return "UNKNOWN"

        enum_name = getattr(reason, "name", None)
        if enum_name:
            return str(enum_name).upper()

        enum_value = getattr(reason, "value", reason)
        try:
            numeric_reason = int(enum_value)
            reason_map = {0: "EOF", 2: "STOP", 3: "QUIT", 4: "ERROR", 5: "REDIRECT"}
            return reason_map.get(numeric_reason, f"UNKNOWN_{numeric_reason}")
        except (TypeError, ValueError):
            pass

        reason_text = str(enum_value).upper()
        if "EOF" in reason_text: return "EOF"
        if "STOP" in reason_text: return "STOP"
        if "QUIT" in reason_text: return "QUIT"
        if "ERROR" in reason_text: return "ERROR"
        if "REDIRECT" in reason_text: return "REDIRECT"
        return reason_text
    except Exception as exc:
        print(f"[mpv] Could not extract end-file reason: {exc}")
        return "UNKNOWN"

class CustomConfirmDialog(QDialog):
    def __init__(self, parent, title, message):
        super().__init__(parent)
        self.setWindowTitle(title)
        if sys.platform == "win32":
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumWidth(500)
        
        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetMinimumSize)
        lbl = QLabel(message)
        lbl.setWordWrap(True)
        lbl.setMinimumWidth(460)
        lbl.setStyleSheet("font-size: 14px; padding: 10px;")
        layout.addWidget(lbl)
        
        btn_layout = QHBoxLayout()
        self.btn_yes = QPushButton("Yes")
        self.btn_no = QPushButton("No")
        self.btn_yes.setStyleSheet("font-size: 16px; padding: 8px 24px;")
        self.btn_no.setStyleSheet("font-size: 16px; padding: 8px 24px;")
        
        self.btn_yes.clicked.connect(self.accept)
        self.btn_no.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_yes)
        btn_layout.addWidget(self.btn_no)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        self.btn_no.setFocus()

    def showEvent(self, event):
        super().showEvent(event)
        if sys.platform == "win32":
            try:
                ctypes.windll.user32.SetForegroundWindow(int(self.winId()))
            except Exception:
                pass

class FolderScanner(QThread):
    files_found = pyqtSignal(list)
    scan_error = pyqtSignal(str)

    def __init__(self, targets):
        super().__init__()
        self.targets = targets

    def run(self):
        try:
            found = []
            for target in self.targets:
                if os.path.isdir(target):
                    for root, dirs, files in os.walk(target):
                        dirs[:] = [
                            d for d in dirs
                            if not d.startswith("$") and d.lower() not in {"system volume information", "$recycle.bin"}
                        ]
                        for filename in files:
                            ext = Path(filename).suffix.lower()
                            if ext in SUPPORTED_EXTENSIONS:
                                found.append(os.path.join(root, filename))
                elif os.path.isfile(target):
                    ext = Path(target).suffix.lower()
                    if ext in SUPPORTED_EXTENSIONS:
                        found.append(target)
                    elif ext in PLAYLIST_EXTENSIONS:
                        found.extend(read_playlist_file(target))
            found.sort(key=lambda path: path.casefold())
            self.files_found.emit(found)
        except Exception as exc:
            self.scan_error.emit(str(exc))

class MediaWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Alexbed Light Media Player")
        
        settings = load_settings()
        geom = settings.get("window_geometry", [1200, 700])
        self.resize(geom[0], geom[1])

        icon_file_path = get_app_icon_path()
        if icon_file_path:
            self.setWindowIcon(QIcon(icon_file_path))

        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.files = []
        self.current_path = None
        self.current_index = -1
        self.shuffle_enabled = True 
        self.scanner = None
        self._closing = False
        self.player = None
        self._is_scrubbing = False
        self._pre_mute_volume = 100
        self._is_cursor_hidden = False
        self._dialog_active = False 
        self._is_fullscreen = False 
        self._end_event_pending = False
        self._ext_queue = []
        self._last_ext_time = 0.0
        self.ipc_server = None
        self.resume_data = load_resume()

        self.track_timer = QTimer(self)
        self.track_timer.setInterval(250)
        self.track_timer.timeout.connect(self._poll_player_metrics)

        self.hide_timer = QTimer(self)
        self.hide_timer.setInterval(3000) 
        self.hide_timer.timeout.connect(self._hide_fullscreen_overlays)

        self._build_ui()
        self._setup_shortcuts()
        self._init_player()
        self._apply_settings()

        self.installEventFilter(self)
        QTimer.singleShot(100, self._force_focus)

    def start_ipc_server(self):
        self.ipc_server = QLocalServer(self)
        QLocalServer.removeServer(IPC_NAME)
        if self.ipc_server.listen(IPC_NAME):
            self.ipc_server.newConnection.connect(self._on_ipc_connection)

    def _on_ipc_connection(self):
        sock = self.ipc_server.nextPendingConnection()
        if sock is None:
            return
        buf = bytearray()
        sock.readyRead.connect(lambda: buf.extend(bytes(sock.readAll())))
        def done():
            buf.extend(bytes(sock.readAll()))
            paths = [x for x in buf.decode("utf-8", "ignore").split("\n") if x.strip()]
            self.open_external(paths)
            sock.deleteLater()
        sock.disconnected.connect(done)

    def open_external(self, paths):
        if not paths:
            self._bring_to_front()
            return
        self._ext_queue.extend(paths)
        QTimer.singleShot(250, self._drain_external)

    def _drain_external(self):
        if not self._ext_queue:
            return
        if self.scanner is not None and self.scanner.isRunning():
            QTimer.singleShot(200, self._drain_external)
            return
        paths, self._ext_queue = self._ext_queue, []
        now = time.monotonic()
        if now - self._last_ext_time > 3.0:
            self.clear_playlist()
        self._last_ext_time = now
        self.scan_targets(paths)
        self._bring_to_front()

    def _bring_to_front(self):
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def _setup_shortcuts(self):
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, activated=self.play_or_resume)
        QShortcut(QKeySequence(Qt.Key.Key_F), self, activated=self._toggle_fullscreen)
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, activated=lambda: self.player.seek(5, reference="relative") if self.player else None)
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, activated=lambda: self.player.seek(-5, reference="relative") if self.player else None)
        QShortcut(QKeySequence(Qt.Key.Key_Up), self, activated=lambda: self.volume_slider.setValue(self.volume_slider.value() + 5))
        QShortcut(QKeySequence(Qt.Key.Key_Down), self, activated=lambda: self.volume_slider.setValue(self.volume_slider.value() - 5))
        QShortcut(QKeySequence(Qt.Key.Key_PageUp), self, activated=self.previous_track)
        QShortcut(QKeySequence(Qt.Key.Key_PageDown), self, activated=self.next_track)
        QShortcut(QKeySequence(Qt.Key.Key_M), self, activated=self._toggle_mute)
        QShortcut(QKeySequence(Qt.Key.Key_A), self, activated=self._cycle_aspect)
        QShortcut(QKeySequence(Qt.Key.Key_P), self, activated=self._toggle_fs_playlist)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self._focus_search)
        QShortcut(QKeySequence(Qt.Key.Key_S), self, activated=self.take_snapshot)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=lambda: self._toggle_fullscreen() if self._is_fullscreen else None)
        
        QShortcut(QKeySequence(Qt.Key.Key_MediaPlay), self, activated=self.play_or_resume)
        QShortcut(QKeySequence(Qt.Key.Key_MediaPause), self, activated=self.play_or_resume)
        QShortcut(QKeySequence(Qt.Key.Key_MediaTogglePlayPause), self, activated=self.play_or_resume)
        QShortcut(QKeySequence(Qt.Key.Key_MediaNext), self, activated=self.next_track)
        QShortcut(QKeySequence(Qt.Key.Key_MediaPrevious), self, activated=self.previous_track)

    def _cycle_aspect(self):
        if not self.player:
            return
        self._aspect_mode = (getattr(self, "_aspect_mode", 0) + 1) % 3
        try:
            if self._aspect_mode == 0:
                self.player.panscan = 0.0
                self.player.keepaspect = True
                name = "Fit"
            elif self._aspect_mode == 1:
                self.player.keepaspect = True
                self.player.panscan = 1.0
                name = "Fill (cropped)"
            else:
                self.player.panscan = 0.0
                self.player.keepaspect = False
                name = "Stretch"
            self.status_label.setText(f"Video size: {name}   (press A to change)")
        except Exception:
            pass

    def _set_fs_title(self, name):
        self._fs_title_full = name
        self._fs_title_key = None
        self._layout_fs_title()

    def _drawer_width(self):
        if self.right_panel.parent() is self and self.right_panel.isVisible():
            return int(min(560, max(400, self.width() * 0.28)))
        return 0

    def _layout_fs_title(self):
        name = getattr(self, "_fs_title_full", "")
        area_w = max(300, self.width() - self._drawer_width())
        key = (name, area_w, self.width())
        if key == getattr(self, "_fs_title_key", None):
            return
        self._fs_title_key = key
        f = self.fullscreen_title_label.font()
        f.setPixelSize(18)
        fm = QFontMetrics(f)
        pad = 52
        avail = area_w - 140
        text = fm.elidedText(name, Qt.TextElideMode.ElideMiddle, max(120, avail - pad))
        w = int(min(avail, fm.horizontalAdvance(text) + pad))
        self.fullscreen_title_label.setText(text)
        origin = self.mapToGlobal(QPoint(0, 0))
        self.fullscreen_title_label.setGeometry(origin.x() + int((area_w - w) / 2), origin.y() + 28, w, 44)

    def _toggle_mute(self):
        if self.player:
            if self.volume_slider.value() > 0:
                self._pre_mute_volume = self.volume_slider.value()
                self.volume_slider.setValue(0)
            else:
                self.volume_slider.setValue(self._pre_mute_volume)

    def _force_focus(self):
        if self._dialog_active:
            return
        self.activateWindow()
        self.raise_()
        self.setFocus()

    def _hide_cursor(self):
        if not self._is_cursor_hidden:
            QApplication.setOverrideCursor(Qt.CursorShape.BlankCursor)
            self._is_cursor_hidden = True

    def _show_cursor(self):
        if self._is_cursor_hidden:
            QApplication.restoreOverrideCursor()
            self._is_cursor_hidden = False

    def eventFilter(self, obj, event):
        if obj == self and event.type() == QEvent.Type.ActivationChange:
            if self.isActiveWindow() and not self._dialog_active:
                self._force_focus()
        
        if obj == self.video:
            if event.type() == QEvent.Type.MouseButtonDblClick:
                self._toggle_fullscreen()
                return True
            # RIGHT CLICK DISABLED TO PREVENT CRASH
            # elif event.type() == QEvent.Type.MouseButtonPress:
            #     if event.button() == Qt.MouseButton.RightButton:
            #         self.show_context_menu(event.globalPos())
            #         return True
            elif event.type() == QEvent.Type.MouseMove and self._is_fullscreen:
                self._on_fs_activity()
            elif event.type() == QEvent.Type.Wheel:
                delta = event.angleDelta().y()
                if delta > 0:
                    self.volume_slider.setValue(self.volume_slider.value() + 5)
                elif delta < 0:
                    self.volume_slider.setValue(self.volume_slider.value() - 5)
                return True
        return super().eventFilter(obj, event)

    def show_context_menu(self, pos):
        if not self.player or self.player.idle_active:
            return
        
        try:
            self.active_menu = QMenu(self)
            menu = self.active_menu
            
            audio_tracks = []
            sub_tracks = []
            try:
                tracks = self.player.track_list
                if tracks:
                    for track in tracks:
                        if track.type == "audio":
                            audio_tracks.append(track)
                        elif track.type == "sub":
                            sub_tracks.append(track)
            except Exception:
                pass
                
            if audio_tracks:
                audio_menu = menu.addMenu("Audio Tracks")
                for t in audio_tracks:
                    title = getattr(t, "title", "") or getattr(t, "lang", "") or f"Track {t.id}"
                    action = audio_menu.addAction(f"{'✓ ' if getattr(t, 'selected', False) else ''}{title}")
                    action.triggered.connect(lambda checked=False, tid=t.id: self._safe_set_mpv_prop('aid', tid))
                    
            if sub_tracks:
                sub_menu = menu.addMenu("Subtitles")
                action = sub_menu.addAction(f"{'✓ ' if getattr(self.player, 'sid', 'no') == 'no' else ''}Disable")
                action.triggered.connect(lambda: self._safe_set_mpv_prop('sid', 'no'))
                for t in sub_tracks:
                    title = getattr(t, "title", "") or getattr(t, "lang", "") or f"Track {t.id}"
                    action = sub_menu.addAction(f"{'✓ ' if getattr(t, 'selected', False) else ''}{title}")
                    action.triggered.connect(lambda checked=False, tid=t.id: self._safe_set_mpv_prop('sid', tid))
                    
            menu.addSeparator()
            menu.addAction("Load Subtitle File...", self.load_external_subtitle)
            menu.addAction("Take Snapshot (S)", self.take_snapshot)
            menu.addSeparator()
            
            aspect_menu = menu.addMenu("Video Size")
            aspect_menu.addAction("Fit (Original)", lambda: self._set_specific_aspect(0))
            aspect_menu.addAction("Fill (Cropped)", lambda: self._set_specific_aspect(1))
            aspect_menu.addAction("Stretch", lambda: self._set_specific_aspect(2))
            
            menu.addAction("Fullscreen (F)", self._toggle_fullscreen)
            
            menu.popup(pos)
        except Exception as e:
            print(f"Error showing context menu: {e}")
            self.status_label.setText("Right-click menu failed. Please use the Settings button on the bottom bar.")

    def _safe_set_mpv_prop(self, prop, value):
        if self.player:
            try:
                setattr(self.player, prop, value)
            except Exception as e:
                print(f"Failed to set {prop} to {value}: {e}")

    def _set_specific_aspect(self, mode):
        if not self.player:
            return
        self._aspect_mode = mode
        try:
            if mode == 0:
                self.player.panscan = 0.0
                self.player.keepaspect = True
                name = "Fit"
            elif mode == 1:
                self.player.keepaspect = True
                self.player.panscan = 1.0
                name = "Fill (cropped)"
            else:
                self.player.panscan = 0.0
                self.player.keepaspect = False
                name = "Stretch"
            self.status_label.setText(f"Video size: {name}")
        except Exception:
            pass

    def load_external_subtitle(self):
        if not self.player or self.player.idle_active:
            return
        fname, _ = QFileDialog.getOpenFileName(self, "Load Subtitle", "", "Subtitles (*.srt *.ass *.vtt *.ssa)")
        if fname:
            try:
                self.player.sub_add(fname)
                self.status_label.setText(f"Subtitle loaded: {Path(fname).name}")
            except Exception as e:
                QMessageBox.warning(self, "Subtitle Error", f"Could not load subtitle:\n{e}")

    def take_snapshot(self):
        if not self.player or self.player.idle_active or not self.current_path:
            return
        try:
            pictures_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)
            base_name = Path(self.current_path).stem
            timestamp = int(time.time())
            out_path = os.path.join(pictures_dir, f"{base_name}_snapshot_{timestamp}.png")
            self.player.screenshot_to_file(out_path)
            self.status_label.setText(f"Snapshot saved to Pictures: {Path(out_path).name}")
        except Exception as e:
            self.status_label.setText(f"Snapshot failed: {e}")

    def _build_ui(self):
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_layout.addWidget(self.splitter)

        self.left_panel = QWidget()
        self.left_panel.setObjectName("leftPanel")
        self.left_layout = QVBoxLayout(self.left_panel)
        self.left_layout.setContentsMargins(0, 0, 0, 0)
        self.left_layout.setSpacing(0)

        self.video = QWidget()
        self.video.setObjectName("videoSurface")
        self.video.setMinimumSize(480, 270)
        self.video.setStyleSheet("background-color: black; border: none;")
        self.video.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.video.installEventFilter(self)
        self.left_layout.addWidget(self.video, stretch=1)

        self.audio_art_label = QLabel(self.video)
        self.audio_art_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.audio_art_label.setStyleSheet("background-color: transparent;")
        self.audio_art_label.hide()

        self.control_panel_widget = QWidget()
        self.control_panel_widget.setObjectName("controlBar")
        self.control_panel_layout = QVBoxLayout(self.control_panel_widget)
        self.control_panel_layout.setContentsMargins(12, 8, 12, 10)
        self.control_panel_layout.setSpacing(6)

        self.progress_slider = QSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setRange(0, 0)
        self.progress_slider.sliderMoved.connect(self.slider_user_scrubbed)
        self.progress_slider.sliderPressed.connect(self._start_scrubbing)
        self.progress_slider.sliderReleased.connect(self._stop_scrubbing)
        self.control_panel_layout.addWidget(self.progress_slider)

        self.status_label = QLabel("Drag & Drop folders/videos here or choose an action.")
        self.status_label.setStyleSheet("font-size: 13px; font-weight: 600; color: #cfd8dc;")
        self.status_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setStyleSheet("font-size: 12px; color: #9aa4a8;")
        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.addWidget(self.status_label, stretch=1)
        status_row.addWidget(self.time_label)
        self.control_panel_layout.addLayout(status_row)

        self.controls_widget = QWidget()
        controls_layout = QHBoxLayout(self.controls_widget)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)

        control_btn_style = "font-size: 15px; padding: 9px 16px; font-weight: 600;"
        ICON_SZ = QSize(18, 18)

        volume_box = QWidget()
        volume_box.setFixedWidth(200)
        volume_row = QHBoxLayout(volume_box)
        volume_row.setContentsMargins(0, 0, 0, 0)
        volume_row.setSpacing(8)
        self.volume_label = QLabel()
        self.volume_label.setPixmap(make_icon("volume", "#9aa4a8", 18).pixmap(18, 18))
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)
        self.volume_slider.valueChanged.connect(self.change_volume)
        self.volume_value_label = QLabel("100%")
        self.volume_value_label.setFixedWidth(40)
        self.volume_value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.volume_value_label.setStyleSheet("color: #9aa4a8; font-size: 12px;")
        volume_row.addWidget(self.volume_label)
        volume_row.addWidget(self.volume_slider, stretch=1)
        volume_row.addWidget(self.volume_value_label)
        controls_layout.addWidget(volume_box)
        controls_layout.addStretch(1)

        self.previous_button = QPushButton("Prev")
        self.previous_button.setIcon(make_icon("prev", "#e6e6e6", 18))
        self.previous_button.setIconSize(ICON_SZ)
        self.previous_button.setStyleSheet(control_btn_style)
        self.previous_button.clicked.connect(self.previous_track)
        self.previous_button.setFixedWidth(112)
        controls_layout.addWidget(self.previous_button)

        self.play_button = QPushButton("Play")
        self.play_button.setObjectName("playButton")
        self.play_button.setIconSize(ICON_SZ)
        self.play_button.setStyleSheet(control_btn_style)
        self.play_button.clicked.connect(self.play_or_resume)
        self.play_button.setFixedWidth(150)
        controls_layout.addWidget(self.play_button)
        self._set_play_ui(False)

        self.next_button = QPushButton("Next")
        self.next_button.setIcon(make_icon("next", "#e6e6e6", 18))
        self.next_button.setIconSize(ICON_SZ)
        self.next_button.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.next_button.setStyleSheet(control_btn_style)
        self.next_button.clicked.connect(self.next_track)
        self.next_button.setFixedWidth(112)
        controls_layout.addWidget(self.next_button)

        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["0.5x", "1.0x", "1.5x", "2.0x"])
        self.speed_combo.setCurrentText("1.0x")
        self.speed_combo.currentTextChanged.connect(self.change_speed)
        self.speed_combo.setStyleSheet("font-size: 14px; padding: 4px;")
        self.speed_combo.setFixedWidth(84)
        controls_layout.addWidget(self.speed_combo)

        self.tracks_button = QPushButton()
        self.tracks_button.setIcon(make_icon("settings", "#e6e6e6", 18))
        self.tracks_button.setIconSize(ICON_SZ)
        self.tracks_button.setFixedSize(42, 38)
        self.tracks_button.setToolTip("Audio / Subtitle Tracks")
        self.tracks_button.clicked.connect(lambda: self.show_context_menu(self.tracks_button.mapToGlobal(QPoint(0, self.tracks_button.height()))))
        controls_layout.addWidget(self.tracks_button)
        
        controls_layout.addStretch(1)

        right_box = QWidget()
        right_box.setFixedWidth(200)
        right_row = QHBoxLayout(right_box)
        right_row.setContentsMargins(0, 0, 0, 0)
        right_row.setSpacing(8)
        right_row.addStretch(1)
        self.playlist_toggle_button = QPushButton()
        self.playlist_toggle_button.setIcon(make_icon("playlist", "#e6e6e6", 18))
        self.playlist_toggle_button.setIconSize(ICON_SZ)
        self.playlist_toggle_button.setFixedSize(42, 38)
        self.playlist_toggle_button.setToolTip("Show / hide playlist  (P)")
        self.playlist_toggle_button.clicked.connect(self._toggle_fs_playlist)
        self.playlist_toggle_button.hide()
        right_row.addWidget(self.playlist_toggle_button)
        
        self.fullscreen_button = QPushButton()
        self.fullscreen_button.setIconSize(ICON_SZ)
        self.fullscreen_button.setFixedSize(42, 38)
        self.fullscreen_button.clicked.connect(self._toggle_fullscreen)
        right_row.addWidget(self.fullscreen_button)
        
        self.fs_close_button = QPushButton()
        self.fs_close_button.setObjectName("closeButton")
        self.fs_close_button.setIcon(make_icon("close", "#e6e6e6", 18))
        self.fs_close_button.setIconSize(ICON_SZ)
        self.fs_close_button.setFixedSize(42, 38)
        self.fs_close_button.setToolTip("Close ALMP")
        self.fs_close_button.clicked.connect(self.close)
        self.fs_close_button.hide()
        right_row.addWidget(self.fs_close_button)
        controls_layout.addWidget(right_box)
        self._update_fs_button()

        self.control_panel_layout.addWidget(self.controls_widget)
        self.left_layout.addWidget(self.control_panel_widget)

        self.right_panel = QWidget()
        self.right_panel.setObjectName("rightPanel")
        self.right_layout = QVBoxLayout(self.right_panel)
        self.right_layout.setContentsMargins(10, 10, 10, 10)
        self.right_layout.setSpacing(8)

        self.playlist_count_label = QLabel("0 items")
        self.playlist_count_label.setStyleSheet(
            "background-color: #1f2a2d; color: #19c8e6; border-radius: 13px; padding: 5px 14px; font-size: 14px; font-weight: 700;"
        )
        self.playlist_count_label.setMinimumWidth(96)
        self.playlist_count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        playlist_title = QLabel("Playlist")
        playlist_title.setStyleSheet("font-size: 17px; font-weight: 600; color: #f1f4f5;")
        header_row = QHBoxLayout()
        header_row.setContentsMargins(2, 0, 0, 0)
        header_row.addWidget(playlist_title)
        header_row.addStretch(1)
        header_row.addWidget(self.playlist_count_label)
        self.right_layout.addLayout(header_row)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search playlist...   (Ctrl+F)")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.addAction(make_icon("search", "#8a9499", 16), QLineEdit.ActionPosition.LeadingPosition)
        self.search_edit.textChanged.connect(self._schedule_filter)
        self.search_edit.returnPressed.connect(self._play_first_visible)
        self.right_layout.addWidget(self.search_edit)
        self._filter_q = ""
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(180)
        self._filter_timer.timeout.connect(self._apply_filter)

        self.playlist = QListWidget()
        self.playlist.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.playlist.itemDoubleClicked.connect(self.play_selected_item)
        self.playlist.setStyleSheet("QListWidget { font-size: 13px; } QListWidget::item { padding: 7px 8px; }")
        self.playlist.setUniformItemSizes(True)
        self.playlist.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.playlist.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.playlist.setWordWrap(False)
        
        self.playlist.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.playlist.model().rowsMoved.connect(self._on_playlist_reordered)
        
        self.right_layout.addWidget(self.playlist, stretch=1)

        self.options_widget_1 = QWidget()
        self.options_layout_1 = QHBoxLayout(self.options_widget_1)
        self.options_layout_1.setContentsMargins(0, 0, 0, 0)
        self.options_layout_1.setSpacing(4)

        self.open_file_button = QPushButton("Add Files")
        self.open_file_button.clicked.connect(self.choose_files)
        self.options_layout_1.addWidget(self.open_file_button)

        self.open_folder_button = QPushButton("Open Folder")
        self.open_folder_button.clicked.connect(self.choose_folder)
        self.options_layout_1.addWidget(self.open_folder_button)

        self.clear_playlist_button = QPushButton("Clear")
        self.clear_playlist_button.setToolTip("Clear the whole playlist (files are kept)")
        self.clear_playlist_button.clicked.connect(self.clear_playlist)
        self.options_layout_1.addWidget(self.clear_playlist_button)

        self.remove_from_list_button = QPushButton("Remove")
        self.remove_from_list_button.setToolTip("Remove the selected item from the list (file is kept)")
        self.remove_from_list_button.setStyleSheet("color: #ffb86b;")
        self.remove_from_list_button.clicked.connect(self.remove_from_playlist)
        self.options_layout_1.addWidget(self.remove_from_list_button)

        self.delete_file_button = QPushButton("Delete")
        self.delete_file_button.setToolTip("Permanently delete the selected file from your computer")
        self.delete_file_button.setStyleSheet("color: #ff6b6b; font-weight: bold;")
        self.delete_file_button.clicked.connect(self.delete_selected_file)
        self.options_layout_1.addWidget(self.delete_file_button)

        self.right_layout.addWidget(self.options_widget_1)

        self.options_widget_2 = QWidget()
        self.options_layout_2 = QGridLayout(self.options_widget_2)
        self.options_layout_2.setContentsMargins(2, 2, 2, 0)
        self.options_layout_2.setHorizontalSpacing(12)
        self.options_layout_2.setVerticalSpacing(8)

        self.shuffle_checkbox = QCheckBox("Shuffle")
        self.shuffle_checkbox.setChecked(True)
        self.shuffle_checkbox.toggled.connect(self.set_shuffle)
        self.options_layout_2.addWidget(self.shuffle_checkbox, 0, 0)

        self.loop_single_checkbox = QCheckBox("Loop 1")
        self.options_layout_2.addWidget(self.loop_single_checkbox, 0, 1)

        self.remove_played_checkbox = QCheckBox("Remove played")
        self.remove_played_checkbox.setChecked(True)
        self.options_layout_2.addWidget(self.remove_played_checkbox, 1, 0)

        self.startup_checkbox = QCheckBox("Run at Startup")
        self.startup_checkbox.toggled.connect(self.toggle_startup)
        self.options_layout_2.addWidget(self.startup_checkbox, 1, 1)

        size_label = QLabel("Interface size")
        size_label.setStyleSheet("color: #9aa4a8; font-size: 12px;")
        self.scale_combo = QComboBox()
        for label, _val in SCALE_CHOICES:
            self.scale_combo.addItem(label)
        _saved_scale = float(load_settings().get("ui_scale", 1.0))
        for i, (_label, val) in enumerate(SCALE_CHOICES):
            if abs(val - _saved_scale) < 0.01:
                self.scale_combo.setCurrentIndex(i)
        self.scale_combo.currentIndexChanged.connect(self._on_scale_changed)
        size_row = QHBoxLayout()
        size_row.setContentsMargins(0, 0, 0, 0)
        size_row.addWidget(size_label)
        size_row.addWidget(self.scale_combo, stretch=1)
        self.options_layout_2.addLayout(size_row, 2, 0, 1, 2)

        self.right_layout.addWidget(self.options_widget_2)

        self.splitter.addWidget(self.left_panel)
        self.splitter.addWidget(self.right_panel)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([800, 400])

        self.setMouseTracking(True)
        self.video.setMouseTracking(True)

        self.fullscreen_title_label = FullscreenTitlePill(self)
        self.fullscreen_title_label.hide()
        self.fullscreen_title_label.raise_()

        self.check_startup_state()

    def _init_player(self):
        try:
            self.player_events = PlayerEventBridge(self)
            self.player_events.end_file.connect(self._handle_end_file)

            mpv_opts = dict(
                wid=str(int(self.video.winId())),
                osc=False,
                input_default_bindings=False,
                input_vo_keyboard=False,
                keep_open="no",
                idle="yes",
                hwdec="auto",
                cursor_autohide="no",
            )
            if sys.platform.startswith("linux"):
                forced_vo = os.environ.get("ALMP_VO")
                if forced_vo:
                    mpv_opts["vo"] = forced_vo
                else:
                    try:
                        in_wsl = "microsoft" in open("/proc/version").read().lower()
                    except Exception:
                        in_wsl = False
                    if in_wsl:
                        mpv_opts["vo"] = "x11"
                        mpv_opts["hwdec"] = "no"
                        mpv_opts["profile"] = "fast"
                        mpv_opts["vd_lavc_fast"] = True
            self.player = mpv.MPV(**mpv_opts)
            self.player.volume = self.volume_slider.value()

            @self.player.event_callback("end-file")
            def handle_end_file(event):
                reason = get_mpv_end_reason(event)
                self.player_events.end_file.emit(reason)

            self.status_label.setText("Media player engine ready.")
        except Exception as e:
            self.status_label.setText(f"Media Player Initialization Error: {e}")

    def _on_playlist_reordered(self, parent, start, end, destination, row):
        new_files = []
        for i in range(self.playlist.count()):
            new_files.append(self.playlist.item(i).data(Qt.ItemDataRole.UserRole))
        
        self.files = new_files
        
        if self.current_path in self.files:
            self.current_index = self.files.index(self.current_path)
        else:
            self.current_index = -1

    def _update_playlist_count(self, visible=None):
        total = len(self.files)
        if not getattr(self, "_filter_q", ""):
            self.playlist_count_label.setText(f"{total:,} item" + ("" if total == 1 else "s"))
            return
        if visible is None:
            visible = sum(1 for i in range(self.playlist.count()) if not self.playlist.item(i).isHidden())
        self.playlist_count_label.setText(f"{visible:,} of {total:,}")

    def _schedule_filter(self, _text=None):
        self._filter_timer.start()

    def _apply_filter(self):
        q = self.search_edit.text().strip().casefold()
        self._filter_q = q
        visible = 0
        self.playlist.setUpdatesEnabled(False)
        for i in range(self.playlist.count()):
            item = self.playlist.item(i)
            hide = bool(q) and q not in item.text().casefold()
            item.setHidden(hide)
            if not hide:
                visible += 1
        self.playlist.setUpdatesEnabled(True)
        self._update_playlist_count(visible)

    def _play_first_visible(self):
        for i in range(self.playlist.count()):
            item = self.playlist.item(i)
            if not item.isHidden():
                self.play_selected_item(item)
                self.video.setFocus()
                return

    def _focus_search(self):
        if self._is_fullscreen:
            return
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    def _on_scale_changed(self, index):
        if 0 <= index < len(SCALE_CHOICES):
            data = load_settings()
            data["ui_scale"] = SCALE_CHOICES[index][1]
            save_settings(data)
            self.status_label.setText("Interface size saved - close and reopen ALMP to apply it.")

    def _save_settings(self):
        data = load_settings()
        data.update({
            "volume": self.volume_slider.value(),
            "shuffle": self.shuffle_checkbox.isChecked(),
            "loop_single": self.loop_single_checkbox.isChecked(),
            "remove_played": self.remove_played_checkbox.isChecked(),
            "window_geometry": [self.width(), self.height()]
        })
        save_settings(data)

    def _apply_settings(self):
        data = load_settings()
        try:
            self.volume_slider.setValue(int(data.get("volume", 100)))
            self.shuffle_checkbox.setChecked(bool(data.get("shuffle", True)))
            self.loop_single_checkbox.setChecked(bool(data.get("loop_single", False)))
            self.remove_played_checkbox.setChecked(bool(data.get("remove_played", True)))
        except Exception:
            pass

    def resizeEvent(self, event):
        QTimer.singleShot(0, self._layout_fs_title)
        QTimer.singleShot(0, self._layout_overlay)
        self.audio_art_label.resize(self.video.width(), self.video.height())
        super().resizeEvent(event)

    def check_startup_state(self):
        if sys.platform == "win32":
            if WIN_SHORTCUT.exists():
                self.startup_checkbox.blockSignals(True)
                self.startup_checkbox.setChecked(True)
                self.startup_checkbox.blockSignals(False)
                if self._is_compiled() and APP_EXE_PATH:
                    threading.Thread(target=self._repair_startup_shortcut, daemon=True).start()
            else:
                self.startup_checkbox.setChecked(False)
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_PATH, 0, winreg.KEY_SET_VALUE)
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
                winreg.CloseKey(key)
            except Exception:
                pass
        else:
            if LINUX_DESKTOP_FILE.exists():
                try:
                    with open(LINUX_DESKTOP_FILE, "r") as f:
                        content = f.read()
                        if sys.executable in content:
                            self.startup_checkbox.setChecked(True)
                        else:
                            self.startup_checkbox.setChecked(False)
                except Exception:
                    self.startup_checkbox.setChecked(False)
            else:
                self.startup_checkbox.setChecked(False)

    @staticmethod
    def _is_compiled():
        return hasattr(sys, "frozen") or "__compiled__" in globals()

    @staticmethod
    def _write_startup_shortcut(exe_path):
        def q(v):
            return "'" + str(v).replace("'", "''") + "'"
        ps = (
            "$s=(New-Object -ComObject WScript.Shell).CreateShortcut(%s);"
            "$s.TargetPath=%s;$s.WorkingDirectory=%s;$s.IconLocation=%s;$s.Save()"
            % (q(WIN_SHORTCUT), q(exe_path), q(os.path.dirname(exe_path)), q(exe_path))
        )
        WIN_STARTUP_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                       capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            STARTUP_MARKER.parent.mkdir(parents=True, exist_ok=True)
            STARTUP_MARKER.write_text(os.path.normcase(exe_path), encoding="utf-8")
        except Exception:
            pass

    def _repair_startup_shortcut(self):
        try:
            if STARTUP_MARKER.exists() and \
               STARTUP_MARKER.read_text(encoding="utf-8").strip() == os.path.normcase(APP_EXE_PATH):
                return
            def q(v): return "'" + str(v).replace("'", "''") + "'"
            ps = "(New-Object -ComObject WScript.Shell).CreateShortcut(%s).TargetPath" % q(WIN_SHORTCUT)
            r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                               capture_output=True, text=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            target = os.path.normcase(os.path.normpath(r.stdout.strip())) if r.stdout.strip() else ""
            if target != os.path.normcase(APP_EXE_PATH):
                self._write_startup_shortcut(APP_EXE_PATH)
        except Exception:
            pass

    def toggle_startup(self, checked):
        is_compiled = hasattr(sys, "frozen") or "__compiled__" in globals()
        if not is_compiled:
            self.startup_checkbox.blockSignals(True)
            self.startup_checkbox.setChecked(False)
            self.startup_checkbox.blockSignals(False)
            self._dialog_active = True
            QMessageBox.warning(self, "Notice", "Run at Startup only works in the compiled .exe version.")
            self._dialog_active = False
            return

        exe_path = APP_EXE_PATH
        if not exe_path or not os.path.isfile(exe_path):
            self.startup_checkbox.blockSignals(True)
            self.startup_checkbox.setChecked(False)
            self.startup_checkbox.blockSignals(False)
            self._dialog_active = True
            QMessageBox.warning(self, "Notice", "Could not locate ALMP.exe, so Run at Startup was not changed.")
            self._dialog_active = False
            return
        
        if sys.platform == "win32":
            try:
                if checked:
                    if WIN_SHORTCUT.exists():
                        WIN_SHORTCUT.unlink()
                    self._write_startup_shortcut(exe_path)
                    self.status_label.setText("App set to run at Windows startup.")
                else:
                    if WIN_SHORTCUT.exists():
                        WIN_SHORTCUT.unlink()
                    self.status_label.setText("App removed from Windows startup.")
            except Exception as e:
                self._dialog_active = True
                QMessageBox.critical(self, "Startup Error", f"Failed to modify startup settings: {e}")
                self._dialog_active = False
                self.startup_checkbox.setChecked(not checked)
        else:
            try:
                if checked:
                    LINUX_AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
                    with open(LINUX_DESKTOP_FILE, "w") as f:
                        f.write("[Desktop Entry]\n")
                        f.write("Type=Application\n")
                        f.write(f"Name={APP_NAME}\n")
                        f.write(f'Exec="{exe_path}"\n')
                        f.write("Terminal=false\n")
                    self.status_label.setText("App set to run at Linux startup.")
                else:
                    if LINUX_DESKTOP_FILE.exists():
                        LINUX_DESKTOP_FILE.unlink()
                    self.status_label.setText("App removed from Linux startup.")
            except Exception as e:
                QMessageBox.critical(self, "Autostart Error", f"Failed to modify startup settings: {e}")
                self.startup_checkbox.setChecked(not checked)

    def _load_album_art(self, file_path):
        try:
            from mutagen import File as MutagenFile
            audio = MutagenFile(file_path)
            if audio is None:
                return None
            art_data = None
            if hasattr(audio, 'tags') and 'APIC:' in audio.tags:
                art_data = audio.tags['APIC:'].data
            elif hasattr(audio, 'pictures') and len(audio.pictures) > 0:
                art_data = audio.pictures[0].data
            elif hasattr(audio, 'tags') and 'covr' in audio.tags:
                art_data = bytes(audio.tags['covr'][0])
            if art_data:
                image = QImage.fromData(art_data)
                if not image.isNull():
                    return QPixmap.fromImage(image)
        except Exception:
            pass
        return None

    def change_volume(self):
        self.volume_value_label.setText(f"{self.volume_slider.value()}%")
        if self.player:
            self.player.volume = self.volume_slider.value()

    def change_speed(self, text):
        if self.player:
            speed = float(text.replace("x", ""))
            self.player.speed = speed

    def clear_playlist(self):
        self._pending_paths = []
        self.track_timer.stop()
        self.files.clear()
        self.current_index = -1
        self.current_path = None
        self.playlist.clear()
        self.progress_slider.setValue(0)
        self.progress_slider.setMaximum(0)
        self._set_play_ui(False)
        self.audio_art_label.hide()
        self.status_label.setText("Playlist cleared cleanly. Drag & Drop files to start again.")
        self._update_playlist_count()
        if self.player:
            try:
                self.player.stop()
            except Exception:
                pass

    def remove_from_playlist(self):
        item = self.playlist.currentItem()
        if item is None:
            self._dialog_active = True
            QMessageBox.warning(self, "Remove from List", "Please select a file to remove.")
            self._dialog_active = False
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        try:
            idx = self.files.index(path)
        except ValueError:
            return
        is_currently_playing = (idx == self.current_index)
        self.files.pop(idx)
        self.playlist.takeItem(idx)
        self._update_playlist_count()
        self.status_label.setText(f"Removed from list: {Path(path).name}")
        if is_currently_playing:
            if self.player:
                self.player.stop()
            self.current_index = -1
            self.current_path = None
            self.audio_art_label.hide()
            self._set_play_ui(False)
            self.progress_slider.setValue(0)
            self.progress_slider.setMaximum(1)
            self.track_timer.stop()
            self._end_event_pending = False
            if self.files:
                self.next_track()
        else:
            if idx < self.current_index:
                self.current_index -= 1

    def _set_mpv_pause(self, value):
        if not self.player:
            return
        try:
            if sys.platform != "win32":
                self.player.command_async("set", "pause", "yes" if value else "no")
            else:
                self.player.pause = value
        except Exception:
            try:
                self.player.pause = value
            except Exception:
                pass

    def delete_selected_file(self):
        item = self.playlist.currentItem()
        if item is None:
            self._dialog_active = True
            QMessageBox.warning(self, "Delete File", "Please select a file in the playlist to delete.")
            self._dialog_active = False
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        if not path or not os.path.exists(path):
            self.status_label.setText("File no longer exists.")
            return
        was_fullscreen = self._is_fullscreen
        was_playing = False
        if self.player:
            try:
                was_playing = not bool(self.player.pause)
                if was_playing:
                    self._set_mpv_pause(True)
            except Exception:
                pass
        self.hide_timer.stop()
        self._show_cursor()
        self.video.setMouseTracking(True)
        if was_fullscreen:
            self._is_fullscreen = False
            self._exit_fullscreen_ui()
            self.showMaximized()
            self.activateWindow()
            self.raise_()
            self.left_panel.show()
            self.right_panel.show()
            self.control_panel_widget.show()
            self.fullscreen_title_label.hide()
            QApplication.processEvents()
            available_width = self.splitter.width()
            self.splitter.setSizes([int(available_width * 0.75), int(available_width * 0.25)])
            QApplication.processEvents()
        self._dialog_active = True
        dialog = CustomConfirmDialog(
            self, "Delete File",
            f"Are you sure you want to PERMANENTLY delete this file from your computer?\n\n{Path(path).name}"
        )
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        dialog.setModal(True)
        reply = dialog.exec()
        self._dialog_active = False
        if was_fullscreen:
            self.showFullScreen()
            self._is_fullscreen = True
            self._enter_fullscreen_ui()
            QApplication.processEvents()
            self._fs_drawer_wanted = False
            self.left_panel.show()
            self.right_panel.hide()
            self.control_panel_widget.hide()
            self.fullscreen_title_label.hide()
            self._show_cursor()
            self.hide_timer.start()
            self.video.setMouseTracking(True)
            self.video.setFocus()
            QApplication.processEvents()
        if reply != QDialog.DialogCode.Accepted:
            if was_playing and self.player:
                try:
                    self._set_mpv_pause(False)
                    self._set_play_ui(True)
                except Exception:
                    pass
            return
        try:
            idx = self.files.index(path)
        except ValueError:
            self.status_label.setText("The selected file is no longer in the playlist.")
            return
        is_currently_playing = (path == self.current_path)
        if is_currently_playing and self.player:
            try:
                self.player.stop()
            except Exception:
                pass
        try:
            os.remove(path)
        except Exception as exc:
            self._dialog_active = True
            QMessageBox.critical(self, "Delete Error", f"Could not delete file:\n{exc}")
            self._dialog_active = False
            if was_playing and not is_currently_playing and self.player:
                self.player.pause = False
                self._set_play_ui(True)
            return
        self.files.pop(idx)
        self.playlist.takeItem(idx)
        self._update_playlist_count()
        self.status_label.setText(f"Permanently deleted: {Path(path).name}")
        if is_currently_playing:
            self.current_index = -1
            self.current_path = None
            self.audio_art_label.hide()
            self._set_play_ui(False)
            self.progress_slider.setValue(0)
            self.progress_slider.setMaximum(1)
            self.track_timer.stop()
            self._end_event_pending = False
            if self.files:
                self.next_track()
            else:
                self.status_label.setText("Playlist is empty.")
                if self.player:
                    try:
                        self.player.stop()
                    except Exception:
                        pass
        else:
            if idx < self.current_index:
                self.current_index -= 1
            if was_playing and self.player:
                try:
                    self.player.pause = False
                    self._set_play_ui(True)
                except Exception:
                    pass

    def _poll_player_metrics(self):
        if not self.player or self._closing:
            return
        try:
            if self._is_scrubbing:
                return
            if self.isMinimized():
                return
            current_time = getattr(self.player, "time_pos", 0) or 0
            duration = getattr(self.player, "duration", 0) or 1
            key = (int(current_time), int(duration))
            if duration > 0 and key != getattr(self, "_last_tick_key", None):
                self._last_tick_key = key
                self.progress_slider.setMaximum(int(duration))
                self.progress_slider.setValue(int(current_time))
                self.time_label.setText(f"{self._fmt_time(current_time)} / {self._fmt_time(duration)}")
                
                if current_time > 0 and int(current_time) % 5 == 0 and self.current_path:
                    self.resume_data[self.current_path] = int(current_time)
                    save_resume(self.resume_data)
        except Exception:
            pass

    @staticmethod
    def _fmt_time(seconds):
        seconds = int(max(0, seconds))
        h, rem = divmod(seconds, 3600)
        m, sec = divmod(rem, 60)
        return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"

    def slider_user_scrubbed(self):
        if self.player:
            self.player.seek(self.progress_slider.value(), reference="absolute")

    def _start_scrubbing(self):
        self._is_scrubbing = True

    def _stop_scrubbing(self):
        self._is_scrubbing = False
        self.slider_user_scrubbed()

    def mouseMoveEvent(self, event):
        if self._is_fullscreen:
            self._on_fs_activity()
        super().mouseMoveEvent(event)

    def _enter_fullscreen_ui(self):
        bar = self.control_panel_widget
        if bar.parent() is self:
            return
        self.left_layout.removeWidget(bar)
        bar.setParent(self)
        bar.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        bar.hide()
        self.right_panel.setParent(self)
        self.right_panel.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.right_panel.hide()
        self.playlist_toggle_button.show()
        self.fs_close_button.show()
        self._update_fs_button()

    def _exit_fullscreen_ui(self):
        bar = self.control_panel_widget
        if bar.parent() is not self:
            return
        self.left_layout.addWidget(bar)
        bar.show()
        self.splitter.addWidget(self.right_panel)
        self.right_panel.show()
        self.playlist_toggle_button.hide()
        self.fs_close_button.hide()
        self._update_fs_button()

    def _layout_overlay(self):
        bar = self.control_panel_widget
        if bar.parent() is not self:
            return
        W, H = self.width(), self.height()
        dw = self._drawer_width()
        h = bar.sizeHint().height()
        bar.setGeometry(0, max(0, H - h), max(300, W - dw), h)
        if dw:
            self.right_panel.setGeometry(W - dw, 0, dw, H)
            self.right_panel.raise_()
        bar.raise_()

    def _show_fs_overlays(self):
        bar = self.control_panel_widget
        if bar.parent() is not self:
            return
        wanted = getattr(self, "_fs_drawer_wanted", False)
        newly = (not bar.isVisible()) or (wanted != self.right_panel.isVisible())
        if wanted:
            self.right_panel.show()
        else:
            self.right_panel.hide()
        bar.show()
        if newly:
            self._layout_overlay()
            QTimer.singleShot(0, self._layout_fs_title)

    def _on_fs_activity(self):
        self._show_cursor()
        self._show_fs_overlays()
        if not self.fullscreen_title_label.isVisible():
            self.fullscreen_title_label.show()
            QTimer.singleShot(0, self._layout_fs_title)
        self.hide_timer.start()

    def _hide_fullscreen_overlays(self):
        if not self._is_fullscreen or self._is_scrubbing:
            return
        pos = QCursor.pos()
        for w in (self.control_panel_widget, self.right_panel):
            if w.isVisible() and w.width() > 0 and w.rect().contains(w.mapFromGlobal(pos)):
                self.hide_timer.start()
                return
        self._hide_cursor()
        if self.control_panel_widget.parent() is self:
            self.control_panel_widget.hide()
            self.right_panel.hide()
        self.fullscreen_title_label.hide()
        self.hide_timer.stop()
        self.video.setFocus()

    def _toggle_fs_playlist(self):
        if not self._is_fullscreen:
            return
        self._fs_drawer_wanted = not getattr(self, "_fs_drawer_wanted", False)
        self._fs_title_key = None
        self._on_fs_activity()
        QTimer.singleShot(0, self._layout_overlay)

    def _update_fs_button(self):
        if self._is_fullscreen:
            self.fullscreen_button.setIcon(make_icon("exitfullscreen", "#e6e6e6", 18))
            self.fullscreen_button.setToolTip("Exit fullscreen  (Esc / F)")
        else:
            self.fullscreen_button.setIcon(make_icon("fullscreen", "#e6e6e6", 18))
            self.fullscreen_button.setToolTip("Fullscreen  (F)")

    def _set_play_ui(self, playing):
        self.play_button.setText("Pause" if playing else "Play")
        self.play_button.setIcon(make_icon("pause" if playing else "play", "#04222a", 18))

    def _toggle_fullscreen(self):
        if self._is_fullscreen:
            self.showNormal()
            self._is_fullscreen = False
            self._exit_fullscreen_ui()
            if getattr(self, "_pre_fs_maximized", False):
                self.showMaximized()
            elif getattr(self, "_pre_fs_geometry", None) is not None:
                self.setGeometry(self._pre_fs_geometry)
            else:
                screen_geo = self.screen().availableGeometry()
                self.resize(1200, 700)
                self.move(screen_geo.x() + (screen_geo.width() - self.width()) // 2,
                          screen_geo.y() + (screen_geo.height() - self.height()) // 2)
            self._show_cursor()
            self.hide_timer.stop()
            self.fullscreen_title_label.hide()
            self.splitter.setSizes([800, 400])
            self.main_layout.setContentsMargins(0, 0, 0, 0)
        else:
            self._pre_fs_maximized = self.isMaximized()
            self._pre_fs_geometry = None if self.isMaximized() else self.geometry()
            self.showFullScreen()
            self._is_fullscreen = True
            self._enter_fullscreen_ui()
            self._fs_drawer_wanted = False
            if self.current_path:
                self._set_fs_title(Path(self.current_path).name)
            self.fullscreen_title_label.hide()
            self._hide_cursor()
            self.hide_timer.start()
        self._update_fs_button()
        QTimer.singleShot(0, self._layout_overlay)
        self.setFocus()
        self.video.setFocus()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.scan_targets(paths)

    def choose_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, 
            "Select Media Files", 
            "", 
            "Media Files (*.mp4 *.mkv *.avi *.mp3 *.flac *.wav *.m3u);;All Files (*)"
        )
        if files:
            self.scan_targets(files)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select media folder")
        if folder:
            self.scan_targets([folder])

    def scan_targets(self, targets):
        if self.scanner is not None and self.scanner.isRunning():
            return
        self.status_label.setText("Processing imported tracks...")
        self.open_file_button.setEnabled(False)
        self.open_folder_button.setEnabled(False)
        self.scanner = FolderScanner(targets)
        self.scanner.files_found.connect(self._on_files_found)
        self.scanner.scan_error.connect(self._on_scan_error)
        self.scanner.finished.connect(lambda: (self.open_file_button.setEnabled(True), self.open_folder_button.setEnabled(True)))
        self.scanner.start()

    def _on_files_found(self, paths):
        if not paths:
            return
        was_empty = len(self.files) == 0 and not getattr(self, "_pending_paths", [])
        self._pending_paths = list(getattr(self, "_pending_paths", [])) + list(paths)
        self._pending_started_empty = was_empty or getattr(self, "_pending_started_empty", False)
        if not getattr(self, "_chunk_running", False):
            self._chunk_running = True
            QTimer.singleShot(0, self._add_next_chunk)

    def _add_next_chunk(self):
        pending = getattr(self, "_pending_paths", [])
        if not pending:
            self._chunk_running = False
            return
        chunk, self._pending_paths = pending[:1500], pending[1500:]
        was_empty = len(self.files) == 0

        self.playlist.setUpdatesEnabled(False)
        self.files.extend(chunk)
        q = getattr(self, "_filter_q", "")
        for path in chunk:
            name = Path(path).name
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, path)
            self.playlist.addItem(item)
            if q and q not in name.casefold():
                item.setHidden(True)
        self.playlist.setUpdatesEnabled(True)
        self._update_playlist_count()

        if was_empty and self.files:
            self.play_index(0)

        if self._pending_paths:
            self.status_label.setText(f"Loading... {len(self.files):,} added, {len(self._pending_paths):,} to go")
            QTimer.singleShot(0, self._add_next_chunk)
        else:
            self._chunk_running = False
            self.status_label.setText(f"Added media. Total: {len(self.files):,} item(s).")

    def _on_scan_error(self, message):
        self.status_label.setText("Import operation failed.")
        self._dialog_active = True
        QMessageBox.critical(self, "Import error", message)
        self._dialog_active = False

    def set_shuffle(self, enabled):
        self.shuffle_enabled = enabled

    def play_selected_item(self, item=None):
        if item is None:
            item = self.playlist.currentItem()
        if item is None:
            if self.files:
                self.play_index(0)
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        try:
            index = self.files.index(path)
            self.play_index(index)
        except ValueError:
            return

    def play_index(self, index):
        if not self.files or not (0 <= index < len(self.files)):
            return

        path = self.files[index]
        self._end_event_pending = False
        self.current_index = index
        self.current_path = path

        self.playlist.setCurrentRow(index)
        
        if self._is_fullscreen:
            self._set_fs_title(Path(path).name)
            if not self.hide_timer.isActive():
                self._hide_cursor()
                self.control_panel_widget.hide()
            else:
                self.hide_timer.start()

        ext = Path(path).suffix.lower()
        if ext in AUDIO_EXTENSIONS:
            pixmap = self._load_album_art(path)
            if pixmap:
                scaled_pixmap = pixmap.scaled(
                    self.video.size(), 
                    Qt.AspectRatioMode.KeepAspectRatio, 
                    Qt.TransformationMode.SmoothTransformation
                )
                self.audio_art_label.setPixmap(scaled_pixmap)
            else:
                self.audio_art_label.clear()
                self.audio_art_label.setText("Audio Playing")
                self.audio_art_label.setStyleSheet("color: white; font-size: 24px; background-color: black;")
            
            self.audio_art_label.resize(self.video.width(), self.video.height())
            self.audio_art_label.show()
        else:
            self.audio_art_label.hide()

        if self.player:
            self.speed_combo.setCurrentText("1.0x")
            self.player.loadfile(path, mode="replace")
            
            resume_time = self.resume_data.get(path, 0)
            if resume_time > 0:
                QTimer.singleShot(500, lambda: self.player.seek(resume_time, reference="absolute"))
                
            self.player.pause = False
            self.status_label.setText(f"Playing: {Path(path).name}")
            self._set_play_ui(True)
            self.track_timer.start()

    def play_or_resume(self):
        if not self.player or not self.files:
            return

        if self.player.idle_active:
            self.play_index(self.current_index if self.current_index >= 0 else 0)
        else:
            self.player.pause = not self.player.pause
            self._set_play_ui(not self.player.pause)

    def previous_track(self):
        if not self.files:
            return
        if self.shuffle_enabled:
            if len(self.files) > 1:
                prev_idx = self.current_index
                while prev_idx == self.current_index:
                    prev_idx = random.randint(0, len(self.files) - 1)
            else:
                prev_idx = 0
            self.play_index(prev_idx)
        else:
            prev_idx = self.current_index - 1
            if prev_idx < 0:
                prev_idx = len(self.files) - 1
            self.play_index(prev_idx)

    def next_track(self):
        if not self.files:
            return
        if self.shuffle_enabled:
            if len(self.files) > 1:
                next_idx = self.current_index
                while next_idx == self.current_index:
                    next_idx = random.randint(0, len(self.files) - 1)
            else:
                next_idx = 0
            self.play_index(next_idx)
        else:
            next_idx = self.current_index + 1
            if next_idx >= len(self.files):
                next_idx = 0
            self.play_index(next_idx)

    def _handle_end_file(self, reason):
        if self._closing:
            return
        reason = str(reason).upper()
        if reason != "EOF":
            return
        if self._end_event_pending:
            return
        self._end_event_pending = True
        self.track_timer.stop()
            
        if self.loop_single_checkbox.isChecked() and self.current_index >= 0:
            self.play_index(self.current_index)
            return

        if self.current_path in self.resume_data:
            self.resume_data.pop(self.current_path, None)
            save_resume(self.resume_data)

        if self.remove_played_checkbox.isChecked():
            self._remove_current_and_advance()
        else:
            self.next_track()

    def _remove_current_and_advance(self):
        if self.current_index < 0 or self.current_index >= len(self.files):
            return
        idx_to_remove = self.current_index
        self.files.pop(idx_to_remove)
        self.playlist.takeItem(idx_to_remove)
        self._update_playlist_count()

        if not self.files:
            self.status_label.setText("Playlist finished.")
            self.current_index = -1
            self.current_path = None
            self._set_play_ui(False)
            self.progress_slider.setValue(0)
            self.progress_slider.setMaximum(1)
            self.track_timer.stop()
            self.audio_art_label.hide()
            self._end_event_pending = False
            if self.player:
                self.player.stop()
            return

        if self.shuffle_enabled:
            self.current_index = -1
            self.next_track()
        else:
            if idx_to_remove >= len(self.files):
                idx_to_remove = 0
            self.play_index(idx_to_remove)

    def closeEvent(self, event):
        try:
            self._save_settings()
        except Exception:
            pass
        self._closing = True
        self.track_timer.stop()
        self.hide_timer.stop()
        self._show_cursor()
        if self.scanner and self.scanner.isRunning():
            self.scanner.wait(1000)
        if self.player:
            try:
                self.player.terminate()
            except Exception:
                pass
        super().closeEvent(event)


if __name__ == "__main__":
    if sys.platform != "win32":
        try:
            import faulthandler
            faulthandler.enable()
        except Exception:
            pass
    temp_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation)
    lock_file = QLockFile(os.path.join(temp_dir, "ALMP.lock"))
    cli_paths = [os.path.abspath(a) for a in sys.argv[1:] if a and not a.startswith("-")]
    if not lock_file.tryLock(100):
        from PyQt6.QtCore import QCoreApplication
        _qc = QCoreApplication(sys.argv)
        sock = QLocalSocket()
        sock.connectToServer(IPC_NAME)
        if sock.waitForConnected(2000):
            sock.write("\n".join(cli_paths).encode("utf-8"))
            sock.flush()
            sock.waitForBytesWritten(2000)
            sock.disconnectFromServer()
        sys.exit(0)

    if sys.platform == "win32":
        try:
            myappid = "Alexbed.LightMediaPlayer.ALMP.7.5" 
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

    try:
        _scale = float(load_settings().get("ui_scale", 1.0))
        if 0.75 <= _scale <= 3.0 and abs(_scale - 1.0) > 0.01 and "QT_SCALE_FACTOR" not in os.environ:
            os.environ["QT_SCALE_FACTOR"] = str(_scale)
    except Exception:
        pass
    app = QApplication(sys.argv)
    if sys.platform != "win32":
        import locale
        locale.setlocale(locale.LC_NUMERIC, "C")
    print(f"[ALMP] Qt platform: {app.platformName()}")
    
    dark_stylesheet = """
        QWidget {
            color: #e6e6e6;
            font-family: "Segoe UI", "Ubuntu", "Noto Sans", sans-serif;
        }
        QMainWindow, QDialog, QMessageBox { background-color: #121212; }
        QLabel, QCheckBox { background: transparent; }
        #leftPanel { background-color: #000000; }
        #controlBar { background-color: #161616; border-top: 1px solid #242424; }
        #rightPanel { background-color: #161616; border-left: 1px solid #242424; }
        QSplitter::handle { background-color: #242424; width: 2px; }
        QSplitter::handle:hover { background-color: #19c8e6; }

        QPushButton {
            background-color: #232323;
            border: 1px solid #303030;
            border-radius: 8px;
            padding: 6px 12px;
            color: #e6e6e6;
        }
        QPushButton:hover { background-color: #2c2c2c; border-color: #19c8e6; }
        QPushButton:pressed { background-color: #1a1a1a; }
        QPushButton:disabled { color: #666666; border-color: #262626; }
        #closeButton:hover { background-color: #c42b1c; border-color: #c42b1c; }
        #closeButton:pressed { background-color: #a32316; }
        #playButton { background-color: #19c8e6; color: #04222a; border: 1px solid #19c8e6; }
        #playButton:hover { background-color: #3ad8f2; }
        #playButton:pressed { background-color: #12a9c3; }

        QListWidget {
            background-color: #101010;
            border: 1px solid #242424;
            border-radius: 8px;
            outline: none;
        }
        QListWidget::item { padding: 6px 8px; border: none; border-radius: 6px; }
        QListWidget::item:hover { background-color: #1d1d1d; }
        QListWidget::item:selected { background-color: #123a44; color: #ffffff; }

        QSlider::groove:horizontal { height: 4px; background: #2e2e2e; border-radius: 2px; }
        QSlider::sub-page:horizontal { background: #19c8e6; border-radius: 2px; }
        QSlider::handle:horizontal {
            background: #ffffff; border: none;
            width: 12px; height: 12px; margin: -4px 0; border-radius: 6px;
        }
        QSlider::handle:horizontal:hover { background: #19c8e6; }

        QCheckBox { spacing: 6px; }
        QCheckBox::indicator {
            width: 15px; height: 15px;
            border: 1px solid #4a4a4a; border-radius: 4px; background: #1c1c1c;
        }
        QCheckBox::indicator:hover { border-color: #19c8e6; }
        QCheckBox::indicator:checked { background: #19c8e6; border-color: #19c8e6; }

        QComboBox {
            background-color: #232323;
            border: 1px solid #303030;
            border-radius: 8px;
            padding: 4px 8px;
        }
        QComboBox:hover { border-color: #19c8e6; }
        QComboBox QAbstractItemView {
            background-color: #1c1c1c; border: 1px solid #303030;
            selection-background-color: #123a44; outline: none;
        }

        QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
        QScrollBar::handle:vertical { background: #3a3a3a; border-radius: 5px; min-height: 30px; }
        QScrollBar::handle:vertical:hover { background: #19c8e6; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

        QLineEdit {
            background-color: #101010; border: 1px solid #262626; border-radius: 9px;
            padding: 7px 10px; selection-background-color: #123a44;
        }
        QLineEdit:focus { border-color: #19c8e6; }
        QToolTip { background-color: #1c1c1c; color: #e6e6e6; border: 1px solid #19c8e6; padding: 4px; }
    """
    app.setStyleSheet(dark_stylesheet)

    icon_path = get_app_icon_path()
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))

    window = MediaWindow()
    if icon_path:
        window.setWindowIcon(QIcon(icon_path))
    if sys.platform != "win32":
        app.setDesktopFileName("ALMP")

    window.show()
    window.start_ipc_server()
    if cli_paths:
        QTimer.singleShot(400, lambda: window.open_external(cli_paths))
    sys.exit(app.exec())