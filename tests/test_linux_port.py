"""Linux port (ALMP-Linux): the freedesktop.org Trash and the .desktop menu entry. Pure parts, so
they run on Windows too (a temporary folder stands in for the home folder)."""
import os
import sys
import time
from pathlib import Path

import pytest

from almp import platform_linux as pl
from almp import platform_win as pw


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    (h / ".local" / "share").mkdir(parents=True)
    env = {"XDG_DATA_HOME": str(h / ".local" / "share")}
    return h, env


def test_bin_name_per_system():
    assert pw.bin_name("linux") == "Trash"
    assert pw.bin_name("win32") == "Recycle Bin"


def test_trash_dir_is_home_trash_on_the_same_drive(home, tmp_path):
    h, env = home
    f = tmp_path / "music" / "a.mp3"
    f.parent.mkdir()
    f.write_bytes(b"x")
    folder, top = pl.trash_dir_for(f, env, h, uid=1000)
    assert folder == h / ".local" / "share" / "Trash" and top is None


def test_missing_file_has_no_trash(home, tmp_path):
    h, env = home
    assert pl.trash_dir_for(tmp_path / "nope.mp3", env, h, uid=1000) == (None, None)
    assert pl.trash_available(str(tmp_path / "nope.mp3"), "linux", env, h, 1000) is False


def test_trash_available_only_on_linux(home, tmp_path):
    h, env = home
    f = tmp_path / "a.mp3"
    f.write_bytes(b"x")
    assert pl.trash_available(str(f), "linux", env, h, 1000) is True
    assert pl.trash_available(str(f), "win32", env, h, 1000) is False


def test_move_to_trash_moves_file_and_writes_info(home, tmp_path):
    h, env = home
    f = tmp_path / "Song ｜ name.flac"           # full-width bar, as in ALMP 8.2.8
    f.write_bytes(b"audio")
    when = time.mktime((2026, 11, 24, 13, 5, 9, 0, 0, -1))
    assert pl.move_to_trash(str(f), env, h, 1000, when) == pl.DELETE_OK
    trash = h / ".local" / "share" / "Trash"
    assert not f.exists()
    assert (trash / "files" / f.name).read_bytes() == b"audio"
    info = (trash / "info" / f"{f.name}.trashinfo").read_text(encoding="utf-8")
    assert info.startswith("[Trash Info]\nPath=")
    assert "%EF%BD%9C" in info and "%20" in info             # URL-escaped, as the spec asks
    assert "DeletionDate=2026-11-24T13:05:09" in info


def test_same_name_twice_gets_a_new_name(home, tmp_path):
    h, env = home
    for i in range(2):
        f = tmp_path / "a.mp3"
        f.write_bytes(bytes([i]))
        assert pl.move_to_trash(str(f), env, h, 1000) == pl.DELETE_OK
    files = sorted(p.name for p in (h / ".local" / "share" / "Trash" / "files").iterdir())
    assert files == ["a.2.mp3", "a.mp3"]
    infos = sorted(p.name for p in (h / ".local" / "share" / "Trash" / "info").iterdir())
    assert infos == ["a.2.mp3.trashinfo", "a.mp3.trashinfo"]


def test_failed_move_leaves_the_file_and_no_info(home, tmp_path, monkeypatch):
    h, env = home
    f = tmp_path / "a.mp3"
    f.write_bytes(b"x")

    def boom(*a, **k):
        raise OSError("read-only")
    monkeypatch.setattr(pl.os, "rename", boom)
    assert pl.move_to_trash(str(f), env, h, 1000) == pl.DELETE_FAILED
    assert f.exists()
    assert not list((h / ".local" / "share" / "Trash" / "info").iterdir())


def test_trashinfo_relative_path_for_a_drive_trash(tmp_path):
    top = tmp_path / "usb"
    text = pl.trashinfo_text(str(top / "Music" / "a b.mp3"), topdir=top, when=0)
    assert "\nPath=Music/a%20b.mp3\n" in text


def test_drive_trash_name_uses_uid(tmp_path, monkeypatch):
    f = tmp_path / "a.mp3"
    f.write_bytes(b"x")
    monkeypatch.setattr(pl, "_existing_parent_dev", lambda p: -1)     # home is on another drive
    folder, top = pl.trash_dir_for(f, {}, tmp_path / "home", uid=1000, mounts_text="")
    assert top is not None and folder == top / ".Trash-1000"


@pytest.mark.parametrize("fstype, has_trash", [
    ("ext4", True), ("vfat", True), ("exfat", True), ("ntfs3", True), ("btrfs", True),
    ("tmpfs", False), ("nfs4", False), ("cifs", False), ("fuse.sshfs", False), ("iso9660", False),
])
def test_ram_disks_and_network_drives_have_no_trash(tmp_path, monkeypatch, fstype, has_trash):
    # Same rule as Windows (RAM disk / network drive = no Recycle Bin): ALMP asks before a permanent delete.
    f = tmp_path / "a.mp3"
    f.write_bytes(b"x")
    monkeypatch.setattr(pl, "_existing_parent_dev", lambda p: -1)     # not on the home drive
    top = pl.mount_point(f)
    escaped = str(top).replace(" ", r"\040")
    mounts = f"/dev/sda2 / ext4 rw 0 0\nsrv:/x {escaped} {fstype} rw 0 0\n"
    folder, _ = pl.trash_dir_for(f, {}, tmp_path / "home", uid=1000, mounts_text=mounts)
    assert (folder is not None) is has_trash


def test_filesystem_type_reads_proc_mounts_format():
    text = "/dev/sdb1 /media/almp/MY" + r"\040" + "STICK vfat rw 0 0\ntmpfs /tmp tmpfs rw 0 0\n"
    assert pl.filesystem_type("/media/almp/MY STICK", text) == "vfat"
    assert pl.filesystem_type("/tmp", text) == "tmpfs"
    assert pl.filesystem_type("/nowhere", text) == ""
    # the last mount on the same folder wins
    assert pl.filesystem_type("/mnt", "a /mnt ext4 rw 0 0\nb /mnt tmpfs rw 0 0\n") == "tmpfs"


def test_linux_send_to_trash_goes_through_platform_linux(monkeypatch, tmp_path):
    monkeypatch.setattr(pw.sys, "platform", "linux")
    calls = []
    monkeypatch.setattr(pl, "move_to_trash", lambda p: calls.append(p) or pl.DELETE_OK)
    assert pw.send_to_recycle_bin(str(tmp_path / "a.mp3")) == pw.DELETE_OK
    assert calls == [str(tmp_path / "a.mp3")]


# --- .desktop file ---

def test_desktop_entry_lists_types_and_quotes_exec():
    text = pl.desktop_entry_text("/home/al ex/ALMP/ALMP", icon="/home/al ex/ALMP/icon.png")
    assert text.startswith("[Desktop Entry]\nType=Application\n")
    assert 'Exec="/home/al ex/ALMP/ALMP" %F' in text
    assert "audio/flac;" in text and "video/x-matroska;" in text
    assert text.rstrip("\n").splitlines()[-1] == "Icon=/home/al ex/ALMP/icon.png"
    assert pl._desktop_quote('a"b$c') == r'"a\"b\$c"'


def test_install_and_remove_desktop_entry(home):
    h, env = home
    runs = []
    ok, msg = pl.install_desktop_entry("/opt/ALMP/ALMP", make_default=True, environ=env, home=h,
                                       run=lambda c: runs.append(c) or True)
    assert ok and msg == ""
    assert pl.desktop_entry_installed(env, h)
    assert runs[0][0] == "update-desktop-database"
    assert runs[1][:3] == ["xdg-mime", "default", pl.DESKTOP_FILE_NAME] and "audio/mpeg" in runs[1]
    ok, _ = pl.remove_desktop_entry(env, h, run=lambda c: True)
    assert ok and not pl.desktop_entry_installed(env, h)


def test_missing_xdg_mime_is_reported(home):
    h, env = home
    ok, msg = pl.install_desktop_entry("/opt/ALMP/ALMP", make_default=True, environ=env, home=h,
                                       run=lambda c: c[0] != "xdg-mime")
    assert not ok and "xdg-utils" in msg


def test_can_register_only_the_built_linux_program(tmp_path):
    exe = tmp_path / "ALMP"
    exe.write_bytes(b"#!/bin/sh\n")
    os.chmod(exe, 0o755)
    assert pl.can_register(str(exe), "win32") is False
    assert pl.can_register(str(tmp_path / "main.py"), "linux") is False
    if sys.platform.startswith("linux"):
        assert pl.can_register(str(exe), "linux") is True


def test_xdg_data_home_must_be_absolute(tmp_path):
    assert pl.applications_dir({"XDG_DATA_HOME": "relative"}, tmp_path) == \
        Path(tmp_path) / ".local" / "share" / "applications"


# --- mpv options and Settings on Linux ---

def test_exclusive_audio_options_per_system():
    from almp import player
    assert player.mpv_options(1, audio_exclusive=True, platform="win32")["audio_exclusive"] == "yes"  # unchanged
    assert "audio_exclusive" not in player.mpv_options(1, platform="win32")
    env = {}
    o = player.mpv_options(1, audio_exclusive=True, platform="linux", environ=env, proc_version="Linux 6.12")
    assert o["audio_exclusive"] == "yes" and o["audio_device"] == "auto"            # PipeWire, exclusive
    o = player.mpv_options(1, audio_exclusive=True, platform="linux", environ=env, proc_version="Linux 6.12",
                           audio_device="alsa/hdmi:CARD=PCH,DEV=0")
    assert o["audio_device"] == "alsa/hdmi:CARD=PCH,DEV=0" and o["audio_exclusive"] == "no"   # straight to it
    o = player.mpv_options(1, platform="linux", environ=env, proc_version="Linux 6.12")
    assert "audio_exclusive" not in o and "audio_device" not in o                    # off: mpv's defaults
    assert o["ytdl"] == "no" and o["config"] == "no" and o["load_scripts"] == "no"      # still offline
    assert player.exclusive_audio_options(False, "alsa/hdmi:x", "linux") == {"audio_exclusive": "no",
                                                                            "audio_device": "auto"}


def test_exclusive_devices_are_the_direct_ones():
    from almp import player
    listed = [{"name": "auto"}, {"name": "pipewire"}, {"name": "alsa/plughw:CARD=PCH,DEV=0"},
              {"name": "alsa/front:CARD=PCH,DEV=0", "description": "HDA Intel PCH, Analog"},
              {"name": "alsa/hdmi:CARD=PCH,DEV=0", "description": "HDA Intel PCH, HDMI 0"},
              {"name": "alsa/dmix:CARD=PCH,DEV=0"}, {"name": "alsa/sysdefault:CARD=PCH"},
              {"name": "alsa/hw:CARD=Dac,DEV=0", "description": ""}]
    assert player.exclusive_devices(listed) == [
        ("alsa/front:CARD=PCH,DEV=0", "HDA Intel PCH, Analog"),
        ("alsa/hdmi:CARD=PCH,DEV=0", "HDA Intel PCH, HDMI 0"),
        ("alsa/hw:CARD=Dac,DEV=0", "alsa/hw:CARD=Dac,DEV=0")]
    assert player.exclusive_devices(None) == []


def test_exclusive_device_setting_is_checked():
    from almp.settings import effective_settings
    assert effective_settings({})["audio_exclusive_device"] == ""
    assert effective_settings({"audio_exclusive_device": "alsa/hdmi:CARD=PCH,DEV=3"})["audio_exclusive_device"]         == "alsa/hdmi:CARD=PCH,DEV=3"
    for bad in ("pipewire", 5, "rm -rf /", None):
        assert effective_settings({"audio_exclusive_device": bad})["audio_exclusive_device"] == ""


def test_audio_output_failed():
    from types import SimpleNamespace as NS

    from almp.player import audio_output_failed
    playing_sound = [{"type": "audio", "selected": True}]
    assert audio_output_failed(NS(current_ao=None, track_list=playing_sound)) is True
    assert audio_output_failed(NS(current_ao="alsa", track_list=playing_sound)) is False
    assert audio_output_failed(NS(current_ao=None, track_list=[{"type": "video", "selected": True}])) is False
    assert audio_output_failed(object()) is False


from test_v824_features import qapp, qt, win  # noqa: E402,F401  (shared window fixtures)


@qt
def test_settings_shows_a_linux_section(win, monkeypatch):  # noqa: F811
    from almp import dialogs
    monkeypatch.setattr(dialogs, "IS_LINUX", True)
    monkeypatch.setattr(win, "can_register_with_desktop", lambda: True)
    monkeypatch.setattr(win, "desktop_entry_installed", lambda: False)
    changed = []
    monkeypatch.setattr(win, "set_desktop_entry", lambda on: changed.append(on) or False)
    d = dialogs.SettingsDialog(win)
    assert not hasattr(d, "folder_verb") and not hasattr(d, "undo_default")    # no Windows-only options
    assert d.media_keys.isChecked() and "MPRIS" in d.media_keys.text()
    page = d._page.layout()                     # same order as Windows: media keys first
    assert page.indexOf(d.media_keys) < page.indexOf(d.menu_entry)
    assert not d.exclusive.isHidden() and d.exclusive.text() == "Exclusive audio (bit-perfect)"
    assert d.exclusive_output.itemData(0) == "" and "PipeWire" in d.exclusive_output.itemText(0)
    assert d.menu_entry.isEnabled() and not d.menu_entry.isChecked()
    d.menu_entry.setChecked(True)                    # the change fails -> the box goes back
    assert changed == [True] and not d.menu_entry.isChecked()
    d.close()


@qt
def test_settings_on_windows_is_unchanged(win, monkeypatch):  # noqa: F811
    from almp import dialogs
    monkeypatch.setattr(dialogs, "IS_LINUX", False)
    d = dialogs.SettingsDialog(win)
    assert hasattr(d, "folder_verb") and hasattr(d, "media_keys") and not hasattr(d, "menu_entry")
    assert not d.exclusive.isHidden()
    d.close()


def test_settings_page_has_the_dark_theme_background():
    # Found in the Debian VM: the Settings page inside its scroll area took the desktop's light
    # palette (GNOME default), so ALMP's light text was hard to read. The theme now colours it.
    from almp.theme import stylesheet
    for hc, colour in ((False, "#121212"), (True, "#000000")):
        qss = stylesheet(hc)
        rule = "#settingsScroll, #settingsScroll > QWidget, #settingsPage { background-color: " + colour
        assert rule in qss


@qt
def test_settings_page_uses_the_themed_names(win):  # noqa: F811
    from almp import dialogs
    d = dialogs.SettingsDialog(win)
    assert d.findChild(dialogs.QScrollArea, "settingsScroll") is not None
    assert d._page.objectName() == "settingsPage"
    d.close()


def test_engine_missing_message_per_system():
    from almp.app import engine_missing_message
    linux = engine_missing_message(OSError("libmpv.so.2: not found"), "linux")
    assert "sudo apt install libmpv2" in linux and "mpv-2.dll" not in linux and "libmpv.so.2" in linux
    windows = engine_missing_message(OSError("x"), "win32")
    assert "mpv-2.dll" in windows and "WHOLE ALMP zip" in windows          # Windows text unchanged


# --- MPRIS (background media keys on Linux) ---

def test_mpris_playback_status_and_metadata():
    from almp import mpris
    assert [mpris.playback_status(s) for s in ("playing", "paused", "stopped", "closed", "odd")] == \
        ["Playing", "Paused", "Stopped", "Stopped", "Stopped"]
    assert mpris.metadata(3, "") == {}
    m = mpris.metadata(3, "Song ｜ name", length_s=2.5)
    assert m == {"mpris:trackid": "/org/alexbed/almp/track/3", "xesam:title": "Song ｜ name",
                 "mpris:length": 2_500_000}
    assert "mpris:length" not in mpris.metadata(1, "a", length_s=0)
    assert mpris.bus_name_for(False) == "org.mpris.MediaPlayer2.almp"
    assert mpris.bus_name_for(True) == f"org.mpris.MediaPlayer2.almp.instance{os.getpid()}"


def test_mpris_does_nothing_off_linux(monkeypatch):
    from almp import mpris
    monkeypatch.setattr(mpris.sys, "platform", "win32")
    mc = mpris.LinuxMediaControls()
    assert mc.start() is False and not mc.active
    mc.set_status("playing")                       # safe without a bus; state still kept
    mc.set_track("x")
    assert mc.state == "playing" and mc.meta["xesam:title"] == "x"
    mc.clear_track()
    assert mc.meta == {}
    mc.stop()


def test_mpris_new_title_gets_a_new_track_id():
    from almp import mpris
    mc = mpris.LinuxMediaControls()
    mc.set_track("a")
    first = mc.meta["mpris:trackid"]
    mc.set_track("a")                              # same title: nothing changes
    assert mc.meta["mpris:trackid"] == first
    mc.set_track("b")
    assert mc.meta["mpris:trackid"] != first


def test_mpris_volume_and_position_never_raise():
    from almp import mpris
    got = []
    mc = mpris.LinuxMediaControls(volume_get=lambda: 0.4, volume_set=got.append, position_get=lambda: None)
    assert mc.get_volume() == 0.4 and mc.get_position() == 0.0
    mc.set_volume(-1)
    assert got == [0.0]

    def boom(*a):
        raise RuntimeError("player gone")
    bad = mpris.LinuxMediaControls(volume_get=boom, volume_set=boom, position_get=boom)
    assert bad.get_volume() == 1.0 and bad.get_position() == 0.0
    bad.set_volume(0.5)
    assert mpris.LinuxMediaControls().get_volume() == 1.0


def _session_bus():
    if not sys.platform.startswith("linux"):
        return None
    try:
        from PyQt6.QtDBus import QDBusConnection
    except ImportError:
        return None
    bus = QDBusConnection.sessionBus()
    return bus if bus.isConnected() else None


@qt
def test_mpris_over_the_real_session_bus(qapp):  # noqa: F811
    bus = _session_bus()
    if bus is None:
        pytest.skip("needs Linux with a D-Bus session bus")
    from PyQt6.QtDBus import QDBusInterface

    from almp import mpris
    mc = mpris.LinuxMediaControls(volume_get=lambda: 0.75, position_get=lambda: 2.0)
    got = []
    mc.command.connect(got.append)
    raised = []
    mc.raise_requested.connect(lambda: raised.append(1))
    assert mc.start() is True
    try:
        mc.set_track("Test song")
        mc.set_status("playing")
        player = QDBusInterface(mc.bus_name, mpris.OBJECT_PATH, mpris.PLAYER_IFACE, bus)
        root = QDBusInterface(mc.bus_name, mpris.OBJECT_PATH, mpris.ROOT_IFACE, bus)
        props = QDBusInterface(mc.bus_name, mpris.OBJECT_PATH, mpris.PROPS_IFACE, bus)

        def get(iface, name):
            reply = props.call("Get", iface, name)
            assert not reply.errorMessage(), (name, reply.errorMessage())
            return reply.arguments()[0]
        assert get(mpris.PLAYER_IFACE, "PlaybackStatus") == "Playing"
        assert get(mpris.PLAYER_IFACE, "Volume") == 0.75
        assert get(mpris.PLAYER_IFACE, "Position") == 2_000_000
        assert get(mpris.PLAYER_IFACE, "Metadata")["xesam:title"] == "Test song"
        assert get(mpris.ROOT_IFACE, "Identity") == "ALMP"
        assert get(mpris.ROOT_IFACE, "DesktopEntry") == "alexbed-almp"
        for method in ("PlayPause", "Play", "Pause", "Next", "Previous", "Stop"):
            reply = player.call(method)
            assert not reply.errorMessage(), (method, reply.errorMessage())
        root.call("Raise")
        intro = QDBusInterface(mc.bus_name, mpris.OBJECT_PATH, "org.freedesktop.DBus.Introspectable", bus)
        xml = intro.call("Introspect").arguments()[0]
        for needed in ('<method name="SetPosition">', 'type="o"', '<method name="Seek">', 'type="x"',
                       '<property name="Metadata" type="a{sv}"', '<method name="OpenUri">'):
            assert needed in xml, needed
        deadline = time.monotonic() + 3
        while len(got) < 6 and time.monotonic() < deadline:
            qapp.processEvents()
        assert got == ["toggle", "play", "pause", "next", "previous", "stop"]
        assert raised == [1]
    finally:
        mc.stop()
    assert not mc.active and mc.bus_name == ""


@qt
def test_window_uses_mpris_on_linux(win, monkeypatch):  # noqa: F811
    from almp import ui
    made = []

    class FakeMPRIS(ui.QObject):
        command = ui.pyqtSignal(str)
        raise_requested = ui.pyqtSignal()

        def __init__(self, parent, **kw):
            super().__init__(parent)
            self.kw = kw
            self.status = []
            made.append(self)

        def start(self, hwnd):
            return True

        def stop(self):
            pass

        def set_status(self, s):
            self.status.append(s)

        def set_track(self, *a, **k):
            pass

        def clear_track(self):
            pass

    if win.media_controls is not None:
        win.media_controls.stop()
        win.media_controls = None
    monkeypatch.setattr(ui.sys, "platform", "linux")
    monkeypatch.setattr(ui, "LinuxMediaControls", FakeMPRIS)
    monkeypatch.setattr(ui, "previous_start_crashed", lambda: pytest.fail("Windows-only check ran"))
    win.settings["media_controls"] = True
    win._media_controls_note = ""
    win._start_media_controls()
    assert win.media_controls is made[0]
    assert "MPRIS" in win.media_controls_status_text()
    got = []
    monkeypatch.setattr(win, "next_track", lambda: got.append("next"))
    made[0].command.emit("next")
    assert got == ["next"]
    win.volume_slider.setValue(40)
    assert made[0].kw["volume_get"]() == 0.4
    made[0].kw["volume_set"](0.6)
    assert win.volume_slider.value() == 60
    win.media_controls = None


@pytest.mark.parametrize("environ, expected", [
    ({"WAYLAND_DISPLAY": "wayland-0", "QT_QPA_PLATFORM": "xcb"}, "x11egl"),       # GNOME Wayland
    ({"QT_QPA_PLATFORM": "xcb"}, None),                                          # Xorg: unchanged
    ({"WAYLAND_DISPLAY": "wayland-0", "QT_QPA_PLATFORM": "wayland"}, None),      # user chose Wayland Qt
    ({"WAYLAND_DISPLAY": "wayland-0", "QT_QPA_PLATFORM": "xcb", "ALMP_VO": "x11"}, None),
])
def test_video_stays_inside_almp_on_wayland(environ, expected):
    # Found on GNOME Wayland: mpv opened its own window and ALMP's video area stayed black.
    from almp import player
    o = player.mpv_options(1, platform="linux", environ=environ, proc_version="Linux 6.12 Debian")
    assert o.get("gpu_context") == expected
    assert "gpu_context" not in player.mpv_options(1, platform="win32", environ=environ)


def test_mpv_starts_without_an_unknown_gpu_context():
    from almp import player
    calls = []

    def factory(**opts):
        calls.append(dict(opts))
        if "gpu_context" in opts:
            raise ValueError("Invalid value for mpv option", -7, (None, b"gpu-context", b"x11egl,"))
        return "mpv"
    assert player.start_mpv(factory, {"wid": "1", "gpu_context": "x11egl,"}) == "mpv"
    assert calls == [{"wid": "1", "gpu_context": "x11egl,"}, {"wid": "1"}]

    def other_error(**opts):
        raise ValueError("Invalid value for mpv option", -7, (None, b"hwdec", b"x"))
    with pytest.raises(ValueError):
        player.start_mpv(other_error, {"wid": "1", "gpu_context": "x11egl,"})


def test_missing_x11_libraries_are_found_and_named(tmp_path):
    # Found on a fresh Ubuntu 26.04 (Wayland only): Qt's X11 backend could not load and ALMP stopped
    # with no message. ALMP now names the packages to install.
    from almp import app
    (tmp_path / "libxcb-cursor.so.0").write_bytes(b"")          # bundled next to ALMP
    system = {"libxcb-icccm.so.4", "libxcb-image.so.0", "libxcb-keysyms.so.1", "libxcb-render-util.so.0"}

    def loader(name):
        if name not in system:
            raise OSError(name + ": cannot open shared object file")
    missing = app.missing_x11_libraries([str(tmp_path)], loader)
    assert missing == ["libxkbcommon-x11.so.0", "libxcb-xkb.so.1"]
    msg = app.x11_missing_message(missing)
    assert "sudo apt install libxkbcommon-x11-0 libxcb-xkb1" in msg and "libxcb-xkb.so.1" in msg
    assert app.missing_x11_libraries([str(tmp_path)], lambda n: None) == []


# --- portable Linux build: libmpv bundled in mpv-libs ---

def test_bundled_libmpv_is_found_next_to_almp(tmp_path):
    from almp import player
    assert player.bundled_libmpv(tmp_path, "linux") is None             # not there: system libmpv
    lib = tmp_path / "mpv-libs" / "libmpv.so.2"
    lib.parent.mkdir()
    lib.write_bytes(b"")
    assert player.bundled_libmpv(tmp_path, "linux") == str(lib)
    assert player.bundled_libmpv(tmp_path, "win32") is None             # Windows keeps mpv-2.dll


def test_python_mpv_is_pointed_at_the_bundled_libmpv(tmp_path, monkeypatch):
    # python-mpv finds libmpv with ctypes.util.find_library("mpv"), which only knows installed
    # libraries; while it imports, it must get the bundled file, and afterwards nothing is changed.
    import ctypes.util

    from almp import player
    fake = tmp_path / "mpv.py"
    fake.write_text("import ctypes.util\nFOUND = ctypes.util.find_library('mpv')\n"
                    "OTHER = ctypes.util.find_library('c')\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, "mpv", raising=False)
    original = ctypes.util.find_library
    module = player._import_mpv("/opt/ALMP/mpv-libs/libmpv.so.2")
    assert module.FOUND == "/opt/ALMP/mpv-libs/libmpv.so.2"
    assert module.OTHER == original("c")
    assert ctypes.util.find_library is original
    monkeypatch.delitem(sys.modules, "mpv", raising=False)


def test_engine_message_for_the_portable_build():
    from almp.app import engine_missing_message
    msg = engine_missing_message(OSError("libavcodec.so.60: not found"), "linux", bundled=True)
    assert "mpv-libs" in msg and "WHOLE ALMP .tar.gz" in msg and "apt install" not in msg
    assert "libavcodec.so.60" in msg


@pytest.mark.parametrize("soname, system", [
    ("libc.so.6", True), ("ld-linux-x86-64.so.2", True), ("libGL.so.1", True), ("libEGL.so.1", True),
    ("libdrm.so.2", True), ("libdrm_amdgpu.so.1", True), ("libwayland-client.so.0", True),
    ("libX11.so.6", True), ("libxcb.so.1", True), ("libxcb-dri3.so.0", True), ("libasound.so.2", True),
    ("libpulse.so.0", True), ("libpipewire-0.3.so.0", True), ("libdbus-1.so.3", True),
    ("libfontconfig.so.1", True), ("libstdc++.so.6", True), ("libz.so.1", True),
    ("libmpv.so.2", False), ("libavcodec.so.60", False), ("libplacebo.so.338", False), ("libass.so.9", False),
    ("libva.so.2", False), ("libvulkan.so.1", False), ("libcaca.so.0", False), ("libxkbcommon.so.0", False),
    ("libxcb-cursor.so.0", False), ("libcap.so.2", True), ("libglib-2.0.so.0", True),
    ("libgio-2.0.so.0", True), ("libgdk_pixbuf-2.0.so.0", False),
    # found on Ubuntu 26.04 / Debian 13: these sonames are missing there, so they are bundled
    ("libxml2.so.2", False), ("libicuuc.so.74", False), ("libicudata.so.74", False),
])
def test_bundle_keeps_system_only_libraries_out(soname, system):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    try:
        import bundle_libs
    finally:
        sys.path.pop(0)
    assert bundle_libs.is_system_lib(soname) is system


def test_bundle_reads_ldd_output():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    try:
        import bundle_libs
    finally:
        sys.path.pop(0)
    text = ("\tlinux-vdso.so.1 (0x00007ffd)\n"
            "\tlibavcodec.so.60 => /lib/x86_64-linux-gnu/libavcodec.so.60 (0x00007f)\n"
            "\tlibjack.so.0 => not found\n"
            "\t/lib64/ld-linux-x86-64.so.2 (0x00007f)\n")
    assert bundle_libs.parse_ldd(text) == {"libavcodec.so.60": "/lib/x86_64-linux-gnu/libavcodec.so.60",
                                           "libjack.so.0": None}


# --- found on the real Mint PC (2026-11-24 night) ---

def test_mpv_does_not_take_the_mouse_on_linux():
    # mpv's own X11 window selected pointer events, so in fullscreen ALMP never saw the mouse move.
    from almp import player
    assert player.mpv_options(1, platform="linux", environ={}, proc_version="Linux")["input_cursor"] == "no"
    assert "input_cursor" not in player.mpv_options(1, platform="win32", environ={})    # Windows unchanged


@qt
def test_fullscreen_pointer_poll_brings_the_controls_back(win, monkeypatch):  # noqa: F811
    from almp import ui
    positions = iter([(10, 10), (10, 10), (50, 60)])

    class FakeCursor:
        @staticmethod
        def pos():
            return next(positions)
    monkeypatch.setattr(ui, "QCursor", FakeCursor)
    shown = []
    monkeypatch.setattr(win, "_on_fs_activity", lambda: shown.append(1))
    win._is_fullscreen = True
    win._fs_cursor_last = None
    win._poll_fs_cursor()               # first position: nothing to compare with
    win._poll_fs_cursor()               # did not move
    assert shown == []
    win._poll_fs_cursor()               # moved
    assert shown == [1]
    win._is_fullscreen = False
    win._poll_fs_cursor()
    assert not win._fs_cursor_timer.isActive() and win._fs_cursor_last is None


def test_display_title_drops_trailing_dots_and_spaces():
    from almp.media import display_title
    assert display_title("/m/Film.2010..mp4") == "Film.2010"
    assert display_title("/m/Song ｜ name.flac") == "Song ｜ name"
    assert display_title("/m/... .mp3") == "... " or display_title("/m/... .mp3")   # never empty
    assert display_title(r"C:\m\Film.mkv") in ("Film", r"C:\m\Film")      # Windows path on any system


def test_audio_artist_never_raises(tmp_path):
    from almp.media import audio_artist
    f = tmp_path / "not-audio.mp3"
    f.write_bytes(b"hello")
    assert audio_artist(str(f)) is None
    assert audio_artist(str(tmp_path / "missing.mp3")) is None


def test_mpris_metadata_artist_only_for_music_and_art_url():
    from almp import mpris
    m = mpris.metadata(1, "Song", artist="Pink Martini", art_url="file:///run/user/1000/c.png")
    assert m["xesam:artist"] == ["Pink Martini"] and m["mpris:artUrl"] == "file:///run/user/1000/c.png"
    v = mpris.metadata(2, "Film", video=True, artist="x", art_url="file:///opt/ALMP/icon.png")
    assert "xesam:artist" not in v and v["mpris:artUrl"].endswith("icon.png")
    mc = mpris.LinuxMediaControls()
    mc.set_track("Song", artist="A")
    first = mc.meta["mpris:trackid"]
    mc.set_track("Song", artist="A", art_url="file:///c.png")       # picture arrives later: same track
    assert mc.meta["mpris:trackid"] == first and mc.meta["mpris:artUrl"] == "file:///c.png"


@qt
def test_window_sends_artist_and_picture_on_linux(win, monkeypatch, tmp_path):  # noqa: F811
    from almp import ui
    got = []

    class FakeMPRIS(ui.LinuxMediaControls):
        def set_track(self, title, video=False, length_s=None, artist=None, art_url=None, album=None):
            got.append((title, video, artist, art_url, album))
    mc = FakeMPRIS()
    win.media_controls = mc
    tags = {"artist": "Pink Martini", "album": "Sympathique"}
    monkeypatch.setattr(ui, "audio_tags", lambda p: dict(tags))
    playing = [str(tmp_path / "Film.2010..mp4")]
    monkeypatch.setattr(type(win), "current_path", property(lambda self: playing[0]))
    assert win.player
    win._update_media_controls()
    assert got[-1][0] == "Film.2010" and got[-1][1] is True and got[-1][2] is None
    assert got[-1][3] is None or got[-1][3].startswith("file://")              # ALMP's icon
    playing[0] = str(tmp_path / "01 - Sympathique.mp3")
    win._update_media_controls()
    assert got[-1][:3] == ("01 - Sympathique", False, "Pink Martini") and got[-1][4] == "Sympathique"
    tags["title"] = "Hang on Little Tomato"           # the song's own title tag wins over the file name
    playing[0] = str(tmp_path / "03 - Hang on Little Tomato.mp3")
    win._update_media_controls()
    assert got[-1][0] == "Hang on Little Tomato"
    win.media_controls = None


# --- dark window frames on X11 ---

class _FakeDisplay:
    def __init__(self):
        self.calls = []

    def set_dark(self, wid):
        self.calls.append(wid)


@qt
def test_dark_frame_is_asked_for_each_top_level_window_once(qapp):  # noqa: F811
    from PyQt6.QtWidgets import QDialog, QMenu

    from almp import x11_theme
    d = _FakeDisplay()
    flt = x11_theme.DarkTitleBars(d)
    qapp.installEventFilter(flt)
    try:
        dlg = QDialog()
        dlg.show()
        qapp.processEvents()
        dlg.hide()
        dlg.show()                       # shown again: asked only once
        qapp.processEvents()
        assert d.calls == [int(dlg.winId())]
        menu = QMenu()
        menu.addAction("x")
        menu.popup(dlg.pos())            # pop-up menus are not windows with a frame
        qapp.processEvents()
        menu.close()
        assert d.calls == [int(dlg.winId())]
        dlg.close()
    finally:
        qapp.removeEventFilter(flt)


@qt
def test_dark_frames_only_on_x11(qapp):  # noqa: F811
    from almp import x11_theme
    if qapp.platformName() != "xcb":
        assert x11_theme.install(qapp, display_factory=_FakeDisplay) is None


def test_x11_property_call():
    from almp import x11_theme
    calls = []

    class Lib:
        def XOpenDisplay(self, name):
            return 1234

        def XInternAtom(self, display, name, only_if_exists):
            return {b"_GTK_THEME_VARIANT": 300, b"UTF8_STRING": 301}[name]

        def XChangeProperty(self, *args):
            calls.append(args)

        def XFlush(self, display):
            calls.append(("flush", display))
    x = x11_theme.X11Display(Lib())
    x.set_dark(0x4c00002)
    assert calls[0] == (1234, 0x4c00002, 300, 301, 8, 0, b"dark", 4) and calls[1] == ("flush", 1234)


@qt
def test_seek_bar_release_is_exact_and_drag_uses_the_dragged_value(win, monkeypatch):  # noqa: F811
    # python-mpv's seek() defaults to keyframes: a click or drag on the seek bar landed on the keyframe
    # before the spot (15.75 s instead of 23 s). Dragging may stay fast; letting go must be exact.
    seeks = []
    monkeypatch.setattr(type(win), "current_path", property(lambda self: "/m/film.mp4"))
    monkeypatch.setattr(win.player, "seek", lambda *a, **k: seeks.append((a, k)), raising=False)
    monkeypatch.setattr(win.player, "idle_active", False, raising=False)
    win.progress_slider.setMaximum(30)
    win.progress_slider.setValue(9)
    win._start_scrubbing()
    win.progress_slider.sliderMoved.emit(21)            # the drag reports 21 before the value changes
    win.progress_slider.setValue(23)
    win._stop_scrubbing()
    assert seeks[0] == ((21,), {"reference": "absolute", "precision": "keyframes"})
    assert seeks[-1] == ((23,), {"reference": "absolute", "precision": "exact"})
    assert not win._is_scrubbing


@qt
@pytest.mark.parametrize("style", ["fusion", "windows"])
def test_seek_bar_press_beside_the_snapped_handle_still_drags(qapp, style):  # noqa: F811
    # Whole-second values: on a 30 s track the handle snaps up to ~20 px away from the click. A press
    # near the start (x=19) left the handle beside the pointer, so no drag began and nothing was seeked.
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtWidgets import QApplication, QStyleFactory

    from almp.widgets import ClickSeekSlider
    s = ClickSeekSlider(Qt.Orientation.Horizontal)
    st = QStyleFactory.create(style)
    if st is None:
        pytest.skip(f"Qt style {style} not available here")
    s.setStyle(st)
    s.setRange(0, 30)
    s.setValue(1)
    s.resize(1253, 24)
    s.show()
    qapp.processEvents()
    log = []
    s.sliderPressed.connect(lambda: log.append("pressed"))
    s.sliderReleased.connect(lambda: log.append(("released", s.value())))

    def send(kind, x, buttons):
        btn = Qt.MouseButton.NoButton if kind == QMouseEvent.Type.MouseMove else Qt.MouseButton.LeftButton
        QApplication.sendEvent(s, QMouseEvent(kind, QPointF(x, 12), s.mapToGlobal(QPointF(x, 12)), btn, buttons,
                                              Qt.KeyboardModifier.NoModifier))
        qapp.processEvents()
    held = Qt.MouseButton.LeftButton
    for start in (19, 40, 620, 1230):                 # near the start, between seconds, middle, near the end
        log.clear()
        send(QMouseEvent.Type.MouseButtonPress, start, held)
        assert s.isSliderDown(), (style, start)
        send(QMouseEvent.Type.MouseMove, 940, held)
        send(QMouseEvent.Type.MouseButtonRelease, 940, Qt.MouseButton.NoButton)
        assert log[0] == "pressed" and log[-1][0] == "released", (style, start, log)
        assert 21 <= log[-1][1] <= 24, (style, start, log)
    s.close()


def test_mpris_album_and_tags():
    from almp import mpris
    from almp.media import audio_tags
    m = mpris.metadata(1, "Hang on Little Tomato", artist="Pink Martini", album="Hang on Little Tomato")
    assert m["xesam:album"] == "Hang on Little Tomato"
    assert "xesam:album" not in mpris.metadata(1, "Film", video=True, album="x")
    assert audio_tags("/nowhere/missing.mp3") == {}


def _gdbus(qapp, *args, seconds=3.0, until=None):  # noqa: F811
    """Run gdbus without blocking this process (it answers the D-Bus calls itself)."""
    from PyQt6.QtCore import QProcess
    proc = QProcess()
    proc.start("gdbus", list(args))
    deadline = time.monotonic() + seconds
    out = b""
    while time.monotonic() < deadline:
        qapp.processEvents()
        proc.waitForReadyRead(20)
        out += bytes(proc.readAllStandardOutput())
        if until is not None and until(out.decode("utf-8", "replace")):
            break
        if proc.state() == QProcess.ProcessState.NotRunning:
            break
    proc.kill()
    proc.waitForFinished(1000)
    return (out + bytes(proc.readAllStandardOutput())).decode("utf-8", "replace")


@qt
def test_mpris_artist_is_a_string_array_on_the_wire(qapp):  # noqa: F811
    # Found on the Mint PC: the artist went out as an array of VARIANTS ('av'); Cinnamon's applet showed
    # "Unknown Artist". It must be a string array ('as'), in Get and in the PropertiesChanged signal.
    import shutil
    if _session_bus() is None or not shutil.which("gdbus"):
        pytest.skip("needs Linux with a D-Bus session bus and gdbus")
    from almp import mpris
    mc = mpris.LinuxMediaControls()
    assert mc.start() is True
    try:
        mc.set_track("Song", artist="Pink Martini", album="Sympathique", art_url="file:///x.png", length_s=2.5)
        got = _gdbus(qapp, "call", "--session", "-d", mc.bus_name, "-o", mpris.OBJECT_PATH, "-m",
                     "org.freedesktop.DBus.Properties.Get", mpris.PLAYER_IFACE, "Metadata")
        assert "'xesam:artist': <['Pink Martini']>" in got, got
        assert "'xesam:album': <'Sympathique'>" in got, got
        assert "'mpris:length': <int64 2500000>" in got, got
        from PyQt6.QtCore import QProcess
        mon = QProcess()
        mon.start("gdbus", ["monitor", "--session", "-d", mc.bus_name])
        mon.waitForStarted(2000)
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            qapp.processEvents()
            time.sleep(0.02)
        mc.set_track("Next song", artist="China Forbes")
        out = b""
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and b"China Forbes" not in out:
            qapp.processEvents()
            mon.waitForReadyRead(50)
            out += bytes(mon.readAllStandardOutput())
        mon.kill()
        mon.waitForFinished(1000)
        text = out.decode("utf-8", "replace")
        assert "PropertiesChanged" in text and "'xesam:artist': <['China Forbes']>" in text, text
    finally:
        mc.stop()


@qt
def test_exclusive_output_choice_and_busy_fallback(win, monkeypatch):  # noqa: F811
    from almp import dialogs, ui
    monkeypatch.setattr(ui.sys, "platform", "linux")
    monkeypatch.setattr(dialogs, "IS_LINUX", True)
    monkeypatch.setattr(win, "can_register_with_desktop", lambda: False)
    monkeypatch.setattr(win, "desktop_entry_installed", lambda: False)
    props, commands = {}, []
    monkeypatch.setattr(ui, "set_prop", lambda player, k, v: props.__setitem__(k, v) or True)
    monkeypatch.setattr(win.player, "command", lambda *a: commands.append(a), raising=False)
    monkeypatch.setattr(win.player, "audio_device_list",
                        [{"name": "pipewire"}, {"name": "alsa/hdmi:CARD=PCH,DEV=0", "description": "TV (HDMI)"}],
                        raising=False)
    monkeypatch.setattr(ui.QTimer, "singleShot", lambda *a: None)
    win.settings["audio_exclusive"] = False
    d = dialogs.SettingsDialog(win)
    assert d.exclusive_output.count() == 2 and not d.exclusive_output.isEnabled()
    d.exclusive.setChecked(True)                                  # on: PipeWire exclusive first
    assert props["audio-exclusive"] == "yes" and props["audio-device"] == "auto" and ("ao-reload",) in commands
    d.exclusive_output.setCurrentIndex(1)                         # the TV, directly
    assert win.settings["audio_exclusive_device"] == "alsa/hdmi:CARD=PCH,DEV=0"
    assert props["audio-device"] == "alsa/hdmi:CARD=PCH,DEV=0" and props["audio-exclusive"] == "no"
    # the device is busy: mpv logs "Could not open/initialize audio device -> no sound." (from its own
    # thread) -> PipeWire, exclusive, and the same track plays again instead of being skipped
    said, played = [], []
    monkeypatch.setattr(win, "_status", lambda text, announce=False: said.append(text))
    monkeypatch.setattr(type(win), "current_path", property(lambda self: "/m/song.flac"))
    monkeypatch.setattr(type(win), "current_index", property(lambda self: 0), raising=False)
    monkeypatch.setattr(win, "store", ["/m/song.flac"])
    monkeypatch.setattr(win, "play_index", lambda i, *a, **k: played.append(i))
    win._mpv_log("error", "cplayer", "Could not open/initialize audio device -> no sound.")
    win._mpv_log("error", "ao/alsa", "Playback open error: Device or resource busy")   # not acted on
    qapp_ = __import__("PyQt6.QtWidgets", fromlist=["QApplication"]).QApplication.instance()
    qapp_.processEvents()
    assert props["audio-device"] == "auto" and props["audio-exclusive"] == "yes" and props["aid"] == "auto"
    assert "busy" in said[-1] and win._exclusive_fallback
    win._handle_end_file("EOF")                                   # the music file ended without sound
    assert played == [0]
    win._mpv_log("error", "cplayer", "Could not open/initialize audio device -> no sound.")
    qapp_.processEvents()
    assert len(said) == 1                                         # only once
    d.close()
    win.settings["audio_exclusive"] = False


def test_menu_entry_covers_the_types_linux_gives_almps_files():
    # Checked on Linux Mint 22.3 (shared-mime-info): these are the types its files get. Before,
    # .avi (video/vnd.avi), .m4b audiobooks, DSD and others were missing, so they would not open in ALMP.
    needed = {"video/vnd.avi", "video/x-matroska", "video/mp4", "video/webm", "video/quicktime", "video/mp2t",
              "video/x-ms-wmv", "video/mpeg", "video/3gpp", "video/3gpp2", "video/x-flv", "video/ogg",
              "audio/mpeg", "audio/flac", "audio/x-m4b", "audio/x-dsf", "audio/x-dff", "audio/ac3",
              "audio/x-wav", "audio/ogg", "audio/x-opus+ogg", "audio/mp4", "audio/x-ape", "audio/x-wavpack",
              "audio/AMR", "audio/x-musepack", "application/vnd.rn-realmedia", "application/vnd.ms-asf"}
    assert needed <= set(pl.MIME_TYPES)
    assert len(pl.MIME_TYPES) == len(set(pl.MIME_TYPES))          # no doubles
    assert "MimeType=" + ";".join(pl.MIME_TYPES) + ";" in pl.desktop_entry_text("/opt/ALMP/ALMP")
