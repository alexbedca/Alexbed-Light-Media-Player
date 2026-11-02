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
from .logsetup import install_hooks, log, set_exception_notify, setup_logging
from .paths import SOURCE_ROOT, get_app_icon_path, is_compiled
from .settings import effective_settings, load_settings, migrate_settings_file, remove_legacy_history_files

# --- Linux: embed mpv through X11 ---
if sys.platform.startswith("linux") and "QT_QPA_PLATFORM" not in os.environ and os.environ.get("DISPLAY"):
    os.environ["QT_QPA_PLATFORM"] = "xcb"


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
        subprocess.Popen(cmd, close_fds=True, creationflags=flags,
                         cwd=os.path.dirname(cmd[-1]) or None)
        log.info("Restarting ALMP for the new interface size")
    except OSError:
        log.exception("Could not restart ALMP")


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    setup_logging()
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
        if not send_paths_to_running_instance(cli_paths):
            log.warning("Could not reach the running ALMP; %d file(s) were not passed on", len(cli_paths))
        return 0

    pw.set_app_user_model_id()

    settings = effective_settings(load_settings())
    scale = 1.0
    if "QT_SCALE_FACTOR" not in os.environ:
        scale = float(settings["ui_scale"])
        if abs(scale - 1.0) > 0.01:
            os.environ["QT_SCALE_FACTOR"] = str(scale)
    else:
        try:
            scale = float(os.environ["QT_SCALE_FACTOR"])
        except ValueError:
            scale = 1.0

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
    if cli_paths:
        window.open_external(cli_paths)
    window.attach_ipc_server(ipc)
    rc = app.exec()
    restart = window._restart_requested
    if restart:
        lock_file.unlock()            # the new ALMP must be able to take the single-instance lock
        try:
            ipc.server.close()
        except RuntimeError:
            pass
        _spawn_restart()
    if window.any_scan_running():
        # A folder scan is stuck on a slow drive: exit at once instead of letting Qt abort.
        logging.shutdown()
        os._exit(rc)
    return rc
