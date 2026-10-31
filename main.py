import os
import sys
import ctypes
import random
import winreg
from pathlib import Path


# --- Nuitka & PyInstaller Resource Path Engine ---
def get_resource_path(relative_path):
    if hasattr(sys, "_MEIPASS"):
        base_path = sys._MEIPASS
    elif hasattr(sys, "frozen") or "__compiled__" in globals():
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


# --- Inject Local MPV DLL Dependency ---
try:
    runtime_dir = get_resource_path("runtime")
    if os.path.exists(runtime_dir):
        os.environ["PATH"] = runtime_dir + os.pathsep + os.environ["PATH"]
except Exception:
    pass

from PyQt6.QtCore import (
    Qt,
    QObject,
    pyqtSignal,
    QThread,
    QTimer,
    QEvent,
    QLockFile,
    QStandardPaths,
)
from PyQt6.QtGui import QIcon, QPixmap, QImage, QShortcut, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QFileDialog,
    QLabel,
    QCheckBox,
    QMessageBox,
    QSplitter,
    QSlider,
    QComboBox,
    QDialog,
)

import mpv
from mutagen import File as MutagenFile

SUPPORTED_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
    ".wmv",
    ".m4v",
    ".webm",
    ".mpg",
    ".mpeg",
    ".ts",
    ".m2ts",
    ".flv",
    ".mp3",
    ".flac",
    ".wav",
    ".aac",
    ".m4a",
    ".ogg",
    ".opus",
    ".wma",
}

AUDIO_EXTENSIONS = {".mp3", ".flac", ".wav", ".aac", ".m4a", ".ogg", ".opus", ".wma"}

APP_NAME = "AlexbedLightMediaPlayer"
REGISTRY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


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
        if "EOF" in reason_text:
            return "EOF"
        if "STOP" in reason_text:
            return "STOP"
        if "QUIT" in reason_text:
            return "QUIT"
        if "ERROR" in reason_text:
            return "ERROR"
        if "REDIRECT" in reason_text:
            return "REDIRECT"
        return reason_text
    except Exception as exc:
        print(f"[mpv] Could not extract end-file reason: {exc}")
        return "UNKNOWN"


class CustomConfirmDialog(QDialog):
    def __init__(self, parent, title, message):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setFixedWidth(500)

        layout = QVBoxLayout(self)
        lbl = QLabel(message)
        lbl.setWordWrap(True)
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
                            d
                            for d in dirs
                            if not d.startswith("$")
                            and d.lower()
                            not in {"system volume information", "$recycle.bin"}
                        ]
                        for filename in files:
                            ext = Path(filename).suffix.lower()
                            if ext in SUPPORTED_EXTENSIONS:
                                found.append(os.path.join(root, filename))
                elif os.path.isfile(target):
                    ext = Path(target).suffix.lower()
                    if ext in SUPPORTED_EXTENSIONS:
                        found.append(target)
            found.sort(key=lambda path: path.casefold())
            self.files_found.emit(found)
        except Exception as exc:
            self.scan_error.emit(str(exc))


class MediaWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Alexbed Light Media Player")
        self.resize(1200, 700)

        icon_file_path = get_resource_path("icon.ico")
        if os.path.exists(icon_file_path):
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

        self.track_timer = QTimer(self)
        self.track_timer.setInterval(200)
        self.track_timer.timeout.connect(self._poll_player_metrics)

        self.hide_timer = QTimer(self)
        self.hide_timer.setInterval(5000)
        self.hide_timer.timeout.connect(self._hide_fullscreen_overlays)

        self._build_ui()
        self._setup_shortcuts()
        self._init_player()

        self.installEventFilter(self)
        QTimer.singleShot(100, self._force_focus)

    def _setup_shortcuts(self):
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, activated=self.play_or_resume)
        QShortcut(QKeySequence(Qt.Key.Key_F), self, activated=self._toggle_fullscreen)
        QShortcut(
            QKeySequence(Qt.Key.Key_Right),
            self,
            activated=lambda: (
                self.player.seek(5, reference="relative") if self.player else None
            ),
        )
        QShortcut(
            QKeySequence(Qt.Key.Key_Left),
            self,
            activated=lambda: (
                self.player.seek(-5, reference="relative") if self.player else None
            ),
        )
        QShortcut(
            QKeySequence(Qt.Key.Key_Up),
            self,
            activated=lambda: self.volume_slider.setValue(
                self.volume_slider.value() + 5
            ),
        )
        QShortcut(
            QKeySequence(Qt.Key.Key_Down),
            self,
            activated=lambda: self.volume_slider.setValue(
                self.volume_slider.value() - 5
            ),
        )
        QShortcut(QKeySequence(Qt.Key.Key_PageUp), self, activated=self.previous_track)
        QShortcut(QKeySequence(Qt.Key.Key_PageDown), self, activated=self.next_track)
        QShortcut(QKeySequence(Qt.Key.Key_M), self, activated=self._toggle_mute)

        QShortcut(
            QKeySequence(Qt.Key.Key_MediaPlay), self, activated=self.play_or_resume
        )
        QShortcut(
            QKeySequence(Qt.Key.Key_MediaPause), self, activated=self.play_or_resume
        )
        QShortcut(
            QKeySequence(Qt.Key.Key_MediaTogglePlayPause),
            self,
            activated=self.play_or_resume,
        )
        QShortcut(QKeySequence(Qt.Key.Key_MediaNext), self, activated=self.next_track)
        QShortcut(
            QKeySequence(Qt.Key.Key_MediaPrevious), self, activated=self.previous_track
        )

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
            elif event.type() == QEvent.Type.MouseMove and self._is_fullscreen:
                self._show_cursor()
                self.splitter.setSizes(
                    [int(self.width() * 0.75), int(self.width() * 0.25)]
                )
                self.control_panel_widget.show()
                self.fullscreen_close_button.show()
                self.fullscreen_title_label.show()
                self.hide_timer.start()
            elif event.type() == QEvent.Type.Wheel:
                delta = event.angleDelta().y()
                if delta > 0:
                    self.volume_slider.setValue(self.volume_slider.value() + 5)
                elif delta < 0:
                    self.volume_slider.setValue(self.volume_slider.value() - 5)
                return True
        return super().eventFilter(obj, event)

    def _build_ui(self):
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_layout.addWidget(self.splitter)

        self.left_panel = QWidget()
        self.left_layout = QVBoxLayout(self.left_panel)
        self.left_layout.setContentsMargins(5, 5, 5, 5)

        self.video = QWidget()
        self.video.setMinimumSize(480, 270)
        self.video.setStyleSheet("background-color: black;")
        self.video.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.video.installEventFilter(self)
        self.left_layout.addWidget(self.video, stretch=1)

        self.audio_art_label = QLabel(self.video)
        self.audio_art_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.audio_art_label.setStyleSheet("background-color: transparent;")
        self.audio_art_label.hide()

        self.control_panel_widget = QWidget()
        self.control_panel_layout = QVBoxLayout(self.control_panel_widget)
        self.control_panel_layout.setContentsMargins(0, 0, 0, 0)

        self.progress_slider = QSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setRange(0, 0)
        self.progress_slider.sliderMoved.connect(self.slider_user_scrubbed)
        self.progress_slider.sliderPressed.connect(self._start_scrubbing)
        self.progress_slider.sliderReleased.connect(self._stop_scrubbing)
        self.control_panel_layout.addWidget(self.progress_slider)

        self.status_label = QLabel(
            "Drag & Drop folders/videos here or choose an action."
        )
        self.status_label.setStyleSheet(
            "font-size: 15px; font-weight: bold; margin-left: 5px;"
        )
        self.control_panel_layout.addWidget(self.status_label)

        self.controls_widget = QWidget()
        controls_layout = QHBoxLayout(self.controls_widget)
        controls_layout.setContentsMargins(0, 0, 0, 0)

        control_btn_style = "font-size: 18px; padding: 8px 16px; font-weight: bold;"

        self.previous_button = QPushButton("⏮ Previous")
        self.previous_button.setStyleSheet(control_btn_style)
        self.previous_button.clicked.connect(self.previous_track)
        controls_layout.addWidget(self.previous_button)

        self.play_button = QPushButton("▶ Play")
        self.play_button.setStyleSheet(
            "font-size: 20px; padding: 8px 20px; font-weight: bold;"
        )
        self.play_button.clicked.connect(self.play_or_resume)
        controls_layout.addWidget(self.play_button)

        self.next_button = QPushButton("Next ⏭")
        self.next_button.setStyleSheet(control_btn_style)
        self.next_button.clicked.connect(self.next_track)
        controls_layout.addWidget(self.next_button)

        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["0.5x", "1.0x", "1.5x", "2.0x"])
        self.speed_combo.setCurrentText("1.0x")
        self.speed_combo.currentTextChanged.connect(self.change_speed)
        self.speed_combo.setStyleSheet("font-size: 14px; padding: 4px;")
        controls_layout.addWidget(self.speed_combo)

        self.control_panel_layout.addWidget(self.controls_widget)
        self.left_layout.addWidget(self.control_panel_widget)

        self.right_panel = QWidget()
        self.right_layout = QVBoxLayout(self.right_panel)
        self.right_layout.setContentsMargins(5, 5, 5, 5)

        self.playlist_count_label = QLabel("Playlist: 0 items")
        self.playlist_count_label.setStyleSheet(
            "background-color: #4A4A4A; color: #FFFFFF; border-radius: 12px; padding: 4px 12px; font-size: 13px; font-weight: bold;"
        )
        self.playlist_count_label.setFixedWidth(130)
        self.playlist_count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        count_layout = QHBoxLayout()
        count_layout.addWidget(self.playlist_count_label)
        count_layout.addStretch()
        self.right_layout.addLayout(count_layout)

        self.playlist = QListWidget()
        self.playlist.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.playlist.itemDoubleClicked.connect(self.play_selected_item)
        self.playlist.setStyleSheet(
            "QListWidget { font-size: 14px; } QListWidget::item { padding: 6px; }"
        )
        self.right_layout.addWidget(self.playlist, stretch=1)

        self.options_widget_1 = QWidget()
        self.options_layout_1 = QHBoxLayout(self.options_widget_1)
        self.options_layout_1.setContentsMargins(0, 0, 0, 0)

        self.open_folder_button = QPushButton("Open Folder")
        self.open_folder_button.clicked.connect(self.choose_folder)
        self.options_layout_1.addWidget(self.open_folder_button)

        self.clear_playlist_button = QPushButton("Clear Playlist")
        self.clear_playlist_button.clicked.connect(self.clear_playlist)
        self.options_layout_1.addWidget(self.clear_playlist_button)

        self.delete_file_button = QPushButton("Delete File")
        self.delete_file_button.setStyleSheet("color: #d9534f; font-weight: bold;")
        self.delete_file_button.clicked.connect(self.delete_selected_file)
        self.options_layout_1.addWidget(self.delete_file_button)

        self.shuffle_checkbox = QCheckBox("Shuffle")
        self.shuffle_checkbox.setChecked(True)
        self.shuffle_checkbox.toggled.connect(self.set_shuffle)
        self.options_layout_1.addWidget(self.shuffle_checkbox)

        self.loop_single_checkbox = QCheckBox("Loop 1")
        self.options_layout_1.addWidget(self.loop_single_checkbox)

        self.right_layout.addWidget(self.options_widget_1)

        self.options_widget_2 = QWidget()
        self.options_layout_2 = QHBoxLayout(self.options_widget_2)
        self.options_layout_2.setContentsMargins(0, 0, 0, 0)

        # --- REPLACED "Load Sub" WITH "Remove from List" ---
        self.remove_from_list_button = QPushButton("Remove from List")
        self.remove_from_list_button.setStyleSheet("font-weight: bold; color: #d9534f;")
        self.remove_from_list_button.clicked.connect(self.remove_from_playlist)
        self.options_layout_2.addWidget(self.remove_from_list_button)

        self.remove_played_checkbox = QCheckBox("Remove played")
        self.remove_played_checkbox.setChecked(True)
        self.options_layout_2.addWidget(self.remove_played_checkbox)

        self.startup_checkbox = QCheckBox("Run at Startup")
        self.startup_checkbox.toggled.connect(self.toggle_startup)
        self.options_layout_2.addWidget(self.startup_checkbox)

        self.volume_label = QLabel("Vol:")
        self.options_layout_2.addWidget(self.volume_label)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)
        self.volume_slider.setFixedWidth(80)
        self.volume_slider.valueChanged.connect(self.change_volume)
        self.options_layout_2.addWidget(self.volume_slider)

        self.right_layout.addWidget(self.options_widget_2)

        self.splitter.addWidget(self.left_panel)
        self.splitter.addWidget(self.right_panel)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([800, 400])

        self.setMouseTracking(True)
        self.video.setMouseTracking(True)

        self.fullscreen_close_button = QPushButton("🗗", self)
        self.fullscreen_close_button.setToolTip("Exit Fullscreen")
        self.fullscreen_close_button.setStyleSheet(
            "background-color: rgba(40, 40, 40, 180); color: white; border: none; font-size: 18px; font-weight: bold; border-radius: 15px;"
        )
        self.fullscreen_close_button.setFixedSize(30, 30)
        self.fullscreen_close_button.hide()
        self.fullscreen_close_button.clicked.connect(self._toggle_fullscreen)
        self.fullscreen_close_button.raise_()

        self.fullscreen_title_label = QLabel("", self)
        self.fullscreen_title_label.setStyleSheet(
            "background-color: rgba(0, 0, 0, 140); color: white; font-size: 20px; padding: 8px 20px; border-radius: 8px;"
        )
        self.fullscreen_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fullscreen_title_label.hide()
        self.fullscreen_title_label.raise_()

        self.check_startup_state()

    def _init_player(self):
        try:
            self.player_events = PlayerEventBridge(self)
            self.player_events.end_file.connect(self._handle_end_file)

            self.player = mpv.MPV(
                wid=str(int(self.video.winId())),
                osc=False,
                input_default_bindings=False,
                input_vo_keyboard=False,
                keep_open="no",
                idle="yes",
                hwdec="auto",
                cursor_autohide="no",
            )
            self.player.volume = 100

            @self.player.event_callback("end-file")
            def handle_end_file(event):
                reason = get_mpv_end_reason(event)
                self.player_events.end_file.emit(reason)

            self.status_label.setText("Media player engine ready.")
        except Exception as e:
            self.status_label.setText(f"Media Player Initialization Error: {e}")

    def _update_playlist_count(self):
        count = len(self.files)
        self.playlist_count_label.setText(f"Playlist: {count} items")

    def resizeEvent(self, event):
        self.fullscreen_close_button.move(self.width() - 45, 15)
        title_width = 600
        self.fullscreen_title_label.setGeometry(
            int((self.width() - title_width) / 2), 15, title_width, 45
        )
        self.audio_art_label.resize(self.video.width(), self.video.height())
        super().resizeEvent(event)

    def check_startup_state(self):
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, REGISTRY_PATH, 0, winreg.KEY_READ
            )
            try:
                winreg.QueryValueEx(key, APP_NAME)
                self.startup_checkbox.setChecked(True)
            except FileNotFoundError:
                self.startup_checkbox.setChecked(False)
            finally:
                winreg.CloseKey(key)
        except Exception:
            self.startup_checkbox.setChecked(False)

    def toggle_startup(self, checked):
        if not (hasattr(sys, "frozen") or "__compiled__" in globals()):
            self._dialog_active = True
            QMessageBox.warning(
                self,
                "Notice",
                "Run at Startup only works in the compiled .exe version.",
            )
            self._dialog_active = False
            self.startup_checkbox.setChecked(False)
            return

        exe_path = sys.executable

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, REGISTRY_PATH, 0, winreg.KEY_SET_VALUE
            )
            if checked:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{exe_path}"')
                self.status_label.setText("App set to run at Windows startup.")
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                    self.status_label.setText("App removed from Windows startup.")
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception as e:
            self._dialog_active = True
            QMessageBox.critical(
                self, "Registry Error", f"Failed to modify startup settings: {e}"
            )
            self._dialog_active = False
            self.startup_checkbox.setChecked(not checked)

    def _load_album_art(self, file_path):
        try:
            audio = MutagenFile(file_path)
            if audio is None:
                return None

            art_data = None
            if hasattr(audio, "tags") and "APIC:" in audio.tags:
                art_data = audio.tags["APIC:"].data
            elif hasattr(audio, "pictures") and len(audio.pictures) > 0:
                art_data = audio.pictures[0].data
            elif hasattr(audio, "tags") and "covr" in audio.tags:
                art_data = bytes(audio.tags["covr"][0])

            if art_data:
                image = QImage.fromData(art_data)
                if not image.isNull():
                    return QPixmap.fromImage(image)
        except Exception:
            pass
        return None

    def change_volume(self):
        if self.player:
            self.player.volume = self.volume_slider.value()

    def change_speed(self, text):
        if self.player:
            speed = float(text.replace("x", ""))
            self.player.speed = speed

    def clear_playlist(self):
        self.track_timer.stop()
        self.files.clear()
        self.current_index = -1
        self.current_path = None
        self.playlist.clear()
        self.progress_slider.setValue(0)
        self.progress_slider.setMaximum(0)
        self.play_button.setText("▶ Play")
        self.audio_art_label.hide()
        self.status_label.setText(
            "Playlist cleared cleanly. Drag & Drop files to start again."
        )
        self._update_playlist_count()
        if self.player:
            try:
                self.player.stop()
            except Exception:
                pass

    # --- NEW: REMOVE FROM LIST (NO DELETE) ---
    def remove_from_playlist(self):
        item = self.playlist.currentItem()
        if item is None:
            self._dialog_active = True
            QMessageBox.warning(
                self, "Remove from List", "Please select a file to remove."
            )
            self._dialog_active = False
            return

        path = item.data(Qt.ItemDataRole.UserRole)
        try:
            idx = self.files.index(path)
        except ValueError:
            return

        is_currently_playing = idx == self.current_index

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
            self.play_button.setText("▶ Play")
            self.progress_slider.setValue(0)
            self.progress_slider.setMaximum(1)
            self.track_timer.stop()
            self._end_event_pending = False

            if self.files:
                self.next_track()
        else:
            if idx < self.current_index:
                self.current_index -= 1

    def delete_selected_file(self):
        item = self.playlist.currentItem()
        if item is None:
            self._dialog_active = True
            QMessageBox.warning(
                self, "Delete File", "Please select a file in the playlist to delete."
            )
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
                    self.player.pause = True
            except Exception:
                pass

        self.hide_timer.stop()
        self._show_cursor()
        self.video.setMouseTracking(True)

        if was_fullscreen:
            self._is_fullscreen = False
            self.showMaximized()
            self.activateWindow()
            self.raise_()

            self.left_panel.show()
            self.right_panel.show()
            self.control_panel_widget.show()
            self.fullscreen_close_button.hide()
            self.fullscreen_title_label.hide()

            QApplication.processEvents()
            available_width = self.splitter.width()
            self.splitter.setSizes(
                [int(available_width * 0.75), int(available_width * 0.25)]
            )
            QApplication.processEvents()

        self._dialog_active = True
        dialog = CustomConfirmDialog(
            self,
            "Delete File",
            f"Are you sure you want to PERMANENTLY delete this file from your computer?\n\n{Path(path).name}",
        )
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        dialog.setModal(True)
        reply = dialog.exec()
        self._dialog_active = False

        if was_fullscreen:
            self.showFullScreen()
            self._is_fullscreen = True
            QApplication.processEvents()

            self.left_panel.show()
            self.right_panel.show()
            self.splitter.setSizes([self.splitter.width(), 0])
            self.control_panel_widget.hide()
            self.fullscreen_close_button.hide()
            self.fullscreen_title_label.hide()

            self._show_cursor()
            self.hide_timer.start()
            self.video.setMouseTracking(True)
            self.video.setFocus()
            QApplication.processEvents()

        if reply != QDialog.DialogCode.Accepted:
            if was_playing and self.player:
                try:
                    self.player.pause = False
                    self.play_button.setText("⏸ Pause")
                except Exception:
                    pass
            return

        try:
            idx = self.files.index(path)
        except ValueError:
            self.status_label.setText("The selected file is no longer in the playlist.")
            return

        is_currently_playing = path == self.current_path
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
                self.play_button.setText("⏸ Pause")
            return

        self.files.pop(idx)
        self.playlist.takeItem(idx)
        self._update_playlist_count()
        self.status_label.setText(f"Permanently deleted: {Path(path).name}")

        if is_currently_playing:
            self.current_index = -1
            self.current_path = None
            self.audio_art_label.hide()
            self.play_button.setText("▶ Play")
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
                    self.play_button.setText("⏸ Pause")
                except Exception:
                    pass

    def _poll_player_metrics(self):
        if not self.player or self._closing:
            return
        try:
            if self._is_scrubbing:
                return
            current_time = getattr(self.player, "time_pos", 0) or 0
            duration = getattr(self.player, "duration", 0) or 1
            if duration > 0:
                self.progress_slider.setMaximum(int(duration))
                self.progress_slider.setValue(int(current_time))
        except Exception:
            pass

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
            self._show_cursor()
            self.splitter.setSizes([int(self.width() * 0.75), int(self.width() * 0.25)])
            self.control_panel_widget.show()
            self.fullscreen_close_button.show()
            self.fullscreen_title_label.show()
            self.hide_timer.start()
        super().mouseMoveEvent(event)

    def _hide_fullscreen_overlays(self):
        if self._is_fullscreen and not self._is_scrubbing:
            self._hide_cursor()
            self.splitter.setSizes([self.width(), 0])
            self.control_panel_widget.hide()
            self.fullscreen_close_button.hide()
            self.fullscreen_title_label.hide()
            self.hide_timer.stop()
            self.video.setFocus()

    def _toggle_fullscreen(self):
        if self._is_fullscreen:
            self.showNormal()
            self._is_fullscreen = False

            screen_geo = self.screen().availableGeometry()
            self.resize(1200, 700)
            x = screen_geo.x() + (screen_geo.width() - self.width()) // 2
            y = screen_geo.y() + (screen_geo.height() - self.height()) // 2
            self.move(x, y)

            self._show_cursor()
            self.hide_timer.stop()
            self.control_panel_widget.show()
            self.fullscreen_close_button.hide()
            self.fullscreen_title_label.hide()
            self.splitter.setSizes([800, 400])
            self.main_layout.setContentsMargins(0, 0, 0, 0)
        else:
            self.showFullScreen()
            self._is_fullscreen = True
            self.splitter.setSizes([self.width(), 0])
            self.control_panel_widget.hide()
            self.fullscreen_close_button.hide()
            if self.current_path:
                self.fullscreen_title_label.setText(Path(self.current_path).name)
            self.fullscreen_title_label.hide()
            self._hide_cursor()
            self.hide_timer.start()
        self.setFocus()
        self.video.setFocus()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [
            url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()
        ]
        if paths:
            self.scan_targets(paths)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select media folder")
        if folder:
            self.scan_targets([folder])

    def scan_targets(self, targets):
        if self.scanner is not None and self.scanner.isRunning():
            return
        self.status_label.setText("Processing imported tracks...")
        self.open_folder_button.setEnabled(False)
        self.scanner = FolderScanner(targets)
        self.scanner.files_found.connect(self._on_files_found)
        self.scanner.scan_error.connect(self._on_scan_error)
        self.scanner.finished.connect(lambda: self.open_folder_button.setEnabled(True))
        self.scanner.start()

    # --- MODIFIED: APPEND LOGIC ---
    def _on_files_found(self, paths):
        if not paths:
            return

        was_empty = len(self.files) == 0

        self.playlist.setUpdatesEnabled(False)

        # Append to existing files list
        self.files.extend(paths)

        for path in paths:
            item = QListWidgetItem(Path(path).name)
            item.setToolTip(path)
            item.setData(Qt.ItemDataRole.UserRole, path)
            self.playlist.addItem(item)

        self.playlist.setUpdatesEnabled(True)
        self.status_label.setText(
            f"Added {len(paths)} media file(s). Total: {len(self.files)}."
        )
        self._update_playlist_count()

        # Autoplay only if the list was previously completely empty
        if was_empty and self.files:
            self.play_index(0)

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
            self.fullscreen_title_label.setText(Path(path).name)
            if not self.hide_timer.isActive():
                self._hide_cursor()
                self.control_panel_widget.hide()
                self.fullscreen_close_button.hide()
            else:
                self.hide_timer.start()

        ext = Path(path).suffix.lower()
        if ext in AUDIO_EXTENSIONS:
            pixmap = self._load_album_art(path)
            if pixmap:
                scaled_pixmap = pixmap.scaled(
                    self.video.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.audio_art_label.setPixmap(scaled_pixmap)
            else:
                self.audio_art_label.clear()
                self.audio_art_label.setText("🎵 Audio Playing")
                self.audio_art_label.setStyleSheet(
                    "color: white; font-size: 24px; background-color: black;"
                )

            self.audio_art_label.resize(self.video.width(), self.video.height())
            self.audio_art_label.show()
        else:
            self.audio_art_label.hide()

        if self.player:
            self.player.loadfile(path, mode="replace")
            self.player.pause = False  # FORCE UNPAUSE
            self.status_label.setText(f"Playing: {Path(path).name}")
            self.play_button.setText("⏸ Pause")
            self.track_timer.start()

    def play_or_resume(self):
        if not self.player or not self.files:
            return

        if self.player.idle_active:
            self.play_index(self.current_index if self.current_index >= 0 else 0)
        else:
            self.player.pause = not self.player.pause
            self.play_button.setText("▶ Play" if self.player.pause else "⏸ Pause")

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
            self.play_button.setText("▶ Play")
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
    temp_dir = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.TempLocation
    )
    lock_file = QLockFile(os.path.join(temp_dir, "ALMP.lock"))
    if not lock_file.tryLock(100):
        sys.exit(0)

    try:
        myappid = "Alexbed.LightMediaPlayer.ALMP.6.3"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass

    app = QApplication(sys.argv)

    icon_path = get_resource_path("icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = MediaWindow()
    if os.path.exists(icon_path):
        window.setWindowIcon(QIcon(icon_path))

    window.show()
    sys.exit(app.exec())
