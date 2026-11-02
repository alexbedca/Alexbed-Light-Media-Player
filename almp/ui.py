# Alexbed Light Media Player (ALMP)
# Copyright (C) 2026 Alexander Bediako
# SPDX-License-Identifier: GPL-3.0-or-later
"""The main window. Decisions live in logic.py / store.py / settings.py; this file wires them to
Qt and mpv. Rules kept from v8.0.x: start clean (no playlist is ever restored), the loop mode is
never saved, Delete never deletes without a clear question, nothing connects to the internet."""
import os
import sys
import threading
import time
from collections import deque
from pathlib import Path

from PyQt6.QtCore import QEvent, QEventLoop, QObject, QPoint, QSize, QStandardPaths, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import (
    QCursor,
    QDesktopServices,
    QFontMetrics,
    QGuiApplication,
    QIcon,
    QImage,
    QKeySequence,
    QPixmap,
    QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from . import APP_TITLE, __version__
from . import platform_win as pw
from .dialogs import AboutDialog, HelpDialog, SettingsDialog, describe_engine
from .logic import (
    LARGE_BUTTON_MODES,
    LOOP_ALL,
    LOOP_LABELS,
    LOOP_MODES,
    LOOP_OFF,
    LOOP_ONE,
    LOOP_QUICK_END_LIMIT,
    LOOP_QUICK_END_SECONDS,
    LOOP_TIPS,
    REMOVE_PLAYED_LOOP_ALL_TIP,
    REMOVE_PLAYED_TIP,
    SLEEP_CLOSE,
    SLEEP_PAUSE,
    SPEED_CHOICES,
    MediaCommandFilter,
    add_to_queue,
    decide_after_track_end,
    extend_sleep_ms,
    fmt_time,
    next_from_queue,
    next_loop_mode,
    parse_speed,
    pick_shuffle_index,
    remove_played_for_loop,
    remove_played_to_save,
    resume_start_for,
    sleep_fade_factor,
    sleep_minutes_left,
    speed_for_new_track,
    tv_scale,
    update_resume_table,
)
from .logsetup import log
from .media import (
    AUDIO_EXTENSIONS,
    PLAYLIST_EXTENSIONS,
    SUPPORTED_EXTENSIONS,
    VIDEO_EXTENSIONS,
    is_audio_path,
    write_playlist_file,
)
from .naturalsort import natural_name_key, natural_path_key
from .paths import get_app_icon_path, is_compiled
from .player import (
    BOOST_MAX_VOLUME,
    MPV_IMPORT_ERROR,
    NORMAL_MAX_VOLUME,
    VIDEO_SIZE_NAMES,
    get_mpv_end_reason,
    mpv,
    mpv_options,
    next_video_size,
    set_audio_filter,
    set_prop,
    subtitle_background_options,
    video_size_properties,
)
from .playlist_model import PlaylistModel
from .scanner import FolderScanner
from .settings import (
    SCALE_CHOICES,
    effective_settings,
    forget_positions,
    load_positions,
    load_settings,
    save_positions,
    save_settings,
    settings_to_save,
    update_settings,
)
from .smtc import WindowsMediaControls, previous_start_crashed
from .store import PlaylistStore
from .theme import ICON_ON_ACCENT, accent, icon_color, make_icon, stylesheet
from .widgets import ClickSeekSlider, CustomConfirmDialog, FullscreenTitlePill, PlaylistView, WelcomeScreen, logo_pixmap

APP_EXE_PATH = pw.resolve_app_exe_path()
LINUX_AUTOSTART_DIR = Path.home() / ".config" / "autostart"
LINUX_DESKTOP_FILE = LINUX_AUTOSTART_DIR / "almp.desktop"
CHUNK_ROWS = 5000            # rows added to the list per event-loop turn (about 5-15 ms of work)
ICON_PX = 18


class _Bridge(QObject):
    end_file = pyqtSignal(str)
    startup_done = pyqtSignal(bool, str)
    sorted_ready = pyqtSignal(object, int, str)


class MediaWindow(QMainWindow):
    def __init__(self, running_scale=1.0):
        super().__init__()
        self.running_scale = running_scale
        self.setWindowTitle(f"{APP_TITLE} {__version__}")
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        icon_file_path = get_app_icon_path()
        if icon_file_path:
            self.setWindowIcon(QIcon(icon_file_path))

        self.settings = effective_settings(load_settings())
        self.store = PlaylistStore()
        self.model = PlaylistModel(self.store, self)
        self.queue = []                    # "Play next" (paths), used before shuffle / order
        self.model.queued = self._queue_position
        self.shuffle_enabled = True
        self._played_paths = set()
        self._history = []
        self._autoplay_pending = True
        self._ext_play_key = None          # file opened from Explorer that should start playing
        self._removed_played_count = 0
        self._modal_depth = 0
        self._error_streak = 0
        self._loop_mode = LOOP_OFF          # temporary: never saved, always Off at start
        self._remove_played_saved = None    # user's own "Remove played" while Loop All overrides it
        self._quick_end_streak = 0
        self._play_started = 0.0
        self._playlist_ended = False
        self._stopped_by_sleep = False
        self._high_contrast = bool(self.settings["high_contrast"])
        self._video_size = self.settings["video_size"]
        self._sleep_minutes = 0
        self._sleep_action = SLEEP_PAUSE
        self._sleep_end_of_track = False
        self._sleep_timer = QTimer(self)
        self._sleep_timer.setSingleShot(True)
        self._sleep_timer.timeout.connect(self._sleep_timer_fired)
        self._sleep_tip_timer = QTimer(self)      # keeps "x min left" in the tooltip up to date
        self._sleep_tip_timer.setInterval(20000)
        self._sleep_tip_timer.timeout.connect(self._update_sleep_button)
        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(1000)
        self._fade_timer.timeout.connect(self._apply_sleep_fade)
        self._bridge = _Bridge(self)
        self._bridge.startup_done.connect(self._on_startup_result)
        self._bridge.sorted_ready.connect(self._on_sorted_ready)
        self._startup_busy = False
        self.scanner = None
        self._old_scanners = []
        self._scan_job = 0
        self._scan_queue = []
        self._scan_active = False
        self._scan_external = False
        self._scan_first_batch = False
        self._scan_found = 0
        self._pending = deque()
        self._chunk_running = False
        self._closing = False
        self._restart_requested = False
        self.player = None
        self._is_scrubbing = False
        self._pre_mute_volume = 100
        self._is_cursor_hidden = False
        self._dialog_active = False
        self._is_fullscreen = False
        self._fs_drawer_wanted = False
        self._fs_key_time = 0.0          # last key pressed in the fullscreen playlist drawer
        self._fs_title_full = ""
        self._fs_title_key = None
        self._pre_fs_maximized = False
        self._pre_fs_geometry = None
        self._end_event_pending = False
        self._ext_queue = []
        self._last_ext_time = -1e9
        self._last_tick_key = None
        self._bar_mode = None
        self._bar_widths = None
        self._sort_busy = False
        self.ipc_server = None
        self._media_filter = MediaCommandFilter()
        self.media_controls = None
        self._media_controls_note = ""
        self._positions = load_positions() if self.settings["resume_long_files"] else {}
        if not self.settings["resume_long_files"]:
            forget_positions()             # privacy: no saved places unless the option is on

        self.track_timer = QTimer(self)
        self.track_timer.setInterval(250)
        self.track_timer.timeout.connect(self._poll_player_metrics)

        self.hide_timer = QTimer(self)
        self.hide_timer.setInterval(3000)
        self.hide_timer.timeout.connect(self._hide_fullscreen_overlays)

        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(180)
        self._filter_timer.timeout.connect(self._apply_filter)

        self._build_ui()
        self._setup_shortcuts()
        self._init_player()
        self._apply_settings()
        self._size_to_screen()

        self.welcome_widget.show()
        self.welcome_widget.raise_()
        QTimer.singleShot(0, self._sync_video_overlays)
        QTimer.singleShot(0, self._update_bar_mode)
        QTimer.singleShot(400, self._start_media_controls)

        self.installEventFilter(self)
        self.search_edit.installEventFilter(self)
        self.playlist.installEventFilter(self)
        QTimer.singleShot(100, self._initial_focus)

    # ------------------------------------------------------------------ properties
    @property
    def files(self):
        """The playlist paths, in order (read-only use; change it through the model)."""
        return self.store.paths

    @property
    def current_index(self):
        return self.model.current

    @current_index.setter
    def current_index(self, value):
        self.model.set_current(value)

    @property
    def current_path(self):
        i = self.model.current
        return self.store.paths[i] if 0 <= i < len(self.store.paths) else None

    def _queue_position(self, path):
        if not self.queue:
            return 0
        try:
            return self.queue.index(path) + 1
        except ValueError:
            return 0

    # ------------------------------------------------------------------ setup
    def _size_to_screen(self):
        """Never open bigger than the screen (matters at 150-200% on a 1366x768 laptop)."""
        try:
            geo = self.screen().availableGeometry()
            w = min(1200, int(geo.width() * 0.92))
            h = min(720, int(geo.height() * 0.9))
            self.resize(w, h)
            self.move(geo.x() + (geo.width() - w) // 2, geo.y() + (geo.height() - h) // 2)
            self.splitter.setSizes([int(w * 0.68), int(w * 0.32)])
        except (AttributeError, RuntimeError):
            self.resize(1200, 700)

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
        if not self._closing:
            try:
                self.status_label.setText(text)
            except RuntimeError:
                pass

    def _status(self, text, announce=False):
        self.status_label.setText(text)
        if announce:
            self._announce(text)

    def _announce(self, text):
        """Tell screen readers about an important change (Qt 6.8+; silently skipped before)."""
        try:
            from PyQt6.QtGui import QAccessible, QAccessibleAnnouncementEvent
            QAccessible.updateAccessibility(QAccessibleAnnouncementEvent(self.status_label, text))
        except (ImportError, AttributeError, TypeError, RuntimeError):
            pass

    # ------------------------------------------------------------------ files from Explorer
    def open_external(self, paths):
        if not paths:
            self._bring_to_front()
            return
        self._ext_queue.extend(paths)
        QTimer.singleShot(250, self._drain_external)

    def _drain_external(self):
        if not self._ext_queue:
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

    # ------------------------------------------------------------------ keyboard
    def _setup_shortcuts(self):
        # Letter keys and F-keys: window-wide (a focused text box still gets its letters).
        # Space, arrows and Page Up/Down are NOT shortcuts: they are handled in keyPressEvent, which
        # only runs when the focused control did not use the key. So a focused button still gets
        # Space, the playlist keeps Up/Down, and a slider keeps its arrows.
        def sc(key, fn, ctx=Qt.ShortcutContext.WindowShortcut):
            s = QShortcut(QKeySequence(key), self)
            s.setContext(ctx)
            s.activated.connect(fn)
            return s

        sc(Qt.Key.Key_F, self._toggle_fullscreen)
        sc(Qt.Key.Key_M, self._toggle_mute)
        sc(Qt.Key.Key_A, self._cycle_aspect)
        sc(Qt.Key.Key_P, self._toggle_fs_playlist)
        sc("Ctrl+F", self._focus_search)
        sc("Ctrl+O", self.choose_files)
        sc("Ctrl+Shift+O", self.choose_folder)
        sc("Ctrl+,", self.show_settings)
        sc(Qt.Key.Key_S, self.take_snapshot)
        sc(Qt.Key.Key_L, self.cycle_loop_mode)
        sc(Qt.Key.Key_F1, self.show_help)
        sc(Qt.Key.Key_Escape, lambda: self._toggle_fullscreen() if self._is_fullscreen else None)
        app_ctx = Qt.ShortcutContext.ApplicationShortcut
        sc(Qt.Key.Key_MediaPlay, lambda: self.media_command("play", "key"), app_ctx)
        sc(Qt.Key.Key_MediaPause, lambda: self.media_command("pause", "key"), app_ctx)
        sc(Qt.Key.Key_MediaTogglePlayPause, lambda: self.media_command("toggle", "key"), app_ctx)
        sc(Qt.Key.Key_MediaStop, lambda: self.media_command("stop", "key"), app_ctx)
        sc(Qt.Key.Key_MediaNext, lambda: self.media_command("next", "key"), app_ctx)
        sc(Qt.Key.Key_MediaPrevious, lambda: self.media_command("previous", "key"), app_ctx)

    def keyPressEvent(self, event):
        key = event.key()
        mods = event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier
        if mods == Qt.KeyboardModifier.NoModifier:
            if key == Qt.Key.Key_Space:
                self.play_or_resume()
                return
            if key == Qt.Key.Key_Right:
                self._seek_relative(5)
                return
            if key == Qt.Key.Key_Left:
                self._seek_relative(-5)
                return
            if key == Qt.Key.Key_Up:
                self.volume_slider.setValue(self.volume_slider.value() + 5)
                return
            if key == Qt.Key.Key_Down:
                self.volume_slider.setValue(self.volume_slider.value() - 5)
                return
            if key == Qt.Key.Key_PageUp:
                self.previous_track()
                return
            if key == Qt.Key.Key_PageDown:
                self.next_track()
                return
        super().keyPressEvent(event)

    def media_command(self, cmd, source):
        """Media keys and the Windows media controls. The same press can arrive from both, so the
        second copy within 0.4 s is ignored."""
        cmd = "toggle" if cmd in ("play", "pause") and source == "key" else cmd
        if not self._media_filter.accept("playpause" if cmd in ("play", "pause", "toggle") else cmd, source):
            return
        if cmd == "toggle":
            self.play_or_resume()
        elif cmd == "play":
            if not self._is_playing():
                self.play_or_resume()
        elif cmd == "pause":
            if self._is_playing():
                self.play_or_resume()
        elif cmd == "stop":
            if self._is_playing():
                self.play_or_resume()
        elif cmd == "next":
            self.next_track()
        elif cmd == "previous":
            self.previous_track()

    def _is_playing(self):
        if not self.player:
            return False
        try:
            return not self.player.idle_active and not self.player.pause
        except Exception:          # noqa: BLE001 - mpv not ready
            return False

    # ------------------------------------------------------------------ Windows media controls
    def _start_media_controls(self):
        if self._closing or sys.platform != "win32":
            self._media_controls_note = "Media keys work while ALMP is the active window."
            return
        if previous_start_crashed():
            log.warning("The Windows media controls did not finish starting last time; switched off")
            self.settings["media_controls"] = False
            update_settings(media_controls=False)
            self._media_controls_note = ("Switched off because they did not start correctly last time. "
                                         "You can try switching them on again.")
        if not self.settings["media_controls"]:
            if not self._media_controls_note:
                self._media_controls_note = "Off: media keys work while ALMP is the active window."
            return
        mc = WindowsMediaControls(self)
        if mc.start(int(self.winId())):
            mc.command.connect(lambda c: self.media_command(c, "smtc"))
            self.media_controls = mc
            self._media_controls_note = "On: media keys and the Windows volume pop-up control ALMP."
            self._update_media_controls()
            if self.current_path:
                mc.set_status("playing" if self._is_playing() else "paused")
        else:
            self._media_controls_note = ("Not available on this PC: media keys work while ALMP is the "
                                         "active window (details in almp.log).")

    def media_controls_status_text(self):
        return self._media_controls_note or "Media keys work while ALMP is the active window."

    def set_media_controls(self, on):
        self.settings["media_controls"] = bool(on)
        update_settings(media_controls=bool(on))
        if on and self.media_controls is None:
            self._media_controls_note = ""
            self._start_media_controls()
        elif not on and self.media_controls is not None:
            self.media_controls.stop()
            self.media_controls = None
            self._media_controls_note = "Off: media keys work while ALMP is the active window."
        self._status("Media keys in the background: " + ("on." if on and self.media_controls else "off."))

    def _update_media_controls(self):
        """Track name for the Windows media controls (Play/Pause state is set by _set_play_ui)."""
        mc = self.media_controls
        if mc is None:
            return
        path = self.current_path
        if not path or not self.player:
            mc.set_status("stopped")
            mc.clear_track()
            return
        mc.set_track(Path(path).stem, video=not is_audio_path(path))

    # ------------------------------------------------------------------ help / about / settings
    def show_help(self):
        with self._modal():
            dlg = HelpDialog(self)
            dlg.exec()
            dlg.deleteLater()

    def show_shortcuts(self):
        with self._modal():
            dlg = HelpDialog(self, start_tab=1)
            dlg.exec()
            dlg.deleteLater()

    def show_about(self):
        with self._modal():
            dlg = AboutDialog(self, describe_engine(self.player))
            dlg.exec()
            dlg.deleteLater()

    def show_settings(self):
        if self._is_fullscreen:
            self._on_fs_activity()
        with self._modal():
            dlg = SettingsDialog(self)
            dlg.exec()
            dlg.deleteLater()

    def set_simple_setting(self, key, value):
        self.settings[key] = value
        update_settings(**{key: value})

    def save_ui_scale(self, value):
        self.settings["ui_scale"] = float(value)
        update_settings(ui_scale=float(value))
        if abs(float(value) - self.running_scale) > 0.01:
            self._status("Interface size saved. It changes when ALMP restarts (Settings > Apply now).")

    def restart_for_new_size(self):
        """Close and start again (the size can only change at start). The playlist is not kept."""
        self._restart_requested = True
        self.close()

    def can_register_with_windows(self):
        return pw.can_register(APP_EXE_PATH)

    def folder_verb_installed(self):
        return pw.folder_verb_installed()

    def make_default_player(self):
        ok, details = pw.register_default_player(APP_EXE_PATH)
        if not ok:
            with self._modal():
                QMessageBox.warning(self, "Default player", "ALMP could not register itself with Windows.\n\n" + details)
            return
        with self._modal():
            QMessageBox.information(
                self, "Default player",
                "ALMP is now in Windows' list of players.\n\n"
                "ONE LAST STEP (Windows asks you to do it yourself): on the page that opens now,\n"
                "  - Windows 11: click \"Set default\" at the top;\n"
                "  - Windows 10: click \"Set this program as default\".\n\n"
                "If you move the ALMP folder later, press this button again.")
        pw.open_default_apps_settings()
        self._status("ALMP was added to Windows' Default apps.")

    def remove_default_player(self):
        ok, details = pw.unregister_default_player()
        self._status("ALMP was removed from Windows' Default apps." if ok else "Could not remove: " + details)

    def set_folder_verb(self, on):
        ok, details = pw.set_folder_verb(APP_EXE_PATH, on)
        if ok:
            self._status('"Play with ALMP" is now in the folder menu.' if on else '"Play with ALMP" was removed.')
        else:
            self._status("Could not change the folder menu: " + details)
        return ok

    def set_volume_boost(self, on):
        self.settings["volume_boost"] = bool(on)
        update_settings(volume_boost=bool(on))
        top = BOOST_MAX_VOLUME if on else NORMAL_MAX_VOLUME
        set_prop(self.player, "volume-max", top)
        self.volume_slider.setMaximum(top)
        self._status("Volume can now go up to 150%." if on else "Volume goes up to 100%.")

    def set_normalize_volume(self, on):
        self.settings["normalize_volume"] = bool(on)
        update_settings(normalize_volume=bool(on))
        ok = set_audio_filter(self.player, on)
        if on:
            self._status("Loud and quiet parts are evened out." if ok else
                         "The volume normaliser could not be started (details in almp.log).")
        else:
            self._status("Volume normaliser is off.")

    def set_subtitle_scale(self, value):
        self.settings["subtitle_scale"] = float(value)
        update_settings(subtitle_scale=float(value))
        set_prop(self.player, "sub-scale", float(value))

    def set_subtitle_background(self, on):
        self.settings["subtitle_background"] = bool(on)
        update_settings(subtitle_background=bool(on))
        for k, v in subtitle_background_options(on).items():
            set_prop(self.player, k, v)

    def set_resume_long_files(self, on):
        self.settings["resume_long_files"] = bool(on)
        update_settings(resume_long_files=bool(on))
        if not on:
            self.forget_resume_positions(quiet=True)
            self._status("ALMP will not remember where you stopped.")
        else:
            self._status("Long files (20 minutes or more) will continue where you stopped.")

    def forget_resume_positions(self, quiet=False):
        self._positions = {}
        forget_positions()
        if not quiet:
            self._status("Saved places were forgotten.")

    def _resume_key(self, path):
        return os.path.normcase(os.path.abspath(path))

    def _remember_position(self):
        """Optional resume: store where the current long file is (or forget it if finished)."""
        if not self.settings["resume_long_files"] or not self.player or not self.current_path:
            return
        try:
            pos = self.player.time_pos
            dur = self.player.duration
        except Exception:          # noqa: BLE001
            return
        update_resume_table(self._positions, self._resume_key(self.current_path), pos, dur)
        save_positions(self._positions)

    # ------------------------------------------------------------------ seeking / video size
    def _seek_relative(self, seconds):
        """Left/Right arrows. mpv refuses to seek when nothing is loaded, so do nothing then."""
        if not self.player or not self.current_path:
            return
        try:
            if self.player.idle_active:
                return
            self.player.seek(seconds, reference="relative")
        except Exception:          # noqa: BLE001
            log.debug("Seek ignored", exc_info=True)

    def set_video_size(self, mode, save=False, announce=True):
        self._video_size = mode if mode in VIDEO_SIZE_NAMES else "fit"
        if self.player:
            for k, v in video_size_properties(self._video_size).items():
                set_prop(self.player, k, v)
        if save:
            self.settings["video_size"] = self._video_size
            update_settings(video_size=self._video_size)
        if announce:
            self._status(f"Video size: {VIDEO_SIZE_NAMES[self._video_size]}   (press A to change)")

    def _cycle_aspect(self):
        self.set_video_size(next_video_size(self._video_size))

    # ------------------------------------------------------------------ fullscreen title
    def _set_fs_title(self, name):
        self._fs_title_full = name
        self._fs_title_key = None
        self._layout_fs_title()

    def _drawer_width(self):
        if self.right_panel.parent() is self and self.right_panel.isVisible():
            return int(min(560, max(300, self.width() * 0.28)))
        return 0

    def _layout_fs_title(self):
        name = self._fs_title_full
        area_w = max(300, self.width() - self._drawer_width())
        key = (name, area_w, self.width())
        if key == self._fs_title_key:
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
                self._status("Muted (press M again for sound).")
            else:
                self.volume_slider.setValue(self._pre_mute_volume or 50)
                self._status("Sound on.")

    def _initial_focus(self):
        if self._dialog_active:
            return
        self.activateWindow()
        self.raise_()
        if QApplication.focusWidget() is None:
            self.video.setFocus()

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
        et = event.type()
        playlist = getattr(self, "playlist", None)
        search = getattr(self, "search_edit", None)
        if obj is getattr(self, "video", None) and et == QEvent.Type.Resize:
            self._sync_video_overlays()
        if obj is self and et == QEvent.Type.ActivationChange:
            # Only give the video the focus when nothing has it, so the list or a button keeps it.
            if self.isActiveWindow() and not self._dialog_active and QApplication.focusWidget() is None:
                self.video.setFocus()
        if obj is getattr(self, "controls_host", None) and et == QEvent.Type.Resize:
            QTimer.singleShot(0, self._update_bar_mode)
        if playlist is not None and obj is playlist and et == QEvent.Type.KeyPress and self._is_fullscreen:
            self._fs_key_time = time.monotonic()
            self._on_fs_activity()
        if search is not None and obj is search and et == QEvent.Type.KeyPress:
            if self._is_fullscreen:
                self._fs_key_time = time.monotonic()
                self._on_fs_activity()          # typing in the drawer's search box keeps it open
            if event.key() == Qt.Key.Key_Down:
                self.playlist.setFocus()
                if self.model.rowCount() and not self.playlist.currentIndex().isValid():
                    self.playlist.setCurrentIndex(self.model.index(0))
                return True
            if event.key() == Qt.Key.Key_Escape and self.search_edit.text():
                self.search_edit.clear()
                return True

        if obj is getattr(self, "video", None):
            if et == QEvent.Type.MouseButtonDblClick:
                self._toggle_fullscreen()
                return True
            if et == QEvent.Type.MouseMove and self._is_fullscreen:
                self._on_fs_activity()
            elif et == QEvent.Type.Wheel:
                delta = event.angleDelta().y()
                if delta > 0:
                    self.volume_slider.setValue(self.volume_slider.value() + 5)
                elif delta < 0:
                    self.volume_slider.setValue(self.volume_slider.value() - 5)
                return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------ menus
    def _new_menu(self):
        menu = QMenu(self)
        menu.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        return menu

    def _fill_tracks_menu(self, menu):
        """Audio tracks and subtitles of the file that is playing."""
        def tv(t, key, default=None):
            try:
                if isinstance(t, dict):
                    return t.get(key, default)
                return getattr(t, key, default)
            except Exception:          # noqa: BLE001
                return default

        audio_tracks, sub_tracks = [], []
        try:
            for t in (self.player.track_list or []):
                kind = tv(t, "type")
                if kind == "audio":
                    audio_tracks.append(t)
                elif kind == "sub":
                    sub_tracks.append(t)
        except Exception:          # noqa: BLE001
            log.debug("track_list not available", exc_info=True)

        def label(t):
            title, lang = tv(t, "title"), tv(t, "lang")
            text = f"{title} ({lang})" if title and lang else (title or lang or f"Track {tv(t, 'id')}")
            return ("✓  " if tv(t, "selected") else "      ") + str(text)

        if audio_tracks:
            audio_menu = menu.addMenu("Audio tracks")
            for t in audio_tracks:
                act = audio_menu.addAction(label(t))
                act.triggered.connect(lambda checked=False, tid=tv(t, "id"): self._safe_set_mpv_prop("aid", tid))
        sub_menu = menu.addMenu("Subtitles")
        if sub_tracks:
            any_selected = any(tv(t, "selected") for t in sub_tracks)
            act = sub_menu.addAction(("      " if any_selected else "✓  ") + "Off")
            act.triggered.connect(lambda checked=False: self._safe_set_mpv_prop("sid", "no"))
            for t in sub_tracks:
                act = sub_menu.addAction(label(t))
                act.triggered.connect(lambda checked=False, tid=tv(t, "id"): self._safe_set_mpv_prop("sid", tid))
            sub_menu.addSeparator()
        sub_menu.addAction("Load subtitle file...", self.load_external_subtitle)
        sub_menu.addAction("Subtitle size and box (Settings)...", self.show_settings)

    def show_context_menu(self, pos):
        """The subtitles button on the control bar."""
        if not self.player or self.player.idle_active:
            self._status("Start playing something first, then use this button for audio and subtitles.")
            return
        menu = self._new_menu()
        self._fill_tracks_menu(menu)
        menu.addSeparator()
        menu.addAction("Take snapshot (S)", self.take_snapshot)
        self._fill_video_size_menu(menu.addMenu("Video size"))
        menu.addAction("Fullscreen (F)", self._toggle_fullscreen)
        menu.popup(pos)

    def _fill_video_size_menu(self, menu):
        for mode in ("fit", "fill", "stretch"):
            act = menu.addAction(VIDEO_SIZE_NAMES[mode])
            act.setCheckable(True)
            act.setChecked(mode == self._video_size)
            act.triggered.connect(lambda checked=False, m=mode: self.set_video_size(m))

    def show_video_menu(self, pos):
        """Right-click on the video or album art."""
        menu = self._new_menu()
        playing = self._is_playing()
        menu.addAction("Pause (Space)" if playing else "Play (Space)", self.play_or_resume)
        menu.addAction("Next track (Page Down)", self.next_track)
        menu.addAction("Previous track (Page Up)", self.previous_track)
        menu.addSeparator()
        if self.player and not self.player.idle_active:
            self._fill_tracks_menu(menu)
            menu.addAction("Take snapshot (S)", self.take_snapshot)
            self._fill_video_size_menu(menu.addMenu("Video size"))
        menu.addAction("Leave fullscreen (Esc)" if self._is_fullscreen else "Fullscreen (F)", self._toggle_fullscreen)
        menu.addSeparator()
        menu.addAction("Add files...", self.choose_files)
        menu.addAction("Add folder...", self.choose_folder)
        menu.addAction("Settings...", self.show_settings)
        menu.addAction("Help (F1)", self.show_help)
        menu.popup(self.video.mapToGlobal(pos))

    def show_playlist_menu(self, pos):
        """Right-click (or the Menu key) on the playlist."""
        index = self.playlist.indexAt(pos)
        if not index.isValid():
            index = self.playlist.currentIndex()
        menu = self._new_menu()
        if index.isValid():
            self.playlist.setCurrentIndex(index)
            src = self.model.source_row(index.row())
            path = self.store.paths[src] if src >= 0 else None
            menu.addAction("Play", self.play_selected_item)
            if path in self.queue:
                menu.addAction("Remove from \"Play next\"", lambda: self._unqueue(path))
            else:
                menu.addAction("Play next", lambda: self.queue_next(path))
            menu.addSeparator()
            up = menu.addAction("Move up", lambda: self._move_selected(-1))
            down = menu.addAction("Move down", lambda: self._move_selected(1))
            movable = not self.model.filtered
            up.setEnabled(movable and src > 0)
            down.setEnabled(movable and 0 <= src < len(self.store) - 1)
            if not movable:
                up.setToolTip("Clear the search to move items")
            menu.addSeparator()
            menu.addAction("Remove from list (Delete)", self.remove_from_playlist)
            menu.addAction("Show in folder", lambda: self.show_in_folder(path))
            menu.addAction("Copy file path", lambda: QGuiApplication.clipboard().setText(path or ""))
            menu.addSeparator()
            menu.addAction("Delete file... (Shift+Delete)", self.delete_selected_file)
            menu.addSeparator()
        self._fill_sort_menu(menu.addMenu("Sort the playlist"))
        menu.addAction("Add files...", self.choose_files)
        menu.addAction("Add folder...", self.choose_folder)
        if self.store:
            menu.addAction("Clear the playlist", self.clear_playlist)
        menu.popup(self.playlist.viewport().mapToGlobal(pos))

    def queue_next(self, path):
        if not path:
            return
        pos = add_to_queue(self.queue, path)
        self.model.refresh_path(path)
        self._status(f"Plays next: {Path(path).name}" if pos == 1 else f"Plays after {pos - 1} other(s): {Path(path).name}")

    def _unqueue(self, path):
        try:
            self.queue.remove(path)
        except ValueError:
            return
        self.model.refresh_all()        # positions of the others change too
        self._status(f"Removed from \"Play next\": {Path(path).name}")

    def _move_selected(self, delta):
        ix = self.playlist.currentIndex()
        if not ix.isValid() or self.model.filtered:
            return
        src = self.model.source_row(ix.row())
        dst = src + delta
        if self.model.move_source(src, dst):
            self.playlist.setCurrentIndex(self.model.index(dst))

    def show_in_folder(self, path):
        if not path:
            return
        if not os.path.exists(path):
            self._status("That file is no longer there.")
            return
        if not pw.show_in_explorer(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))

    def _fill_sort_menu(self, menu):
        menu.addAction("By name (2 before 10)", lambda: self.sort_playlist("name"))
        menu.addAction("By folder, then name", lambda: self.sort_playlist("folder"))
        menu.addAction("Reverse the order", lambda: self.sort_playlist("reverse"))
        for a in menu.actions():
            a.setEnabled(bool(self.store) and not self._sort_busy and not self._scan_active and not self._pending)

    def sort_playlist(self, how):
        """Sorting 100,000 names takes a moment, so the keys are made on a background thread and
        the new order is applied in one step (refused if the list changed meanwhile)."""
        if not self.store or self._sort_busy:
            return
        paths = list(self.store.paths)
        version = self.store.version
        self._sort_busy = True
        self._status("Sorting the playlist...")
        bridge = self._bridge

        def work():
            try:
                if how == "reverse":
                    order = list(range(len(paths) - 1, -1, -1))
                else:
                    keyf = natural_name_key if how == "name" else natural_path_key
                    keys = [keyf(p) for p in paths]
                    order = sorted(range(len(paths)), key=keys.__getitem__)
            except Exception:          # noqa: BLE001
                log.exception("Sorting failed")
                order = None
            try:
                bridge.sorted_ready.emit(order, version, how)
            except RuntimeError:
                pass

        threading.Thread(target=work, daemon=True, name="almp-sort").start()

    def _on_sorted_ready(self, order, version, how):
        self._sort_busy = False
        if order is None:
            self._status("The playlist could not be sorted (details in almp.log).")
            return
        if not self.model.reorder(order, expected_version=version):
            self._status("The playlist changed while sorting - please sort again.")
            return
        cur = self.current_index
        if cur >= 0:
            v = self.model.view_row(cur)
            if v >= 0:
                self.playlist.scrollTo(self.model.index(v))
        names = {"name": "by name", "folder": "by folder", "reverse": "in reverse order"}
        self._status(f"Playlist sorted {names.get(how, '')}.")

    def _safe_set_mpv_prop(self, prop, value):
        if self.player:
            try:
                setattr(self.player, prop, value)
            except Exception:          # noqa: BLE001
                log.warning("Failed to set %s to %r", prop, value, exc_info=True)

    def load_external_subtitle(self):
        if not self.player or self.player.idle_active:
            return
        with self._modal():
            fname, _ = QFileDialog.getOpenFileName(self, "Load Subtitle", "", "Subtitles (*.srt *.ass *.vtt *.ssa *.sub)")
        if fname:
            try:
                self.player.sub_add(fname)
                self._status(f"Subtitle loaded: {Path(fname).name}")
            except Exception as e:          # noqa: BLE001
                log.exception("Could not load subtitle %s", fname)
                with self._modal():
                    QMessageBox.warning(self, "Subtitle Error", f"Could not load subtitle:\n{e}")

    def take_snapshot(self):
        if not self.player or self.player.idle_active or not self.current_path:
            return
        try:
            pictures_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)
            base_name = Path(self.current_path).stem
            out_path = os.path.join(pictures_dir, f"{base_name}_snapshot_{int(time.time())}.png")
            self.player.screenshot_to_file(out_path)
            self._status(f"Snapshot saved to Pictures: {Path(out_path).name}")
        except Exception as e:          # noqa: BLE001
            log.warning("Snapshot failed", exc_info=True)
            self._status(f"Snapshot failed: {e}")

    # ------------------------------------------------------------------ building the window
    def _icon_btn(self, kind, tip, name, slot, size=(44, 40)):
        b = QPushButton()
        b.setIcon(make_icon(kind, icon_color(self._high_contrast), ICON_PX))
        b.setIconSize(QSize(ICON_PX, ICON_PX))
        b.setFixedSize(*size)
        b.setToolTip(tip)
        b.setAccessibleName(name)
        b.clicked.connect(slot)
        return b

    def _build_ui(self):
        hc = self._high_contrast
        ic = icon_color(hc)
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.main_layout.addWidget(self.splitter)

        self.left_panel = QWidget()
        self.left_panel.setObjectName("leftPanel")
        self.left_layout = QVBoxLayout(self.left_panel)
        self.left_layout.setContentsMargins(0, 0, 0, 0)
        self.left_layout.setSpacing(0)

        self.video = QWidget()
        self.video.setObjectName("videoSurface")
        self.video.setMinimumSize(320, 160)
        self.video.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.video.setAccessibleName("Video")
        self.video.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.video.customContextMenuRequested.connect(self.show_video_menu)
        self.video.installEventFilter(self)
        self.left_layout.addWidget(self.video, stretch=1)

        self.audio_art_label = QLabel(self.video)
        self.audio_art_label.setObjectName("audioArt")
        self.audio_art_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.audio_art_label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.audio_art_label.customContextMenuRequested.connect(
            lambda p: self.show_video_menu(self.audio_art_label.mapTo(self.video, p)))
        self.audio_art_label.hide()

        self.welcome_widget = WelcomeScreen(self.video)
        self.welcome_widget.set_high_contrast(hc)
        self.welcome_widget.add_files_requested.connect(self.choose_files)
        self.welcome_widget.add_folder_requested.connect(self.choose_folder)
        self.welcome_widget.hide()

        # --- control bar ---
        self.control_panel_widget = QWidget()
        self.control_panel_widget.setObjectName("controlBar")
        self.control_panel_layout = QVBoxLayout(self.control_panel_widget)
        self.control_panel_layout.setContentsMargins(12, 8, 12, 10)
        self.control_panel_layout.setSpacing(6)

        self.progress_slider = ClickSeekSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setToolTip("Click or drag to jump to a point in the track")
        self.progress_slider.setAccessibleName("Position in the track")
        self.progress_slider.setRange(0, 0)
        self.progress_slider.sliderMoved.connect(self.slider_user_scrubbed)
        self.progress_slider.sliderPressed.connect(self._start_scrubbing)
        self.progress_slider.sliderReleased.connect(self._stop_scrubbing)
        self.control_panel_layout.addWidget(self.progress_slider)

        self.status_label = QLabel("Drag & drop folders or files here, or choose Add Files.")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.status_label.setAccessibleName("Status")
        self.scan_cancel_button = QPushButton("Stop adding")
        self.scan_cancel_button.setToolTip("Stop looking for more files (what was found stays in the list)")
        self.scan_cancel_button.setAccessibleName("Stop adding files")
        self.scan_cancel_button.clicked.connect(self.cancel_scan)
        self.scan_cancel_button.hide()
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setObjectName("timeLabel")
        self.time_label.setAccessibleName("Time")
        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.addWidget(self.status_label, stretch=1)
        status_row.addWidget(self.scan_cancel_button)
        status_row.addWidget(self.time_label)
        self.control_panel_layout.addLayout(status_row)

        # controls_host holds row 1 (always) and row 2 (only when the window is narrow)
        self.controls_host = QWidget()
        self.controls_host.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.controls_host.setMinimumWidth(240)
        host_layout = QVBoxLayout(self.controls_host)
        host_layout.setContentsMargins(0, 0, 0, 0)
        host_layout.setSpacing(6)
        self.controls_widget = QWidget()
        controls_layout = QHBoxLayout(self.controls_widget)
        self.controls_layout = controls_layout
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)
        self.tools_row = QWidget()
        self.tools_row_layout = QHBoxLayout(self.tools_row)
        self.tools_row_layout.setContentsMargins(0, 0, 0, 0)
        self.tools_row_layout.addStretch(1)
        self.tools_row_layout.addStretch(1)
        self.tools_row.hide()
        host_layout.addWidget(self.controls_widget)
        host_layout.addWidget(self.tools_row)

        self.volume_box = QWidget()
        volume_row = QHBoxLayout(self.volume_box)
        volume_row.setContentsMargins(0, 0, 0, 0)
        volume_row.setSpacing(8)
        self.volume_label = QLabel()
        self.volume_label.setPixmap(make_icon("volume", ic, ICON_PX).pixmap(ICON_PX, ICON_PX))
        self.volume_label.setAccessibleName("Volume")
        self.volume_slider = ClickSeekSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, BOOST_MAX_VOLUME if self.settings["volume_boost"] else NORMAL_MAX_VOLUME)
        self.volume_slider.setValue(100)
        self.volume_slider.setAccessibleName("Volume")
        self.volume_slider.setToolTip("Volume (Up / Down keys, or the mouse wheel over the video)")
        self.volume_slider.setMinimumWidth(50)
        self.volume_slider.valueChanged.connect(self.change_volume)
        self.volume_value_label = QLabel("100%")
        self.volume_value_label.setObjectName("volumeValue")
        self.volume_value_label.setMinimumWidth(40)
        self.volume_value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        volume_row.addWidget(self.volume_label)
        volume_row.addWidget(self.volume_slider, stretch=1)
        volume_row.addWidget(self.volume_value_label)
        controls_layout.addWidget(self.volume_box)
        controls_layout.addStretch(1)

        self.previous_button = QPushButton("Prev")
        self.previous_button.setObjectName("transportButton")
        self.previous_button.setIconSize(QSize(ICON_PX, ICON_PX))
        self.previous_button.setAccessibleName("Previous track")
        self.previous_button.setToolTip("Previous track  (Page Up)")
        self.previous_button.clicked.connect(self.previous_track)
        controls_layout.addWidget(self.previous_button)

        self.play_button = QPushButton("Play")
        self.play_button.setObjectName("playButton")
        self.play_button.setIconSize(QSize(ICON_PX, ICON_PX))
        self.play_button.setAccessibleName("Play")
        self.play_button.setToolTip("Play / pause  (Space)")
        self.play_button.clicked.connect(self.play_or_resume)
        controls_layout.addWidget(self.play_button)

        self.next_button = QPushButton("Next")
        self.next_button.setObjectName("transportButton")
        self.next_button.setIconSize(QSize(ICON_PX, ICON_PX))
        self.next_button.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.next_button.setAccessibleName("Next track")
        self.next_button.setToolTip("Next track  (Page Down)")
        self.next_button.clicked.connect(self.next_track)
        controls_layout.addWidget(self.next_button)

        self.tools_box = QWidget()
        tools = QHBoxLayout(self.tools_box)
        tools.setContentsMargins(0, 0, 0, 0)
        tools.setSpacing(8)
        self.speed_combo = QComboBox()
        self.speed_combo.addItems(list(SPEED_CHOICES))
        self.speed_combo.setCurrentText("1.0x")
        self.speed_combo.currentTextChanged.connect(self.change_speed)
        self.speed_combo.setAccessibleName("Playback speed")
        self.speed_combo.setToolTip("Playback speed (kept for the next tracks until ALMP closes;\n"
                                    "change this in Settings)")
        self.speed_combo.setMinimumWidth(78)
        tools.addWidget(self.speed_combo)
        self.tracks_button = self._icon_btn(
            "subtitles", "Audio tracks and subtitles", "Audio tracks and subtitles",
            lambda: self.show_context_menu(self.tracks_button.mapToGlobal(QPoint(0, self.tracks_button.height()))))
        tools.addWidget(self.tracks_button)
        self.sleep_button = self._icon_btn("clock", "Sleep timer", "Sleep timer", self.show_sleep_menu)
        tools.addWidget(self.sleep_button)
        self.contrast_button = self._icon_btn("contrast", "High contrast", "High contrast theme",
                                              self._toggle_high_contrast)
        tools.addWidget(self.contrast_button)
        self.settings_button = self._icon_btn("settings", "Settings  (Ctrl+,)", "Settings", self.show_settings)
        tools.addWidget(self.settings_button)
        controls_layout.addWidget(self.tools_box)
        controls_layout.addStretch(1)

        self.right_box = QWidget()
        right_row = QHBoxLayout(self.right_box)
        right_row.setContentsMargins(0, 0, 0, 0)
        right_row.setSpacing(8)
        right_row.addStretch(1)
        self.playlist_toggle_button = self._icon_btn("playlist", "Show / hide playlist  (P)", "Show or hide playlist",
                                                     self._toggle_fs_playlist)
        self.playlist_toggle_button.hide()
        right_row.addWidget(self.playlist_toggle_button)
        self.fullscreen_button = self._icon_btn("fullscreen", "Fullscreen  (F)", "Fullscreen", self._toggle_fullscreen)
        right_row.addWidget(self.fullscreen_button)
        self.fs_close_button = self._icon_btn("close", "Close ALMP", "Close ALMP", self.close)
        self.fs_close_button.setObjectName("closeButton")
        self.fs_close_button.hide()
        right_row.addWidget(self.fs_close_button)
        controls_layout.addWidget(self.right_box)
        self._update_fs_button()
        self._update_contrast_button()
        self._set_play_ui(False)

        self.control_panel_layout.addWidget(self.controls_host)
        self.controls_host.installEventFilter(self)
        self.left_layout.addWidget(self.control_panel_widget)

        # --- playlist panel ---
        self.right_panel = QWidget()
        self.right_panel.setObjectName("rightPanel")
        self.right_panel.setMinimumWidth(250)
        self.right_layout = QVBoxLayout(self.right_panel)
        self.right_layout.setContentsMargins(10, 10, 10, 10)
        self.right_layout.setSpacing(8)

        self.playlist_count_label = QLabel("0 items")
        self.playlist_count_label.setObjectName("countPill")
        self.playlist_count_label.setMinimumWidth(96)
        self.playlist_count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.playlist_count_label.setAccessibleName("Number of items")
        playlist_title = QLabel("Playlist")
        playlist_title.setObjectName("playlistTitle")
        header_row = QHBoxLayout()
        header_row.setContentsMargins(2, 0, 0, 0)
        header_row.addWidget(playlist_title)
        header_row.addStretch(1)
        header_row.addWidget(self.playlist_count_label)
        self.right_layout.addLayout(header_row)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search playlist...   (Ctrl+F)")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setAccessibleName("Search the playlist")
        self.search_edit.setToolTip("Type part of a name or folder. Enter plays the first match, Down goes to the list.")
        self.search_action = self.search_edit.addAction(make_icon("search", "#8a9499", 16),
                                                        QLineEdit.ActionPosition.LeadingPosition)
        self.search_edit.textChanged.connect(self._schedule_filter)
        self.search_edit.returnPressed.connect(self._play_first_visible)
        self.right_layout.addWidget(self.search_edit)

        self.playlist = PlaylistView()
        self.playlist.setModel(self.model)
        # Double-click and Enter play (not Qt's "activated", which fires on double-click as well
        # on Windows and would start the same track twice).
        self.playlist.doubleClicked.connect(lambda _ix: self.play_selected_item())
        self.playlist.play_requested.connect(self.play_selected_item)
        self.playlist.remove_requested.connect(self.remove_from_playlist)
        self.playlist.delete_requested.connect(self.delete_selected_file)
        self.playlist.customContextMenuRequested.connect(self.show_playlist_menu)
        self.right_layout.addWidget(self.playlist, stretch=1)

        self.options_widget_1 = QWidget()
        self.options_layout_1 = QHBoxLayout(self.options_widget_1)
        self.options_layout_1.setContentsMargins(0, 0, 0, 0)
        self.options_layout_1.setSpacing(4)
        self.add_media_button = QPushButton("+ Add Media")
        self.add_media_button.setAccessibleName("Add media and playlist options")
        self.add_media_button.clicked.connect(self.show_add_media_menu)
        self.options_layout_1.addWidget(self.add_media_button)
        self.clear_playlist_button = QPushButton("Clear")
        self.clear_playlist_button.setToolTip("Clear the whole playlist (files are kept)")
        self.clear_playlist_button.setAccessibleName("Clear the playlist")
        self.clear_playlist_button.clicked.connect(self.clear_playlist)
        self.options_layout_1.addWidget(self.clear_playlist_button)
        self.remove_from_list_button = QPushButton("Remove")
        self.remove_from_list_button.setObjectName("removeButton")
        self.remove_from_list_button.setToolTip("Remove the selected item from the list (the file is kept)  (Delete)\n"
                                                "Right-click an item for more, such as Delete file.")
        self.remove_from_list_button.setAccessibleName("Remove the selected item from the list")
        self.remove_from_list_button.clicked.connect(self.remove_from_playlist)
        self.options_layout_1.addWidget(self.remove_from_list_button)
        self.right_layout.addWidget(self.options_widget_1)

        self.options_widget_2 = QWidget()
        self.options_layout_2 = QGridLayout(self.options_widget_2)
        self.options_layout_2.setContentsMargins(2, 2, 2, 0)
        self.options_layout_2.setHorizontalSpacing(12)
        self.options_layout_2.setVerticalSpacing(8)
        self.shuffle_checkbox = QCheckBox("Shuffle")
        self.shuffle_checkbox.setChecked(True)
        self.shuffle_checkbox.setToolTip("Play the list in a random order (each track once per round)")
        self.shuffle_checkbox.toggled.connect(self.set_shuffle)
        self.options_layout_2.addWidget(self.shuffle_checkbox, 0, 0)
        self.loop_button = QPushButton()
        self.loop_button.setIconSize(QSize(16, 16))
        self.loop_button.setAccessibleName("Loop")
        self.loop_button.clicked.connect(self.cycle_loop_mode)
        self.options_layout_2.addWidget(self.loop_button, 0, 1)
        self._update_loop_button()
        self.remove_played_checkbox = QCheckBox("Remove played")
        self.remove_played_checkbox.setChecked(False)
        self.remove_played_checkbox.setToolTip(REMOVE_PLAYED_TIP)
        self.remove_played_checkbox.toggled.connect(self._remove_played_toggled)
        self.options_layout_2.addWidget(self.remove_played_checkbox, 1, 0, 1, 2)
        self.right_layout.addWidget(self.options_widget_2)

        # Run at Startup lives in Settings now; this hidden box keeps its state.
        self.startup_checkbox = QCheckBox("Run at Startup", self)
        self.startup_checkbox.hide()
        self.startup_checkbox.toggled.connect(self.toggle_startup)

        self.splitter.addWidget(self.left_panel)
        self.splitter.addWidget(self.right_panel)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)

        self.setMouseTracking(True)
        self.video.setMouseTracking(True)

        self.fullscreen_title_label = FullscreenTitlePill(self)
        self.fullscreen_title_label.high_contrast = hc
        self.fullscreen_title_label.hide()
        self.fullscreen_title_label.raise_()

        self.check_startup_state()

        # Buttons, boxes and sliders take keyboard focus with Tab only (not when clicked),
        # so the yellow focus ring shows up only for people who use the keyboard.
        for kind in (QPushButton, QCheckBox, QComboBox, QSlider):
            for w in self.findChildren(kind):
                w.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setTabOrder(self.video, self.previous_button)

    # ------------------------------------------------------------------ responsive control bar
    def _measure_bar(self):
        """Widths needed by the control row in each layout (measured once, again after a theme change)."""
        sp = self.controls_layout.spacing()
        buttons = (self.previous_button, self.play_button, self.next_button)
        saved = [b.text() for b in buttons]
        for b, t in zip(buttons, ("Prev", "Pause", "Next"), strict=True):
            b.setText(t)
        wide_transport = sum(max(b.minimumSizeHint().width(), b.sizeHint().width()) for b in buttons)
        for b in buttons:
            b.setText("")
        icon_transport = sum(b.sizeHint().width() for b in buttons)
        for b, t in zip(buttons, saved, strict=True):
            b.setText(t)
        tools = self.tools_box.sizeHint().width()
        right = 3 * 44 + 2 * sp
        self._bar_widths = {
            "wide": 2 * 175 + wide_transport + 104 + tools + 8 * sp + 40,
            "compact": 2 * 130 + icon_transport + 40 + tools + 8 * sp + 20,
            "_right": right,
        }

    def _update_bar_mode(self):
        if self._closing:
            return
        if self._bar_widths is None:
            self._measure_bar()
        w = self.controls_host.width()
        hyst = 16 if self._bar_mode else 0
        need = self._bar_widths
        if w >= need["wide"] + (hyst if self._bar_mode != "wide" else 0):
            mode = "wide"
        elif w >= need["compact"] + (hyst if self._bar_mode == "narrow" else 0):
            mode = "compact"
        else:
            mode = "narrow"
        if mode != self._bar_mode:
            self._apply_bar_mode(mode)

    def _apply_bar_mode(self, mode):
        self._bar_mode = mode
        wide = mode == "wide"
        side = 175 if wide else 130
        self.volume_box.setFixedWidth(side if mode != "narrow" else 150)
        self.right_box.setFixedWidth(side if mode != "narrow" else 3 * 44 + 16)
        for b, w in ((self.previous_button, 104), (self.play_button, 140), (self.next_button, 104)):
            b.setMinimumWidth(w if wide else (64 if b is self.play_button else 48))
        self.previous_button.setText("Prev" if wide else "")
        self.next_button.setText("Next" if wide else "")
        self._set_play_ui(self._is_playing())
        in_row2 = self.tools_row_layout.indexOf(self.tools_box) >= 0
        if mode == "narrow" and not in_row2:
            self.controls_layout.removeWidget(self.tools_box)
            self.tools_row_layout.insertWidget(1, self.tools_box)
            self.tools_row.show()
        elif mode != "narrow" and in_row2:
            self.tools_row_layout.removeWidget(self.tools_box)
            # back between "Next" and the right-hand stretch
            self.controls_layout.insertWidget(self.controls_layout.indexOf(self.next_button) + 1, self.tools_box)
            self.tools_row.hide()
        if self.control_panel_widget.parent() is self:
            QTimer.singleShot(0, self._layout_overlay)

    # ------------------------------------------------------------------ add media menu
    def show_add_media_menu(self):
        menu = self._new_menu()
        menu.addAction("Add files...  (Ctrl+O)", self.choose_files)
        menu.addAction("Add folder...  (Ctrl+Shift+O)", self.choose_folder)
        menu.addAction("Open a playlist file (.m3u, .pls)...", self.choose_playlist_file)
        menu.addSeparator()
        menu.addAction("Save playlist as M3U...", self.save_playlist_m3u)
        self._fill_sort_menu(menu.addMenu("Sort the playlist"))
        menu.addSeparator()
        self._fill_sleep_menu(menu.addMenu("Sleep timer"))
        hc = menu.addAction("High contrast theme")
        hc.setCheckable(True)
        hc.setChecked(self._high_contrast)
        hc.triggered.connect(self.set_high_contrast)
        menu.addAction("Settings...  (Ctrl+,)", self.show_settings)
        menu.addAction("Help  (F1)", self.show_help)
        menu.addAction("About ALMP", self.show_about)
        b = self.add_media_button
        menu.popup(b.mapToGlobal(QPoint(0, b.height())))

    # ------------------------------------------------------------------ sleep timer
    def _fill_sleep_menu(self, sleep_menu):
        left = self._sleep_minutes_left()
        if left:
            info = sleep_menu.addAction(f"Time left: {left} min")
            info.setEnabled(False)
            sleep_menu.addAction("+15 minutes", self.extend_sleep_timer)
            sleep_menu.addSeparator()
        elif self._sleep_end_of_track:
            info = sleep_menu.addAction("Stops at the end of this track")
            info.setEnabled(False)
            sleep_menu.addSeparator()
        off = sleep_menu.addAction("Off")
        off.setCheckable(True)
        off.setChecked(self._sleep_minutes == 0 and not self._sleep_end_of_track)
        off.triggered.connect(lambda checked=False: self.set_sleep_timer(0))
        eot = sleep_menu.addAction("At the end of this track")
        eot.setCheckable(True)
        eot.setChecked(self._sleep_end_of_track)
        eot.triggered.connect(lambda checked=False: self.set_sleep_end_of_track())
        for label, minutes in (("5 minutes", 5), ("15 minutes", 15), ("30 minutes", 30),
                               ("45 minutes", 45), ("1 hour", 60), ("1 hour 30 minutes", 90), ("2 hours", 120)):
            act = sleep_menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(minutes == self._sleep_minutes)
            act.triggered.connect(lambda checked=False, m=minutes: self.set_sleep_timer(m))
        sleep_menu.addSeparator()
        for label, action in (("When time is up: Pause playback", SLEEP_PAUSE), ("When time is up: Close ALMP", SLEEP_CLOSE)):
            act = sleep_menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(self._sleep_action == action)
            act.triggered.connect(lambda checked=False, a=action: self.set_sleep_action(a))
        fade = sleep_menu.addAction("Fade out during the last minute")
        fade.setCheckable(True)
        fade.setChecked(bool(self.settings["sleep_fade"]))
        fade.triggered.connect(lambda checked: self.set_simple_setting("sleep_fade", bool(checked)))

    def show_sleep_menu(self):
        if self._is_fullscreen:
            self._on_fs_activity()
        menu = self._new_menu()
        self._fill_sleep_menu(menu)
        b = self.sleep_button
        menu.popup(b.mapToGlobal(QPoint(0, b.height())))

    def _sleep_minutes_left(self):
        if self._sleep_minutes <= 0 or not self._sleep_timer.isActive():
            return 0
        return sleep_minutes_left(self._sleep_timer.remainingTime())

    def _update_sleep_button(self):
        on = self._sleep_minutes > 0 or self._sleep_end_of_track
        self.sleep_button.setIcon(make_icon("clock", accent(self._high_contrast) if on else icon_color(self._high_contrast), ICON_PX))
        if self._sleep_end_of_track:
            self.sleep_button.setToolTip("Sleep timer on: playback stops at the end of this track")
        elif on:
            what = "close ALMP" if self._sleep_action == SLEEP_CLOSE else "pause playback"
            self.sleep_button.setToolTip(f"Sleep timer on: will {what} in {self._sleep_minutes_left()} min")
        else:
            self.sleep_button.setToolTip("Sleep timer")
        self.sleep_button.setAccessibleName("Sleep timer, on" if on else "Sleep timer, off")

    def set_sleep_action(self, action):
        """Only changes WHAT happens; a running countdown keeps its time."""
        self._sleep_action = action
        self._update_sleep_button()
        what = "close." if action == SLEEP_CLOSE else "pause playback."
        left = self._sleep_minutes_left()
        if left:
            self._status(f"Sleep timer: in {left} min ALMP will {what}")
        else:
            self._status("When the sleep timer ends, ALMP will " + what)

    def set_sleep_timer(self, minutes):
        self._sleep_minutes = minutes
        self._sleep_end_of_track = False
        self._sleep_timer.stop()
        self._sleep_tip_timer.stop()
        self._stop_fade()
        if minutes > 0:
            self._sleep_timer.start(minutes * 60 * 1000)
            self._sleep_tip_timer.start()
            self._fade_timer.start()
            if self._sleep_action == SLEEP_CLOSE:
                self._status(f"Sleep timer set: ALMP will close in {minutes} minutes.", announce=True)
            else:
                self._status(f"Sleep timer set: playback will pause in {minutes} minutes.", announce=True)
        else:
            self._status("Sleep timer is off.", announce=True)
        self._update_sleep_button()

    def set_sleep_end_of_track(self):
        self.set_sleep_timer(0)
        self._sleep_end_of_track = True
        self._update_sleep_button()
        self._status("Sleep timer: playback stops at the end of this track.", announce=True)

    def extend_sleep_timer(self):
        if not self._sleep_timer.isActive():
            return
        new_ms = extend_sleep_ms(self._sleep_timer.remainingTime(), 15)
        self._sleep_timer.start(new_ms)
        self._sleep_minutes = max(1, new_ms // 60000)
        self._stop_fade()
        self._fade_timer.start()
        self._update_sleep_button()
        self._status(f"Sleep timer: {self._sleep_minutes_left()} min left.")

    def _apply_sleep_fade(self):
        if not self._sleep_timer.isActive() or not self.player:
            self._fade_timer.stop()
            return
        if not self.settings["sleep_fade"]:
            return
        factor = sleep_fade_factor(self._sleep_timer.remainingTime())
        if factor < 1.0:
            try:
                self.player.volume = self.volume_slider.value() * factor
            except Exception:          # noqa: BLE001
                log.debug("Fade step failed", exc_info=True)

    def _stop_fade(self):
        self._fade_timer.stop()
        self.change_volume()                    # back to the slider's volume

    def _sleep_timer_fired(self):
        self._sleep_minutes = 0
        self._sleep_tip_timer.stop()
        self._fade_timer.stop()
        self._update_sleep_button()
        if self._sleep_action == SLEEP_CLOSE:
            self.close()
            return
        self._set_mpv_pause(True)
        self._set_play_ui(False)
        self.change_volume()
        self._status("Sleep timer: playback paused.", announce=True)
        self._update_media_controls()

    # ------------------------------------------------------------------ playlist file save / open
    def save_playlist_m3u(self):
        if not self.store:
            self._status("The playlist is empty - nothing to save.")
            return
        if self._pending or self._scan_active:
            self._status("Still adding files - please wait until loading has finished, then save.")
            return
        start = str(Path.home() / "Music" / "ALMP-playlist.m3u8")
        with self._modal():
            path, _ = QFileDialog.getSaveFileName(self, "Save Playlist", start, "Playlist (*.m3u8 *.m3u)")
        if not path:
            return
        if not path.lower().endswith((".m3u", ".m3u8")):
            path += ".m3u8"
        try:
            write_playlist_file(path, self.store.paths)
            msg = f"Saved {len(self.store):,} items to {os.path.basename(path)}"
            if self._removed_played_count:
                msg += " (items already played and removed are not included)"
            self._status(msg)
        except OSError as e:
            log.exception("Could not save playlist %s", path)
            with self._modal():
                QMessageBox.warning(self, "Save Playlist", f"Could not save the playlist:\n{e}")

    def choose_playlist_file(self):
        with self._modal():
            path, _ = QFileDialog.getOpenFileName(self, "Open Playlist", "", "Playlists (*.m3u *.m3u8 *.pls)")
        if path:
            self.scan_targets([path])

    # ------------------------------------------------------------------ theme
    def set_high_contrast(self, enabled):
        """Used by the menu item, the bar button and Settings, so they always agree."""
        enabled = bool(enabled)
        self._high_contrast = enabled
        self.settings["high_contrast"] = enabled
        QApplication.instance().setStyleSheet(stylesheet(enabled))
        update_settings(high_contrast=enabled)
        self.welcome_widget.set_high_contrast(enabled)
        self.fullscreen_title_label.high_contrast = enabled
        self.model.set_accent(accent(enabled))
        self._refresh_icons()
        self._bar_widths = None                 # borders changed: measure again
        QTimer.singleShot(0, self._update_bar_mode)
        self._status("High contrast theme is on." if enabled else "High contrast theme is off.", announce=True)

    def _refresh_icons(self):
        ic = icon_color(self._high_contrast)
        for b, kind in ((self.previous_button, "prev"), (self.next_button, "next"),
                        (self.tracks_button, "subtitles"), (self.settings_button, "settings"),
                        (self.playlist_toggle_button, "playlist"), (self.fs_close_button, "close")):
            b.setIcon(make_icon(kind, ic, ICON_PX))
        self.volume_label.setPixmap(make_icon("volume", ic, ICON_PX).pixmap(ICON_PX, ICON_PX))
        self._update_contrast_button()
        self._update_sleep_button()
        self._update_loop_button()
        self._update_fs_button()
        self._set_play_ui(self._is_playing())

    def _toggle_high_contrast(self):
        if self._is_fullscreen:
            self._on_fs_activity()
        self.set_high_contrast(not self._high_contrast)

    def _update_contrast_button(self):
        on = self._high_contrast
        self.contrast_button.setIcon(make_icon("contrast", accent(on) if on else icon_color(on), ICON_PX))
        self.contrast_button.setToolTip("High contrast theme (on/off)\nNow: " + ("On" if on else "Off"))
        self.contrast_button.setAccessibleName("High contrast theme, " + ("on" if on else "off"))

    # ------------------------------------------------------------------ loop / remove played
    def cycle_loop_mode(self):
        self.set_loop_mode(next_loop_mode(self._loop_mode))

    def set_loop_mode(self, mode):
        self._loop_mode = mode if mode in LOOP_MODES else LOOP_OFF
        self._quick_end_streak = 0
        box = self.remove_played_checkbox
        checked, enabled, self._remove_played_saved = remove_played_for_loop(
            self._loop_mode, box.isChecked(), self._remove_played_saved)
        box.blockSignals(True)
        box.setChecked(checked)
        box.blockSignals(False)
        box.setEnabled(enabled)
        box.setToolTip(REMOVE_PLAYED_TIP if enabled else REMOVE_PLAYED_LOOP_ALL_TIP)
        self._update_loop_button()
        if self._loop_mode == LOOP_ONE:
            self._status("Loop One: the track that is playing will repeat.", announce=True)
        elif self._loop_mode == LOOP_ALL:
            self._status("Loop All: the playlist will start again after the last track "
                         "(\"Remove played\" is off meanwhile).", announce=True)
        else:
            self._status("Loop is off.", announce=True)

    def _update_loop_button(self):
        on = self._loop_mode != LOOP_OFF
        self.loop_button.setText(LOOP_LABELS[self._loop_mode])
        self.loop_button.setIcon(make_icon("loop", accent(self._high_contrast) if on else icon_color(self._high_contrast), 16))
        self.loop_button.setToolTip(LOOP_TIPS[self._loop_mode])
        self.loop_button.setAccessibleName(LOOP_LABELS[self._loop_mode])

    def _remove_played_toggled(self, checked):
        if self._remove_played_saved is None:
            self.settings["remove_played"] = bool(checked)

    # ------------------------------------------------------------------ mpv
    def _init_player(self):
        try:
            self.player_events = self._bridge
            self._bridge.end_file.connect(self._handle_end_file)
            s = self.settings
            self.player = mpv.MPV(**mpv_options(self.video.winId(), boost=s["volume_boost"],
                                                subtitle_scale=s["subtitle_scale"]))
            self.player.volume = self.volume_slider.value()

            @self.player.event_callback("end-file")
            def handle_end_file(event):
                self._bridge.end_file.emit(get_mpv_end_reason(event))

            if s["normalize_volume"]:
                set_audio_filter(self.player, True)
            if s["subtitle_background"]:
                for k, v in subtitle_background_options(True).items():
                    set_prop(self.player, k, v)
            self._status("Media player engine ready.")
        except Exception as e:          # noqa: BLE001 - the window still opens and says what is wrong
            log.exception("mpv could not start")
            self.player = None
            self._status(f"Media Player Initialization Error: {e}")

    def _update_playlist_count(self):
        total = len(self.store)
        if self.model.filtered:
            self.playlist_count_label.setText(f"{self.model.rowCount():,} of {total:,}")
        else:
            self.playlist_count_label.setText(f"{total:,} item" + ("" if total == 1 else "s"))

    # ------------------------------------------------------------------ search
    def _schedule_filter(self, _text=None):
        # Bigger lists wait a little longer for the next key press before searching.
        self._filter_timer.setInterval(150 if len(self.store) < 50_000 else 250)
        self._filter_timer.start()

    def _apply_filter(self):
        t = time.perf_counter()
        self.model.set_filter(self.search_edit.text())
        ms = (time.perf_counter() - t) * 1000
        if ms > 50:
            log.info("Playlist search took %.0f ms for %d items", ms, len(self.store))
        self._update_playlist_count()
        cur = self.current_index
        v = self.model.view_row(cur) if cur >= 0 else -1
        if v >= 0:
            self.playlist.setCurrentIndex(self.model.index(v))
            self.playlist.scrollTo(self.model.index(v))

    def _play_first_visible(self):
        if self._filter_timer.isActive():
            self._filter_timer.stop()
            self._apply_filter()
        if self.model.rowCount():
            src = self.model.source_row(0)
            if src >= 0:
                self.play_index(src)
                self._finish_search()
                self.video.setFocus()

    def _finish_search(self):
        """After a track was chosen from a search result, empty the search box and show the whole
        playlist again (scrolled to the track that is playing)."""
        if self.search_edit.text():
            self._filter_timer.stop()
            self.search_edit.blockSignals(True)
            self.search_edit.clear()
            self.search_edit.blockSignals(False)
            self._apply_filter()

    def _focus_search(self):
        if self._is_fullscreen:
            if not self._fs_drawer_wanted:
                self._toggle_fs_playlist()
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    # ------------------------------------------------------------------ settings
    def _save_settings(self):
        save_settings(settings_to_save(load_settings(), min(self.volume_slider.value(), BOOST_MAX_VOLUME),
                                       self.shuffle_checkbox.isChecked(),
                                       remove_played_to_save(self.remove_played_checkbox.isChecked(),
                                                             self._remove_played_saved)))

    def _apply_settings(self):
        # The repeat (L) mode is deliberately not read here: it always starts Off.
        data = self.settings
        self.volume_slider.setValue(int(data["volume"]))
        self.shuffle_checkbox.setChecked(bool(data["shuffle"]))
        self.remove_played_checkbox.setChecked(bool(data["remove_played"]))
        self.set_video_size(data["video_size"], announce=False)

    def showEvent(self, event):
        super().showEvent(event)
        self._bar_widths = None                 # measure the control row with the real fonts
        QTimer.singleShot(0, self._update_bar_mode)

    def resizeEvent(self, event):
        QTimer.singleShot(0, self._layout_fs_title)
        QTimer.singleShot(0, self._layout_overlay)
        QTimer.singleShot(0, self._sync_video_overlays)
        super().resizeEvent(event)

    # ------------------------------------------------------------------ Run at Startup
    def check_startup_state(self):
        if sys.platform == "win32":
            on = pw.WIN_SHORTCUT.exists()
            self._set_startup_box(on)
            if on and is_compiled() and APP_EXE_PATH:
                threading.Thread(target=pw.repair_startup_shortcut, args=(APP_EXE_PATH,), daemon=True).start()
            pw.remove_legacy_run_value()
        else:
            on = False
            if LINUX_DESKTOP_FILE.exists():
                try:
                    on = sys.executable in LINUX_DESKTOP_FILE.read_text(encoding="utf-8")
                except OSError:
                    on = False
            self._set_startup_box(on)

    def _set_startup_box(self, checked):
        self.startup_checkbox.blockSignals(True)
        self.startup_checkbox.setChecked(checked)
        self.startup_checkbox.blockSignals(False)

    def toggle_startup(self, checked):
        if not is_compiled():
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
                self._status("Adding ALMP to Windows startup...")
                bridge = self._bridge

                def work():
                    try:
                        ok, details = pw.write_startup_shortcut(exe_path)
                    except Exception as e:          # noqa: BLE001
                        ok, details = False, str(e)
                    try:
                        bridge.startup_done.emit(ok, details)
                    except RuntimeError:
                        pass          # the window was closed meanwhile

                threading.Thread(target=work, daemon=True).start()
            else:
                try:
                    pw.remove_startup_shortcut()
                    self._status("ALMP removed from Windows startup.")
                except OSError as e:
                    log.exception("Could not remove the startup shortcut")
                    self._set_startup_box(True)
                    with self._modal():
                        QMessageBox.critical(self, "Startup Error", f"Could not remove ALMP from Windows startup:\n{e}")
        else:
            try:
                if checked:
                    LINUX_AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
                    LINUX_DESKTOP_FILE.write_text(
                        "[Desktop Entry]\nType=Application\nName=ALMP\n"
                        f'Exec="{exe_path}"\nTerminal=false\n', encoding="utf-8")
                    self._status("App set to run at Linux startup.")
                else:
                    if LINUX_DESKTOP_FILE.exists():
                        LINUX_DESKTOP_FILE.unlink()
                    self._status("App removed from Linux startup.")
            except OSError as e:
                log.exception("Autostart change failed")
                self._set_startup_box(not checked)
                with self._modal():
                    QMessageBox.critical(self, "Autostart Error", f"Failed to modify startup settings: {e}")

    def _on_startup_result(self, ok, details):
        self._startup_busy = False
        self.startup_checkbox.setEnabled(True)
        if ok:
            self._set_startup_box(True)
            self._status("ALMP will now start when you sign in to Windows.")
            return
        log.warning("Run at Startup failed: %s", details)
        self._set_startup_box(False)
        self._status("Run at Startup could not be turned on.")
        if not self._closing:
            with self._modal():
                QMessageBox.warning(
                    self, "Run at Startup",
                    "Windows did not allow ALMP to add itself to startup, so nothing was changed.\n\n"
                    "This can happen on school or office computers. "
                    "Details were saved in almp.log.")

    # ------------------------------------------------------------------ album art
    @staticmethod
    def _load_album_art(file_path):
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
            except Exception:          # noqa: BLE001
                pics = []
            if pics:
                front = [p for p in pics if getattr(p, "type", None) == 3]
                art_data = (front or pics)[0].data
            elif tags is not None and 'APIC:' in tags:
                art_data = tags['APIC:'].data
            elif hasattr(audio, 'pictures') and len(audio.pictures) > 0:
                art_data = audio.pictures[0].data
            elif tags is not None and 'covr' in tags:
                art_data = bytes(tags['covr'][0])
            if art_data:
                image = QImage.fromData(art_data)
                if not image.isNull():
                    return QPixmap.fromImage(image)
        except Exception:          # noqa: BLE001 - a broken tag only means "no picture"
            log.debug("No album art for %s", file_path, exc_info=True)
        return None

    # ------------------------------------------------------------------ volume / speed
    def change_volume(self, *_args):
        v = self.volume_slider.value()
        self.volume_value_label.setText(f"{v}%")
        if self.player:
            try:
                self.player.volume = v
            except Exception:          # noqa: BLE001
                log.exception("Could not set the volume")

    def change_speed(self, text):
        if self.player:
            try:
                self.player.speed = parse_speed(text)
            except Exception:          # noqa: BLE001
                log.exception("Could not set the speed to %r", text)

    # ------------------------------------------------------------------ clear / remove / delete
    def clear_playlist(self):
        self._remember_position()
        self.cancel_scan(quiet=True)
        self._scan_queue.clear()
        self._pending.clear()
        self._chunk_running = False
        self._autoplay_pending = True
        self._ext_play_key = None
        self._removed_played_count = 0
        self.track_timer.stop()
        self.search_edit.clear()        # an old search must not hide the files added next
        self.model.clear()
        self.queue.clear()
        self._played_paths.clear()
        self._history.clear()
        self.progress_slider.setValue(0)
        self.progress_slider.setMaximum(0)
        self._set_play_ui(False)
        self.audio_art_label.hide()
        self._status("Playlist cleared. Drag & drop files to start again.", announce=True)
        self._update_playlist_count()
        self.welcome_widget.show()
        self.welcome_widget.raise_()
        if self.player:
            try:
                self.player.stop()
            except Exception:          # noqa: BLE001
                log.debug("stop failed", exc_info=True)
        self._update_media_controls()

    def _selected_source_row(self):
        ix = self.playlist.currentIndex()
        if not ix.isValid():
            sel = self.playlist.selectionModel().selectedIndexes() if self.playlist.selectionModel() else []
            if not sel:
                return -1
            ix = sel[0]
        return self.model.source_row(ix.row())

    def _after_current_removed(self, row=-1):
        """The track that was playing left the list (it was at `row`): stop it and go on with the
        track that took its place (or a random one with Shuffle, or the "Play next" one)."""
        if self.player:
            try:
                self.player.stop()
            except Exception:          # noqa: BLE001
                log.debug("stop failed", exc_info=True)
        self.audio_art_label.hide()
        self._set_play_ui(False)
        self.progress_slider.setValue(0)
        self.progress_slider.setMaximum(1)
        self.track_timer.stop()
        self._end_event_pending = False
        if self.store:
            if self._play_queued():
                return
            if self.shuffle_enabled or row < 0:
                self.next_track()
            else:
                self.play_index(row if row < len(self.store) else 0)
        else:
            self.welcome_widget.show()
            self.welcome_widget.raise_()
            self._update_media_controls()

    def remove_from_playlist(self):
        src = self._selected_source_row()
        if src < 0:
            with self._modal():
                QMessageBox.warning(self, "Remove from List", "Please select a file to remove.")
            return
        view_row = self.playlist.currentIndex().row()
        was_current = src == self.current_index
        path = self.model.remove_source(src)
        if path in self.queue:
            self.queue.remove(path)
        self._update_playlist_count()
        self._status(f"Removed from list: {Path(path).name}")
        # keep the selection on the next item so pressing Delete again removes the next one
        n = self.model.rowCount()
        if n:
            self.playlist.setCurrentIndex(self.model.index(min(view_row, n - 1)))
        if was_current:
            self._after_current_removed(src)

    def _set_mpv_pause(self, value):
        if not self.player:
            return
        try:
            if sys.platform != "win32":
                self.player.command_async("set", "pause", "yes" if value else "no")
            else:
                self.player.pause = value
        except Exception:          # noqa: BLE001
            try:
                self.player.pause = value
            except Exception:          # noqa: BLE001
                log.debug("pause failed", exc_info=True)

    def _wait_until_idle(self, timeout_ms=1000):
        """After stop(), mpv closes the file a moment later. Wait for that (up to 1 s) so Windows does
        not refuse the delete with "file in use". The window keeps painting meanwhile; clicks and
        keys wait until this is done (no time.sleep on the window thread)."""
        if not self.player:
            return
        deadline = time.monotonic() + timeout_ms / 1000.0

        def idle():
            try:
                return bool(self.player.idle_active)
            except Exception:          # noqa: BLE001
                return True

        if idle():
            return
        loop = QEventLoop()
        timer = QTimer()
        timer.setInterval(30)
        timer.timeout.connect(lambda: loop.quit() if (idle() or time.monotonic() >= deadline) else None)
        timer.start()
        loop.exec(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
        timer.stop()

    def delete_selected_file(self):
        src = self._selected_source_row()
        if src < 0:
            with self._modal():
                QMessageBox.warning(self, "Delete File", "Please select a file in the playlist to delete.")
            return
        path = self.store.paths[src]
        if not path or not os.path.exists(path):
            self._status("File no longer exists.")
            return
        was_fullscreen = self._is_fullscreen
        was_playing = False
        if self.player:
            try:
                was_playing = not bool(self.player.pause) and not self.player.idle_active
                if was_playing:
                    self._set_mpv_pause(True)
            except Exception:          # noqa: BLE001
                log.exception("Could not pause before delete")
        self.video.setMouseTracking(True)

        has_bin = pw.recycle_bin_available(path)
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
            dialog = CustomConfirmDialog(self, title, message,
                                         yes_text="Yes, delete" if not has_bin else "Yes, to Recycle Bin")
            dialog.setModal(True)
            reply = dialog.exec()
            dialog.deleteLater()
        if was_fullscreen:
            self.video.setFocus()
        if reply != QDialog.DialogCode.Accepted:
            if was_playing and self.player:
                self._set_mpv_pause(False)
                self._set_play_ui(True)
            return
        src = self.store.index_of(path, hint=src)
        if src < 0:
            self._status("The selected file is no longer in the playlist.")
            return
        is_currently_playing = (src == self.current_index)
        resume_at = None
        if is_currently_playing and self.player:
            try:
                resume_at = self.player.time_pos
                self.player.stop()
            except Exception:          # noqa: BLE001
                log.exception("Could not stop playback before delete")
            self._wait_until_idle()

        self._status("Deleting...")
        hwnd = 0
        try:
            hwnd = int(self.winId())
        except (RuntimeError, TypeError):
            pass
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = pw.send_to_recycle_bin(path, permanent=not has_bin, hwnd=hwnd)
        finally:
            QApplication.restoreOverrideCursor()
        if result != pw.DELETE_OK:
            if result == pw.DELETE_CANCELLED:
                self._status(f"Not deleted: {name}")
            else:
                self._status(f"Could not delete: {name}")
                with self._modal():
                    QMessageBox.critical(self, "Delete Error",
                                         f"Could not delete this file. It was not changed:\n{path}")
            if is_currently_playing:
                if was_playing or resume_at:
                    self.play_index(src, start=resume_at)        # carry on where it was
                    if not was_playing:
                        self._set_mpv_pause(True)
                        self._set_play_ui(False)
            elif was_playing and self.player:
                self._set_mpv_pause(False)
                self._set_play_ui(True)
            return

        self.model.remove_source(src)
        if path in self.queue:
            self.queue.remove(path)
        self._update_playlist_count()
        self._status(f"File sent to Recycle Bin: {name}" if has_bin else f"File deleted permanently: {name}", announce=True)
        if is_currently_playing:
            self._after_current_removed(src)
        elif was_playing and self.player:
            self._set_mpv_pause(False)
            self._set_play_ui(True)

    # ------------------------------------------------------------------ progress
    def _poll_player_metrics(self):
        if not self.player or self._closing:
            return
        try:
            if self._is_scrubbing or self.isMinimized():
                return
            current_time = getattr(self.player, "time_pos", 0) or 0
            duration = getattr(self.player, "duration", 0) or 1
            key = (int(current_time), int(duration))
            if duration > 0 and key != self._last_tick_key:
                self._last_tick_key = key
                self.progress_slider.setMaximum(int(duration))
                self.progress_slider.setValue(int(current_time))
                self.time_label.setText(f"{fmt_time(current_time)} / {fmt_time(duration)}")
                if current_time > 0:
                    self._error_streak = 0
        except Exception:          # noqa: BLE001 - mpv between files
            log.debug("poll failed", exc_info=True)

    @staticmethod
    def _fmt_time(seconds):
        return fmt_time(seconds)

    def slider_user_scrubbed(self):
        if not self.player or not self.current_path:
            return
        try:
            if self.player.idle_active:
                return
            self.player.seek(self.progress_slider.value(), reference="absolute")
        except Exception:          # noqa: BLE001
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

    # ------------------------------------------------------------------ fullscreen
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
        wanted = self._fs_drawer_wanted
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
        # With nothing loaded the start screen is all there is: keep the pointer visible so its buttons work.
        if self.welcome_widget.isVisible():
            self._show_cursor()
            self.hide_timer.start()
            return
        # Do not close the drawer while someone is using it with the KEYBOARD. A mouse click or a
        # double-click in the list gives the list the focus too, but that must not keep the drawer open.
        fw = QApplication.focusWidget()
        keyboard_recent = time.monotonic() - self._fs_key_time < 8.0
        if (self.right_panel.isVisible() and fw is not None and self.right_panel.isAncestorOf(fw)
                and keyboard_recent):
            self.hide_timer.start()
            return
        if fw is not None and self.control_panel_widget.isAncestorOf(fw) and fw is not self.video:
            self.hide_timer.start()             # a keyboard user is on a control-bar button
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
        self._fs_drawer_wanted = not self._fs_drawer_wanted
        self._fs_title_key = None
        self._on_fs_activity()
        QTimer.singleShot(0, self._layout_overlay)

    def _update_fs_button(self):
        ic = icon_color(self._high_contrast)
        if self._is_fullscreen:
            self.fullscreen_button.setIcon(make_icon("exitfullscreen", ic, ICON_PX))
            self.fullscreen_button.setToolTip("Exit fullscreen  (Esc / F)")
            self.fullscreen_button.setAccessibleName("Leave fullscreen")
        else:
            self.fullscreen_button.setIcon(make_icon("fullscreen", ic, ICON_PX))
            self.fullscreen_button.setToolTip("Fullscreen  (F)")
            self.fullscreen_button.setAccessibleName("Fullscreen")

    def _set_play_ui(self, playing):
        text = "Pause" if playing else "Play"
        self.play_button.setText(text if self._bar_mode in (None, "wide") else "")
        self.play_button.setAccessibleName(text)
        color = "#000000" if self._high_contrast else ICON_ON_ACCENT
        self.play_button.setIcon(make_icon("pause" if playing else "play", color, ICON_PX))
        ic = icon_color(self._high_contrast)
        self.previous_button.setIcon(make_icon("prev", ic, ICON_PX))
        self.next_button.setIcon(make_icon("next", ic, ICON_PX))
        if self.media_controls is not None:
            self.media_controls.set_status("playing" if playing else ("paused" if self.current_path else "stopped"))

    def _toggle_fullscreen(self):
        if self._is_fullscreen:
            self.showNormal()
            self._is_fullscreen = False
            self._exit_fullscreen_ui()
            if self._pre_fs_maximized:
                self.showMaximized()
            elif self._pre_fs_geometry is not None:
                self.setGeometry(self._pre_fs_geometry)
            else:
                self._size_to_screen()
            self._show_cursor()
            self.hide_timer.stop()
            self.fullscreen_title_label.hide()
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
            if not self.welcome_widget.isVisible():
                self._hide_cursor()
            self.hide_timer.start()
        self._update_fs_button()
        self._apply_tv_mode()
        QTimer.singleShot(0, self._layout_overlay)
        self.video.setFocus()

    def _apply_tv_mode(self):
        """Bigger start screen in fullscreen on a TV or big screen (Settings > Large start screen)."""
        try:
            h = self.screen().geometry().height()
        except (AttributeError, RuntimeError):
            h = 0
        self.welcome_widget.set_tv_scale(tv_scale(self.settings.get("large_buttons", "auto"),
                                                  self._is_fullscreen, h))

    def set_large_buttons(self, value):
        if value not in LARGE_BUTTON_MODES:
            value = "auto"
        self.settings["large_buttons"] = value
        update_settings(large_buttons=value)
        self._apply_tv_mode()

    # ------------------------------------------------------------------ adding files
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
        targets = [t for t in targets if t]
        if not targets:
            return
        if self._scan_active:
            self._scan_queue.append((targets, external))
            self._status("Will add these next, after the files that are being added now.")
            return
        self._start_scan(targets, external)

    def _start_scan(self, targets, external):
        self._scan_job += 1
        job = self._scan_job
        self._scan_active = True
        self._scan_external = external
        self._scan_first_batch = True
        self._scan_found = 0
        self._status("Looking for media files...")
        self.scan_cancel_button.show()
        self._old_scanners = [s for s in self._old_scanners if s.isRunning()]
        if self.scanner is not None:
            self._old_scanners.append(self.scanner)
        scanner = FolderScanner(targets, play_first=external)
        scanner.batch_found.connect(lambda entries, j=job: self._on_scan_batch(j, entries))
        scanner.scan_done.connect(lambda total, cancelled, j=job: self._on_scan_done(j, total, cancelled))
        scanner.scan_error.connect(self._on_scan_error)
        self.scanner = scanner
        scanner.start()

    def cancel_scan(self, quiet=False):
        if self.scanner is not None and self.scanner.isRunning():
            self.scanner.requestInterruption()
        was = self._scan_active
        self._scan_job += 1                     # late batches from that scan are ignored
        self._scan_active = False
        self._scan_queue.clear()
        self.scan_cancel_button.hide()
        if was and not quiet:
            self._status(f"Stopped adding. {len(self.store):,} item(s) in the list.")

    def _on_scan_batch(self, job, entries):
        if self._closing or job != self._scan_job or not entries:
            return
        if self._scan_first_batch and self._scan_external:
            # Play the first opened file once it is in the list (or right away if it already was).
            self._ext_play_key = entries[0][1]
        self._scan_first_batch = False
        self._scan_found += len(entries)
        self._pending.append(entries)
        if not self._chunk_running:
            self._chunk_running = True
            QTimer.singleShot(0, self._add_next_chunk)

    def _on_scan_done(self, job, total, cancelled):
        if job != self._scan_job:
            return
        self._scan_active = False
        if not self._pending and not self._chunk_running:
            self._finish_loading(total)
        if self._scan_queue and not self._closing:
            targets, external = self._scan_queue.pop(0)
            self._start_scan(targets, external)

    def _play_external_if_ready(self):
        key = self._ext_play_key
        if key is None or not self.store.contains_key(key):
            return False
        self._ext_play_key = None
        i = self.store.index_of_key(key)
        if i >= 0:
            self.play_index(i)
            return True
        return False

    def _add_next_chunk(self):
        """Adds up to CHUNK_ROWS files per event-loop turn, so the window never freezes."""
        if self._closing:
            return
        if not self._pending:
            self._chunk_running = False
            if not self._scan_active:
                self._finish_loading(self._scan_found)
            return
        chunk = []
        while self._pending and len(chunk) < CHUNK_ROWS:
            batch = self._pending.popleft()
            room = CHUNK_ROWS - len(chunk)
            if len(batch) > room:
                chunk.extend(batch[:room])
                self._pending.appendleft(batch[room:])
            else:
                chunk.extend(batch)
        was_empty = not self.store
        self.welcome_widget.hide()
        self.model.append_entries(chunk)
        self._update_playlist_count()

        if self._play_external_if_ready():
            self._autoplay_pending = False
        elif was_empty and self.store and self._autoplay_pending:
            self._autoplay_pending = False
            self.play_index(0)

        if self._pending or self._scan_active:
            self._status(f"Adding files... {len(self.store):,} in the list so far")
        if self._pending:
            QTimer.singleShot(0, self._add_next_chunk)
        else:
            self._chunk_running = False
            if not self._scan_active:
                self._finish_loading(self._scan_found)

    def _finish_loading(self, found=None):
        self.scan_cancel_button.hide()
        self._autoplay_pending = True
        self._ext_play_key = None
        if not self.store:
            self._status("No playable files were found there. Add files or a folder.")
            self.welcome_widget.show()
            self.welcome_widget.raise_()
            return
        if found == 0:
            self._status("No new playable files were found there.")
        elif self.current_path:
            self._status(f"Playing: {Path(self.current_path).name}   ({len(self.store):,} items in the list)")
        else:
            self._status(f"Added media. Total: {len(self.store):,} item(s).")

    def _on_scan_error(self, message):
        log.error("Import failed: %s", message)
        self._status("Some files could not be added (details in almp.log).")

    # ------------------------------------------------------------------ playing
    def set_shuffle(self, enabled):
        self.shuffle_enabled = enabled
        self._played_paths.clear()
        self._history.clear()
        if enabled and self.current_path:
            self._played_paths.add(self.current_path)

    def play_selected_item(self, *_args):
        src = self._selected_source_row()
        if src < 0:
            if self.store:
                self.play_index(0)
            return
        self.play_index(src)
        self._finish_search()

    def play_index(self, index, _from_prev=False, start=None):
        if not self.store or not (0 <= index < len(self.store)):
            return
        self._remember_position()
        path = self.store.paths[index]
        prev_path = self.current_path
        if self.shuffle_enabled and not _from_prev and prev_path and prev_path != path:
            self._history.append(prev_path)
            if len(self._history) > 500:
                del self._history[:100]
        if path in self.queue:
            self.queue.remove(path)
            self.model.refresh_all()
        self._end_event_pending = False
        self._playlist_ended = False
        self._stopped_by_sleep = False
        self._play_started = time.monotonic()
        self.current_index = index
        self._played_paths.add(path)
        self._last_tick_key = None

        v = self.model.view_row(index)
        if v >= 0:
            ix = self.model.index(v)
            self.playlist.setCurrentIndex(ix)
            self.playlist.scrollTo(ix)

        name = Path(path).name
        if self._is_fullscreen:
            self._set_fs_title(name)
            if not self.hide_timer.isActive():
                self._hide_cursor()
                self.control_panel_widget.hide()
            else:
                self.hide_timer.start()

        if is_audio_path(path):
            pixmap = self._load_album_art(path)
            self._sync_video_overlays()
            if pixmap:
                self.audio_art_label.setPixmap(pixmap.scaled(
                    self.video.size(), Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))
            else:
                side = max(160, min(self.video.width(), self.video.height()) // 3)
                self.audio_art_label.setPixmap(logo_pixmap(side))
            self.audio_art_label.show()
        else:
            self.audio_art_label.hide()

        if self.player:
            new_speed = speed_for_new_track(self.speed_combo.currentText(), self.settings["keep_speed"])
            if new_speed != self.speed_combo.currentText():
                self.speed_combo.setCurrentText(new_speed)
            options = {}
            resumed = None
            if isinstance(start, (int, float)) and start > 1:
                options["start"] = str(int(start))     # carry on after a failed delete
            elif self.settings["resume_long_files"]:
                resumed = resume_start_for(self._positions, self._resume_key(path))
                if resumed:
                    options["start"] = str(resumed)
            try:
                self.player.loadfile(path, mode="replace", **options)
                self.player.pause = False
            except Exception:          # noqa: BLE001
                log.exception("Could not start %s", path)
                self._status(f"Could not play: {name}")
                self._set_play_ui(False)
                return
            if resumed:
                self._status(f"Playing: {name}  (continuing at {fmt_time(resumed)})")
            else:
                self._status(f"Playing: {name}")
            self._set_play_ui(True)
            self.track_timer.start()
            self._update_media_controls()

    def play_or_resume(self):
        if not self.player or not self.store:
            return
        try:
            if self.player.idle_active:
                if self._stopped_by_sleep:
                    self._stopped_by_sleep = False
                    self.next_track()
                elif self._playlist_ended:                  # Loop Off finished the list: start again
                    self._played_paths.clear()
                    idx = pick_shuffle_index(self.store.paths, self._played_paths, -1) if self.shuffle_enabled else 0
                    self.play_index(idx if idx >= 0 else 0)
                else:
                    self.play_index(self.current_index if self.current_index >= 0 else 0)
            else:
                self.player.pause = not self.player.pause
                playing = not self.player.pause
                self._set_play_ui(playing)
                if not playing:
                    self._remember_position()
        except Exception:          # noqa: BLE001
            log.exception("Play/pause failed")

    def previous_track(self):
        if not self.store:
            return
        if self.shuffle_enabled:
            while self._history:                      # go back to what you really heard before
                path = self._history.pop()
                idx = self.store.index_of(path)
                if idx < 0:
                    continue
                self.play_index(idx, _from_prev=True)
                return
            self.play_index(self.current_index if self.current_index >= 0 else 0, _from_prev=True)
        else:
            prev_idx = self.current_index - 1
            if prev_idx < 0:
                prev_idx = len(self.store) - 1
            self.play_index(prev_idx)

    def _play_queued(self):
        """Play the next "Play next" track, if there is one. Returns True if it did."""
        path = next_from_queue(self.queue, self.store.contains)
        if path is None:
            return False
        idx = self.store.index_of(path)
        if idx < 0:
            return False
        self.model.refresh_all()
        self.play_index(idx)
        return True

    def next_track(self):
        if not self.store:
            return
        if self._play_queued():
            return
        if self.shuffle_enabled:
            idx = pick_shuffle_index(self.store.paths, self._played_paths, self.current_index)
            if idx >= 0:
                self.play_index(idx)
        else:
            next_idx = self.current_index + 1
            if next_idx >= len(self.store):
                next_idx = 0
            self.play_index(next_idx)

    def _handle_end_file(self, reason):
        if self._closing:
            return
        reason = str(reason).upper()
        if reason == "ERROR":
            self._error_streak += 1
            name = Path(self.current_path).name if self.current_path else "this file"
            self._status(f"Could not play: {name}")
            if self._error_streak <= 5 and len(self.store) > 1:
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
        if self.settings["resume_long_files"] and self.current_path:
            self._positions.pop(self._resume_key(self.current_path), None)    # finished: start at 0 next time
            save_positions(self._positions)

        if time.monotonic() - self._play_started < LOOP_QUICK_END_SECONDS:
            self._quick_end_streak += 1
        else:
            self._quick_end_streak = 0

        if self._sleep_end_of_track:
            self._sleep_end_of_track = False
            self._stopped_by_sleep = True
            self._set_play_ui(False)
            self._update_sleep_button()
            self.progress_slider.setValue(0)
            self._status("Sleep timer: stopped at the end of the track. Press Play for the next one.", announce=True)
            self._update_media_controls()
            return

        n = len(self.store)
        all_played = False
        if self.shuffle_enabled and n:
            played = self._played_paths
            paths = self.store.paths
            played_in_list = sum(1 for p in paths if p in played)
            if played_in_list != len(played):
                played.intersection_update(paths)   # forget tracks no longer in the list
            all_played = played_in_list == n
        # Loop is done by playing the file again ourselves (not with mpv's loop-file option),
        # so every repeat still sends this end-of-file event and nothing else has to change.
        action, idx = decide_after_track_end(
            n, self.current_index, self._loop_mode, self.shuffle_enabled,
            self.remove_played_checkbox.isChecked(), all_played, self._quick_end_streak)

        if action == "replay":
            self.play_index(idx)
        elif action == "remove":
            self._remove_current_and_advance()
        elif self._play_queued():
            pass                                    # "Play next" goes before order and shuffle
        elif action == "play":
            self.play_index(idx)
        elif action == "shuffle":
            self.next_track()
        elif action == "new_round":
            # Every track was played: forget them all, so the new round plays each track again
            # (pick_shuffle_index never picks the track that just ended as the very next one).
            self._played_paths.clear()
            self.next_track()
        else:
            self._finish_playlist()

    def _finish_playlist(self):
        """Loop Off reached the end of the list (or looping was stopped because files end at once).
        The list is kept; Play starts again from the beginning."""
        quick = self._loop_mode != LOOP_OFF and self._quick_end_streak >= LOOP_QUICK_END_LIMIT
        self._quick_end_streak = 0
        self._playlist_ended = True
        self._played_paths.clear()
        self._set_play_ui(False)
        self.track_timer.stop()
        self.progress_slider.setValue(0)
        if quick:
            self._status("Loop stopped: these files end straight away (they may be damaged).", announce=True)
        else:
            self._status("End of playlist. Press Play to start again.", announce=True)
        self._update_media_controls()

    def _remove_current_and_advance(self):
        cur = self.current_index
        if cur < 0 or cur >= len(self.store):
            return
        path = self.model.remove_source(cur)
        if path in self.queue:
            self.queue.remove(path)
        self._removed_played_count += 1
        self._update_playlist_count()

        if not self.store:
            self._status("Playlist finished.", announce=True)
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
            self._update_media_controls()
            return

        if self._play_queued():
            return
        if self.shuffle_enabled:
            self.next_track()
        else:
            self.play_index(cur if cur < len(self.store) else 0)

    # ------------------------------------------------------------------ closing
    def stop_background_work(self, wait_ms=5000):
        """Stop folder scans (ALMP is closing)."""
        for s in [self.scanner, *self._old_scanners]:
            if s is not None and s.isRunning():
                s.requestInterruption()
        for s in [self.scanner, *self._old_scanners]:
            if s is not None and s.isRunning() and not s.wait(wait_ms):
                log.warning("Folder scan was still running when ALMP closed")

    def any_scan_running(self):
        return any(s is not None and s.isRunning() for s in [self.scanner, *self._old_scanners])

    def closeEvent(self, event):
        try:
            self._remember_position()
            self._save_settings()
        except Exception:          # noqa: BLE001
            log.exception("Could not save settings")
        self._closing = True
        self.track_timer.stop()
        self.hide_timer.stop()
        self._sleep_timer.stop()
        self._sleep_tip_timer.stop()
        self._fade_timer.stop()
        self._show_cursor()
        self.stop_background_work()
        if self.media_controls is not None:
            self.media_controls.stop()
        if self.player:
            try:
                self.player.terminate()
            except Exception:          # noqa: BLE001
                log.exception("mpv did not close cleanly")
        super().closeEvent(event)


__all__ = ["MediaWindow", "APP_EXE_PATH", "MPV_IMPORT_ERROR", "SCALE_CHOICES"]
