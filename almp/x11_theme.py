# ALMP (Alexbed Light Media Player) - Linux port
# SPDX-License-Identifier: GPL-3.0-or-later
"""Dark window frames on X11 (the Linux counterpart of the Windows dark title bar).

Window managers that draw the title bar themselves (Cinnamon/Muffin, GNOME/Mutter, Xfce...) use the
theme's dark variant for a window that has the X11 property _GTK_THEME_VARIANT = "dark" (UTF8_STRING).
Found on the real Mint 22.3 PC: Cinnamon drew ALMP's frame white; setting this property made it dark.
ALMP sets it on every top-level window (main window, Settings, dialogs) when it is first shown.
Only libX11 from the system is used (ctypes); nothing happens on Windows or without X11."""
import ctypes
import ctypes.util
import logging

from PyQt6.QtCore import QEvent, QObject

log = logging.getLogger("almp.x11_theme")

PROPERTY = b"_GTK_THEME_VARIANT"
VALUE = b"dark"
PROP_MODE_REPLACE = 0


class X11Display:
    """The few libX11 calls needed, on its own display connection."""

    def __init__(self, lib=None):
        if lib is None:
            name = ctypes.util.find_library("X11") or "libX11.so.6"
            lib = ctypes.CDLL(name)
            lib.XOpenDisplay.restype = ctypes.c_void_p
            lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
            lib.XInternAtom.restype = ctypes.c_ulong
            lib.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
            lib.XChangeProperty.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong,
                                            ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
            lib.XFlush.argtypes = [ctypes.c_void_p]
        self.lib = lib
        self.display = lib.XOpenDisplay(None)
        if not self.display:
            raise OSError("cannot open the X display")
        self.prop = lib.XInternAtom(self.display, PROPERTY, 0)
        self.utf8 = lib.XInternAtom(self.display, b"UTF8_STRING", 0)

    def set_dark(self, window_id):
        self.lib.XChangeProperty(self.display, int(window_id), self.prop, self.utf8, 8, PROP_MODE_REPLACE,
                                 VALUE, len(VALUE))
        self.lib.XFlush(self.display)


class DarkTitleBars(QObject):
    """Application event filter: the first time a top-level window is shown, ask for the dark frame."""

    def __init__(self, display, parent=None):
        super().__init__(parent)
        self.display = display
        self.done = set()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Show:
            try:
                if obj.isWidgetType() and obj.isWindow() and not self._is_popup(obj):
                    wid = int(obj.winId())
                    if wid and wid not in self.done:
                        self.done.add(wid)
                        self.display.set_dark(wid)
            except Exception:          # noqa: BLE001 - a light frame is better than a crash
                log.debug("Could not ask for a dark window frame", exc_info=True)
        return False

    @staticmethod
    def _is_popup(widget):
        from PyQt6.QtCore import Qt
        kind = widget.windowType()
        return kind in (Qt.WindowType.Popup, Qt.WindowType.ToolTip, Qt.WindowType.SplashScreen)


def install(app, display_factory=X11Display):
    """Install on the QApplication when Qt runs on X11 (also XWayland). Returns the filter or None."""
    if app.platformName() != "xcb":
        return None
    try:
        flt = DarkTitleBars(display_factory(), app)
    except Exception:          # noqa: BLE001
        log.info("Dark window frames not available", exc_info=True)
        return None
    app.installEventFilter(flt)
    return flt
