# Alexbed Light Media Player (ALMP)
# Copyright (C) 2026 Alexander Bediako
# SPDX-License-Identifier: GPL-3.0-or-later
"""Start-up: logging, single instance, interface size, style, the window, and a clean exit."""
import locale
import logging
import os
import subprocess
import sys

from . import __version__
from . import platform_win as pw
from . import settings as settings_file
from .datafolder import migrate_legacy_files
from .logsetup import (
    finish_logging,
    install_hooks,
    log,
    seconds_since_start,
    set_exception_notify,
    setup_logging,
    start_new_run_log,
)
from .paths import (
    SOURCE_ROOT,
    get_app_icon_path,
    init_data_dir,
    is_compiled,
    legacy_log_dir,
    legacy_settings_dir,
)
from .settings import effective_settings, load_settings, migrate_settings_file, remove_legacy_history_files

# --- Linux: embed mpv through X11 ---
if sys.platform.startswith("linux") and "QT_QPA_PLATFORM" not in os.environ and os.environ.get("DISPLAY"):
    os.environ["QT_QPA_PLATFORM"] = "xcb"


# Qt 6.8+ reads the font list through DirectWrite, which opens every installed font the first time
# any text is measured. On a PC with 9,223 fonts that took 5 to 70 s before the window appeared.
# Qt's older GDI font list (its default up to Qt 6.7) lists the same fonts in about 0.05 s.
WINDOWS_QT_PLATFORM = "windows:fontengine=gdi"


def qt_platform_override(environ, platform=None):
    """The QT_QPA_PLATFORM value ALMP sets before Qt starts, or None to leave it alone.
    A value the user set themselves always wins."""
    platform = sys.platform if platform is None else platform
    if platform != "win32" or environ.get("QT_QPA_PLATFORM"):
        return None
    return WINDOWS_QT_PLATFORM


def _add_runtime_to_path():
    from .paths import get_resource_path
    runtime_dir = get_resource_path("runtime")
    if os.path.isdir(runtime_dir):
        os.environ["PATH"] = runtime_dir + os.pathsep + os.environ.get("PATH", "")


def _show_startup_error(text):
    from PyQt6.QtWidgets import QApplication, QMessageBox
    try:
        _app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841 (keeps it alive)
        QMessageBox.critical(None, "ALMP cannot start", text)
    except Exception:          # noqa: BLE001
        log.exception("Could not show the start-up error")


def restart_command():
    """How to start ALMP again (after 'Apply now' for the interface size)."""
    if is_compiled():
        exe = pw.resolve_app_exe_path() or sys.executable
        return [exe]
    return [sys.executable, str(SOURCE_ROOT / "main.py")]


def _spawn_restart():
    cmd = restart_command()
    try:
        flags = 0
        if sys.platform == "win32":
            flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        env = dict(os.environ)
        if env.pop("ALMP_SET_SCALE_FACTOR", None):
            # We set QT_SCALE_FACTOR ourselves from the settings; the new process must read the
            # (possibly changed) setting again instead of inheriting the old size.
            env.pop("QT_SCALE_FACTOR", None)
        subprocess.Popen(cmd, close_fds=True, creationflags=flags, env=env,
                         cwd=os.path.dirname(cmd[-1]) or None)
        log.info("Restarting ALMP for the new interface size")
    except OSError:
        log.exception("Could not restart ALMP")


def prepare_data_folder():
    """Choose where ALMP keeps its files (Data next to ALMP.exe, or the old folders if that cannot be
    written), move files from older versions there, and start the log. Returns (folder, portable,
    migration result, log mode)."""
    folder, portable = init_data_dir()
    settings_file.use_folder(folder)
    moved = migrate_legacy_files(folder, legacy_settings_dir(), legacy_log_dir()) if portable else None
    log_mode = effective_settings(load_settings())["log_mode"]
    setup_logging(log_mode)
    if not portable:
        log.info("The Data folder next to ALMP cannot be written to; using %s", folder)
    if moved and (moved["copied"] or moved["removed"] or moved["error"]):
        log.info("Files from an older ALMP: copied %s, removed %d, error: %s",
                 moved["copied"], len(moved["removed"]), moved["error"] or "none")
    return folder, portable, moved, log_mode


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    _folder, _portable, _moved, log_mode = prepare_data_folder()
    install_hooks()
    if sys.platform != "win32":
        try:
            import faulthandler
            faulthandler.enable()
        except (ImportError, RuntimeError, ValueError):
            pass
    _add_runtime_to_path()

    from PyQt6.QtCore import QCoreApplication, QLockFile, QStandardPaths
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QApplication

    from .ipc import IPC_NAME, SingleInstanceServer, send_paths_to_running_instance

    temp_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation)
    lock_file = QLockFile(os.path.join(temp_dir, "ALMP.lock"))
    cli_paths = [os.path.abspath(a) for a in argv[1:] if a and not a.startswith("-")]
    if not lock_file.tryLock(100):
        # ALMP is already open (or still opening): hand our files to it, then quit.
        _qc = QCoreApplication(argv)  # noqa: F841
        # "Add to ALMP playlist" (right-click menu): tell the running ALMP not to interrupt what plays.
        message = ([pw.ADD_FLAG] if pw.ADD_FLAG in argv[1:] else []) + cli_paths
        if not send_paths_to_running_instance(message):
            log.warning("Could not reach the running ALMP; %d file(s) were not passed on", len(cli_paths))
        return 0
    if log_mode == "keep":
        start_new_run_log()

    # v8.2.8: no explicit AppUserModelID. Windows groups ALMP's window with its taskbar pin by ALMP.exe's
    # path; an own ID made a pin of ALMP.exe (or its shortcut) show a second taskbar button when playing.

    settings = effective_settings(load_settings())
    scale = 1.0
    if "QT_SCALE_FACTOR" not in os.environ:
        scale = float(settings["ui_scale"])
        if abs(scale - 1.0) > 0.01:
            os.environ["QT_SCALE_FACTOR"] = str(scale)
            os.environ["ALMP_SET_SCALE_FACTOR"] = "1"
    else:
        try:
            scale = float(os.environ["QT_SCALE_FACTOR"])
        except ValueError:
            scale = 1.0

    qpa = qt_platform_override(os.environ)
    if qpa:
        os.environ["QT_QPA_PLATFORM"] = qpa
    app = QApplication(argv)
    app.setApplicationName("ALMP")
    app.setApplicationVersion(__version__)

    from .player import MPV_IMPORT_ERROR
    if MPV_IMPORT_ERROR is not None:
        log.error("libmpv could not be loaded: %r", MPV_IMPORT_ERROR)
        _show_startup_error(
            "The playback engine (mpv-2.dll) could not be loaded.\n\n"
            "Please extract the WHOLE ALMP zip file again into a folder on this computer, "
            "and do not move ALMP.exe out of that folder. If your antivirus program removed "
            "mpv-2.dll, restore it there.\n\nDetails: " + str(MPV_IMPORT_ERROR))
        return 1

    # Start listening for "open this file" requests before the window is built, so files
    # opened from Explorer while ALMP is still starting are not lost.
    ipc = SingleInstanceServer(IPC_NAME, app)
    ipc.listen()

    if sys.platform != "win32":
        locale.setlocale(locale.LC_NUMERIC, "C")      # libmpv needs "C" number formatting
    log.debug("Qt platform: %s", app.platformName())

    from .theme import stylesheet
    settings = migrate_settings_file()
    app.setStyleSheet(stylesheet(bool(settings["high_contrast"])))

    icon_path = get_app_icon_path()
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))

    removed = remove_legacy_history_files()
    if removed:
        log.info("Removed old history files from earlier versions: %s", ", ".join(removed))

    from .ui import MediaWindow
    window = MediaWindow(running_scale=scale)
    if sys.platform != "win32":
        app.setDesktopFileName("ALMP")
    set_exception_notify(window.notify_error)

    window.show()
    log.info("Start-up: window shown after %.1f s", seconds_since_start())
    if qpa or "fontengine=gdi" in os.environ.get("QT_QPA_PLATFORM", ""):
        from .titlefonts import register_thin_title_fonts
        log.debug("Thin title-bar fonts added: %s", register_thin_title_fonts())
    if cli_paths:
        if len(cli_paths) == 1 and os.path.isfile(cli_paths[0]):
            window.set_playlist_panel(False, auto=True)     # one file double-clicked: all room for the video
        window.open_external(cli_paths, wait_ms=0)
    window.attach_ipc_server(ipc)
    rc = app.exec()
    log_mode = window.settings.get("log_mode", log_mode)
    restart = window._restart_requested
    if restart:
        lock_file.unlock()            # the new ALMP must be able to take the single-instance lock
        try:
            ipc.server.close()
        except RuntimeError:
            pass
        _spawn_restart()
    # A normal close: the log is cleared unless this run wrote an error (Settings > Privacy).
    finish_logging(log_mode)
    if window.any_scan_running():
        # A folder scan is stuck on a slow drive: exit at once instead of letting Qt abort.
        logging.shutdown()
        os._exit(rc)
    return rc
