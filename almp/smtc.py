# Alexbed Light Media Player (ALMP)
# Copyright (C) 2026 Alexander Bediako
# SPDX-License-Identifier: GPL-3.0-or-later
"""Windows media controls (System Media Transport Controls, "SMTC") with plain ctypes.

What it gives: the keyboard's Play/Pause, Next and Previous keys reach ALMP while another window
is in front (a browser, an e-mail program...), the Windows volume pop-up and the lock screen show
the track name with Play/Pause/Next/Previous buttons. No extra package is needed (it calls
Windows' own combase.dll), so the download does not get bigger.

Safety:
  * It never steals keys from other programs: Windows sends media keys to the media app that is
    "current" (the one that played last), like with any modern player.
  * Every native call is guarded. If anything fails, ALMP simply goes on without it.
  * A marker file is written while it starts. If ALMP ever stops during that start (a native
    crash cannot be caught), the next start finds the marker, switches this feature off in
    Settings and writes a note in almp.log, so ALMP can never get stuck crashing at start.
  * Settings > "Media keys and Windows media controls" can switch it off.

Interface layouts (method order in each COM vtable) and IIDs are from the Windows SDK
(windows.media.idl / systemmediatransportcontrolsinterop.h); the event-handler IID is the
WinRT parameterised-interface GUID, computed by `pinterface_iid` and checked in the tests.
"""
import hashlib
import sys
import uuid

from PyQt6.QtCore import QObject, pyqtSignal

from .logsetup import log
from .paths import get_log_dir

# WinRT enums (windows.media.idl)
STATUS_CLOSED, STATUS_CHANGING, STATUS_STOPPED, STATUS_PLAYING, STATUS_PAUSED = range(5)
TYPE_UNKNOWN, TYPE_MUSIC, TYPE_VIDEO = 0, 1, 2
BUTTON_NAMES = {0: "play", 1: "pause", 2: "stop", 3: "record", 4: "fastforward", 5: "rewind",
                6: "next", 7: "previous", 8: "channelup", 9: "channeldown"}

IID_IUnknown = "00000000-0000-0000-c000-000000000046"
IID_IAgileObject = "94ea2b94-e9cc-49e0-c0ff-ee64ca8f5b90"
IID_ISystemMediaTransportControlsInterop = "ddb0472d-c911-4a1f-86d9-dc3d71a95f5a"
IID_ISystemMediaTransportControls = "99fa3ff4-1742-42a6-902e-087d41f965ec"
IID_ISystemMediaTransportControlsButtonPressedEventArgs = "b7f47116-a56f-4dc8-9e11-92031f4a87c2"
IID_ISystemMediaTransportControlsDisplayUpdater = "8abbc53e-fa55-4ecf-ad8e-c984e5dd1550"
IID_IMusicDisplayProperties = "6bbf0c59-d0a0-4d26-92a0-f978e1d18e7b"
IID_IVideoDisplayProperties = "5609fdb1-5d2d-4872-8170-45dee5bc2f5c"
IID_TypedEventHandler = "9de1c534-6ae1-11e0-84e1-18a905bcc53f"   # Windows.Foundation.TypedEventHandler`2
WINRT_PINTERFACE_NAMESPACE = "11f47ad5-7b73-42c0-abae-878b1e16adee"

BUTTON_HANDLER_SIGNATURE = (
    "pinterface({%s};rc(Windows.Media.SystemMediaTransportControls;{%s});"
    "rc(Windows.Media.SystemMediaTransportControlsButtonPressedEventArgs;{%s}))"
    % (IID_TypedEventHandler, IID_ISystemMediaTransportControls,
       IID_ISystemMediaTransportControlsButtonPressedEventArgs))

# vtable slots (0-2 IUnknown, 3-5 IInspectable)
VT_RELEASE = 2
VT_INTEROP_GET_FOR_WINDOW = 6
VT_SMTC_PUT_PLAYBACK_STATUS = 7
VT_SMTC_GET_DISPLAY_UPDATER = 8
VT_SMTC_PUT_IS_ENABLED = 11
VT_SMTC_PUT_IS_PLAY_ENABLED = 13
VT_SMTC_PUT_IS_STOP_ENABLED = 15
VT_SMTC_PUT_IS_PAUSE_ENABLED = 17
VT_SMTC_PUT_IS_PREVIOUS_ENABLED = 25
VT_SMTC_PUT_IS_NEXT_ENABLED = 27
VT_SMTC_ADD_BUTTON_PRESSED = 32
VT_SMTC_REMOVE_BUTTON_PRESSED = 33
VT_ARGS_GET_BUTTON = 6
VT_UPD_PUT_TYPE = 7
VT_UPD_GET_MUSIC = 12
VT_UPD_GET_VIDEO = 13
VT_UPD_CLEAR_ALL = 16
VT_UPD_UPDATE = 17
VT_MUSIC_PUT_TITLE = 7
VT_MUSIC_PUT_ARTIST = 11
VT_VIDEO_PUT_TITLE = 7

S_OK = 0
E_NOINTERFACE = -2147467262          # 0x80004002

MARKER_NAME = "media-controls-starting.flag"


def pinterface_iid(signature):
    """GUID of a WinRT parameterised interface (UUID version 5 over the type signature)."""
    ns = uuid.UUID(WINRT_PINTERFACE_NAMESPACE)
    digest = bytearray(hashlib.sha1(ns.bytes + signature.encode("utf-8")).digest()[:16])
    digest[6] = (digest[6] & 0x0F) | 0x50
    digest[8] = (digest[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(digest)))


IID_ButtonPressedHandler = pinterface_iid(BUTTON_HANDLER_SIGNATURE)


def button_name(value):
    return BUTTON_NAMES.get(int(value), "unknown")


def marker_path(folder=None):
    return (folder if folder is not None else get_log_dir()) / MARKER_NAME


def previous_start_crashed(folder=None):
    """True if the marker from an unfinished start is still there (and removes it)."""
    p = marker_path(folder)
    try:
        if p.exists():
            p.unlink()
            return True
    except OSError:
        log.debug("Could not remove %s", p, exc_info=True)
    return False


class _Native:
    """The ctypes part. Only created on Windows."""

    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ctypes = ctypes
        self.wintypes = wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16),
                        ("Data3", ctypes.c_uint16), ("Data4", ctypes.c_ubyte * 8)]
        self.GUID = GUID
        self.combase = ctypes.WinDLL("combase.dll")
        self.combase.WindowsCreateString.argtypes = [wintypes.LPCWSTR, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)]
        self.combase.WindowsCreateString.restype = ctypes.c_long
        self.combase.WindowsDeleteString.argtypes = [ctypes.c_void_p]
        self.combase.WindowsDeleteString.restype = ctypes.c_long
        self.combase.RoGetActivationFactory.argtypes = [ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
        self.combase.RoGetActivationFactory.restype = ctypes.c_long
        self.combase.RoInitialize.argtypes = [ctypes.c_int]
        self.combase.RoInitialize.restype = ctypes.c_long

    def guid(self, text):
        return self.GUID.from_buffer_copy(uuid.UUID(text).bytes_le)

    def guid_equals(self, gptr, text):
        try:
            return bytes(self.ctypes.string_at(self.ctypes.addressof(gptr.contents), 16)) == uuid.UUID(text).bytes_le
        except (ValueError, TypeError):
            return False

    def hstring(self, text):
        h = self.ctypes.c_void_p()
        text = text or ""
        hr = self.combase.WindowsCreateString(text, len(text), self.ctypes.byref(h))
        if hr < 0:
            raise OSError(f"WindowsCreateString failed {hr:#x}")
        return h

    def free_hstring(self, h):
        if h:
            self.combase.WindowsDeleteString(h)

    def call(self, obj, index, argtypes, *args):
        """Call method `index` of COM object `obj`. Returns the HRESULT (negative = failed)."""
        c = self.ctypes
        if not obj:
            raise OSError("null COM pointer")
        vtbl = c.cast(obj, c.POINTER(c.POINTER(c.c_void_p))).contents
        proto = c.WINFUNCTYPE(c.c_long, c.c_void_p, *argtypes)
        return proto(vtbl[index])(obj, *args)

    def check(self, hr, what):
        if hr < 0:
            raise OSError(f"{what} failed: HRESULT {hr & 0xFFFFFFFF:#010x}")

    def release(self, obj):
        if obj:
            try:
                c = self.ctypes
                vtbl = c.cast(obj, c.POINTER(c.POINTER(c.c_void_p))).contents
                c.WINFUNCTYPE(c.c_ulong, c.c_void_p)(vtbl[VT_RELEASE])(obj)
            except Exception:          # noqa: BLE001
                log.debug("Release failed", exc_info=True)


class WindowsMediaControls(QObject):
    """Signals `command(str)` with "play", "pause", "toggle", "next", "previous" or "stop"."""
    command = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.active = False
        self._n = None
        self._smtc = None
        self._token = None
        self._handler = None          # keeps the ctypes callback objects alive
        self._last_title = None

    # --- start / stop ---
    def start(self, hwnd):
        """Connect to Windows for this window. Returns True when it works."""
        if sys.platform != "win32" or not hwnd:
            return False
        marker = marker_path()
        try:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("ALMP was starting the Windows media controls.\n", encoding="utf-8")
        except OSError:
            log.debug("Could not write the media-controls marker", exc_info=True)
        try:
            self._start(int(hwnd))
            self.active = True
            log.info("Windows media controls are on")
        except Exception:          # noqa: BLE001 - ALMP works fine without it
            log.warning("Windows media controls are not available; media keys work while ALMP is in front",
                        exc_info=True)
            self.active = False
            self._smtc = None
        finally:
            try:
                marker.unlink()
            except OSError:
                pass
        return self.active

    def _start(self, hwnd):
        n = self._n = _Native()
        c = n.ctypes
        n.combase.RoInitialize(0)          # already initialised by Qt is fine (S_FALSE / changed mode)
        cls = n.hstring("Windows.Media.SystemMediaTransportControls")
        interop = c.c_void_p()
        try:
            iid = n.guid(IID_ISystemMediaTransportControlsInterop)
            n.check(n.combase.RoGetActivationFactory(cls, c.byref(iid), c.byref(interop)), "RoGetActivationFactory")
        finally:
            n.free_hstring(cls)
        smtc = c.c_void_p()
        try:
            iid = n.guid(IID_ISystemMediaTransportControls)
            n.check(n.call(interop, VT_INTEROP_GET_FOR_WINDOW,
                           [n.wintypes.HWND, c.POINTER(n.GUID), c.POINTER(c.c_void_p)],
                           hwnd, c.byref(iid), c.byref(smtc)), "GetForWindow")
        finally:
            n.release(interop)
        self._smtc = smtc
        b = [c.c_ubyte]
        for slot in (VT_SMTC_PUT_IS_PLAY_ENABLED, VT_SMTC_PUT_IS_PAUSE_ENABLED, VT_SMTC_PUT_IS_NEXT_ENABLED,
                     VT_SMTC_PUT_IS_PREVIOUS_ENABLED, VT_SMTC_PUT_IS_STOP_ENABLED):
            n.check(n.call(smtc, slot, b, 1), f"vtable slot {slot}")
        n.check(n.call(smtc, VT_SMTC_PUT_IS_ENABLED, b, 1), "put_IsEnabled")
        self._handler = self._make_handler()
        token = c.c_int64()
        n.check(n.call(smtc, VT_SMTC_ADD_BUTTON_PRESSED, [c.c_void_p, c.POINTER(c.c_int64)],
                       c.addressof(self._handler["obj"]), c.byref(token)), "add_ButtonPressed")
        self._token = token
        self.set_status("stopped")

    def _make_handler(self):
        """A tiny COM object (TypedEventHandler) whose Invoke is a Python function."""
        n = self._n
        c = n.ctypes
        QI = c.WINFUNCTYPE(c.c_long, c.c_void_p, c.POINTER(n.GUID), c.POINTER(c.c_void_p))
        REF = c.WINFUNCTYPE(c.c_ulong, c.c_void_p)
        INVOKE = c.WINFUNCTYPE(c.c_long, c.c_void_p, c.c_void_p, c.c_void_p)

        class Vtbl(c.Structure):
            _fields_ = [("QueryInterface", QI), ("AddRef", REF), ("Release", REF), ("Invoke", INVOKE)]

        class Obj(c.Structure):
            _fields_ = [("lpVtbl", c.POINTER(Vtbl))]

        known = (IID_IUnknown, IID_IAgileObject, IID_ButtonPressedHandler)

        def query_interface(this, riid, ppv):
            try:
                if any(n.guid_equals(riid, k) for k in known):
                    ppv[0] = this
                    return S_OK
                ppv[0] = None
            except Exception:          # noqa: BLE001 - never raise into Windows
                log.debug("QueryInterface failed", exc_info=True)
            return E_NOINTERFACE

        def add_ref(this):
            return 2                   # the object lives as long as ALMP runs

        def release(this):
            return 1

        def invoke(this, sender, args):
            try:
                value = c.c_int(-1)
                hr = n.call(args, VT_ARGS_GET_BUTTON, [c.POINTER(c.c_int)], c.byref(value))
                if hr >= 0:
                    name = button_name(value.value)
                    if name in ("play", "pause", "next", "previous", "stop"):
                        self.command.emit(name)        # thread-safe: queued to the window
            except Exception:          # noqa: BLE001
                log.debug("Media button handler failed", exc_info=True)
            return S_OK

        funcs = (QI(query_interface), REF(add_ref), REF(release), INVOKE(invoke))
        vtbl = Vtbl(*funcs)
        obj = Obj(c.pointer(vtbl))
        return {"funcs": funcs, "vtbl": vtbl, "obj": obj}

    def stop(self):
        if not self.active or self._n is None:
            return
        n = self._n
        try:
            if self._token is not None:
                n.call(self._smtc, VT_SMTC_REMOVE_BUTTON_PRESSED, [n.ctypes.c_int64], self._token.value)
            n.call(self._smtc, VT_SMTC_PUT_IS_ENABLED, [n.ctypes.c_ubyte], 0)
        except Exception:          # noqa: BLE001
            log.debug("Stopping the media controls failed", exc_info=True)
        n.release(self._smtc)
        self._smtc = None
        self.active = False

    # --- updates from the player ---
    def set_status(self, state):
        if not self._smtc:
            return
        value = {"playing": STATUS_PLAYING, "paused": STATUS_PAUSED, "stopped": STATUS_STOPPED,
                 "closed": STATUS_CLOSED}.get(state, STATUS_STOPPED)
        try:
            self._n.call(self._smtc, VT_SMTC_PUT_PLAYBACK_STATUS, [self._n.ctypes.c_int], value)
        except Exception:          # noqa: BLE001
            log.debug("put_PlaybackStatus failed", exc_info=True)

    def set_track(self, title, video=False):
        """Show the track name in the Windows volume pop-up and on the lock screen."""
        if not self._smtc or title == self._last_title:
            return
        self._last_title = title
        n = self._n
        c = n.ctypes
        upd = c.c_void_p()
        props = c.c_void_p()
        h = None
        try:
            n.check(n.call(self._smtc, VT_SMTC_GET_DISPLAY_UPDATER, [c.POINTER(c.c_void_p)], c.byref(upd)),
                    "get_DisplayUpdater")
            n.check(n.call(upd, VT_UPD_PUT_TYPE, [c.c_int], TYPE_VIDEO if video else TYPE_MUSIC), "put_Type")
            slot = VT_UPD_GET_VIDEO if video else VT_UPD_GET_MUSIC
            n.check(n.call(upd, slot, [c.POINTER(c.c_void_p)], c.byref(props)), "get_Properties")
            h = n.hstring(title or "")
            n.check(n.call(props, VT_VIDEO_PUT_TITLE if video else VT_MUSIC_PUT_TITLE, [c.c_void_p], h),
                    "put_Title")
            n.check(n.call(upd, VT_UPD_UPDATE, []), "Update")
        except Exception:          # noqa: BLE001
            log.debug("Updating the media controls title failed", exc_info=True)
        finally:
            if h is not None:
                n.free_hstring(h)
            n.release(props)
            n.release(upd)

    def clear_track(self):
        if not self._smtc:
            return
        self._last_title = None
        n = self._n
        c = n.ctypes
        upd = c.c_void_p()
        try:
            n.check(n.call(self._smtc, VT_SMTC_GET_DISPLAY_UPDATER, [c.POINTER(c.c_void_p)], c.byref(upd)),
                    "get_DisplayUpdater")
            n.call(upd, VT_UPD_CLEAR_ALL, [])
            n.call(upd, VT_UPD_UPDATE, [])
        except Exception:          # noqa: BLE001
            log.debug("Clearing the media controls failed", exc_info=True)
        finally:
            n.release(upd)
