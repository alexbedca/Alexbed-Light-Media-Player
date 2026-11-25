# ALMP (Alexbed Light Media Player) - Linux port
# SPDX-License-Identifier: GPL-3.0-or-later
"""Linux media controls: MPRIS over D-Bus (the Linux counterpart of the Windows media controls in smtc.py).

With this, the keyboard media keys work while ALMP is in the background (GNOME/KDE send them to the
active MPRIS player), and the desktop's media controls (GNOME's date menu, KDE's media applet,
`playerctl`) show the track name and can play, pause, skip and stop.

Same small interface as `smtc.WindowsMediaControls`: a `command(str)` signal ("play", "pause", "toggle",
"next", "previous", "stop"), `start()`, `stop()`, `set_status()`, `set_track()`, `clear_track()`.
Only the local session bus is used (no network). If D-Bus is missing, ALMP works as before: keys work
while its window is active.
"""
import logging
import os
import sys

from PyQt6.QtCore import QObject, pyqtClassInfo, pyqtProperty, pyqtSignal, pyqtSlot

log = logging.getLogger("almp.mpris")

BUS_NAME = "org.mpris.MediaPlayer2.almp"
OBJECT_PATH = "/org/mpris/MediaPlayer2"
ROOT_IFACE = "org.mpris.MediaPlayer2"
PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"
PROPS_IFACE = "org.freedesktop.DBus.Properties"
TRACK_PATH = "/org/alexbed/almp/track/"
NO_TRACK = "/org/mpris/MediaPlayer2/TrackList/NoTrack"

STATUS_TEXT = {"playing": "Playing", "paused": "Paused", "stopped": "Stopped", "closed": "Stopped"}

# D-Bus method name -> ALMP command (same names the Windows media controls send).
METHOD_COMMANDS = {"Play": "play", "Pause": "pause", "PlayPause": "toggle", "Stop": "stop",
                   "Next": "next", "Previous": "previous"}


def playback_status(state):
    """ALMP's state -> MPRIS PlaybackStatus."""
    return STATUS_TEXT.get(state, "Stopped")


def metadata(track_number, title, video=False, length_s=None, artist=None, art_url=None, album=None):
    """MPRIS Metadata for the current file (plain dict; turned into a{sv} by Qt).
    artist only when the file has one (desktops show "Unknown artist" otherwise, so videos get none);
    art_url: file:// picture for the desktop's media panel (album art, else ALMP's icon)."""
    if not title:
        return {}
    meta = {"mpris:trackid": f"{TRACK_PATH}{int(track_number)}", "xesam:title": title}
    if length_s and length_s > 0:
        meta["mpris:length"] = int(length_s * 1_000_000)
    if artist and not video:
        meta["xesam:artist"] = [str(artist)]
    if album and not video:
        meta["xesam:album"] = str(album)
    if art_url:
        meta["mpris:artUrl"] = str(art_url)
    return meta


def bus_name_for(taken):
    """`org.mpris.MediaPlayer2.almp`, or with `.instance<pid>` when another ALMP already has it (as the spec asks)."""
    return f"{BUS_NAME}.instance{os.getpid()}" if taken else BUS_NAME


def _dbus_metadata(meta):
    """The dict as Qt needs it: the track id must be an object path ('o'), the length an int64 ('x')."""
    from PyQt6.QtDBus import QDBusObjectPath
    out = {}
    for key, value in meta.items():
        if key == "mpris:trackid":
            out[key] = QDBusObjectPath(value)
        elif key == "mpris:length":
            out[key] = _int64(value)
        elif isinstance(value, (list, tuple)):
            # MPRIS needs a string ARRAY ('as'). A plain Python list became an array of variants ('av'):
            # playerctl accepted it, Cinnamon's sound applet did not and showed "Unknown Artist".
            out[key] = _string_list(value)
        else:
            out[key] = value
    return out


def _string_list(values):
    from PyQt6.QtCore import QMetaType, QVariant
    v = QVariant([str(x) for x in values])
    v.convert(QMetaType(QMetaType.Type.QStringList.value))
    return v


def _int64(value):
    from PyQt6.QtCore import QMetaType, QVariant
    v = QVariant(int(value))
    v.convert(QMetaType(QMetaType.Type.LongLong.value))
    return v


def _make_adaptor_classes():
    """Built only when D-Bus is used, so importing this module never needs QtDBus (Windows tests)."""
    from PyQt6.QtDBus import QDBusAbstractAdaptor

    @pyqtClassInfo("D-Bus Interface", ROOT_IFACE)
    class RootAdaptor(QDBusAbstractAdaptor):
        def __init__(self, owner):
            super().__init__(owner)
            self.mc = owner.mc
            self.setAutoRelaySignals(False)

        @pyqtProperty(bool)
        def CanQuit(self):
            return False

        @pyqtProperty(bool)
        def CanRaise(self):
            return True

        @pyqtProperty(bool)
        def HasTrackList(self):
            return False

        @pyqtProperty(str)
        def Identity(self):
            return "ALMP"

        @pyqtProperty(str)
        def DesktopEntry(self):
            return "alexbed-almp"

        @pyqtProperty("QStringList")
        def SupportedUriSchemes(self):
            return ["file"]

        @pyqtProperty("QStringList")
        def SupportedMimeTypes(self):
            from .platform_linux import MIME_TYPES
            return list(MIME_TYPES)

        @pyqtSlot()
        def Raise(self):
            self.mc.raise_requested.emit()

        @pyqtSlot()
        def Quit(self):
            pass

    @pyqtClassInfo("D-Bus Interface", PLAYER_IFACE)
    class PlayerAdaptor(QDBusAbstractAdaptor):
        Seeked = pyqtSignal("qlonglong")

        def __init__(self, owner):
            super().__init__(owner)
            self.mc = owner.mc
            self.setAutoRelaySignals(False)

        @pyqtProperty(str)
        def PlaybackStatus(self):
            return playback_status(self.mc.state)

        @pyqtProperty(float)
        def Rate(self):
            return 1.0

        @pyqtProperty(float)
        def MinimumRate(self):
            return 1.0

        @pyqtProperty(float)
        def MaximumRate(self):
            return 1.0

        @pyqtProperty("QVariantMap")
        def Metadata(self):
            return _dbus_metadata(self.mc.meta)

        def _get_volume(self):
            return self.mc.get_volume()

        def _set_volume(self, value):
            self.mc.set_volume(value)

        Volume = pyqtProperty(float, fget=_get_volume, fset=_set_volume)

        @pyqtProperty("qlonglong")
        def Position(self):
            return int(self.mc.get_position() * 1_000_000)

        @pyqtProperty(bool)
        def CanGoNext(self):
            return True

        @pyqtProperty(bool)
        def CanGoPrevious(self):
            return True

        @pyqtProperty(bool)
        def CanPlay(self):
            return True

        @pyqtProperty(bool)
        def CanPause(self):
            return True

        @pyqtProperty(bool)
        def CanSeek(self):
            return False

        @pyqtProperty(bool)
        def CanControl(self):
            return True

        @pyqtSlot()
        def Next(self):
            self.mc.command.emit("next")

        @pyqtSlot()
        def Previous(self):
            self.mc.command.emit("previous")

        @pyqtSlot()
        def Pause(self):
            self.mc.command.emit("pause")

        @pyqtSlot()
        def PlayPause(self):
            self.mc.command.emit("toggle")

        @pyqtSlot()
        def Stop(self):
            self.mc.command.emit("stop")

        @pyqtSlot()
        def Play(self):
            self.mc.command.emit("play")

        @pyqtSlot("qlonglong")
        def Seek(self, offset):
            pass                       # CanSeek is False

        @pyqtSlot("QDBusObjectPath", "qlonglong")      # a string: the built program cannot see the class here
        def SetPosition(self, track, position):
            pass

        @pyqtSlot(str)
        def OpenUri(self, uri):
            pass                       # ALMP opens files from its own window only

    return RootAdaptor, PlayerAdaptor


class _Exported(QObject):
    def __init__(self, mc):
        super().__init__()
        self.mc = mc


class LinuxMediaControls(QObject):
    """Signals `command(str)` with "play", "pause", "toggle", "next", "previous" or "stop", and
    `raise_requested` when the desktop asks to show ALMP's window."""
    command = pyqtSignal(str)
    raise_requested = pyqtSignal()

    def __init__(self, parent=None, volume_get=None, volume_set=None, position_get=None):
        super().__init__(parent)
        self.active = False
        self.state = "stopped"
        self.meta = {}
        self.bus_name = ""
        self._track_number = 0
        self._last_title = None
        self._bus = None
        self._obj = None
        self._volume_get = volume_get
        self._volume_set = volume_set
        self._position_get = position_get

    # --- values the adaptors read ---
    def get_volume(self):
        try:
            return max(0.0, float(self._volume_get())) if self._volume_get else 1.0
        except Exception:          # noqa: BLE001
            return 1.0

    def set_volume(self, value):
        if self._volume_set is not None:
            try:
                self._volume_set(max(0.0, float(value)))
            except Exception:          # noqa: BLE001
                log.debug("MPRIS volume change failed", exc_info=True)

    def get_position(self):
        try:
            return max(0.0, float(self._position_get() or 0)) if self._position_get else 0.0
        except Exception:          # noqa: BLE001
            return 0.0

    # --- start / stop ---
    def start(self, _hwnd=None):
        """Register on the session bus. Returns True when it works."""
        if not sys.platform.startswith("linux"):
            return False
        try:
            self._start()
            self.active = True
            log.info("MPRIS media controls are on (%s)", self.bus_name)
        except Exception:          # noqa: BLE001 - ALMP works fine without it
            log.warning("MPRIS media controls are not available; media keys work while ALMP is in front",
                        exc_info=True)
            self.stop()
        return self.active

    def _start(self):
        from PyQt6.QtDBus import QDBusConnection
        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            raise OSError("no D-Bus session bus")
        root_cls, player_cls = _make_adaptor_classes()
        obj = _Exported(self)
        obj._root = root_cls(obj)
        obj._player = player_cls(obj)
        if not bus.registerObject(OBJECT_PATH, obj):
            raise OSError("registerObject failed: " + bus.lastError().message())
        self._bus, self._obj = bus, obj
        name = bus_name_for(False)
        if not bus.registerService(name):
            name = bus_name_for(True)
            if not bus.registerService(name):
                raise OSError("registerService failed: " + bus.lastError().message())
        self.bus_name = name

    def stop(self):
        if self._bus is not None:
            try:
                if self.bus_name:
                    self._bus.unregisterService(self.bus_name)
                self._bus.unregisterObject(OBJECT_PATH)
            except Exception:          # noqa: BLE001
                log.debug("Stopping MPRIS failed", exc_info=True)
        self._bus = None
        self._obj = None
        self.bus_name = ""
        self.active = False

    # --- updates from the player ---
    def set_status(self, state):
        if state == self.state:
            return
        self.state = state
        self._changed({"PlaybackStatus": playback_status(state)})

    def set_track(self, title, video=False, length_s=None, artist=None, art_url=None, album=None):
        key = (title, artist, art_url, album)
        if key == self._last_title:
            return
        new_track = self._last_title is None or self._last_title[0] != title
        self._last_title = key
        if new_track:
            self._track_number += 1
        self.meta = metadata(self._track_number, title, video, length_s, artist, art_url, album)
        self._changed({"Metadata": _dbus_metadata(self.meta) if self._bus is not None else self.meta})

    def clear_track(self):
        self._last_title = None
        self.meta = {}
        self._changed({"Metadata": {}})

    def _changed(self, props):
        """org.freedesktop.DBus.Properties.PropertiesChanged, so desktops update at once."""
        if self._bus is None:
            return
        try:
            from PyQt6.QtCore import QMetaType
            from PyQt6.QtDBus import QDBusArgument, QDBusMessage
            msg = QDBusMessage.createSignal(OBJECT_PATH, PROPS_IFACE, "PropertiesChanged")
            invalidated = QDBusArgument()
            invalidated.add([], QMetaType.Type.QStringList.value)
            msg.setArguments([PLAYER_IFACE, props, invalidated])
            self._bus.send(msg)
        except Exception:          # noqa: BLE001
            log.debug("PropertiesChanged failed", exc_info=True)
