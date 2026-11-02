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

__version__ = "8.0.1"

import os
import sys
import random
import subprocess
import json
import math
import ntpath
import threading
import time
import getpass
import locale
import logging
import logging.handlers
import re
import traceback
import urllib.parse
from pathlib import Path

log = logging.getLogger("almp")
log.addHandler(logging.NullHandler())

def get_log_dir():
    """Where almp.log goes: %LOCALAPPDATA%\\ALMP on Windows, ~/.cache/ALMP elsewhere."""
    base = os.getenv("LOCALAPPDATA") or os.getenv("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "ALMP"

def setup_logging():
    """Errors are written to a small rotating log file (about 1 MB at most), never sent anywhere.
    The file is only created when there is something to write."""
    try:
        log_dir = get_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            log_dir / "almp.log", maxBytes=512 * 1024, backupCount=1, encoding="utf-8", delay=True)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(handler)
        log.setLevel(logging.INFO)
        return log_dir / "almp.log"
    except Exception:
        return None

_EXCEPTION_NOTIFY = None    # set to a callable(str) once the window exists

def _almp_excepthook(exc_type, exc, tb):
    """Log any uncaught error instead of letting PyQt abort the whole program."""
    try:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        log.error("Uncaught error (ALMP %s):\n%s", __version__,
                  "".join(traceback.format_exception(exc_type, exc, tb)))
    except Exception:
        pass
    try:
        if _EXCEPTION_NOTIFY is not None:
            _EXCEPTION_NOTIFY("Something went wrong - ALMP kept running. Details were saved in almp.log.")
    except Exception:
        pass

def _almp_thread_excepthook(args):
    try:
        log.error("Uncaught error in a background thread:\n%s",
                  "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))
    except Exception:
        pass

VERSION_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+", re.ASCII)

def is_valid_version(text):
    """True only for a plain X.Y.Z version (digits and two dots, nothing else)."""
    return isinstance(text, str) and VERSION_RE.fullmatch(text) is not None

# --- Cross-Platform Import Handling ---
if sys.platform == "win32":
    import ctypes
    import winreg
    from ctypes import wintypes

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

try:
    runtime_dir = get_resource_path("runtime")
    if os.path.exists(runtime_dir):
        os.environ["PATH"] = runtime_dir + os.pathsep + os.environ["PATH"]
except Exception:
    pass

from PyQt6.QtCore import Qt, QSize, QPoint, QPointF, QRectF, QObject, pyqtSignal, QThread, QTimer, QEvent, QLockFile, QStandardPaths
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtGui import (QCursor, QColor, QPainter, QPen, QPolygonF, QFontMetrics, QIcon, QPixmap, QImage,
                         QShortcut, QKeySequence, QLinearGradient, QRadialGradient, QBrush)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QListWidget, QListWidgetItem, QFileDialog, QLabel,
    QCheckBox, QMessageBox, QSplitter, QSlider, QComboBox, QDialog,
    QGridLayout, QSizePolicy, QLineEdit, QMenu, QAbstractItemView,
    QStyle, QStyleOptionSlider
)

try:
    import mpv
    MPV_IMPORT_ERROR = None
except Exception as _mpv_exc:          # mpv-2.dll missing, blocked by antivirus, or wrong build
    mpv = None
    MPV_IMPORT_ERROR = _mpv_exc

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
def make_ipc_name(user=None):
    """One single-instance channel per Windows user, so two people signed in on the same PC
    (fast user switching, Remote Desktop) each get their own ALMP window."""
    if user is None:
        try:
            user = getpass.getuser()
        except Exception:
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
        except Exception:
            log.exception("Single-instance connect attempt failed")
        if clock() >= deadline:
            return False
        sleep(interval_s)

def decode_playlist_bytes(raw, fallback_encoding=None):
    """Playlists from Windows Media Player, Winamp and older tools are often in the old Windows
    ("ANSI") code page instead of UTF-8. Try UTF-8 (with or without BOM) first, then fall back."""
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", errors="replace")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    if fallback_encoding is None:
        fallback_encoding = "mbcs" if sys.platform == "win32" else (locale.getpreferredencoding(False) or "cp1252")
    for enc in (fallback_encoding, "cp1252"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("latin-1")

def _playlist_entry_to_path(line, base):
    if line.lower().startswith("file:"):
        parsed = urllib.parse.urlparse(line)
        p = parsed.path
        if parsed.netloc and parsed.netloc.lower() != "localhost":
            p = "//" + parsed.netloc + p          # file://server/share/song.mp3
        p = urllib.parse.unquote(p)
        if re.match(r"/[A-Za-z]:", p):            # file:///C:/Music/song.mp3
            p = p[1:]
        return os.path.normpath(p)
    entry = line if os.path.isabs(line) else os.path.join(base, line)
    return os.path.normpath(entry)

def read_playlist_file(path, fallback_encoding=None):
    out = []
    base = os.path.dirname(path)
    is_pls = path.lower().endswith(".pls")
    try:
        with open(path, "rb") as f:
            text = decode_playlist_bytes(f.read(), fallback_encoding)
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if is_pls:
                if not line.lower().startswith("file"):
                    continue
                line = line.split("=", 1)[-1].strip()
            entry = _playlist_entry_to_path(line, base)
            if os.path.isfile(entry) and Path(entry).suffix.lower() in SUPPORTED_EXTENSIONS:
                out.append(entry)
    except Exception:
        log.exception("Could not read playlist %s", path)
    return out

def write_playlist_file(path, files):
    """.m3u8 is UTF-8 by definition. Plain .m3u gets a UTF-8 BOM so other players
    do not show accented names as garbage."""
    encoding = "utf-8" if path.lower().endswith(".m3u8") else "utf-8-sig"
    with open(path, "w", encoding=encoding, newline="\n") as f:
        f.write("#EXTM3U\n")
        for item in files:
            f.write(item + "\n")

HIGH_CONTRAST_QSS = """
    QMainWindow, QDialog, QMessageBox { background-color: #000000; }
    QWidget { color: #ffffff; }
    #leftPanel { background-color: #000000; }
    #controlBar { background-color: #000000; border-top: 2px solid #ffff00; }
    QPushButton { background-color: #000000; border: 2px solid #ffffff; color: #ffffff; font-weight: 600; }
    QPushButton:hover { border-color: #ffff00; color: #ffff00; }
    #playButton { background-color: #ffff00; color: #000000; border: 2px solid #ffff00; }
    QListWidget { background-color: #000000; border: 2px solid #ffffff; }
    QListWidget::item:selected { background-color: #ffff00; color: #000000; }
    QLineEdit, QComboBox { background-color: #000000; border: 2px solid #ffffff; color: #ffffff; }
    QMenu { background-color: #000000; border: 2px solid #ffffff; }
    QMenu::item:selected { background-color: #ffff00; color: #000000; }
    QPushButton:focus, QComboBox:focus, #playButton:focus { border: 3px solid #00ffff; }
    QCheckBox:focus { color: #00ffff; }
    QListWidget:focus { border: 3px solid #00ffff; }
    QSlider::handle:horizontal:focus { background: #00ffff; }
"""

# Only name fonts that really exist on the platform. Listing missing families (for example
# "Ubuntu" on Windows) makes Qt scan and load every installed font, which cost ~300 MB of memory.
if sys.platform == "win32":
    UI_FONT_FAMILY = '"Segoe UI"'
elif sys.platform == "darwin":
    UI_FONT_FAMILY = '"Helvetica Neue"'
else:
    UI_FONT_FAMILY = '"Ubuntu", "Noto Sans", "DejaVu Sans"'

APP_NAME = "AlexbedLightMediaPlayer"
REGISTRY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
LINUX_AUTOSTART_DIR = Path.home() / ".config" / "autostart"
LINUX_DESKTOP_FILE = LINUX_AUTOSTART_DIR / "almp.desktop"
WIN_STARTUP_DIR = Path(os.getenv('APPDATA') or Path.home()) / r"Microsoft\Windows\Start Menu\Programs\Startup"
WIN_SHORTCUT = WIN_STARTUP_DIR / "ALMP.lnk"
STARTUP_MARKER = Path(os.getenv("APPDATA") or Path.home()) / "ALMP" / "startup_target.txt"

def windows_powershell_path():
    """Full path to Windows PowerShell in System32, so a file called powershell.exe in the
    ALMP folder or the current folder can never be run instead."""
    root = os.environ.get("SystemRoot") or os.environ.get("windir") or r"C:\Windows"
    return os.path.join(root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")

SETTINGS_DIR = Path(os.getenv("APPDATA") or (Path.home() / ".config")) / "ALMP"
SETTINGS_PATH = SETTINGS_DIR / "settings.json"
# Older versions (v7) could save the last playlist and video positions here. ALMP now always
# starts clean, so these files are removed once at start-up: they only held file history.
LEGACY_HISTORY_FILES = ("resume.json", "last_playlist.json", "last_playlist.tmp")
LEGACY_SETTINGS_KEYS = ("remember_playlist",)

def remove_legacy_history_files(folder=None):
    """Delete only the exact old history files listed above (never anything else). Returns what was removed."""
    folder = Path(folder) if folder is not None else SETTINGS_DIR
    removed = []
    for name in LEGACY_HISTORY_FILES:
        p = folder / name
        try:
            if p.is_file() and not p.is_symlink():
                p.unlink()
                removed.append(name)
        except Exception:
            log.warning("Could not remove old history file %s", p)
    return removed

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

def sleep_minutes_left(remaining_ms):
    """Whole minutes left on the sleep timer, rounded up (59 s left shows as 1 min)."""
    if remaining_ms is None or remaining_ms <= 0:
        return 0
    return int(math.ceil(remaining_ms / 60000.0))

def pick_shuffle_index(files, played, current_index, rng=random):
    """Random track that has not been played yet (never the current one).
    `played` is a set of paths; when everything was played it starts over."""
    n = len(files)
    if n == 0:
        return -1
    if n == 1:
        return 0
    if len(played) >= n:
        played.clear()
        if 0 <= current_index < n:
            played.add(files[current_index])
    for _ in range(24):                       # fast path: almost always succeeds
        i = rng.randrange(n)
        if i != current_index and files[i] not in played:
            return i
    candidates = [i for i, p in enumerate(files) if i != current_index and p not in played]
    if not candidates:
        played.clear()
        candidates = [i for i in range(n) if i != current_index]
    return rng.choice(candidates)

# --- Deleting files safely ---
# USB sticks, memory cards, CDs and network drives have no Recycle Bin: Windows would delete
# the file for good. ALMP checks the drive type first and asks plainly before a permanent delete.
DRIVE_UNKNOWN, DRIVE_NO_ROOT_DIR, DRIVE_REMOVABLE, DRIVE_FIXED, DRIVE_REMOTE, DRIVE_CDROM, DRIVE_RAMDISK = range(7)

FO_DELETE = 3
FOF_SILENT = 0x0004
FOF_NOCONFIRMATION = 0x0010
FOF_ALLOWUNDO = 0x0040
FOF_WANTNUKEWARNING = 0x4000

DELETE_OK, DELETE_CANCELLED, DELETE_FAILED = "ok", "cancelled", "failed"

def drive_root(path):
    """'C:\\Music\\a.mp3' -> 'C:\\', '\\\\server\\share\\a.mp3' -> '\\\\server\\share\\'."""
    drive, _rest = ntpath.splitdrive(path)
    if not drive:
        return None
    return drive.rstrip("\\/") + "\\"

def get_drive_type(path):
    """Windows drive type of the drive that holds `path` (DRIVE_UNKNOWN when it cannot be told)."""
    if sys.platform != "win32":
        return DRIVE_UNKNOWN
    root = drive_root(os.path.abspath(path))
    if root is None:
        return DRIVE_UNKNOWN
    if root.startswith("\\\\"):
        return DRIVE_REMOTE
    try:
        return int(ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(root)))
    except Exception:
        log.exception("GetDriveTypeW failed for %s", root)
        return DRIVE_UNKNOWN

def recycle_bin_available(path, platform=None, drive_type_func=None):
    """True only when Windows can really put this file in the Recycle Bin (a fixed, local drive).
    Everything else (USB stick, card reader, network, CD, RAM disk, unknown, not Windows) is treated
    as 'no Recycle Bin' so the user is warned before anything is deleted for good."""
    platform = sys.platform if platform is None else platform
    if platform != "win32":
        return False
    drive_type_func = drive_type_func or get_drive_type
    return drive_type_func(path) == DRIVE_FIXED

def recycle_flags(permanent):
    """SHFileOperation flags. The Recycle Bin route also asks Windows to warn (FOF_WANTNUKEWARNING)
    if the file would be destroyed instead of recycled, so a wrong guess can never delete silently."""
    if permanent:
        return FOF_NOCONFIRMATION | FOF_SILENT
    return FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_WANTNUKEWARNING

def send_to_recycle_bin(file_path, permanent=False, hwnd=0):
    """Returns DELETE_OK, DELETE_CANCELLED or DELETE_FAILED. Never falls back to a silent
    permanent delete: if the Recycle Bin call fails, the file is left alone."""
    if sys.platform != "win32":
        if not permanent:
            return DELETE_FAILED              # no Recycle Bin support here: the caller must ask first
        try:
            os.remove(file_path)
            return DELETE_OK
        except Exception:
            log.exception("Could not delete %s", file_path)
            return DELETE_FAILED

    try:
        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [
                ("hwnd", wintypes.HWND),
                ("wFunc", wintypes.UINT),
                ("pFrom", wintypes.LPCWSTR),
                ("pTo", wintypes.LPCWSTR),
                ("fFlags", ctypes.c_uint16),
                ("fAnyOperationsAborted", wintypes.BOOL),
                ("hNameMappings", ctypes.c_void_p),
                ("lpszProgressTitle", wintypes.LPCWSTR),
            ]

        op = SHFILEOPSTRUCTW()
        op.hwnd = hwnd or 0
        op.wFunc = FO_DELETE
        op.pFrom = os.path.abspath(file_path) + "\0\0"
        op.pTo = None
        op.fFlags = recycle_flags(permanent)

        result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        if op.fAnyOperationsAborted:
            return DELETE_CANCELLED
        if result != 0:
            log.warning("SHFileOperationW returned %s for %s", result, file_path)
            return DELETE_FAILED
        return DELETE_OK if not os.path.exists(file_path) else DELETE_FAILED
    except Exception:
        log.exception("Recycle Bin call failed for %s", file_path)
        return DELETE_FAILED

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
    elif kind == "subtitles":
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(3 * u, 5 * u, 18 * u, 14 * u), 3 * u, 3 * u)
        line((6.5, 11), (10.5, 11)); line((13.5, 11), (17.5, 11))
        line((6.5, 15), (12.5, 15)); line((15.5, 15), (17.5, 15))
    elif kind == "clock":
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(3.5 * u, 3.5 * u, 17 * u, 17 * u))
        line((12, 7.5), (12, 12), (15.5, 14))
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

class WelcomeScreen(QWidget):
    """Start screen: painted wallpaper, gently moving sound bars, and two big buttons."""
    add_files_requested = pyqtSignal()
    add_folder_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(66)           # ~15 frames per second, only while visible
        self._timer.timeout.connect(self._tick)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(24, 24, 24, 110)
        layout.setSpacing(10)

        logo = QLabel()
        logo.setPixmap(self.logo_pixmap(132))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)

        title = QLabel("Alexbed Light Media Player")
        title.setObjectName("welcomeTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        tagline = QLabel("Press play on anything.")
        tagline.setObjectName("welcomeTagline")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(tagline)
        layout.addSpacing(14)

        row = QHBoxLayout()
        row.setSpacing(14)
        row.addStretch(1)
        btn_files = QPushButton("Add Files")
        btn_files.setObjectName("welcomePrimary")
        btn_files.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_files.clicked.connect(self.add_files_requested.emit)
        btn_folder = QPushButton("Add Folder")
        btn_folder.setObjectName("welcomeSecondary")
        btn_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_folder.clicked.connect(self.add_folder_requested.emit)
        row.addWidget(btn_files)
        row.addWidget(btn_folder)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addSpacing(6)

        hint = QLabel("or drag and drop files and folders here     |     F1 for keyboard shortcuts")
        hint.setObjectName("welcomeHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

    @staticmethod
    def logo_pixmap(size=132):
        dpr = 1.0
        try:
            dpr = float(QApplication.primaryScreen().devicePixelRatio())
        except Exception:
            pass
        for name in ("icon.png", "icon.ico"):
            path = get_resource_path(name)
            if os.path.exists(path):
                pm = QPixmap(path)
                if not pm.isNull():
                    pm = pm.scaled(int(size * dpr), int(size * dpr), Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
                    pm.setDevicePixelRatio(dpr)
                    return pm
        return make_icon("play", "#19c8e6", size).pixmap(size, size)

    def showEvent(self, event):
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def _tick(self):
        try:
            if self.window().isMinimized():
                return
        except Exception:
            pass
        self._phase += 0.05
        h = self.height()
        self.update(0, int(h * 0.6), self.width(), int(h * 0.4) + 2)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        if w < 10 or h < 10:
            p.end()
            return
        bg = QLinearGradient(0, 0, 0, h)
        bg.setColorAt(0.0, QColor("#0b1b26"))
        bg.setColorAt(0.55, QColor("#070c11"))
        bg.setColorAt(1.0, QColor("#030406"))
        p.fillRect(self.rect(), QBrush(bg))
        glow = QRadialGradient(w * 0.5, h * 0.34, max(w, h) * 0.55)
        glow.setColorAt(0.0, QColor(25, 200, 230, 64))
        glow.setColorAt(1.0, QColor(25, 200, 230, 0))
        p.fillRect(self.rect(), QBrush(glow))

        n = max(24, int(w / 16))
        slot = w / n
        bar_w = slot * 0.55
        base_y = h * 0.95
        max_h = h * 0.20
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(n):
            t = i / (n - 1)
            env = math.sin(math.pi * t) ** 1.4
            wave = abs(math.sin(self._phase * 1.3 + i * 0.42) * math.sin(self._phase * 0.7 + i * 0.17))
            bh = max(3.0, max_h * env * (0.22 + 0.78 * wave))
            p.setBrush(QColor(25, 200, 230, int(28 + 62 * env)))
            x = (i + 0.5) * slot - bar_w / 2
            p.drawRoundedRect(QRectF(x, base_y - bh, bar_w, bh), bar_w / 2, bar_w / 2)
        p.end()


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
        lbl.setTextFormat(Qt.TextFormat.PlainText)     # file names are shown exactly as they are
        lbl.setWordWrap(True)
        lbl.setMinimumWidth(460)
        lbl.setStyleSheet("font-size: 14px; padding: 10px;")
        layout.addWidget(lbl)
        
        btn_layout = QHBoxLayout()
        self.btn_yes = QPushButton("Yes")
        self.btn_no = QPushButton("No")
        self.btn_yes.setStyleSheet("font-size: 15px; padding: 8px 24px;")
        self.btn_no.setStyleSheet("font-size: 15px; padding: 8px 24px;")
        
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

class ClickSeekSlider(QSlider):
    """A slider that jumps to the spot you click (a normal QSlider only moves one step),
    and then lets you keep dragging."""
    def mousePressEvent(self, event):
        try:
            if event.button() == Qt.MouseButton.LeftButton and self.maximum() > self.minimum():
                opt = QStyleOptionSlider()
                self.initStyleOption(opt)
                style = self.style()
                handle = style.subControlRect(QStyle.ComplexControl.CC_Slider, opt,
                                              QStyle.SubControl.SC_SliderHandle, self)
                pos = event.position().toPoint()
                if not handle.contains(pos):
                    groove = style.subControlRect(QStyle.ComplexControl.CC_Slider, opt,
                                                  QStyle.SubControl.SC_SliderGroove, self)
                    span = max(1, groove.width() - handle.width())
                    x = pos.x() - groove.x() - handle.width() // 2
                    self.setValue(QStyle.sliderValueFromPosition(
                        self.minimum(), self.maximum(), max(0, min(span, x)), span, opt.upsideDown))
        except Exception:
            log.exception("Slider click failed")
        super().mousePressEvent(event)


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
        except Exception:
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


class StartupResultBridge(QObject):
    done = pyqtSignal(bool, str)


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
                if self.isInterruptionRequested():
                    return
                if os.path.isdir(target):
                    for root, dirs, files in os.walk(target):
                        if self.isInterruptionRequested():
                            return             # ALMP is closing: stop scanning right away
                        dirs[:] = [
                            d for d in dirs
                            if not d.startswith("$") and d.lower() != "system volume information"
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
            if self.isInterruptionRequested():
                return
            found.sort(key=lambda path: path.casefold())
            self.files_found.emit(found)
        except Exception as exc:
            self.scan_error.emit(str(exc))

class MediaWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Alexbed Light Media Player")
        self.resize(1200, 700)

        icon_file_path = get_app_icon_path()
        if icon_file_path:
            self.setWindowIcon(QIcon(icon_file_path))

        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.files = []
        self.path_set = set()
        self.current_path = None
        self.current_index = -1
        self.shuffle_enabled = True 
        self._played_paths = set()
        self._history = []
        self._autoplay_pending = True
        self._ext_play_key = None          # file opened from Explorer that should start playing
        self._removed_played_count = 0
        self._modal_depth = 0
        self._error_streak = 0
        self._sleep_minutes = 0
        self._sleep_action = "pause"
        self._sleep_timer = QTimer(self)
        self._sleep_timer.setSingleShot(True)
        self._sleep_timer.timeout.connect(self._sleep_timer_fired)
        self._sleep_tip_timer = QTimer(self)      # keeps "x min left" in the tooltip up to date
        self._sleep_tip_timer.setInterval(20000)
        self._sleep_tip_timer.timeout.connect(self._update_sleep_button)
        self._startup_bridge = StartupResultBridge(self)
        self._startup_bridge.done.connect(self._on_startup_result)
        self._startup_busy = False
        self._marked_item = None
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
        self._last_ext_time = -1e9
        self.ipc_server = None

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

        self.welcome_widget.show()
        self.welcome_widget.raise_()
        QTimer.singleShot(0, self._sync_video_overlays)

        self.installEventFilter(self)
        self.search_edit.installEventFilter(self)
        self.playlist.installEventFilter(self)
        QTimer.singleShot(100, self._force_focus)

    def attach_ipc_server(self, server):
        """Connect the single-instance channel (already listening) to this window."""
        self.ipc_server = server
        if server is None or not server.listening:
            self.status_label.setText("Note: opening files by double-click may not reach this window until ALMP is restarted.")
            return
        server.set_receiver(self.open_external)

    class _ModalGuard:
        def __init__(self, window):
            self.w = window

        def __enter__(self):
            w = self.w
            w._modal_depth += 1
            w._dialog_active = True
            w.hide_timer.stop()
            w._show_cursor()
            if w._is_fullscreen:
                w._show_fs_overlays()
            return self

        def __exit__(self, *exc):
            w = self.w
            w._modal_depth = max(0, w._modal_depth - 1)
            if w._modal_depth == 0:
                w._dialog_active = False
                if w._is_fullscreen and not w._closing:
                    w.hide_timer.start()
            return False

    def _modal(self):
        """Use around every dialog: keeps the mouse pointer and fullscreen controls visible."""
        return MediaWindow._ModalGuard(self)

    def notify_error(self, text):
        try:
            if not self._closing:
                self.status_label.setText(text)
        except Exception:
            pass

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
        # Files opened from Explorer are ADDED to the playlist (it is never wiped), and the
        # first of them starts playing, so a double-click always plays what was clicked.
        # Several files opened together arrive one after another (one small message each);
        # only the first group of such a burst starts playing, the rest are just added.
        now = time.monotonic()
        start_playing = (now - self._last_ext_time) > 3.0
        self._last_ext_time = now
        self.scan_targets(paths, external=start_playing)
        self._bring_to_front()

    def _bring_to_front(self):
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def _setup_shortcuts(self):
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, activated=self.play_or_resume)
        QShortcut(QKeySequence(Qt.Key.Key_F), self, activated=self._toggle_fullscreen)
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, activated=lambda: self._seek_relative(5))
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, activated=lambda: self._seek_relative(-5))
        QShortcut(QKeySequence(Qt.Key.Key_Up), self, activated=lambda: self.volume_slider.setValue(self.volume_slider.value() + 5))
        QShortcut(QKeySequence(Qt.Key.Key_Down), self, activated=lambda: self.volume_slider.setValue(self.volume_slider.value() - 5))
        QShortcut(QKeySequence(Qt.Key.Key_PageUp), self, activated=self.previous_track)
        QShortcut(QKeySequence(Qt.Key.Key_PageDown), self, activated=self.next_track)
        QShortcut(QKeySequence(Qt.Key.Key_M), self, activated=self._toggle_mute)
        QShortcut(QKeySequence(Qt.Key.Key_A), self, activated=self._cycle_aspect)
        QShortcut(QKeySequence(Qt.Key.Key_P), self, activated=self._toggle_fs_playlist)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self._focus_search)
        QShortcut(QKeySequence(Qt.Key.Key_S), self, activated=self.take_snapshot)
        QShortcut(QKeySequence(Qt.Key.Key_F1), self, activated=self.show_shortcuts)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=lambda: self._toggle_fullscreen() if self._is_fullscreen else None)
        
        QShortcut(QKeySequence(Qt.Key.Key_MediaPlay), self, activated=self.play_or_resume)
        QShortcut(QKeySequence(Qt.Key.Key_MediaPause), self, activated=self.play_or_resume)
        QShortcut(QKeySequence(Qt.Key.Key_MediaTogglePlayPause), self, activated=self.play_or_resume)
        QShortcut(QKeySequence(Qt.Key.Key_MediaNext), self, activated=self.next_track)
        QShortcut(QKeySequence(Qt.Key.Key_MediaPrevious), self, activated=self.previous_track)

    def show_shortcuts(self):
        rows = [
            ("Space", "Play / pause"), ("F  /  Esc", "Fullscreen / leave fullscreen"),
            ("Left / Right", "Seek 5 seconds"), ("Up / Down", "Volume"),
            ("Page Up / Page Down", "Previous / next track"), ("M", "Mute"),
            ("A", "Video size: Fit, Fill, Stretch"), ("S", "Save a picture of the video"),
            ("P", "Playlist drawer (fullscreen)"), ("Ctrl+F", "Search the playlist"),
            ("Enter", "Play the selected playlist item"),
            ("F1", "This help"), ("Double-click video", "Fullscreen"),
        ]
        html = "<table cellpadding='6'>" + "".join(
            f"<tr><td><b>{k}</b></td><td>{v}</td></tr>" for k, v in rows) + "</table>"
        with self._modal():
            dlg = QDialog(self)
            dlg.setWindowTitle("Keyboard shortcuts")
            lay = QVBoxLayout(dlg)
            lbl = QLabel(html)
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lay.addWidget(lbl)
            ok = QPushButton("Close")
            ok.clicked.connect(dlg.accept)
            lay.addWidget(ok, alignment=Qt.AlignmentFlag.AlignCenter)
            dlg.exec()
            dlg.deleteLater()

    def _seek_relative(self, seconds):
        """Left/Right arrows. mpv refuses to seek when nothing is loaded, so do nothing then."""
        if not self.player or not self.current_path:
            return
        try:
            if self.player.idle_active:
                return
            self.player.seek(seconds, reference="relative")
        except Exception:
            log.debug("Seek ignored", exc_info=True)

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

    def _sync_video_overlays(self):
        w, h = self.video.width(), self.video.height()
        self.welcome_widget.setGeometry(0, 0, w, h)
        self.audio_art_label.setGeometry(0, 0, w, h)

    def eventFilter(self, obj, event):
        if obj == self.video and event.type() == QEvent.Type.Resize:
            self._sync_video_overlays()
        if obj == self and event.type() == QEvent.Type.ActivationChange:
            if self.isActiveWindow() and not self._dialog_active:
                self._force_focus()
        
        if obj is getattr(self, "playlist", None) and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self.playlist.currentItem() is not None:
                    self.play_selected_item(self.playlist.currentItem())
                    return True
            if self._is_fullscreen:
                self._on_fs_activity()
        if obj is getattr(self, "search_edit", None) and event.type() == QEvent.Type.KeyPress and self._is_fullscreen:
            self._on_fs_activity()          # typing in the drawer's search box keeps it open

        if obj == self.video:
            if event.type() == QEvent.Type.MouseButtonDblClick:
                self._toggle_fullscreen()
                return True
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
            self.status_label.setText("Start playing something first, then use this button for audio and subtitles.")
            return
        
        try:
            self.active_menu = QMenu(self)
            menu = self.active_menu
            
            def tv(t, key, default=None):
                try:
                    if isinstance(t, dict):
                        return t.get(key, default)
                    return getattr(t, key, default)
                except Exception:
                    return default

            audio_tracks, sub_tracks = [], []
            try:
                for t in (self.player.track_list or []):
                    kind = tv(t, "type")
                    if kind == "audio":
                        audio_tracks.append(t)
                    elif kind == "sub":
                        sub_tracks.append(t)
            except Exception:
                pass

            def label(t):
                title, lang = tv(t, "title"), tv(t, "lang")
                text = f"{title} ({lang})" if title and lang else (title or lang or f"Track {tv(t, 'id')}")
                return ("\u2713  " if tv(t, "selected") else "      ") + str(text)

            if audio_tracks:
                audio_menu = menu.addMenu("Audio Tracks")
                for t in audio_tracks:
                    act = audio_menu.addAction(label(t))
                    act.triggered.connect(lambda checked=False, tid=tv(t, "id"): self._safe_set_mpv_prop("aid", tid))

            if sub_tracks:
                sub_menu = menu.addMenu("Subtitles")
                any_selected = any(tv(t, "selected") for t in sub_tracks)
                act = sub_menu.addAction(("      " if any_selected else "\u2713  ") + "Off")
                act.triggered.connect(lambda checked=False: self._safe_set_mpv_prop("sid", "no"))
                for t in sub_tracks:
                    act = sub_menu.addAction(label(t))
                    act.triggered.connect(lambda checked=False, tid=tv(t, "id"): self._safe_set_mpv_prop("sid", tid))

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
        with self._modal():
            fname, _ = QFileDialog.getOpenFileName(self, "Load Subtitle", "", "Subtitles (*.srt *.ass *.vtt *.ssa)")
        if fname:
            try:
                self.player.sub_add(fname)
                self.status_label.setText(f"Subtitle loaded: {Path(fname).name}")
            except Exception as e:
                log.exception("Could not load subtitle %s", fname)
                with self._modal():
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
        self.video.setStyleSheet("#videoSurface { background-color: black; border: none; }")
        self.video.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.video.installEventFilter(self)
        self.left_layout.addWidget(self.video, stretch=1)

        self.audio_art_label = QLabel(self.video)
        self.audio_art_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.audio_art_label.setStyleSheet("background-color: transparent;")
        self.audio_art_label.hide()

        self.welcome_widget = WelcomeScreen(self.video)
        self.welcome_widget.add_files_requested.connect(self.choose_files)
        self.welcome_widget.add_folder_requested.connect(self.choose_folder)
        self.welcome_widget.hide()

        self.control_panel_widget = QWidget()
        self.control_panel_widget.setObjectName("controlBar")
        self.control_panel_layout = QVBoxLayout(self.control_panel_widget)
        self.control_panel_layout.setContentsMargins(12, 8, 12, 10)
        self.control_panel_layout.setSpacing(6)

        self.progress_slider = ClickSeekSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setToolTip("Click or drag to jump to a point in the track")
        self.progress_slider.setRange(0, 0)
        self.progress_slider.sliderMoved.connect(self.slider_user_scrubbed)
        self.progress_slider.sliderPressed.connect(self._start_scrubbing)
        self.progress_slider.sliderReleased.connect(self._stop_scrubbing)
        self.control_panel_layout.addWidget(self.progress_slider)

        self.status_label = QLabel("Drag & Drop folders/videos here or choose an action.")
        self.status_label.setStyleSheet("font-weight: 600; color: #d5dde0;")
        self.status_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setStyleSheet("font-size: 13px; color: #9aa4a8;")
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
        self.volume_slider = ClickSeekSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)
        self.volume_slider.valueChanged.connect(self.change_volume)
        self.volume_value_label = QLabel("100%")
        self.volume_value_label.setFixedWidth(40)
        self.volume_value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.volume_value_label.setStyleSheet("color: #9aa4a8; font-size: 13px;")
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
        self.tracks_button.setIcon(make_icon("subtitles", "#e6e6e6", 18))
        self.tracks_button.setIconSize(ICON_SZ)
        self.tracks_button.setFixedSize(42, 38)
        self.tracks_button.setToolTip("Audio tracks and subtitles")
        self.tracks_button.clicked.connect(lambda: self.show_context_menu(self.tracks_button.mapToGlobal(QPoint(0, self.tracks_button.height()))))
        controls_layout.addWidget(self.tracks_button)

        self.sleep_button = QPushButton()
        self.sleep_button.setIcon(make_icon("clock", "#e6e6e6", 18))
        self.sleep_button.setIconSize(ICON_SZ)
        self.sleep_button.setFixedSize(42, 38)
        self.sleep_button.setToolTip("Sleep timer")
        self.sleep_button.clicked.connect(self.show_sleep_menu)
        controls_layout.addWidget(self.sleep_button)
        
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
        playlist_title.setStyleSheet("font-size: 18px; font-weight: 600; color: #f1f4f5;")
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
        self.playlist.setStyleSheet("QListWidget { font-size: 14px; } QListWidget::item { padding: 8px 10px; }")
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

        self.add_media_button = QPushButton("+ Add Media")
        self.add_media_button.clicked.connect(self.show_add_media_menu)
        self.options_layout_1.addWidget(self.add_media_button)

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
        self.delete_file_button.setToolTip("Delete the selected file (to the Recycle Bin when the drive has one)")
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
        self.startup_checkbox.setToolTip("Start ALMP when you sign in to Windows")
        self.startup_checkbox.toggled.connect(self.toggle_startup)
        self.options_layout_2.addWidget(self.startup_checkbox, 1, 1)

        size_label = QLabel("Interface size")
        size_label.setStyleSheet("color: #9aa4a8; font-size: 13px;")
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

        # Buttons, boxes and sliders take keyboard focus with Tab only (not when clicked),
        # so the yellow focus ring shows up only for people who use the keyboard.
        for kind in (QPushButton, QCheckBox, QComboBox, QSlider):
            for w in self.findChildren(kind):
                w.setFocusPolicy(Qt.FocusPolicy.TabFocus)

    def show_add_media_menu(self):
        menu = QMenu(self)
        menu.addAction("Add Files...", self.choose_files)
        menu.addAction("Add Folder...", self.choose_folder)
        menu.addSeparator()
        menu.addAction("Save Playlist as M3U...", self.save_playlist_m3u)
        self._fill_sleep_menu(menu.addMenu("Sleep Timer"))
        hc = menu.addAction("High Contrast Theme")
        hc.setCheckable(True)
        hc.setChecked(bool(load_settings().get("high_contrast", False)))
        hc.triggered.connect(self.set_high_contrast)

        button = self.sender()
        if isinstance(button, QPushButton):
            menu.exec(button.mapToGlobal(QPoint(0, button.height())))
        else:
            menu.exec(QCursor.pos())

    def _fill_sleep_menu(self, sleep_menu):
        left = self._sleep_minutes_left()
        if left:
            info = sleep_menu.addAction(f"Time left: {left} min")
            info.setEnabled(False)
            sleep_menu.addSeparator()
        for label, minutes in (("Off", 0), ("5 minutes", 5), ("15 minutes", 15), ("30 minutes", 30),
                               ("45 minutes", 45), ("1 hour", 60), ("2 hours", 120)):
            act = sleep_menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(minutes == self._sleep_minutes)
            act.triggered.connect(lambda checked=False, m=minutes: self.set_sleep_timer(m))
        sleep_menu.addSeparator()
        for label, action in (("When time is up: Pause playback", "pause"), ("When time is up: Close ALMP", "close")):
            act = sleep_menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(self._sleep_action == action)
            act.triggered.connect(lambda checked=False, a=action: self.set_sleep_action(a))

    def show_sleep_menu(self):
        if self._is_fullscreen:
            self._on_fs_activity()
        menu = QMenu(self)
        self._fill_sleep_menu(menu)
        b = self.sleep_button
        menu.exec(b.mapToGlobal(QPoint(0, b.height())))

    def _sleep_minutes_left(self):
        if self._sleep_minutes <= 0 or not self._sleep_timer.isActive():
            return 0
        return sleep_minutes_left(self._sleep_timer.remainingTime())

    def _update_sleep_button(self):
        on = self._sleep_minutes > 0
        self.sleep_button.setIcon(make_icon("clock", "#19c8e6" if on else "#e6e6e6", 18))
        if on:
            what = "close ALMP" if self._sleep_action == "close" else "pause playback"
            self.sleep_button.setToolTip(f"Sleep timer on: will {what} in {self._sleep_minutes_left()} min")
        else:
            self.sleep_button.setToolTip("Sleep timer")

    def save_playlist_m3u(self):
        if not self.files:
            self.status_label.setText("The playlist is empty - nothing to save.")
            return
        if getattr(self, "_pending_paths", None):
            self.status_label.setText("Still adding files - please wait until loading has finished, then save.")
            return
        start = str(Path.home() / "Music" / "ALMP-playlist.m3u8")
        with self._modal():
            path, _ = QFileDialog.getSaveFileName(self, "Save Playlist", start, "Playlist (*.m3u8 *.m3u)")
        if not path:
            return
        if not path.lower().endswith((".m3u", ".m3u8")):
            path += ".m3u8"
        try:
            write_playlist_file(path, self.files)
            msg = f"Saved {len(self.files):,} items to {os.path.basename(path)}"
            if self._removed_played_count:
                msg += " (items already played and removed are not included)"
            self.status_label.setText(msg)
        except Exception as e:
            log.exception("Could not save playlist %s", path)
            with self._modal():
                QMessageBox.warning(self, "Save Playlist", f"Could not save the playlist:\n{e}")

    def set_sleep_action(self, action):
        """Only changes WHAT happens; a running countdown keeps its time."""
        self._sleep_action = action
        self._update_sleep_button()
        what = "close." if action == "close" else "pause playback."
        left = self._sleep_minutes_left()
        if left:
            self.status_label.setText(f"Sleep timer: in {left} min ALMP will {what}")
        else:
            self.status_label.setText("When the sleep timer ends, ALMP will " + what)

    def set_sleep_timer(self, minutes):
        self._sleep_minutes = minutes
        self._sleep_timer.stop()
        self._sleep_tip_timer.stop()
        if minutes > 0:
            self._sleep_timer.start(minutes * 60 * 1000)
            self._sleep_tip_timer.start()
            if self._sleep_action == "close":
                self.status_label.setText(f"Sleep timer set: ALMP will close in {minutes} minutes.")
            else:
                self.status_label.setText(f"Sleep timer set: playback will pause in {minutes} minutes.")
        else:
            self.status_label.setText("Sleep timer is off.")
        self._update_sleep_button()

    def _sleep_timer_fired(self):
        self._sleep_minutes = 0
        self._sleep_tip_timer.stop()
        self._update_sleep_button()
        if self._sleep_action == "close":
            self.close()
            return
        self._set_mpv_pause(True)
        self._set_play_ui(False)
        self.status_label.setText("Sleep timer: playback paused.")

    def set_high_contrast(self, enabled):
        app = QApplication.instance()
        base = app.property("almp_base_qss") or ""
        app.setStyleSheet(base + (HIGH_CONTRAST_QSS if enabled else ""))
        data = load_settings()
        data["high_contrast"] = bool(enabled)
        save_settings(data)

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
                # Lean, offline-only engine: no web-video plugin, no Lua scripts, ignore any
                # user mpv.conf, and keep the read-ahead buffers small (less memory, faster start).
                ytdl="no",
                load_scripts="no",
                config="no",
                demuxer_max_bytes="48MiB",
                demuxer_max_back_bytes="8MiB",
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
        })
        for key in LEGACY_SETTINGS_KEYS:
            data.pop(key, None)
        save_settings(data)

    def _apply_settings(self):
        data = load_settings()
        try:
            self.volume_slider.setValue(int(data.get("volume", 100)))
            self.shuffle_checkbox.setChecked(bool(data.get("shuffle", True)))
            self.loop_single_checkbox.setChecked(bool(data.get("loop_single", False)))
            self.remove_played_checkbox.setChecked(bool(data.get("remove_played", True)))
        except Exception:
            log.exception("Could not apply saved settings")

    def resizeEvent(self, event):
        QTimer.singleShot(0, self._layout_fs_title)
        QTimer.singleShot(0, self._layout_overlay)
        QTimer.singleShot(0, self._sync_video_overlays)
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
        """Creates the Startup-folder shortcut. Returns (ok, details). Runs in a worker thread."""
        def q(v):
            return "'" + str(v).replace("'", "''") + "'"
        ps = (
            "$s=(New-Object -ComObject WScript.Shell).CreateShortcut(%s);"
            "$s.TargetPath=%s;$s.WorkingDirectory=%s;$s.IconLocation=%s;$s.Save()"
            % (q(WIN_SHORTCUT), q(exe_path), q(os.path.dirname(exe_path)), q(exe_path))
        )
        WIN_STARTUP_DIR.mkdir(parents=True, exist_ok=True)
        try:
            r = subprocess.run([windows_powershell_path(), "-NoProfile", "-NonInteractive", "-Command", ps],
                               capture_output=True, text=True, timeout=60,
                               creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception as e:
            return False, f"PowerShell could not run: {e}"
        if r.returncode != 0 or not WIN_SHORTCUT.exists():
            return False, f"PowerShell exit code {r.returncode}: {(r.stderr or '').strip()[:500]}"
        try:
            STARTUP_MARKER.parent.mkdir(parents=True, exist_ok=True)
            STARTUP_MARKER.write_text(os.path.normcase(exe_path), encoding="utf-8")
        except Exception:
            log.warning("Could not write %s", STARTUP_MARKER)
        return True, ""

    def _repair_startup_shortcut(self):
        """If the ALMP folder was moved, point the existing startup shortcut at the new place."""
        try:
            if STARTUP_MARKER.exists() and \
               STARTUP_MARKER.read_text(encoding="utf-8").strip() == os.path.normcase(APP_EXE_PATH):
                return
            def q(v): return "'" + str(v).replace("'", "''") + "'"
            ps = "(New-Object -ComObject WScript.Shell).CreateShortcut(%s).TargetPath" % q(WIN_SHORTCUT)
            r = subprocess.run([windows_powershell_path(), "-NoProfile", "-NonInteractive", "-Command", ps],
                               capture_output=True, text=True, timeout=60,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            target = os.path.normcase(os.path.normpath(r.stdout.strip())) if r.stdout.strip() else ""
            if target != os.path.normcase(APP_EXE_PATH):
                ok, details = self._write_startup_shortcut(APP_EXE_PATH)
                if not ok:
                    log.warning("Could not repair the startup shortcut: %s", details)
        except Exception:
            log.exception("Startup shortcut check failed")

    def _set_startup_box(self, checked):
        self.startup_checkbox.blockSignals(True)
        self.startup_checkbox.setChecked(checked)
        self.startup_checkbox.blockSignals(False)

    def toggle_startup(self, checked):
        if not self._is_compiled():
            self._set_startup_box(False)
            with self._modal():
                QMessageBox.warning(self, "Notice", "Run at Startup only works in the compiled .exe version.")
            return

        exe_path = APP_EXE_PATH
        if not exe_path or not os.path.isfile(exe_path):
            self._set_startup_box(False)
            with self._modal():
                QMessageBox.warning(self, "Notice", "Could not locate ALMP.exe, so Run at Startup was not changed.")
            return

        if sys.platform == "win32":
            if checked:
                if self._startup_busy:
                    return
                self._startup_busy = True
                self.startup_checkbox.setEnabled(False)
                self.status_label.setText("Adding ALMP to Windows startup...")
                bridge = self._startup_bridge

                def work():
                    try:
                        if WIN_SHORTCUT.exists():
                            WIN_SHORTCUT.unlink()
                        ok, details = MediaWindow._write_startup_shortcut(exe_path)
                    except Exception as e:
                        ok, details = False, str(e)
                    try:
                        bridge.done.emit(ok, details)
                    except RuntimeError:
                        pass          # the window was closed meanwhile

                threading.Thread(target=work, daemon=True).start()
            else:
                try:
                    if WIN_SHORTCUT.exists():
                        WIN_SHORTCUT.unlink()
                    self.status_label.setText("ALMP removed from Windows startup.")
                except Exception as e:
                    log.exception("Could not remove the startup shortcut")
                    self._set_startup_box(True)
                    with self._modal():
                        QMessageBox.critical(self, "Startup Error", f"Could not remove ALMP from Windows startup:\n{e}")
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
                log.exception("Autostart change failed")
                self._set_startup_box(not checked)
                with self._modal():
                    QMessageBox.critical(self, "Autostart Error", f"Failed to modify startup settings: {e}")

    def _on_startup_result(self, ok, details):
        self._startup_busy = False
        self.startup_checkbox.setEnabled(True)
        if ok:
            self._set_startup_box(True)
            self.status_label.setText("ALMP will now start when you sign in to Windows.")
            return
        log.warning("Run at Startup failed: %s", details)
        self._set_startup_box(False)
        self.status_label.setText("Run at Startup could not be turned on.")
        if not self._closing:
            with self._modal():
                QMessageBox.warning(
                    self, "Run at Startup",
                    "Windows did not allow ALMP to add itself to startup, so nothing was changed.\n\n"
                    "This can happen on school or office computers. "
                    "Details were saved in almp.log.")

    def _load_album_art(self, file_path):
        try:
            from mutagen import File as MutagenFile
            audio = MutagenFile(file_path)
            if audio is None:
                return None
            art_data = None
            tags = getattr(audio, "tags", None)
            pics = []
            try:
                from mutagen.id3 import ID3
                if isinstance(tags, ID3):
                    pics = tags.getall("APIC")     # covers saved as "APIC:Cover", "APIC:Front" and so on
            except Exception:
                pics = []
            if pics:
                front = [p for p in pics if getattr(p, "type", None) == 3]
                art_data = (front or pics)[0].data
            elif tags is not None and 'APIC:' in tags:
                art_data = tags['APIC:'].data
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
            try:
                self.player.volume = self.volume_slider.value()
            except Exception:
                log.exception("Could not set the volume")

    def change_speed(self, text):
        if self.player:
            try:
                self.player.speed = float(text.replace("x", ""))
            except Exception:
                log.exception("Could not set the speed to %r", text)

    def clear_playlist(self):
        self._pending_paths = []
        self._chunk_running = False      # a pending chunk tick will simply find nothing to add
        self._autoplay_pending = True
        self._ext_play_key = None
        self._removed_played_count = 0
        self.track_timer.stop()
        self.files.clear()
        self.path_set.clear()
        self._played_paths.clear()
        self._history.clear()
        self._marked_item = None
        self.current_index = -1
        self.current_path = None
        self.playlist.clear()
        self.progress_slider.setValue(0)
        self.progress_slider.setMaximum(0)
        self._set_play_ui(False)
        self.audio_art_label.hide()
        self.status_label.setText("Playlist cleared cleanly. Drag & Drop files to start again.")
        self._update_playlist_count()
        self.welcome_widget.show()
        self.welcome_widget.raise_()
        if self.player:
            try:
                self.player.stop()
            except Exception:
                pass

    def remove_from_playlist(self):
        item = self.playlist.currentItem()
        if item is None:
            with self._modal():
                QMessageBox.warning(self, "Remove from List", "Please select a file to remove.")
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        name_key = os.path.normcase(path)
        try:
            idx = self.files.index(path)
        except ValueError:
            return
        is_currently_playing = (idx == self.current_index)
        self.files.pop(idx)
        self.path_set.discard(name_key)
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
                self.welcome_widget.show()
                self.welcome_widget.raise_()
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

    def _wait_until_idle(self, timeout_s=1.0):
        """After stop(), mpv closes the file a moment later. Wait (briefly) so Windows does not
        refuse the delete with "file in use"."""
        if not self.player:
            return
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                if self.player.idle_active:
                    return
            except Exception:
                return
            time.sleep(0.05)      # mpv updates idle-active on its own thread

    def delete_selected_file(self):
        item = self.playlist.currentItem()
        if item is None:
            with self._modal():
                QMessageBox.warning(self, "Delete File", "Please select a file in the playlist to delete.")
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        if not path or not os.path.exists(path):
            self.status_label.setText("File no longer exists.")
            return
        was_fullscreen = self._is_fullscreen
        was_playing = False
        if self.player:
            try:
                was_playing = not bool(self.player.pause) and not self.player.idle_active
                if was_playing:
                    self._set_mpv_pause(True)
            except Exception:
                log.exception("Could not pause before delete")
        self.video.setMouseTracking(True)

        has_bin = recycle_bin_available(path)
        name = Path(path).name
        if has_bin:
            title = "Delete File"
            message = f"Send this file to the Recycle Bin?\n\n{name}\n\nYou can restore it from the Recycle Bin later."
        else:
            title = "Delete File Permanently?"
            message = (
                "This drive has no Recycle Bin (for example a USB stick, memory card or network drive).\n\n"
                f"The file will be deleted PERMANENTLY and cannot be restored:\n\n{name}\n\n"
                "Delete it anyway?"
            )
        with self._modal():
            # Stay in fullscreen: the dialog is always-on-top, and the controls and cursor stay visible.
            dialog = CustomConfirmDialog(self, title, message)
            dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
            dialog.setModal(True)
            reply = dialog.exec()
            dialog.deleteLater()
        if was_fullscreen:
            self.video.setFocus()
        if reply != QDialog.DialogCode.Accepted:
            if was_playing and self.player:
                try:
                    self._set_mpv_pause(False)
                    self._set_play_ui(True)
                except Exception:
                    log.exception("Could not resume after cancelled delete")
            return
        try:
            idx = self.files.index(path)
        except ValueError:
            self.status_label.setText("The selected file is no longer in the playlist.")
            return
        is_currently_playing = (path == self.current_path)
        resume_at = None
        if is_currently_playing and self.player:
            try:
                resume_at = self.player.time_pos
                self.player.stop()
            except Exception:
                log.exception("Could not stop playback before delete")
            self._wait_until_idle()

        self.status_label.setText("Deleting...")
        hwnd = 0
        try:
            hwnd = int(self.winId())
        except Exception:
            pass
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        try:
            result = send_to_recycle_bin(path, permanent=not has_bin, hwnd=hwnd)
        finally:
            QApplication.restoreOverrideCursor()
        if result != DELETE_OK:
            if result == DELETE_CANCELLED:
                self.status_label.setText(f"Not deleted: {name}")
            else:
                self.status_label.setText(f"Could not delete: {name}")
                with self._modal():
                    QMessageBox.critical(self, "Delete Error",
                                         f"Could not delete this file. It was not changed:\n{path}")
            if is_currently_playing:
                if was_playing or resume_at:
                    self.play_index(idx, start=resume_at)        # carry on where it was
                    if not was_playing:
                        self._set_mpv_pause(True)
                        self._set_play_ui(False)
            elif was_playing and self.player:
                try:
                    self._set_mpv_pause(False)
                    self._set_play_ui(True)
                except Exception:
                    log.exception("Could not resume after failed delete")
            return

        name_key = os.path.normcase(path)
        self.path_set.discard(name_key)
        self.files.pop(idx)
        self.playlist.takeItem(idx)
        self._update_playlist_count()
        if has_bin:
            self.status_label.setText(f"File sent to Recycle Bin: {name}")
        else:
            self.status_label.setText(f"File deleted permanently: {name}")
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
                self.welcome_widget.show()
                self.welcome_widget.raise_()
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
                    self._set_mpv_pause(False)
                    self._set_play_ui(True)
                except Exception:
                    log.exception("Could not resume after delete")

    def _poll_player_metrics(self):
        if not self.player or self._closing:
            return
        try:
            if self._is_scrubbing or self.isMinimized():
                return
            current_time = getattr(self.player, "time_pos", 0) or 0
            duration = getattr(self.player, "duration", 0) or 1
            key = (int(current_time), int(duration))
            if duration > 0 and key != getattr(self, "_last_tick_key", None):
                self._last_tick_key = key
                self.progress_slider.setMaximum(int(duration))
                self.progress_slider.setValue(int(current_time))
                self.time_label.setText(f"{self._fmt_time(current_time)} / {self._fmt_time(duration)}")
                if current_time > 0:
                    self._error_streak = 0
        except Exception:
            pass

    @staticmethod
    def _fmt_time(seconds):
        seconds = int(max(0, seconds))
        h, rem = divmod(seconds, 3600)
        m, sec = divmod(rem, 60)
        return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"

    def slider_user_scrubbed(self):
        if not self.player or not self.current_path:
            return
        try:
            if self.player.idle_active:
                return
            self.player.seek(self.progress_slider.value(), reference="absolute")
        except Exception:
            log.debug("Seek ignored", exc_info=True)

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
        # Never hide the pointer while a menu or any dialog is open (F1 help, file pickers, messages).
        if (QApplication.activePopupWidget() is not None or self._dialog_active
                or QApplication.activeModalWidget() is not None):
            self._show_cursor()
            self.hide_timer.start()
            return
        # Do not close the drawer while someone is typing in its search box.
        if self.right_panel.isVisible() and self.search_edit.hasFocus():
            self.hide_timer.start()
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
        with self._modal():
            files, _ = QFileDialog.getOpenFileNames(
                self,
                "Select Media Files",
                "",
                "Media Files (" + " ".join("*" + e for e in sorted(SUPPORTED_EXTENSIONS | PLAYLIST_EXTENSIONS)) + ");;"
                "Audio (" + " ".join("*" + e for e in sorted(AUDIO_EXTENSIONS)) + ");;"
                "Video (" + " ".join("*" + e for e in sorted(VIDEO_EXTENSIONS)) + ");;All Files (*)"
            )
        if files:
            self.scan_targets(files)

    def choose_folder(self):
        with self._modal():
            folder = QFileDialog.getExistingDirectory(self, "Select media folder")
        if folder:
            self.scan_targets([folder])

    def scan_targets(self, targets, external=False):
        if self.scanner is not None and self.scanner.isRunning():
            self.status_label.setText("Still loading the previous folder - please wait a moment.")
            return
        self.status_label.setText("Processing imported tracks...")
        self.add_media_button.setEnabled(False)
        self.scanner = FolderScanner(targets)
        self.scanner.files_found.connect(lambda paths, ext=external: self._on_files_found(paths, ext))
        self.scanner.scan_error.connect(self._on_scan_error)
        self.scanner.finished.connect(lambda: self.add_media_button.setEnabled(True))
        self.scanner.start()

    def _on_files_found(self, paths, external=False):
        if self._closing:
            return
        if not paths:
            if not self.files:
                self.status_label.setText("No playable files were found there.")
            else:
                self.status_label.setText("No new playable files were found there.")
            return
        if external:
            # Play the first opened file once it is in the list (or right away if it already was).
            self._ext_play_key = os.path.normcase(paths[0])
        self._pending_paths = list(getattr(self, "_pending_paths", [])) + list(paths)
        if not getattr(self, "_chunk_running", False):
            self._chunk_running = True
            QTimer.singleShot(0, self._add_next_chunk)

    def _play_external_if_ready(self):
        key = self._ext_play_key
        if key is None or key not in self.path_set:
            return False
        self._ext_play_key = None
        for i, p in enumerate(self.files):
            if os.path.normcase(p) == key:
                self.play_index(i)
                return True
        return False

    def _add_next_chunk(self):
        """Adds up to 1,500 files per tick so the window never freezes, even with 100,000+ files."""
        if self._closing:
            return
        pending = getattr(self, "_pending_paths", [])
        if not pending:
            self._chunk_running = False
            return
        chunk, self._pending_paths = pending[:1500], pending[1500:]
        was_empty = len(self.files) == 0

        self.welcome_widget.hide()
        self.playlist.setUpdatesEnabled(False)
        q = getattr(self, "_filter_q", "")
        for path in chunk:
            key = os.path.normcase(path)            # same file twice = skipped; same NAME in another folder = kept
            if key in self.path_set:
                continue
            self.path_set.add(key)
            self.files.append(path)
            name = Path(path).name
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, path)
            self.playlist.addItem(item)
            if q and q not in name.casefold():
                item.setHidden(True)
        self.playlist.setUpdatesEnabled(True)
        self._update_playlist_count()

        if self._play_external_if_ready():
            self._autoplay_pending = False
        elif was_empty and self.files and self._autoplay_pending:
            self._autoplay_pending = False
            self.play_index(0)

        if self._pending_paths:
            self.status_label.setText(f"Loading... {len(self.files):,} added, {len(self._pending_paths):,} to go")
            QTimer.singleShot(0, self._add_next_chunk)
        else:
            self._chunk_running = False
            self._finish_loading()

    def _finish_loading(self):
        self._autoplay_pending = True
        self._ext_play_key = None
        if not self.files:
            self.status_label.setText("Nothing to play yet. Add files or a folder.")
            self.welcome_widget.show()
            self.welcome_widget.raise_()
            return
        if self.current_path:
            self.status_label.setText(f"Playing: {Path(self.current_path).name}")
        else:
            self.status_label.setText(f"Added media. Total: {len(self.files):,} item(s).")

    def _on_scan_error(self, message):
        log.error("Import failed: %s", message)
        self.status_label.setText("Import operation failed.")
        with self._modal():
            QMessageBox.critical(self, "Import error", message)

    def set_shuffle(self, enabled):
        self.shuffle_enabled = enabled
        self._played_paths.clear()
        self._history.clear()
        if enabled and self.current_path:
            self._played_paths.add(self.current_path)

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

    def _mark_playing(self, index):
        """Bold + cyan text for the track that is actually playing."""
        try:
            if self._marked_item is not None:
                f = self._marked_item.font()
                f.setBold(False)
                self._marked_item.setFont(f)
                self._marked_item.setData(Qt.ItemDataRole.ForegroundRole, None)
        except RuntimeError:
            pass
        self._marked_item = None
        item = self.playlist.item(index)
        if item is not None:
            f = item.font()
            f.setBold(True)
            item.setFont(f)
            item.setForeground(QColor("#19c8e6"))
            self._marked_item = item

    def play_index(self, index, _from_prev=False, start=None):
        if not self.files or not (0 <= index < len(self.files)):
            return

        path = self.files[index]
        if self.shuffle_enabled and not _from_prev and self.current_path and self.current_path != path:
            self._history.append(self.current_path)
            if len(self._history) > 500:
                del self._history[:100]
        self._end_event_pending = False
        self.current_index = index
        self.current_path = path
        self._played_paths.add(path)
        self._last_tick_key = None

        self.playlist.setCurrentRow(index)
        self._mark_playing(index)

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
            self._sync_video_overlays()
            if pixmap:
                self.audio_art_label.setPixmap(pixmap.scaled(
                    self.video.size(), Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))
            else:
                side = max(160, min(self.video.width(), self.video.height()) // 3)
                self.audio_art_label.setPixmap(WelcomeScreen.logo_pixmap(side))
            self.audio_art_label.show()
        else:
            self.audio_art_label.hide()

        if self.player:
            self.speed_combo.setCurrentText("1.0x")
            options = {}
            if isinstance(start, (int, float)) and start > 1:
                options["start"] = str(int(start))     # only used to carry on after a failed delete
            try:
                self.player.loadfile(path, mode="replace", **options)
                self.player.pause = False
            except Exception:
                log.exception("Could not start %s", path)
                self.status_label.setText(f"Could not play: {Path(path).name}")
                self._set_play_ui(False)
                return
            self.status_label.setText(f"Playing: {Path(path).name}")
            self._set_play_ui(True)
            self.track_timer.start()

    def play_or_resume(self):
        if not self.player or not self.files:
            return

        try:
            if self.player.idle_active:
                self.play_index(self.current_index if self.current_index >= 0 else 0)
            else:
                self.player.pause = not self.player.pause
                self._set_play_ui(not self.player.pause)
        except Exception:
            log.exception("Play/pause failed")

    def previous_track(self):
        if not self.files:
            return
        if self.shuffle_enabled:
            while self._history:                      # go back to what you really heard before
                path = self._history.pop()
                try:
                    idx = self.files.index(path)
                except ValueError:
                    continue
                self.play_index(idx, _from_prev=True)
                return
            self.play_index(self.current_index if self.current_index >= 0 else 0, _from_prev=True)
        else:
            prev_idx = self.current_index - 1
            if prev_idx < 0:
                prev_idx = len(self.files) - 1
            self.play_index(prev_idx)

    def next_track(self):
        if not self.files:
            return
        if self.shuffle_enabled:
            idx = pick_shuffle_index(self.files, self._played_paths, self.current_index)
            if idx >= 0:
                self.play_index(idx)
        else:
            next_idx = self.current_index + 1
            if next_idx >= len(self.files):
                next_idx = 0
            self.play_index(next_idx)

    def _handle_end_file(self, reason):
        if self._closing:
            return
        reason = str(reason).upper()
        if reason == "ERROR":
            self._error_streak += 1
            name = Path(self.current_path).name if self.current_path else "this file"
            self.status_label.setText(f"Could not play: {name}")
            if self._error_streak <= 5 and len(self.files) > 1:
                QTimer.singleShot(700, self.next_track)        # skip a broken file, but never loop forever
            else:
                self._set_play_ui(False)
            return
        if reason != "EOF":
            return
        if self._end_event_pending:
            return
        self._end_event_pending = True
        self._error_streak = 0
        self.track_timer.stop()

        if self.loop_single_checkbox.isChecked() and self.current_index >= 0:
            self.play_index(self.current_index)
            return

        if self.remove_played_checkbox.isChecked():
            self._remove_current_and_advance()
        else:
            self.next_track()

    def _remove_current_and_advance(self):
        if self.current_index < 0 or self.current_index >= len(self.files):
            return
        idx_to_remove = self.current_index
        path = self.files[idx_to_remove]
        name_key = os.path.normcase(path)
        
        self.path_set.discard(name_key)
        self.files.pop(idx_to_remove)
        self.playlist.takeItem(idx_to_remove)
        self._removed_played_count += 1
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
            self.welcome_widget.show()
            self.welcome_widget.raise_()
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
            log.exception("Could not save settings")
        self._closing = True
        self.track_timer.stop()
        self.hide_timer.stop()
        self._sleep_timer.stop()
        self._sleep_tip_timer.stop()
        self._show_cursor()
        if self.scanner and self.scanner.isRunning():
            self.scanner.requestInterruption()      # stop a long folder scan instead of crashing on exit
            if not self.scanner.wait(5000):
                log.warning("Folder scan was still running when ALMP closed")
        if self.player:
            try:
                self.player.terminate()
            except Exception:
                log.exception("mpv did not close cleanly")
        super().closeEvent(event)


def _show_startup_error(text):
    try:
        _app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841 (keeps it alive)
        QMessageBox.critical(None, "ALMP cannot start", text)
    except Exception:
        pass


if __name__ == "__main__":
    log_path = setup_logging()
    sys.excepthook = _almp_excepthook
    threading.excepthook = _almp_thread_excepthook
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
        # ALMP is already open (or still opening): hand our files to it, then quit.
        from PyQt6.QtCore import QCoreApplication
        _qc = QCoreApplication(sys.argv)
        if not send_paths_to_running_instance(cli_paths):
            log.warning("Could not reach the running ALMP; %d file(s) were not passed on", len(cli_paths))
        sys.exit(0)

    if sys.platform == "win32":
        try:
            myappid = "Alexbed.LightMediaPlayer.ALMP.8.0" 
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
    if MPV_IMPORT_ERROR is not None:
        log.error("libmpv could not be loaded: %r", MPV_IMPORT_ERROR)
        _show_startup_error(
            "The playback engine (mpv-2.dll) could not be loaded.\n\n"
            "Please extract the WHOLE ALMP zip file again into a folder on this computer, "
            "and do not move ALMP.exe out of that folder. If your antivirus program removed "
            "mpv-2.dll, restore it there.\n\nDetails: " + str(MPV_IMPORT_ERROR))
        sys.exit(1)

    # Start listening for "open this file" requests before the window is built, so files
    # opened from Explorer while ALMP is still starting are not lost.
    ipc = SingleInstanceServer(IPC_NAME, app)
    ipc.listen()

    if sys.platform != "win32":
        locale.setlocale(locale.LC_NUMERIC, "C")
    print(f"[ALMP] Qt platform: {app.platformName()}")
    
    dark_stylesheet = """
        QWidget {
            color: #e6e6e6;
            font-family: {UI_FONT_FAMILY};
            font-size: 14px;
        }
        #welcomeTitle { font-size: 30px; font-weight: 700; color: #ffffff; }
        #welcomeTagline { font-size: 16px; color: #9fb3ba; }
        #welcomeHint { font-size: 13px; color: #7f8e94; }
        #welcomePrimary {
            font-size: 16px; font-weight: 700; padding: 13px 34px; border-radius: 10px;
            background-color: #19c8e6; color: #04222a; border: 1px solid #19c8e6;
        }
        #welcomePrimary:hover { background-color: #3ad8f2; }
        #welcomePrimary:pressed { background-color: #12a9c3; }
        #welcomeSecondary {
            font-size: 16px; font-weight: 600; padding: 13px 30px; border-radius: 10px;
            background-color: rgba(255, 255, 255, 16); color: #e6f7fa; border: 1px solid rgba(25, 200, 230, 130);
        }
        #welcomeSecondary:hover { background-color: rgba(25, 200, 230, 46); border-color: #19c8e6; }
        QMenu { background-color: #1a1d1f; border: 1px solid #2c3236; border-radius: 8px; padding: 6px; }
        QMenu::item { padding: 8px 24px; border-radius: 6px; }
        QMenu::item:selected { background-color: #123a44; }
        QMenu::separator { height: 1px; background: #2c3236; margin: 6px 8px; }
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
        QPushButton:focus, QComboBox:focus { border: 2px solid #ffd54a; }
        #playButton:focus, #closeButton:focus, #welcomePrimary:focus, #welcomeSecondary:focus { border: 2px solid #ffd54a; }
        QCheckBox:focus { color: #ffd54a; }

        QListWidget {
            background-color: #101010;
            border: 1px solid #242424;
            border-radius: 8px;
            outline: none;
        }
        QListWidget::item { padding: 6px 8px; border: none; border-radius: 6px; }
        QListWidget::item:hover { background-color: #1d1d1d; }
        QListWidget::item:selected { background-color: #123a44; color: #ffffff; }
        QListWidget:focus { border: 1px solid #ffd54a; }

        QSlider::groove:horizontal { height: 6px; background: #2e2e2e; border-radius: 3px; }
        QSlider::sub-page:horizontal { background: #19c8e6; border-radius: 3px; }
        QSlider::handle:horizontal {
            background: #ffffff; border: none;
            width: 16px; height: 16px; margin: -5px 0; border-radius: 8px;
        }
        QSlider::handle:horizontal:hover { background: #19c8e6; }
        QSlider::handle:horizontal:focus { background: #ffd54a; }

        QCheckBox { spacing: 6px; }
        QCheckBox::indicator {
            width: 16px; height: 16px;
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
        QToolTip { background-color: #1c1c1c; color: #e6e6e6; border: 1px solid #19c8e6; padding: 4px; font-size: 13px; }
    """
    dark_stylesheet = dark_stylesheet.replace("{UI_FONT_FAMILY}", UI_FONT_FAMILY)
    app.setProperty("almp_base_qss", dark_stylesheet)
    try:
        _hc = bool(load_settings().get("high_contrast", False))
    except Exception:
        _hc = False
    app.setStyleSheet(dark_stylesheet + (HIGH_CONTRAST_QSS if _hc else ""))

    icon_path = get_app_icon_path()
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))

    removed = remove_legacy_history_files()
    if removed:
        log.info("Removed old history files from earlier versions: %s", ", ".join(removed))

    window = MediaWindow()
    if icon_path:
        window.setWindowIcon(QIcon(icon_path))
    if sys.platform != "win32":
        app.setDesktopFileName("ALMP")
    _EXCEPTION_NOTIFY = window.notify_error

    window.show()
    if cli_paths:
        window.open_external(cli_paths)
    window.attach_ipc_server(ipc)
    rc = app.exec()
    if window.scanner is not None and window.scanner.isRunning():
        # A folder scan is stuck on a slow drive: exit at once instead of letting Qt abort.
        logging.shutdown()
        os._exit(rc)
    sys.exit(rc)