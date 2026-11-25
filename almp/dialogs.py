# Alexbed Light Media Player (ALMP)
# Copyright (C) 2026 Alexander Bediako
# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings, Help and About windows. Plain words, big controls, everything reachable with Tab."""
import platform
import sys

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
from .paths import data_dir_is_portable, get_log_dir, get_resource_path, get_settings_dir
from .settings import (
    ENHANCE_CHOICES,
    LARGE_BUTTON_CHOICES,
    LOG_MODE_CHOICES,
    REPLAYGAIN_CHOICES,
    SCALE_CHOICES,
    SUBTITLE_SIZE_CHOICES,
    UPSCALING_CHOICES,
    VIDEO_SIZE_CHOICES,
)

IS_LINUX = sys.platform.startswith("linux")      # the Linux port shows a Linux section in Settings
PROJECT_PAGE = "github.com/alexbedca/Alexbed-Light-Media-Player"
RELEASES_PAGE = PROJECT_PAGE + "/releases"
RELEASES_URL = "https://" + RELEASES_PAGE          # what "Copy link" puts on the clipboard (text only)

LOG_MODE_NOTES = {
    "clear": "The log is deleted when ALMP closes normally. If something went wrong during that run, "
             "it is kept (at most 256 KB) so the problem can be looked at.",
    "keep": "The log of the last run is kept (at most 256 KB, plus the run before it). "
            "It can contain names of files you played.",
    "off": "No log file is written at all. If something goes wrong, there are no details to look at, "
           "and tools/bench_startup.py cannot measure start-up times.",
}
UPSCALING_NOTE = ("Only matters when a video is smaller than the screen (for example 480p or 720p on a "
                  "1080p screen). Sharp and High quality use mpv's own built-in scalers (nothing is "
                  "downloaded). High quality needs more graphics power and may stutter on slower "
                  "graphics cards.")

SHADERS_NOTE = ("Automatic sharpens videos of 720p or less with FSRCNNX (by igv, LGPL-3.0, included "
                "with ALMP; nothing is downloaded). HD videos are left as they are, and the shader only "
                "works while the picture is enlarged. If the graphics card cannot keep up (more than 5% "
                "of the frames dropped), ALMP turns it off by itself. Press E while watching to compare "
                "with and without. \"My own shaders\" uses the .glsl files you put in the shaders folder "
                "(for example Anime4K) instead, also only for low-quality videos.")
REPLAYGAIN_NOTE = ("Uses the volume levels stored in the files (ReplayGain tags), so loud and quiet songs "
                   "play at a similar volume. Automatic uses the album level when tracks of one folder play "
                   "in order, and the track level otherwise. Files without tags play as they are, so it "
                   "only helps when most of your music is tagged: otherwise the tagged albums just play "
                   "quieter. Off by default. Automatic does nothing while Exclusive audio (bit-perfect) is on.")

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
    ("E", "Picture sharpening off / on (low-quality videos), to compare"),
    ("P", "Show / hide the playlist"),
    ("Ctrl+F", "Search the playlist"),
    ("Ctrl+O / Ctrl+Shift+O", "Add files / add a folder"),
    ("Ctrl+,", "Settings"),
    ("Enter", "Play the selected playlist item"),
    ("Delete / Shift+Delete", "Remove from the list / delete the file (asks first)"),
    ("Ctrl+click / Shift+click", "Select several items in the playlist (then Delete or Shift+Delete)"),
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
<p>ALMP never connects to the internet. It keeps its settings and a small log in the <b>Data</b>
folder next to ALMP.exe, so deleting the ALMP folder removes everything. The log is cleared when
ALMP closes, unless something went wrong (Settings &gt; Privacy and files). It is never sent anywhere.</p>
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
        self.releases_text = (
            f"Newer versions: {RELEASES_PAGE}\n"
            "ALMP never connects to the internet; open this address yourself to look for a newer version.")
        body.setObjectName("helpText")
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse
                                     | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        lay.addWidget(body)
        rel_row = QHBoxLayout()
        rel = QLabel(self.releases_text)
        rel.setObjectName("helpText")
        rel.setWordWrap(True)
        rel.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse
                                    | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        rel_row.addWidget(rel, 1)
        self.copy_link = QPushButton("Copy link")
        self.copy_link.setToolTip("Copies the address only. ALMP does not open a browser or check anything.")
        self.copy_link.setAccessibleName("Copy the address of the releases page")
        self.copy_link.clicked.connect(self.copy_releases_link)
        rel_row.addWidget(self.copy_link, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(rel_row)
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

    def copy_releases_link(self):
        QGuiApplication.clipboard().setText(RELEASES_URL)
        self.copy_link.setText("Copied")

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
        scroll.setObjectName("settingsScroll")      # themed: else Windows light mode paints it near-white
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        page = QWidget()
        page.setObjectName("settingsPage")
        lay = QVBoxLayout(page)
        lay.setSpacing(8)
        scroll.setWidget(page)
        self._page = page
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

        if IS_LINUX:
            self._add_linux_section(lay, win)
        else:
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
            self.folder_verb = QCheckBox('Show "Play with ALMP" and "Add to ALMP playlist" when I right-click '
                                         'files or a folder in Explorer')
            self.folder_verb.setToolTip("Works with one or many selected audio and video files.\n"
                                        'On Windows 11 they are under "Show more options" (or press Shift+F10).')
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

        self.play_fullscreen = QCheckBox("Always play videos in fullscreen")
        self.play_fullscreen.setChecked(bool(s["play_fullscreen"]))
        self.play_fullscreen.setToolTip("Every video starts in fullscreen. Esc leaves fullscreen for that video;\n"
                                        "the next video starts in fullscreen again. Music is not affected.")
        self.play_fullscreen.toggled.connect(lambda v: win.set_simple_setting("play_fullscreen", v))
        lay.addWidget(self.play_fullscreen)

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

        row = QHBoxLayout()
        lbl = QLabel("Video upscaling:")
        self.upscaling = QComboBox()
        up_values = [v for _l, v in UPSCALING_CHOICES]
        for label, _v in UPSCALING_CHOICES:
            self.upscaling.addItem(label)
        self.upscaling.setCurrentIndex(up_values.index(s["upscaling"]) if s["upscaling"] in up_values else 0)
        self.upscaling.setAccessibleName("Video upscaling")
        self.upscaling.currentIndexChanged.connect(lambda i: win.set_upscaling(up_values[i]))
        lbl.setBuddy(self.upscaling)
        row.addWidget(lbl)
        row.addWidget(self.upscaling, 1)
        lay.addLayout(row)
        lay.addWidget(_note(UPSCALING_NOTE))
        row = QHBoxLayout()
        lbl = QLabel("Picture sharpening:")
        self.enhance = QComboBox()
        en_values = [v for _l, v in ENHANCE_CHOICES]
        for label, _v in ENHANCE_CHOICES:
            self.enhance.addItem(label)
        self.enhance.setCurrentIndex(en_values.index(s["enhance"]) if s["enhance"] in en_values else 0)
        self.enhance.setAccessibleName("Picture sharpening for low-quality videos")
        self.enhance.currentIndexChanged.connect(lambda i: self._enhance_changed(en_values[i]))
        lbl.setBuddy(self.enhance)
        row.addWidget(lbl)
        row.addWidget(self.enhance, 1)
        lay.addLayout(row)
        row = QHBoxLayout()
        self.shader_found = _note("")
        row.addWidget(self.shader_found, 1)
        self.open_shaders = QPushButton("Open shaders folder")
        self.open_shaders.clicked.connect(self._open_shader_folder)
        row.addWidget(self.open_shaders)
        lay.addLayout(row)
        lay.addWidget(_note(SHADERS_NOTE))
        self._update_shader_note()
        lay.addWidget(_line())

        # --- Music (lossless) ---
        lay.addWidget(_section("Music"))
        self.gapless = QCheckBox("Gapless playback (prefetch the next track)")
        self.gapless.setChecked(bool(s["gapless"]))
        self.gapless.setToolTip("Live albums and DJ mixes play without a short silence between tracks.\n"
                                "ALMP reads the start of the next track while this one plays.")
        self.gapless.toggled.connect(win.set_gapless)
        lay.addWidget(self.gapless)
        self.exclusive = QCheckBox("Exclusive audio (bit-perfect)" if IS_LINUX
                                   else "Exclusive audio (WASAPI exclusive, bit-perfect)")
        self.exclusive.setChecked(bool(s["audio_exclusive"]))
        self.exclusive.toggled.connect(win.set_audio_exclusive)
        lay.addWidget(self.exclusive)
        if IS_LINUX:
            self._add_linux_exclusive_output(lay, win, s)
        else:
            lay.addWidget(_note("For FLAC listeners with an external DAC or AV receiver: the sound goes to the "
                                "device untouched (no Windows mixing). While ALMP plays, OTHER programs and "
                                "Windows sounds are silent. ALMP's volume slider still works."))
        row = QHBoxLayout()
        lbl = QLabel("ReplayGain:")
        self.replaygain = QComboBox()
        rg_values = [v for _l, v in REPLAYGAIN_CHOICES]
        for label, _v in REPLAYGAIN_CHOICES:
            self.replaygain.addItem(label)
        self.replaygain.setCurrentIndex(rg_values.index(s["replaygain"]) if s["replaygain"] in rg_values else 0)
        self.replaygain.setAccessibleName("ReplayGain volume levelling")
        self.replaygain.currentIndexChanged.connect(lambda i: win.set_replaygain(rg_values[i]))
        lbl.setBuddy(self.replaygain)
        row.addWidget(lbl)
        row.addWidget(self.replaygain, 1)
        lay.addLayout(row)
        lay.addWidget(_note(REPLAYGAIN_NOTE))
        lay.addWidget(_line())

        # --- Subtitles ---
        lay.addWidget(_section("Subtitles"))
        self.show_subs = QCheckBox("Show subtitles")
        self.show_subs.setChecked(bool(s["show_subtitles"]))
        self.show_subs.setToolTip("Remembered for the next time. Off: subtitles stay hidden until you turn them on\n"
                                  "here or in the subtitles menu (right-click the video).")
        self.show_subs.toggled.connect(win.set_show_subtitles)
        lay.addWidget(self.show_subs)
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

        # --- Privacy and files ---
        lay.addWidget(_section("Privacy and files"))
        row = QHBoxLayout()
        lbl = QLabel("Log:")
        self.log_mode = QComboBox()
        log_values = [v for _l, v in LOG_MODE_CHOICES]
        for label, _v in LOG_MODE_CHOICES:
            self.log_mode.addItem(label)
        self.log_mode.setCurrentIndex(log_values.index(s["log_mode"]) if s["log_mode"] in log_values else 0)
        self.log_mode.setAccessibleName("Log")
        lbl.setBuddy(self.log_mode)
        row.addWidget(lbl)
        row.addWidget(self.log_mode, 1)
        lay.addLayout(row)
        self.log_note = _note(LOG_MODE_NOTES.get(s["log_mode"], ""))
        lay.addWidget(self.log_note)
        self.log_mode.currentIndexChanged.connect(lambda i: self._log_mode_changed(log_values[i]))
        lay.addWidget(_note(data_folder_text()))
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
            # Wide enough for the widest row (8.2.5 cut off "Open shaders folder" and other text on
            # the right), never wider than the screen.
            want = max(640, self._page.sizeHint().width() + 48)
            self.resize(min(want, int(geo.width() * 0.95)), min(760, int(geo.height() * 0.92)))
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

    def _add_linux_section(self, lay, win):
        """Linux port: the app-menu entry ("Open With" in the file manager), default player and
        autostart. All of it is for this user only (~/.local/share/applications, ~/.config/autostart)."""
        lay.addWidget(_section("Linux"))
        # Same order as the Windows section: background media keys first.
        self.media_keys = QCheckBox("Media keys work while ALMP is in the background "
                                    "(desktop media controls, MPRIS)")
        self.media_keys.setChecked(bool(win.settings["media_controls"]))
        self.media_keys.toggled.connect(win.set_media_controls)
        lay.addWidget(self.media_keys)
        self.media_note = _note(win.media_controls_status_text())
        lay.addWidget(self.media_note)
        can_reg = win.can_register_with_desktop()
        self.menu_entry = QCheckBox('Show ALMP in the app menu and in "Open With" in the file manager')
        self.menu_entry.setEnabled(can_reg)
        self.menu_entry.setChecked(win.desktop_entry_installed())
        self.menu_entry.toggled.connect(self._menu_entry_toggled)
        lay.addWidget(self.menu_entry)
        row = QHBoxLayout()
        self.make_default = QPushButton("Make ALMP my default player")
        self.make_default.setEnabled(can_reg)
        self.make_default.clicked.connect(win.make_default_player)
        row.addWidget(self.make_default)
        row.addStretch(1)
        lay.addLayout(row)
        self.startup = QCheckBox("Start ALMP when I sign in")
        self.startup.setChecked(win.startup_checkbox.isChecked())
        self.startup.toggled.connect(win.startup_checkbox.setChecked)
        win.startup_checkbox.toggled.connect(self._sync_startup)
        lay.addWidget(self.startup)
        if not can_reg:
            lay.addWidget(_note("These options work in the built ALMP program only (not python main.py)."))
        else:
            lay.addWidget(_note("These change settings for your Linux account only. Turning the menu entry "
                                "off also undoes the default player."))
        lay.addWidget(_line())

    def _add_linux_exclusive_output(self, lay, win, s):
        """Linux: where "Exclusive audio" sends the sound. PipeWire (exclusive) works everywhere; a direct
        device (HDMI to a TV/receiver, analog out, USB DAC) bypasses PipeWire and is bit-perfect."""
        row = QHBoxLayout()
        row.addWidget(QLabel("Output:"))
        self.exclusive_output = QComboBox()
        self.exclusive_output.addItem("Through PipeWire (exclusive)", "")
        current = s.get("audio_exclusive_device", "")
        names = []
        for name, description in win.exclusive_device_choices():
            self.exclusive_output.addItem(f"Direct: {description}", name)
            names.append(name)
        if current and current not in names:
            self.exclusive_output.addItem(f"Direct: {current} (not connected now)", current)
        index = self.exclusive_output.findData(current)
        self.exclusive_output.setCurrentIndex(max(0, index))
        self.exclusive_output.setEnabled(self.exclusive.isChecked())
        self.exclusive.toggled.connect(self.exclusive_output.setEnabled)
        self.exclusive_output.currentIndexChanged.connect(
            lambda _i: win.set_exclusive_device(self.exclusive_output.currentData() or ""))
        row.addWidget(self.exclusive_output, 1)
        lay.addLayout(row)
        lay.addWidget(_note("For FLAC listeners with an external DAC, AV receiver or TV: the sound goes to the "
                            "device untouched (no PipeWire mixing with a Direct output). While ALMP plays, OTHER "
                            "programs and system sounds are silent on that output. ALMP's volume slider still "
                            "works (bit-perfect at 100%). If the device is busy, ALMP plays through PipeWire and "
                            "says so."))

    def _menu_entry_toggled(self, on):
        ok = self.win.set_desktop_entry(on)
        if not ok:
            self.menu_entry.blockSignals(True)
            self.menu_entry.setChecked(not on)
            self.menu_entry.blockSignals(False)

    def _sync_startup(self, checked):
        try:
            self.startup.blockSignals(True)
            self.startup.setChecked(checked)
            self.startup.blockSignals(False)
        except RuntimeError:
            pass                      # the dialog is closed

    def _enhance_changed(self, mode):
        self.win.set_enhance(mode)
        self._update_shader_note()

    def _open_shader_folder(self):
        self.win.open_user_shader_folder()
        self._update_shader_note()

    def _update_shader_note(self):
        import os

        from .player import find_user_shaders
        found = find_user_shaders(self.win.user_shader_folder())
        if found:
            names = ", ".join(os.path.basename(f) for f in found[:3]) + (" ..." if len(found) > 3 else "")
            self.shader_found.setText(f"Found {len(found)} shader file(s): {names}")
        else:
            self.shader_found.setText("No shader files found yet.")

    def _log_mode_changed(self, mode):
        self.win.set_log_mode(mode)
        self.log_note.setText(LOG_MODE_NOTES.get(mode, ""))

    def _folder_verb_toggled(self, on):
        ok = self.win.set_folder_verb(on)
        if not ok:
            self.folder_verb.blockSignals(True)
            self.folder_verb.setChecked(not on)
            self.folder_verb.blockSignals(False)


def data_folder_text(portable=None, folder=None):
    """Where ALMP keeps its files, in plain words, for Settings."""
    portable = data_dir_is_portable() if portable is None else portable
    folder = get_settings_dir() if folder is None else folder
    if portable:
        return (f"ALMP keeps its settings and log in {folder}. Nothing else is stored on this PC, "
                "so deleting the ALMP folder removes everything (Windows entries such as Default apps, "
                "the right-click menu or Run at Startup only exist if you turned them on above).")
    return (f"The ALMP folder cannot be written to (for example in Program Files or on a read-only USB "
            f"stick), so settings are kept in {folder} and the log in {get_log_dir()}. "
            "Move the ALMP folder somewhere you can write to, to keep everything inside it.")


def describe_engine(player):
    """'mpv 0.40.0, FFmpeg n7.1' for the About window (empty if mpv does not say)."""
    if player is None:
        return ""
    parts = []
    for prop, label in (("mpv-version", ""), ("ffmpeg-version", "FFmpeg ")):
        try:
            # mpv *runtime* properties: python-mpv's player["..."] only reads options, so use attributes.
            v = getattr(player, prop.replace("-", "_"))
            if v:
                parts.append(f"{label}{v}")
        except Exception:          # noqa: BLE001
            log.debug("mpv property %s not available", prop, exc_info=True)
    return ("Playback engine: " + ", ".join(parts)) if parts else ""

