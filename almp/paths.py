# Alexbed Light Media Player (ALMP)
# Copyright (C) 2026 Alexander Bediako
# SPDX-License-Identifier: GPL-3.0-or-later
"""Where ALMP finds its own files (icons, licences) and where it keeps settings and the log.

Since 8.2.4 ALMP keeps everything it writes (settings.json, positions.json, almp.log, ...) in a
"Data" folder next to ALMP.exe (next to main.py when run from source), so nothing is left on the
PC when the ALMP folder is deleted. Only when that folder cannot be written to (Program Files, a
read-only USB stick) does it fall back to %APPDATA%\\ALMP (settings) and %LOCALAPPDATA%\\ALMP (log).
"""
import os
import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
SOURCE_ROOT = PACKAGE_DIR.parent            # the folder that holds main.py when run from source

DATA_DIR_NAME = "Data"
# Tests, benchmarks and test scripts can point ALMP at another folder (never at the real one).
DATA_DIR_ENV = "ALMP_DATA_DIR"
_WRITE_PROBE = ".almp-write-test"

_data_dir = None          # set once by init_data_dir(); None = not decided yet (old folders are used)
_portable = False


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


def legacy_log_dir():
    """Where almp.log was kept up to 8.2.3: %LOCALAPPDATA%\\ALMP on Windows, ~/.cache/ALMP elsewhere."""
    base = os.getenv("LOCALAPPDATA") or os.getenv("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "ALMP"


def legacy_settings_dir():
    """Where settings.json was kept up to 8.2.3: %APPDATA%\\ALMP (~/.config/ALMP elsewhere)."""
    return Path(os.getenv("APPDATA") or (Path.home() / ".config")) / "ALMP"


def folder_is_writable(folder):
    """Create `folder` if needed and check that a file can really be written there.
    (os.access is not enough on Windows: it says yes for Program Files.)"""
    folder = Path(folder)
    probe = folder / _WRITE_PROBE
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        try:
            if probe.exists():
                probe.unlink()
        except OSError:
            pass
        return False


def portable_data_dir(base=None):
    """The Data folder next to ALMP.exe (or main.py), or the folder named in ALMP_DATA_DIR."""
    override = os.environ.get(DATA_DIR_ENV)
    if base is None and override:
        return Path(override)
    return Path(base if base is not None else app_dir()) / DATA_DIR_NAME


def init_data_dir(base=None):
    """Decide once, at start, where ALMP's files go. Returns (folder, portable).
    portable=False means the Data folder could not be written and the old folders are used."""
    global _data_dir, _portable
    candidate = portable_data_dir(base)
    if folder_is_writable(candidate):
        _data_dir, _portable = candidate, True
    else:
        _data_dir, _portable = None, False
    return (_data_dir if _portable else legacy_settings_dir()), _portable


def reset_data_dir():
    """Forget the decision (tests only)."""
    global _data_dir, _portable
    _data_dir, _portable = None, False


def data_dir_is_portable():
    return _portable


def get_log_dir():
    """Where almp.log goes: the Data folder, or %LOCALAPPDATA%\\ALMP if Data cannot be written."""
    return _data_dir if _portable else legacy_log_dir()


def get_settings_dir():
    """Where settings.json goes: the Data folder, or %APPDATA%\\ALMP if Data cannot be written."""
    return _data_dir if _portable else legacy_settings_dir()
