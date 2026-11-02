# Alexbed Light Media Player (ALMP)
# Copyright (C) 2026 Alexander Bediako
# SPDX-License-Identifier: GPL-3.0-or-later
"""Colours, style sheets and the small vector icons.

Every colour lives here and is applied through object names (#statusLabel, #countPill...), never
inline on a widget, so the high-contrast sheet below can override every one of them.
"""
import sys

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF
from PyQt6.QtWidgets import QApplication

ACCENT = "#19c8e6"
ACCENT_HC = "#ffff00"
ICON = "#e6e6e6"
ICON_HC = "#ffffff"
ICON_ON_ACCENT = "#04222a"

# Only name fonts that really exist on the platform. Listing missing families (for example
# "Ubuntu" on Windows) makes Qt scan and load every installed font, which cost ~300 MB of memory.
if sys.platform == "win32":
    UI_FONT_FAMILY = '"Segoe UI"'
elif sys.platform == "darwin":
    UI_FONT_FAMILY = '"Helvetica Neue"'
else:
    UI_FONT_FAMILY = '"Ubuntu", "Noto Sans", "DejaVu Sans"'


def accent(high_contrast):
    return ACCENT_HC if high_contrast else ACCENT


def icon_color(high_contrast):
    return ICON_HC if high_contrast else ICON


BASE_QSS = """
    QWidget { color: #e6e6e6; font-family: {UI_FONT_FAMILY}; font-size: 14px; }
    #welcomeTitle { font-size: 30px; font-weight: 700; color: #ffffff; }
    #welcomeTagline { font-size: 16px; color: #9fb3ba; }
    #welcomeHint { font-size: 13px; color: #8a9aa0; }
    #welcomePrimary {
        font-size: 16px; font-weight: 700; padding: 13px 34px; border-radius: 10px;
        background-color: #19c8e6; color: #04222a; border: 1px solid #19c8e6;
    }
    #welcomePrimary:hover { background-color: #3ad8f2; }
    #welcomePrimary:pressed { background-color: #12a9c3; }
    #welcomeSecondary {
        font-size: 16px; font-weight: 600; padding: 13px 30px; border-radius: 10px;
        background-color: rgba(255, 255, 255, 16); color: #e6f7fa; border: 1px solid rgba(25, 200, 230, 130);
    }
    #welcomeSecondary:hover { background-color: rgba(25, 200, 230, 46); border-color: #19c8e6; }
    QMenu { background-color: #1a1d1f; border: 1px solid #2c3236; border-radius: 8px; padding: 6px; }
    QMenu::item { padding: 8px 24px; border-radius: 6px; }
    QMenu::item:selected { background-color: #123a44; }
    QMenu::item:disabled { color: #8a9499; }
    QMenu::separator { height: 1px; background: #2c3236; margin: 6px 8px; }
    QMainWindow, QDialog, QMessageBox { background-color: #121212; }
    QLabel, QCheckBox, QRadioButton { background: transparent; }
    #leftPanel { background-color: #000000; }
    #videoSurface { background-color: #000000; border: none; }
    #audioArt { background-color: transparent; }
    #controlBar { background-color: #161616; border-top: 1px solid #242424; }
    #rightPanel { background-color: #161616; border-left: 1px solid #242424; }
    QSplitter::handle { background-color: #242424; width: 2px; }
    QSplitter::handle:hover { background-color: #19c8e6; }

    #statusLabel { font-weight: 600; color: #d5dde0; }
    #timeLabel { font-size: 13px; color: #9aa4a8; }
    #volumeValue { color: #9aa4a8; font-size: 13px; }
    #dimLabel { color: #9aa4a8; font-size: 13px; }
    #sectionTitle { font-size: 16px; font-weight: 700; color: #f1f4f5; padding-top: 6px; }
    #playlistTitle { font-size: 18px; font-weight: 600; color: #f1f4f5; }
    #countPill {
        background-color: #1f2a2d; color: #19c8e6; border-radius: 13px; padding: 5px 14px;
        font-size: 14px; font-weight: 700;
    }
    #dialogMessage { font-size: 14px; padding: 10px; }
    #dialogButton { font-size: 15px; padding: 8px 24px; }
    #helpText { font-size: 14px; }

    QPushButton {
        background-color: #232323; border: 1px solid #303030; border-radius: 8px;
        padding: 6px 12px; color: #e6e6e6;
    }
    QPushButton:hover { background-color: #2c2c2c; border-color: #19c8e6; }
    QPushButton:pressed { background-color: #1a1a1a; }
    QPushButton:disabled { color: #666666; border-color: #262626; }
    #transportButton { font-size: 15px; padding: 9px 16px; font-weight: 600; }
    #removeButton { color: #ffb86b; }
    #dangerButton { color: #ff6b6b; font-weight: bold; }
    #closeButton:hover { background-color: #c42b1c; border-color: #c42b1c; }
    #closeButton:pressed { background-color: #a32316; }
    #playButton {
        background-color: #19c8e6; color: #04222a; border: 1px solid #19c8e6;
        font-size: 15px; padding: 9px 16px; font-weight: 700;
    }
    #playButton:hover { background-color: #3ad8f2; }
    #playButton:pressed { background-color: #12a9c3; }
    QPushButton:focus, QComboBox:focus { border: 2px solid #ffd54a; }
    #playButton:focus, #closeButton:focus, #welcomePrimary:focus, #welcomeSecondary:focus { border: 2px solid #ffd54a; }
    QCheckBox:focus, QRadioButton:focus { color: #ffd54a; }

    QListView {
        background-color: #101010; border: 1px solid #242424; border-radius: 8px; outline: none;
        font-size: 14px;
    }
    QListView::item { padding: 7px 10px; border: none; border-radius: 6px; }
    QListView::item:hover { background-color: #1d1d1d; }
    QListView::item:selected { background-color: #123a44; color: #ffffff; }
    QListView:focus { border: 1px solid #ffd54a; }

    QSlider::groove:horizontal { height: 6px; background: #2e2e2e; border-radius: 3px; }
    QSlider::sub-page:horizontal { background: #19c8e6; border-radius: 3px; }
    QSlider::handle:horizontal { background: #ffffff; border: none; width: 16px; height: 16px; margin: -5px 0; border-radius: 8px; }
    QSlider::handle:horizontal:hover { background: #19c8e6; }
    QSlider::handle:horizontal:focus { background: #ffd54a; }

    QCheckBox { spacing: 6px; }
    QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #4a4a4a; border-radius: 4px; background: #1c1c1c; }
    QCheckBox::indicator:hover { border-color: #19c8e6; }
    QCheckBox::indicator:checked { background: #19c8e6; border-color: #19c8e6; }
    QCheckBox:disabled { color: #8a9499; }

    QComboBox { background-color: #232323; border: 1px solid #303030; border-radius: 8px; padding: 4px 8px; }
    QComboBox:hover { border-color: #19c8e6; }
    QComboBox QAbstractItemView {
        background-color: #1c1c1c; border: 1px solid #303030; selection-background-color: #123a44; outline: none;
    }
    QTabWidget::pane { border: 1px solid #2c3236; border-radius: 6px; }
    QTabBar::tab { background: #1a1d1f; padding: 8px 16px; border: 1px solid #2c3236; }
    QTabBar::tab:selected { background: #123a44; }
    QTabBar::tab:focus { border: 2px solid #ffd54a; }
    QTextBrowser, QPlainTextEdit { background-color: #101010; border: 1px solid #262626; }

    QScrollBar:vertical { background: transparent; width: 12px; margin: 0; }
    QScrollBar::handle:vertical { background: #3a3a3a; border-radius: 5px; min-height: 30px; }
    QScrollBar::handle:vertical:hover { background: #19c8e6; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

    QLineEdit {
        background-color: #101010; border: 1px solid #262626; border-radius: 9px;
        padding: 7px 10px; selection-background-color: #123a44;
    }
    QLineEdit:focus { border-color: #19c8e6; }
    QToolTip { background-color: #1c1c1c; color: #e6e6e6; border: 1px solid #19c8e6; padding: 4px; font-size: 13px; }
"""

# Applied on top of BASE_QSS. Black, white and yellow only; focus is cyan so it differs from selection.
HIGH_CONTRAST_QSS = """
    QMainWindow, QDialog, QMessageBox { background-color: #000000; }
    QWidget { color: #ffffff; }
    #leftPanel, #rightPanel { background-color: #000000; }
    #rightPanel { border-left: 2px solid #ffffff; }
    #controlBar { background-color: #000000; border-top: 2px solid #ffff00; }
    #statusLabel, #timeLabel, #volumeValue, #dimLabel, #playlistTitle, #sectionTitle,
    #welcomeTitle, #welcomeTagline, #welcomeHint, #dialogMessage, #helpText { color: #ffffff; }
    #countPill { background-color: #000000; color: #ffff00; border: 2px solid #ffff00; }
    QPushButton, #transportButton, #removeButton, #dangerButton, #dialogButton {
        background-color: #000000; border: 2px solid #ffffff; color: #ffffff; font-weight: 600;
    }
    QPushButton:hover { border-color: #ffff00; color: #ffff00; }
    QPushButton:disabled { color: #bdbdbd; border-color: #bdbdbd; }
    #playButton, #welcomePrimary { background-color: #ffff00; color: #000000; border: 2px solid #ffff00; }
    #welcomeSecondary { background-color: #000000; color: #ffffff; border: 2px solid #ffffff; }
    QListView { background-color: #000000; border: 2px solid #ffffff; }
    QListView::item:hover { background-color: #000000; border: 1px solid #ffff00; }
    QListView::item:selected { background-color: #ffff00; color: #000000; }
    QLineEdit, QComboBox { background-color: #000000; border: 2px solid #ffffff; color: #ffffff; }
    QComboBox QAbstractItemView { background-color: #000000; color: #ffffff; selection-background-color: #ffff00; selection-color: #000000; }
    QMenu { background-color: #000000; border: 2px solid #ffffff; }
    QMenu::item:selected { background-color: #ffff00; color: #000000; }
    QMenu::item:disabled { color: #bdbdbd; }
    QCheckBox::indicator { border: 2px solid #ffffff; background: #000000; }
    QCheckBox::indicator:checked { background: #ffff00; border-color: #ffff00; }
    QCheckBox:disabled { color: #bdbdbd; }
    QSlider::groove:horizontal { background: #ffffff; }
    QSlider::sub-page:horizontal { background: #ffff00; }
    QSlider::handle:horizontal { background: #ffff00; }
    QTabBar::tab { background: #000000; border: 2px solid #ffffff; }
    QTabBar::tab:selected { background: #ffff00; color: #000000; }
    QTextBrowser, QPlainTextEdit { background-color: #000000; color: #ffffff; border: 2px solid #ffffff; }
    QToolTip { background-color: #000000; color: #ffffff; border: 2px solid #ffff00; }
    QPushButton:focus, QComboBox:focus, #playButton:focus, #welcomePrimary:focus, #welcomeSecondary:focus,
    QLineEdit:focus, QTabBar::tab:focus { border: 3px solid #00ffff; }
    QCheckBox:focus, QRadioButton:focus { color: #00ffff; }
    QListView:focus { border: 3px solid #00ffff; }
    QSlider::handle:horizontal:focus { background: #00ffff; }
"""


def base_stylesheet():
    return BASE_QSS.replace("{UI_FONT_FAMILY}", UI_FONT_FAMILY)


def stylesheet(high_contrast):
    return base_stylesheet() + (HIGH_CONTRAST_QSS if high_contrast else "")


# --- Crisp vector icons ---
_ICON_CACHE = {}


def make_icon(kind, color=ICON, px=20):
    key = (kind, color, px)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]
    dpr = 1.0
    try:
        dpr = float(QApplication.primaryScreen().devicePixelRatio())
    except (AttributeError, RuntimeError, TypeError):
        pass
    big = 96
    pm = QPixmap(big, big)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    u = big / 24.0
    col = QColor(color)
    pen = QPen(col)
    pen.setWidthF(2.2 * u)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

    def pt(x, y):
        return QPointF(x * u, y * u)

    def poly(points):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawPolygon(QPolygonF([pt(x, y) for x, y in points]))

    def line(*points):
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for a, b in zip(points, points[1:], strict=False):
            p.drawLine(pt(*a), pt(*b))

    def bar(x, y, w, h):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawRoundedRect(QRectF(x * u, y * u, w * u, h * u), 1.2 * u, 1.2 * u)

    def outline():
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

    if kind == "play":
        poly([(7, 4.5), (20, 12), (7, 19.5)])
    elif kind == "pause":
        bar(6.5, 4.5, 4, 15)
        bar(13.5, 4.5, 4, 15)
    elif kind == "prev":
        poly([(19, 5), (9, 12), (19, 19)])
        bar(4.5, 5, 3, 14)
    elif kind == "next":
        poly([(5, 5), (15, 12), (5, 19)])
        bar(16.5, 5, 3, 14)
    elif kind == "fullscreen":
        line((4, 9), (4, 4), (9, 4))
        line((15, 4), (20, 4), (20, 9))
        line((4, 15), (4, 20), (9, 20))
        line((20, 15), (20, 20), (15, 20))
    elif kind == "exitfullscreen":
        line((9, 4), (9, 9), (4, 9))
        line((15, 4), (15, 9), (20, 9))
        line((4, 15), (9, 15), (9, 20))
        line((20, 15), (15, 15), (15, 20))
    elif kind == "close":
        line((6, 6), (18, 18))
        line((18, 6), (6, 18))
    elif kind == "playlist":
        line((4, 6), (20, 6))
        line((4, 12), (20, 12))
        line((4, 18), (13, 18))
    elif kind == "search":
        outline()
        p.drawEllipse(QRectF(4 * u, 4 * u, 12 * u, 12 * u))
        line((14.5, 14.5), (20, 20))
    elif kind == "volume":
        poly([(3.5, 9), (8, 9), (13, 4.8), (13, 19.2), (8, 15), (3.5, 15)])
        outline()
        p.drawArc(QRectF(10 * u, 7.5 * u, 9 * u, 9 * u), -50 * 16, 100 * 16)
    elif kind == "subtitles":
        outline()
        p.drawRoundedRect(QRectF(3 * u, 5 * u, 18 * u, 14 * u), 3 * u, 3 * u)
        line((6.5, 11), (10.5, 11))
        line((13.5, 11), (17.5, 11))
        line((6.5, 15), (12.5, 15))
        line((15.5, 15), (17.5, 15))
    elif kind == "clock":
        outline()
        p.drawEllipse(QRectF(3.5 * u, 3.5 * u, 17 * u, 17 * u))
        line((12, 7.5), (12, 12), (15.5, 14))
    elif kind == "contrast":
        r = QRectF(3.5 * u, 3.5 * u, 17 * u, 17 * u)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawPie(r, 90 * 16, 180 * 16)                 # left half filled
        outline()
        p.drawEllipse(r)
    elif kind == "loop":
        line((4, 11.5), (4, 7), (15, 7))
        poly([(14.5, 3.6), (20, 7), (14.5, 10.4)])
        line((20, 12.5), (20, 17), (9, 17))
        poly([(9.5, 13.6), (4, 17), (9.5, 20.4)])
    elif kind == "settings":
        outline()
        p.drawEllipse(QRectF(8.5 * u, 8.5 * u, 7 * u, 7 * u))
        for i in range(8):
            p.save()
            p.translate(12 * u, 12 * u)
            p.rotate(i * 45)
            p.drawLine(pt(0, -6.8), pt(0, -10))
            p.restore()
    elif kind == "help":
        outline()
        p.drawEllipse(QRectF(3.5 * u, 3.5 * u, 17 * u, 17 * u))
        p.drawArc(QRectF(9 * u, 7 * u, 6 * u, 5.5 * u), 180 * 16, -200 * 16)
        line((12, 12.6), (12, 14.2))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawEllipse(QRectF(10.9 * u, 16 * u, 2.2 * u, 2.2 * u))
    p.end()

    pm = pm.scaled(int(px * dpr), int(px * dpr), Qt.AspectRatioMode.KeepAspectRatio,
                   Qt.TransformationMode.SmoothTransformation)
    pm.setDevicePixelRatio(dpr)
    icon = QIcon(pm)
    _ICON_CACHE[key] = icon
    return icon
