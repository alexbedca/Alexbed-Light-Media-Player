# Alexbed Light Media Player (ALMP)
# Copyright (C) 2026 Alexander Bediako
# SPDX-License-Identifier: GPL-3.0-or-later
"""Small custom widgets: welcome screen, fullscreen title, confirm dialog, seek slider, playlist view."""
import math
import os
import sys

from PyQt6.QtCore import QEvent, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPen, QPixmap, QRadialGradient
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSlider,
    QStyle,
    QStyleOptionSlider,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from . import APP_TITLE, __version__
from .logsetup import log
from .paths import get_resource_path
from .theme import make_icon


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
        self.high_contrast = False

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
        if self.high_contrast:
            painter.setPen(QPen(QColor("#ffff00"), 2))
            painter.setBrush(QColor(0, 0, 0, 245))
        else:
            painter.setPen(QPen(QColor(255, 255, 255, 45), 1))
            painter.setBrush(QColor(18, 18, 18, 225))
        painter.drawRoundedRect(rect, radius, radius)
        font = self.font()
        font.setPixelSize(18)
        painter.setFont(font)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._text)
        painter.end()


def logo_pixmap(size=132):
    dpr = 1.0
    try:
        dpr = float(QApplication.primaryScreen().devicePixelRatio())
    except (AttributeError, RuntimeError, TypeError):
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


class WelcomeScreen(QWidget):
    """Start screen: painted wallpaper, gently moving sound bars, and two big buttons.
    In high contrast it is plain black with white text and yellow bars (no glow)."""
    add_files_requested = pyqtSignal()
    add_folder_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._phase = 0.0
        self.high_contrast = False
        self._timer = QTimer(self)
        self._timer.setInterval(66)           # ~15 frames per second, only while visible
        self._timer.timeout.connect(self._tick)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(24, 24, 24, 90)
        layout.setSpacing(10)

        logo = QLabel()
        self._logo = logo
        logo.setPixmap(logo_pixmap(120))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setAccessibleName("ALMP logo")
        layout.addWidget(logo)

        title = QLabel(APP_TITLE)
        self._title = title
        title.setObjectName("welcomeTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(True)
        layout.addWidget(title)

        tagline = QLabel("Press play on anything.")
        self._tagline = tagline
        tagline.setObjectName("welcomeTagline")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(tagline)
        layout.addSpacing(14)

        row = QHBoxLayout()
        row.setSpacing(14)
        row.addStretch(1)
        self.btn_files = QPushButton("Add Files")
        self.btn_files.setObjectName("welcomePrimary")
        self.btn_files.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_files.setAccessibleName("Add files")
        self.btn_files.setToolTip("Choose songs or videos to play  (Ctrl+O)")
        self.btn_files.clicked.connect(self.add_files_requested.emit)
        self.btn_folder = QPushButton("Add Folder")
        self.btn_folder.setObjectName("welcomeSecondary")
        self.btn_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_folder.setAccessibleName("Add folder")
        self.btn_folder.setToolTip("Play everything in a folder  (Ctrl+Shift+O)")
        self.btn_folder.clicked.connect(self.add_folder_requested.emit)
        row.addWidget(self.btn_files)
        row.addWidget(self.btn_folder)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addSpacing(6)

        hint = QLabel("or drag and drop files and folders here   |   F1 for help")
        hint.setObjectName("welcomeHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self._hint = hint
        version = QLabel(f"Version {__version__}")
        self._version = version
        version.setObjectName("welcomeHint")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)

    def set_high_contrast(self, on):
        self.high_contrast = bool(on)
        self.update()

    def set_tv_scale(self, factor):
        """Bigger logo, text and buttons for fullscreen on a TV or big screen (1.0 = normal)."""
        f = max(1.0, float(factor))
        if abs(f - getattr(self, "_tv", 1.0)) < 0.01:
            return
        self._tv = f
        if f == 1.0:
            for w in (self.btn_files, self.btn_folder, self._title, self._tagline, self._hint, self._version):
                w.setStyleSheet("")
            self._logo.setPixmap(logo_pixmap(120))
            self.btn_files.setMinimumSize(0, 0)
            self.btn_folder.setMinimumSize(0, 0)
        else:
            def px(n):
                return int(round(n * f))
            for b in (self.btn_files, self.btn_folder):
                b.setStyleSheet("font-size: %dpx; padding: %dpx %dpx; border-radius: %dpx;"
                                % (px(16), px(13), px(32), px(10)))
                b.setMinimumSize(px(150), px(52))
            self._title.setStyleSheet("font-size: %dpx;" % px(30))
            self._tagline.setStyleSheet("font-size: %dpx;" % px(16))
            self._hint.setStyleSheet("font-size: %dpx;" % px(13))
            self._version.setStyleSheet("font-size: %dpx;" % px(13))
            self._logo.setPixmap(logo_pixmap(px(120)))
        self.layout().activate()
        self._fit_to_height()

    def _fit_to_height(self):
        """On a short window (large interface size) drop the extras so the two buttons keep their text:
        first the logo, then the version line, then the drag-and-drop hint."""
        extras = [self._logo, self._version, self._hint]
        for w in extras:
            w.setVisible(True)
        lay = self.layout()
        for w in extras:
            lay.activate()
            if lay.totalMinimumSize().height() <= self.height():
                break
            w.setVisible(False)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_to_height()

    def showEvent(self, event):
        self._fit_to_height()
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def _tick(self):
        win = self.window()
        if win is not None and win.isMinimized():
            return
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
        hc = self.high_contrast
        if hc:
            p.fillRect(self.rect(), QColor("#000000"))
        else:
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
        max_h = h * 0.16
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(n):
            t = i / (n - 1)
            env = math.sin(math.pi * t) ** 1.4
            wave = abs(math.sin(self._phase * 1.3 + i * 0.42) * math.sin(self._phase * 0.7 + i * 0.17))
            bh = max(3.0, max_h * env * (0.22 + 0.78 * wave))
            if hc:
                p.setBrush(QColor(255, 255, 0, int(90 + 120 * env)))
            else:
                p.setBrush(QColor(25, 200, 230, int(28 + 62 * env)))
            x = (i + 0.5) * slot - bar_w / 2
            p.drawRoundedRect(QRectF(x, base_y - bh, bar_w, bh), bar_w / 2, bar_w / 2)
        p.end()


class CustomConfirmDialog(QDialog):
    """Yes/No question with big buttons. "No" has the focus, so Enter never deletes by accident."""

    def __init__(self, parent, title, message, yes_text="Yes", no_text="No"):
        super().__init__(parent)
        self.setWindowTitle(title)
        if sys.platform == "win32":
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetMinimumSize)
        lbl = QLabel(message)
        lbl.setObjectName("dialogMessage")
        lbl.setTextFormat(Qt.TextFormat.PlainText)     # file names are shown exactly as they are
        lbl.setWordWrap(True)
        lbl.setMinimumWidth(380)
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(lbl)

        btn_layout = QHBoxLayout()
        self.btn_yes = QPushButton(yes_text)
        self.btn_no = QPushButton(no_text)
        for b in (self.btn_yes, self.btn_no):
            b.setObjectName("dialogButton")
        self.btn_yes.clicked.connect(self.accept)
        self.btn_no.clicked.connect(self.reject)
        self.btn_no.setDefault(True)
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
                import ctypes
                ctypes.windll.user32.SetForegroundWindow(int(self.winId()))
            except (AttributeError, OSError):
                log.debug("SetForegroundWindow failed", exc_info=True)


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
        except (AttributeError, RuntimeError, TypeError):
            log.exception("Slider click failed")
        super().mousePressEvent(event)


class PlaylistView(QTableView):
    """The playlist on screen. It only draws the rows you can see (fast with 250,000 files).

    It is a one-column table with fixed row heights on purpose: a QListView recalculates the
    position of every row whenever rows are added (measured: about 80 ms per 5,000 rows added to a
    100,000-row list, 190 ms at 250,000), while a table with fixed rows does no per-row work.

    Keys while the list has the keyboard focus:
      Up/Down, Page Up/Down, Home/End   move in the list (the list keeps them)
      Enter                             play the selected track
      Space, Left/Right                 play/pause and seek (passed on to the window)
      Delete                            remove from the list (the file is kept)
      Shift+Delete                      delete the file (asks first)
      Menu key / Shift+F10              the right-click menu
    """
    play_requested = pyqtSignal()
    remove_requested = pyqtSignal()
    delete_requested = pyqtSignal()
    ROW_PADDING = 16                                  # px above + below the text

    def __init__(self, parent=None):
        super().__init__(parent)
        self._row_update_pending = False
        self.setObjectName("playlistView")
        self.setShowGrid(False)
        self.setCornerButtonEnabled(False)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.setWordWrap(False)
        self.setTabKeyNavigation(False)               # Tab leaves the list, like every other control
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        hh = self.horizontalHeader()
        hh.hide()
        hh.setStretchLastSection(True)
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        vh = self.verticalHeader()
        vh.hide()
        vh.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)   # never asks the model for row sizes
        self.update_row_height()
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDragDropOverwriteMode(False)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setAccessibleName("Playlist")
        self.setAccessibleDescription("Enter plays the selected track. Delete removes it from the list. "
                                      "The menu key opens more choices.")

    def update_row_height(self):
        h = self.fontMetrics().height() + self.ROW_PADDING
        self.verticalHeader().setMinimumSectionSize(1)
        self.verticalHeader().setDefaultSectionSize(h)

    def changeEvent(self, event):
        super().changeEvent(event)
        # Never resize the rows in the middle of a style change (Qt is re-polishing every widget
        # then); do it right after, once.
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange) and not self._row_update_pending:
            self._row_update_pending = True
            QTimer.singleShot(0, self._deferred_row_height)

    def _deferred_row_height(self):
        self._row_update_pending = False
        self.update_row_height()

    def keyPressEvent(self, event):
        key = event.key()
        mods = event.modifiers()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.play_requested.emit()
            event.accept()
            return
        if key == Qt.Key.Key_Delete:
            if mods & Qt.KeyboardModifier.ShiftModifier:
                self.delete_requested.emit()
            else:
                self.remove_requested.emit()
            event.accept()
            return
        if key in (Qt.Key.Key_Space, Qt.Key.Key_Left, Qt.Key.Key_Right) and not (
                mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)):
            event.ignore()             # goes to the window: play/pause, seek
            return
        super().keyPressEvent(event)

    def dragEnterEvent(self, event):
        # Files dragged in from Explorer are handled by the window (added to the playlist).
        if event.mimeData().hasUrls() and event.source() is not self:
            event.ignore()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls() and event.source() is not self:
            event.ignore()
            return
        super().dragMoveEvent(event)
