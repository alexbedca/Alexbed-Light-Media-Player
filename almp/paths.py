# Alexbed Light Media Player (ALMP)
# Copyright (C) 2026 Alexander Bediako
# SPDX-License-Identifier: GPL-3.0-or-later
"""Where ALMP finds its own files (icons, licences) and where it keeps settings and the log."""
import os
import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
SOURCE_ROOT = PACKAGE_DIR.parent            # the folder that holds main.py when run from source


def is_compiled():
    """True in the Nuitka/PyInstaller build (ALMP.exe), False when run with `python main.py`."""
    return hasattr(sys, "frozen") or "__compiled__" in globals()


def app_dir():
    """The folder ALMP's own files are in: next to ALMP.exe, or the source folder."""
    if hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    if is_compiled():
        return os.path.dirname(sys.executable)
    return str(SOURCE_ROOT)


def get_resource_path(relative_path):
    return os.path.join(app_dir(), relative_path)


def get_app_icon_path():
    names = ["icon.ico"] if sys.platform == "win32" else ["icon.png", "icon.ico"]
    for n in names:
        p = get_resource_path(n)
        if os.path.exists(p):
            return p
    return ""


def get_log_dir():
    """Where almp.log goes: %LOCALAPPDATA%\\ALMP on Windows, ~/.cache/ALMP elsewhere."""
    base = os.getenv("LOCALAPPDATA") or os.getenv("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "ALMP"


def get_settings_dir():
    return Path(os.getenv("APPDATA") or (Path.home() / ".config")) / "ALMP"
