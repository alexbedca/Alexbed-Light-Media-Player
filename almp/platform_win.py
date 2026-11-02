# Alexbed Light Media Player (ALMP)
# Copyright (C) 2026 Alexander Bediako
# SPDX-License-Identifier: GPL-3.0-or-later
"""Windows-only calls. Every function here is safe to call on any system: off Windows it does
nothing (or returns a "not available" answer), and on Windows every call is guarded.

Registry changes are for the CURRENT USER only (HKEY_CURRENT_USER), never for the whole PC,
need no administrator rights, and each one has a matching "remove" function.
"""
import ntpath
import os
import subprocess
import sys
from pathlib import Path

from .logsetup import log
from .media import AUDIO_EXTENSIONS, PLAYLIST_EXTENSIONS, VIDEO_EXTENSIONS

if sys.platform == "win32":
    import ctypes
    import winreg
    from ctypes import wintypes
else:                      # names exist so tests can patch them
    ctypes = None
    winreg = None
    wintypes = None

APP_USER_MODEL_ID = "Alexbed.ALMP"          # no version in it, so taskbar pins survive updates

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
    except Exception:          # noqa: BLE001 - unknown means "warn before deleting"
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
        except OSError:
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
    except Exception:          # noqa: BLE001 - leave the file alone on any failure
        log.exception("Recycle Bin call failed for %s", file_path)
        return DELETE_FAILED


# --- Small helpers ---

def set_app_user_model_id():
    if sys.platform != "win32":
        return False
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        return True
    except Exception:          # noqa: BLE001
        log.debug("SetCurrentProcessExplicitAppUserModelID failed", exc_info=True)
        return False


def windows_dir():
    return os.environ.get("SystemRoot") or os.environ.get("windir") or r"C:\Windows"


def windows_powershell_path():
    """Full path to Windows PowerShell in System32, so a file called powershell.exe in the
    ALMP folder or the current folder can never be run instead."""
    return os.path.join(windows_dir(), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")


def show_in_explorer(path):
    """Open Explorer with the file selected. Returns True if Explorer was started."""
    if sys.platform != "win32":
        return False
    try:
        explorer = os.path.join(windows_dir(), "explorer.exe")
        # Explorer wants exactly:  explorer.exe /select,"C:\path\file.mp3"
        subprocess.Popen(f'"{explorer}" /select,"{os.path.normpath(path)}"')
        return True
    except OSError:
        log.exception("Could not open Explorer for %s", path)
        return False


def resolve_app_exe_path():
    """Full path of ALMP.exe when running the built app (None when run from source with python)."""
    def _ok(path):
        return bool(path) and os.path.isfile(path) and \
            os.path.basename(path).lower() not in ("python.exe", "pythonw.exe", "python", "python3")

    candidates = []
    try:
        if sys.platform == "win32":
            buf = ctypes.create_unicode_buffer(32768)
            ctypes.windll.kernel32.GetModuleFileNameW(None, buf, 32768)
            candidates.append(buf.value)
        else:
            candidates.append(os.path.realpath("/proc/self/exe"))
    except Exception:          # noqa: BLE001
        log.debug("GetModuleFileNameW failed", exc_info=True)
    candidates.append(os.environ.get("NUITKA_ONEFILE_BINARY", ""))
    candidates.append(sys.argv[0] if sys.argv else "")
    try:
        candidates.append(os.path.join(__compiled__.containing_dir, "ALMP.exe"))  # noqa: F821 (Nuitka)
    except NameError:
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
        except Exception:          # noqa: BLE001
            continue
    return None


# --- Default player and "Play with ALMP" (current user only, reversible) ---

HKCU_CLASSES = r"Software\Classes"
PROG_ID = "ALMP.Media"
FOLDER_VERB = "ALMP.PlayFolder"
REGISTERED_APP = "ALMP"
CAPABILITIES_KEY = r"Software\ALMP\Capabilities"
ALL_ASSOC_EXTENSIONS = tuple(sorted(AUDIO_EXTENSIONS)) + tuple(sorted(VIDEO_EXTENSIONS)) + tuple(sorted(PLAYLIST_EXTENSIONS))
REG_SZ, REG_NONE = 1, 0


def _cmd(exe):
    return f'"{exe}" "%1"'


def default_player_entries(exe, extensions=ALL_ASSOC_EXTENSIONS):
    """The registry values that make ALMP appear in "Open with" and in Settings > Default apps.
    Same values as Set-ALMP-Defaults.bat. List of (key, value_name or "" for default, data, type)."""
    c = HKCU_CLASSES
    e = [
        (rf"{c}\{PROG_ID}", "", "ALMP Media File", REG_SZ),
        (rf"{c}\{PROG_ID}\DefaultIcon", "", f'"{exe}",0', REG_SZ),
        (rf"{c}\{PROG_ID}\shell\open\command", "", _cmd(exe), REG_SZ),
        (rf"{c}\{PROG_ID}\shell\open", "MultiSelectModel", "Player", REG_SZ),
        (rf"{c}\Applications\ALMP.exe", "FriendlyAppName", "ALMP Media Player", REG_SZ),
        (rf"{c}\Applications\ALMP.exe\shell\open\command", "", _cmd(exe), REG_SZ),
        (rf"{c}\Applications\ALMP.exe\shell\open", "MultiSelectModel", "Player", REG_SZ),
        (CAPABILITIES_KEY, "ApplicationName", "ALMP", REG_SZ),
        (CAPABILITIES_KEY, "ApplicationDescription", "Alexbed Light Media Player", REG_SZ),
        (r"Software\RegisteredApplications", REGISTERED_APP, CAPABILITIES_KEY, REG_SZ),
    ]
    for ext in extensions:
        e.append((rf"{c}\{ext}\OpenWithProgids", PROG_ID, None, REG_NONE))
        e.append((rf"{c}\Applications\ALMP.exe\SupportedTypes", ext, "", REG_SZ))
        e.append((rf"{CAPABILITIES_KEY}\FileAssociations", ext, PROG_ID, REG_SZ))
    return e


def folder_verb_entries(exe):
    """Right-click a folder in Explorer > "Play with ALMP"."""
    base = rf"{HKCU_CLASSES}\Directory\shell\{FOLDER_VERB}"
    return [
        (base, "", "Play with ALMP", REG_SZ),
        (base, "MUIVerb", "Play with ALMP", REG_SZ),
        (base, "Icon", f'"{exe}",0', REG_SZ),
        (base, "MultiSelectModel", "Player", REG_SZ),
        (rf"{base}\command", "", _cmd(exe), REG_SZ),
    ]


def default_player_removals(extensions=ALL_ASSOC_EXTENSIONS):
    """What Remove-ALMP-Defaults.bat removes (association part): (key, value_name or None = whole key)."""
    c = HKCU_CLASSES
    out = [(rf"{c}\{ext}\OpenWithProgids", PROG_ID) for ext in extensions]
    out += [(rf"{c}\{PROG_ID}", None), (rf"{c}\Applications\ALMP.exe", None),
            (r"Software\ALMP", None), (r"Software\RegisteredApplications", REGISTERED_APP)]
    return out


def folder_verb_removals():
    return [(rf"{HKCU_CLASSES}\Directory\shell\{FOLDER_VERB}", None)]


def _apply_entries(entries):
    for key, name, data, kind in entries:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as k:
            if kind == REG_NONE:
                winreg.SetValueEx(k, name, 0, winreg.REG_NONE, None)
            else:
                winreg.SetValueEx(k, name, 0, winreg.REG_SZ, data)


def _delete_tree(root, key):
    try:
        with winreg.OpenKey(root, key, 0, winreg.KEY_READ | winreg.KEY_WRITE) as k:
            while True:
                try:
                    sub = winreg.EnumKey(k, 0)
                except OSError:
                    break
                _delete_tree(root, key + "\\" + sub)
        winreg.DeleteKey(root, key)
    except FileNotFoundError:
        pass


def _apply_removals(removals):
    for key, name in removals:
        try:
            if name is None:
                _delete_tree(winreg.HKEY_CURRENT_USER, key)
            else:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as k:
                    winreg.DeleteValue(k, name)
        except FileNotFoundError:
            continue


def _notify_shell():
    try:
        SHCNE_ASSOCCHANGED, SHCNF_IDLIST = 0x08000000, 0
        ctypes.windll.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None)
    except Exception:          # noqa: BLE001
        log.debug("SHChangeNotify failed", exc_info=True)


def can_register(exe):
    """Registering only makes sense for the real ALMP.exe on Windows (not `python main.py`)."""
    return sys.platform == "win32" and bool(exe) and os.path.basename(exe).lower() == "almp.exe" \
        and os.path.isfile(exe)


def register_default_player(exe):
    """Returns (ok, message). The user still has to press "Set default" in Windows Settings
    (Windows does not let any program do that silently); open_default_apps_settings() opens it."""
    if not can_register(exe):
        return False, "This only works in ALMP.exe on Windows."
    try:
        _apply_entries(default_player_entries(exe))
        _notify_shell()
        return True, ""
    except OSError as e:
        log.exception("Could not register ALMP as a player")
        return False, str(e)


def unregister_default_player():
    if sys.platform != "win32":
        return False, "Windows only."
    try:
        _apply_removals(default_player_removals())
        _notify_shell()
        return True, ""
    except OSError as e:
        log.exception("Could not remove ALMP's file associations")
        return False, str(e)


def open_default_apps_settings():
    """Opens Settings > Default apps on ALMP (a local Windows page, nothing is downloaded)."""
    if sys.platform != "win32":
        return False
    try:
        os.startfile("ms-settings:defaultapps?registeredAppUser=ALMP")       # noqa: S606
        return True
    except OSError:
        log.exception("Could not open Default apps")
        return False


def folder_verb_installed():
    if sys.platform != "win32":
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"{HKCU_CLASSES}\Directory\shell\{FOLDER_VERB}\command"):
            return True
    except OSError:
        return False


def set_folder_verb(exe, enabled):
    if sys.platform != "win32":
        return False, "Windows only."
    try:
        if enabled:
            if not can_register(exe):
                return False, "This only works in ALMP.exe on Windows."
            _apply_entries(folder_verb_entries(exe))
        else:
            _apply_removals(folder_verb_removals())
        return True, ""
    except OSError as e:
        log.exception("Could not change the folder menu entry")
        return False, str(e)


# --- Run at Startup (a shortcut in the user's Startup folder) ---

WIN_STARTUP_DIR = Path(os.getenv("APPDATA") or Path.home()) / r"Microsoft\Windows\Start Menu\Programs\Startup"
WIN_SHORTCUT = WIN_STARTUP_DIR / "ALMP.lnk"
STARTUP_MARKER = Path(os.getenv("APPDATA") or Path.home()) / "ALMP" / "startup_target.txt"
LEGACY_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
LEGACY_RUN_VALUE = "AlexbedLightMediaPlayer"


def _ps_quote(v):
    return "'" + str(v).replace("'", "''") + "'"


def _run_powershell(script, timeout=60):
    return subprocess.run([windows_powershell_path(), "-NoProfile", "-NonInteractive", "-Command", script],
                          capture_output=True, text=True, timeout=timeout,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def write_startup_shortcut(exe_path):
    """Creates the Startup-folder shortcut. Returns (ok, details). Call it from a worker thread."""
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut(%s);"
          "$s.TargetPath=%s;$s.WorkingDirectory=%s;$s.IconLocation=%s;$s.Save()"
          % (_ps_quote(WIN_SHORTCUT), _ps_quote(exe_path), _ps_quote(os.path.dirname(exe_path)), _ps_quote(exe_path)))
    try:
        WIN_STARTUP_DIR.mkdir(parents=True, exist_ok=True)
        if WIN_SHORTCUT.exists():
            WIN_SHORTCUT.unlink()
        r = _run_powershell(ps)
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"PowerShell could not run: {e}"
    if r.returncode != 0 or not WIN_SHORTCUT.exists():
        return False, f"PowerShell exit code {r.returncode}: {(r.stderr or '').strip()[:500]}"
    try:
        STARTUP_MARKER.parent.mkdir(parents=True, exist_ok=True)
        STARTUP_MARKER.write_text(os.path.normcase(exe_path), encoding="utf-8")
    except OSError:
        log.warning("Could not write %s", STARTUP_MARKER)
    return True, ""


def remove_startup_shortcut():
    if WIN_SHORTCUT.exists():
        WIN_SHORTCUT.unlink()


def repair_startup_shortcut(exe_path):
    """If the ALMP folder was moved, point the existing startup shortcut at the new place."""
    try:
        if STARTUP_MARKER.exists() and \
           STARTUP_MARKER.read_text(encoding="utf-8").strip() == os.path.normcase(exe_path):
            return
        r = _run_powershell("(New-Object -ComObject WScript.Shell).CreateShortcut(%s).TargetPath"
                            % _ps_quote(WIN_SHORTCUT))
        target = os.path.normcase(os.path.normpath(r.stdout.strip())) if r.stdout.strip() else ""
        if target != os.path.normcase(exe_path):
            ok, details = write_startup_shortcut(exe_path)
            if not ok:
                log.warning("Could not repair the startup shortcut: %s", details)
    except Exception:          # noqa: BLE001 - runs in a background thread
        log.exception("Startup shortcut check failed")


def remove_legacy_run_value():
    """Old versions used a Run registry value; it is removed once (the shortcut replaced it)."""
    if sys.platform != "win32":
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, LEGACY_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            try:
                winreg.DeleteValue(key, LEGACY_RUN_VALUE)
            except FileNotFoundError:
                pass
    except OSError:
        log.debug("Could not open the Run key", exc_info=True)
