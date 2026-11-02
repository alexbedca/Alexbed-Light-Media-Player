# Alexbed Light Media Player (ALMP)
# Copyright (C) 2026 Alexander Bediako
# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings, Help and About windows. Plain words, big controls, everything reachable with Tab."""
import platform

from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR, Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QGuiApplication
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from . import APP_TITLE, __version__
from .logsetup import log
from .paths import get_log_dir, get_resource_path
from .settings import LARGE_BUTTON_CHOICES, SCALE_CHOICES, SUBTITLE_SIZE_CHOICES, VIDEO_SIZE_CHOICES

PROJECT_PAGE = "github.com/alexbedca/Alexbed-Light-Media-Player"

KEYBOARD_ROWS = [
    ("Space", "Play / pause"),
    ("F  /  Esc", "Fullscreen / leave fullscreen"),
    ("Left / Right", "Go back / forward 5 seconds"),
    ("Up / Down", "Volume (in the playlist: move up and down the list)"),
    ("Page Up / Page Down", "Previous / next track"),
    ("M", "Mute"),
    ("A", "Video size: Fit, Fill, Stretch"),
    ("S", "Save a picture of the video (in your Pictures folder)"),
    ("L", "Loop: Off, One (this track), All (whole playlist). Always Off when ALMP starts."),
    ("P", "Playlist drawer (in fullscreen)"),
    ("Ctrl+F", "Search the playlist"),
    ("Ctrl+O / Ctrl+Shift+O", "Add files / add a folder"),
    ("Ctrl+,", "Settings"),
    ("Enter", "Play the selected playlist item"),
    ("Delete / Shift+Delete", "Remove from the list / delete the file (asks first)"),
    ("Menu key or right-click", "More choices for the selected item (Play next, Show in folder...)"),
    ("Tab / Shift+Tab", "Move between buttons; Space presses the button that has the yellow frame"),
    ("F1", "This help"),
    ("Double-click the video", "Fullscreen"),
]

HOW_TO_HTML = """
<h3>Play music or videos</h3>
<p>Click <b>Add Files</b> or <b>Add Folder</b>, or drag files and folders onto the window.
The first track starts at once, even while a big folder is still being added.</p>
<h3>Find a song in a long list</h3>
<p>Type a few letters in the search box above the playlist (or press <b>Ctrl+F</b>).
Press <b>Enter</b> to play the first match.</p>
<h3>Play a song next</h3>
<p>Right-click it in the playlist and choose <b>Play next</b>.</p>
<h3>Bigger text and buttons</h3>
<p>Click the <b>gear</b> button, then choose an <b>Interface size</b> and press <b>Apply now</b>.
<b>High contrast</b> (black, white and yellow) is there too, and on the half-circle button.</p>
<h3>Stop playing after a while</h3>
<p>Click the <b>clock</b> button and choose a time, or <b>At the end of this track</b>.
The sound fades out gently during the last minute.</p>
<h3>Make ALMP open your music and videos</h3>
<p>Gear button &gt; <b>Make ALMP my default player</b>. Windows then shows its own page where you
click <b>Set default</b> (Windows asks you to do this last step yourself).</p>
<h3>Quiet and loud songs</h3>
<p>Gear button &gt; <b>Even out loud and quiet parts</b>. For quiet files you can also allow the
volume to go up to 150%.</p>
<h3>Is my download real?</h3>
<p>Only download ALMP from its GitHub Releases page and compare the SHA-256 code (see the README).</p>
<h3>ALMP and your privacy</h3>
<p>ALMP never connects to the internet. It keeps your settings and, if something went wrong,
a small error log on this PC only (the log can contain file names; it is never sent anywhere).</p>
"""


def _section(text):
    lbl = QLabel(text)
    lbl.setObjectName("sectionTitle")
    return lbl


def _note(text):
    lbl = QLabel(text)
    lbl.setObjectName("dimLabel")
    lbl.setWordWrap(True)
    return lbl


def _line():
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFrameShadow(QFrame.Shadow.Plain)
    return f


def read_text_file(name, limit=400_000):
    path = get_resource_path(name)
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read(limit)
    except OSError:
        return None


def open_log_folder():
    folder = get_log_dir()
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))


class TextDialog(QDialog):
    def __init__(self, parent, title, text):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(720, 560)
        lay = QVBoxLayout(self)
        box = QPlainTextEdit()
        box.setReadOnly(True)
        box.setPlainText(text)
        box.setAccessibleName(title)
        lay.addWidget(box)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        lay.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)


class HelpDialog(QDialog):
    def __init__(self, parent=None, start_tab=0):
        super().__init__(parent)
        self.setWindowTitle("ALMP help")
        self.resize(680, 600)
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        how = QTextBrowser()
        how.setObjectName("helpText")
        how.setOpenLinks(False)
        how.setHtml(HOW_TO_HTML)
        how.setAccessibleName("How do I")
        tabs.addTab(how, "How do I...")
        keys = QTextBrowser()
        keys.setObjectName("helpText")
        keys.setOpenLinks(False)
        keys.setHtml("<table cellpadding='6'>" + "".join(
            f"<tr><td><b>{k}</b></td><td>{v}</td></tr>" for k, v in KEYBOARD_ROWS) + "</table>")
        keys.setAccessibleName("Keyboard shortcuts")
        tabs.addTab(keys, "Keyboard")
        tabs.setCurrentIndex(start_tab)
        lay.addWidget(tabs)
        row = QHBoxLayout()
        about = QPushButton("About ALMP...")
        about.clicked.connect(lambda: AboutDialog(self).exec())
        row.addWidget(about)
        row.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)
        close.setFocus()


class AboutDialog(QDialog):
    def __init__(self, parent=None, engine_info=""):
        super().__init__(parent)
        self.setWindowTitle("About ALMP")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        title = QLabel(f"{APP_TITLE}\nVersion {__version__}")
        title.setObjectName("playlistTitle")
        lay.addWidget(title)
        self.info_text = (
            f"ALMP {__version__}\n"
            f"Python {platform.python_version()}, Qt {QT_VERSION_STR}, PyQt {PYQT_VERSION_STR}\n"
            + (engine_info + "\n" if engine_info else "")
            + f"System: {platform.platform()}\n")
        body = QLabel(
            "Free software by Alexander Bediako, licensed under the GNU General Public License, "
            "version 3 or (at your option) any later version (GPL-3.0-or-later). It comes with "
            "NO WARRANTY.\n\n"
            "ALMP never connects to the internet, has no ads and no tracking.\n\n"
            f"Project page (copy it into your browser): {PROJECT_PAGE}\n\n"
            + self.info_text)
        body.setObjectName("helpText")
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse
                                     | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        lay.addWidget(body)
        grid = QGridLayout()
        b_lic = QPushButton("Licence (GPL)...")
        b_lic.clicked.connect(lambda: self._show_file("LICENSE", "Licence"))
        b_tp = QPushButton("Third-party notices...")
        b_tp.clicked.connect(lambda: self._show_file("THIRD-PARTY-NOTICES.txt", "Third-party notices"))
        b_log = QPushButton("Open log folder")
        b_log.setToolTip(str(get_log_dir()))
        b_log.clicked.connect(open_log_folder)
        b_copy = QPushButton("Copy version info")
        b_copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.info_text))
        grid.addWidget(b_lic, 0, 0)
        grid.addWidget(b_tp, 0, 1)
        grid.addWidget(b_log, 1, 0)
        grid.addWidget(b_copy, 1, 1)
        lay.addLayout(grid)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        lay.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)
        close.setFocus()

    def _show_file(self, name, title):
        text = read_text_file(name)
        if text is None:
            text = (f"{name} was not found next to ALMP.\n\n"
                    f"It is included in the ALMP zip file and on the project page: {PROJECT_PAGE}")
        TextDialog(self, title, text).exec()


class SettingsDialog(QDialog):
    """Every setting in one place. Changes apply at once (except the interface size, which needs a
    restart). `win` is the main window; it does the real work through small methods."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("ALMP settings")
        s = win.settings
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(8)
        scroll.setWidget(page)
        outer.addWidget(scroll)

        # --- Look and size ---
        lay.addWidget(_section("Look and size"))
        self.hc = QCheckBox("High contrast (black, white and yellow)")
        self.hc.setChecked(bool(s["high_contrast"]))
        self.hc.toggled.connect(win.set_high_contrast)
        lay.addWidget(self.hc)
        row = QHBoxLayout()
        lbl = QLabel("Interface size:")
        self.scale = QComboBox()
        for label, _v in SCALE_CHOICES:
            self.scale.addItem(label)
        self.scale.setCurrentIndex(self._scale_index(s["ui_scale"]))
        self.scale.setAccessibleName("Interface size")
        lbl.setBuddy(self.scale)
        self.apply_scale = QPushButton("Apply now (restarts ALMP)")
        self.apply_scale.setToolTip("ALMP closes and opens again at the new size.\n"
                                    "The playlist is not kept: ALMP always starts clean.")
        self.apply_scale.clicked.connect(self._apply_scale_now)
        self.scale.currentIndexChanged.connect(self._scale_changed)
        row.addWidget(lbl)
        row.addWidget(self.scale, 1)
        row.addWidget(self.apply_scale)
        lay.addLayout(row)
        row = QHBoxLayout()
        lbl = QLabel("Start screen in fullscreen:")
        self.large = QComboBox()
        for label, _v in LARGE_BUTTON_CHOICES:
            self.large.addItem(label)
        cur = [v for _l, v in LARGE_BUTTON_CHOICES].index(s["large_buttons"])
        self.large.setCurrentIndex(cur)
        self.large.setAccessibleName("Start screen size in fullscreen")
        lbl.setBuddy(self.large)
        self.large.currentIndexChanged.connect(
            lambda i: win.set_large_buttons(LARGE_BUTTON_CHOICES[i][1]))
        row.addWidget(lbl)
        row.addWidget(self.large, 1)
        lay.addLayout(row)
        lay.addWidget(_note("Big buttons and text on a TV or large screen. Automatic makes them bigger "
                            "only in fullscreen; no restart needed."))
        self.scale_note = _note("The size changes after ALMP restarts. Your playlist is not kept "
                                "when it restarts (ALMP always starts clean).")
        lay.addWidget(self.scale_note)
        lay.addWidget(_line())

        # --- Windows ---
        lay.addWidget(_section("Windows"))
        self.media_keys = QCheckBox("Media keys work while ALMP is in the background "
                                    "(Windows media controls)")
        self.media_keys.setChecked(bool(s["media_controls"]))
        self.media_keys.toggled.connect(win.set_media_controls)
        lay.addWidget(self.media_keys)
        self.media_note = _note(win.media_controls_status_text())
        lay.addWidget(self.media_note)

        self.startup = QCheckBox("Start ALMP when I sign in to Windows")
        self.startup.setChecked(win.startup_checkbox.isChecked())
        self.startup.toggled.connect(win.startup_checkbox.setChecked)
        win.startup_checkbox.toggled.connect(self._sync_startup)
        lay.addWidget(self.startup)

        can_reg = win.can_register_with_windows()
        row = QHBoxLayout()
        self.make_default = QPushButton("Make ALMP my default player...")
        self.make_default.setEnabled(can_reg)
        self.make_default.clicked.connect(win.make_default_player)
        self.undo_default = QPushButton("Remove ALMP from Default apps")
        self.undo_default.setEnabled(can_reg)
        self.undo_default.clicked.connect(win.remove_default_player)
        row.addWidget(self.make_default)
        row.addWidget(self.undo_default)
        row.addStretch(1)
        lay.addLayout(row)
        self.folder_verb = QCheckBox('Show "Play with ALMP" when I right-click a folder in Explorer')
        self.folder_verb.setEnabled(can_reg)
        self.folder_verb.setChecked(win.folder_verb_installed())
        self.folder_verb.toggled.connect(self._folder_verb_toggled)
        lay.addWidget(self.folder_verb)
        if not can_reg:
            lay.addWidget(_note("These Windows options work in ALMP.exe on Windows only."))
        else:
            lay.addWidget(_note("These change settings for your Windows account only, and can be undone "
                                "here or with Remove-ALMP-Defaults.bat."))
        lay.addWidget(_line())

        # --- Playback ---
        lay.addWidget(_section("Playback"))
        row = QHBoxLayout()
        lbl = QLabel("Video size:")
        self.video_size = QComboBox()
        for label, _v in VIDEO_SIZE_CHOICES:
            self.video_size.addItem(label)
        values = [v for _l, v in VIDEO_SIZE_CHOICES]
        self.video_size.setCurrentIndex(values.index(s["video_size"]) if s["video_size"] in values else 0)
        self.video_size.setAccessibleName("Video size")
        self.video_size.currentIndexChanged.connect(lambda i: win.set_video_size(values[i], save=True))
        lbl.setBuddy(self.video_size)
        row.addWidget(lbl)
        row.addWidget(self.video_size, 1)
        lay.addLayout(row)

        self.remove_played = QCheckBox("Remove each track from the list after it has played")
        self.remove_played.setChecked(win.remove_played_checkbox.isChecked())
        self.remove_played.setEnabled(win.remove_played_checkbox.isEnabled())
        if not self.remove_played.isEnabled():
            self.remove_played.setToolTip("Not used while Loop All is on.")
        self.remove_played.toggled.connect(win.remove_played_checkbox.setChecked)
        lay.addWidget(self.remove_played)

        self.keep_speed = QCheckBox("Keep the playback speed for the next tracks (until ALMP closes)")
        self.keep_speed.setChecked(bool(s["keep_speed"]))
        self.keep_speed.toggled.connect(lambda v: win.set_simple_setting("keep_speed", v))
        lay.addWidget(self.keep_speed)

        self.normalize = QCheckBox("Even out loud and quiet parts (volume normaliser)")
        self.normalize.setChecked(bool(s["normalize_volume"]))
        self.normalize.toggled.connect(win.set_normalize_volume)
        lay.addWidget(self.normalize)

        self.boost = QCheckBox("Allow the volume to go up to 150% (for quiet files)")
        self.boost.setChecked(bool(s["volume_boost"]))
        self.boost.toggled.connect(win.set_volume_boost)
        lay.addWidget(self.boost)

        self.resume = QCheckBox("Continue long files (20 minutes or more) where I stopped")
        self.resume.setChecked(bool(s["resume_long_files"]))
        self.resume.setToolTip("Off by default. Only for films, audiobooks and talks of 20 minutes or more.\n"
                               "ALMP still never remembers your playlist.")
        self.resume.toggled.connect(win.set_resume_long_files)
        lay.addWidget(self.resume)
        row = QHBoxLayout()
        row.addWidget(_note("Remembers up to 200 places on this PC only. Turning it off forgets them all."), 1)
        self.forget = QPushButton("Forget saved places")
        self.forget.clicked.connect(win.forget_resume_positions)
        row.addWidget(self.forget)
        lay.addLayout(row)
        lay.addWidget(_line())

        # --- Subtitles ---
        lay.addWidget(_section("Subtitles"))
        row = QHBoxLayout()
        lbl = QLabel("Subtitle size:")
        self.sub_size = QComboBox()
        scales = [v for _l, v in SUBTITLE_SIZE_CHOICES]
        for label, _v in SUBTITLE_SIZE_CHOICES:
            self.sub_size.addItem(label)
        self.sub_size.setCurrentIndex(min(range(len(scales)), key=lambda i: abs(scales[i] - s["subtitle_scale"])))
        self.sub_size.setAccessibleName("Subtitle size")
        self.sub_size.currentIndexChanged.connect(lambda i: win.set_subtitle_scale(scales[i]))
        lbl.setBuddy(self.sub_size)
        row.addWidget(lbl)
        row.addWidget(self.sub_size, 1)
        lay.addLayout(row)
        self.sub_box = QCheckBox("Dark box behind subtitles (easier to read)")
        self.sub_box.setChecked(bool(s["subtitle_background"]))
        self.sub_box.toggled.connect(win.set_subtitle_background)
        lay.addWidget(self.sub_box)
        lay.addWidget(_line())

        lay.addStretch(1)

        bottom = QHBoxLayout()
        b_help = QPushButton("Help")
        b_help.clicked.connect(win.show_help)
        b_about = QPushButton("About ALMP")
        b_about.clicked.connect(win.show_about)
        bottom.addWidget(b_help)
        bottom.addWidget(b_about)
        bottom.addStretch(1)
        close = QPushButton("Close")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        bottom.addWidget(close)
        outer.addLayout(bottom)

        self._scale_changed(self.scale.currentIndex(), save=False)
        self._fit_to_screen()
        self.hc.setFocus()

    def _fit_to_screen(self):
        try:
            geo = self.screen().availableGeometry()
            self.resize(min(640, int(geo.width() * 0.95)), min(760, int(geo.height() * 0.92)))
        except (AttributeError, RuntimeError):
            self.resize(600, 640)

    @staticmethod
    def _scale_index(value):
        for i, (_l, v) in enumerate(SCALE_CHOICES):
            if abs(v - float(value)) < 0.01:
                return i
        return 0

    def _scale_changed(self, index, save=True):
        if 0 <= index < len(SCALE_CHOICES):
            if save:
                self.win.save_ui_scale(SCALE_CHOICES[index][1])
            self.apply_scale.setEnabled(abs(SCALE_CHOICES[index][1] - self.win.running_scale) > 0.01)

    def _apply_scale_now(self):
        self.accept()
        self.win.restart_for_new_size()

    def _sync_startup(self, checked):
        try:
            self.startup.blockSignals(True)
            self.startup.setChecked(checked)
            self.startup.blockSignals(False)
        except RuntimeError:
            pass                      # the dialog is closed

    def _folder_verb_toggled(self, on):
        ok = self.win.set_folder_verb(on)
        if not ok:
            self.folder_verb.blockSignals(True)
            self.folder_verb.setChecked(not on)
            self.folder_verb.blockSignals(False)


def describe_engine(player):
    """'mpv 0.40.0, FFmpeg n7.1' for the About window (empty if mpv does not say)."""
    if player is None:
        return ""
    parts = []
    for prop, label in (("mpv-version", ""), ("ffmpeg-version", "FFmpeg ")):
        try:
            v = player[prop]
            if v:
                parts.append(f"{label}{v}")
        except Exception:          # noqa: BLE001
            log.debug("mpv property %s not available", prop, exc_info=True)
    return ("Playback engine: " + ", ".join(parts)) if parts else ""

