"""The real window with real Qt (offscreen) and a stand-in for mpv.

Skipped when PyQt6 is not installed (the plain-logic tests still run). In CI PyQt6 is installed,
so these run there. Nothing here plays sound or opens a visible window."""
import os
import time
import types
from pathlib import Path

import pytest

from conftest import HAVE_QT

pytestmark = pytest.mark.skipif(not HAVE_QT, reason="PyQt6 is not installed")


class FakeMPV:
    """Just enough of python-mpv's MPV for the window: properties, loadfile, events."""

    def __init__(self, **opts):
        self.opts = opts
        self.volume = 100
        self.pause = False
        self.idle_active = True
        self.time_pos = None
        self.duration = None
        self.speed = 1.0
        self.track_list = []
        self.loaded = []
        self.props = {}
        self.commands = []
        self._callbacks = {}

    def event_callback(self, name):
        def deco(fn):
            self._callbacks[name] = fn
            return fn
        return deco

    def loadfile(self, path, mode="replace", **options):
        self.loaded.append((path, options))
        self.idle_active = False
        self.time_pos = 0
        self.duration = 200

    def stop(self):
        self.idle_active = True

    def terminate(self):
        self.idle_active = True

    def seek(self, *a, **k):
        if self.idle_active:
            raise RuntimeError("not loaded")

    def command(self, *args):
        self.commands.append(args)

    def command_async(self, *args):
        if args[:2] == ("set", "pause"):
            self.pause = args[2] == "yes"

    def __setitem__(self, k, v):
        self.props[k] = v

    def __getitem__(self, k):
        return self.props.get(k, "")

    def sub_add(self, f):
        pass

    def screenshot_to_file(self, p):
        pass


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(["almp-test"])
    from almp.theme import stylesheet
    app.setStyleSheet(stylesheet(False))
    return app


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    from almp import settings, smtc, ui
    monkeypatch.setattr(settings, "SETTINGS_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(ui, "load_positions", lambda folder=None: {})
    monkeypatch.setattr(ui, "forget_positions", lambda folder=None: False)
    monkeypatch.setattr(ui, "save_positions", lambda table, folder=None: True)
    monkeypatch.setattr(ui, "mpv", types.SimpleNamespace(MPV=FakeMPV))
    monkeypatch.setattr(smtc, "get_log_dir", lambda: tmp_path)
    w = ui.MediaWindow()
    w.resize(1100, 650)
    w.show()
    qapp.processEvents()
    yield w
    w.close()
    qapp.processEvents()


def pump(qapp, until, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        qapp.processEvents()
        if until():
            return True
        time.sleep(0.005)
    return False


def make_library(root, n_folders=3, per_folder=40):
    for a in range(n_folders):
        d = root / f"Album {a + 1}"
        d.mkdir(parents=True)
        for t in range(per_folder):
            (d / f"Track {t + 1} - Song.mp3").write_bytes(b"")
    return root


def test_window_builds_with_safe_defaults(window):
    assert window.player is not None and isinstance(window.player, FakeMPV)
    assert window.player.opts["ytdl"] == "no" and window.player.opts["config"] == "no"
    assert window.remove_played_checkbox.isChecked() is False       # new default
    assert window._loop_mode == "off"
    assert window.welcome_widget.isVisible()
    from almp import __version__
    assert __version__ in window.windowTitle()


def test_streaming_scan_plays_first_file_and_counts(window, qapp, tmp_path):
    lib = make_library(tmp_path / "lib")
    window.scan_targets([str(lib)])
    assert pump(qapp, lambda: window.player.loaded, timeout=10)
    first = window.player.loaded[0][0]
    assert first.endswith(os.path.join("Album 1", "Track 1 - Song.mp3"))
    assert pump(qapp, lambda: not window._scan_active and not window._pending and len(window.store) == 120)
    assert window.playlist_count_label.text() == "120 items"
    assert window.model.rowCount() == 120
    # natural order: Track 2 before Track 10
    names = [os.path.basename(p) for p in window.store.paths[:12]]
    assert names.index("Track 2 - Song.mp3") < names.index("Track 10 - Song.mp3")


def test_dropping_the_same_folder_twice_adds_nothing(window, qapp, tmp_path):
    lib = make_library(tmp_path / "lib", 1, 10)
    window.scan_targets([str(lib)])
    assert pump(qapp, lambda: not window._scan_active and len(window.store) == 10)
    window.scan_targets([str(lib)])
    assert pump(qapp, lambda: not window._scan_active and not window._pending)
    assert len(window.store) == 10


def test_search_filter_count_and_enter(window, qapp, tmp_path):
    lib = make_library(tmp_path / "lib", 2, 30)
    window.scan_targets([str(lib)])
    assert pump(qapp, lambda: not window._scan_active and len(window.store) == 60)
    window.search_edit.setText("track 7")             # every word must match (name or folder)
    window._apply_filter()
    shown = window.model.rowCount()
    assert 0 < shown < 60
    assert window.playlist_count_label.text() == f"{shown} of 60"
    assert all("7" in os.path.basename(window.model.path_at_view(r)) for r in range(shown))
    first = window.model.path_at_view(0)
    window._play_first_visible()
    assert window.player.loaded[-1][0] == first
    # choosing a track from the search results empties the search box and shows the whole list again
    assert window.search_edit.text() == ""
    assert window.model.rowCount() == 60
    window.search_edit.clear()
    window._apply_filter()
    assert window.model.rowCount() == 60


def test_play_next_queue_wins_over_order(window, qapp, tmp_path):
    lib = make_library(tmp_path / "lib", 1, 10)
    window.shuffle_checkbox.setChecked(False)
    window.scan_targets([str(lib)])
    assert pump(qapp, lambda: not window._scan_active and len(window.store) == 10)
    target = window.store.paths[7]
    window.queue_next(target)
    assert window.model.data(window.model.index(7)).startswith("[next]")
    window._handle_end_file("EOF")
    assert window.player.loaded[-1][0] == target
    assert window.queue == []


def test_remove_move_and_delete_key_paths(window, qapp, tmp_path):
    lib = make_library(tmp_path / "lib", 1, 5)
    window.shuffle_checkbox.setChecked(False)
    window.scan_targets([str(lib)])
    assert pump(qapp, lambda: not window._scan_active and len(window.store) == 5)
    playing = window.current_path
    window.playlist.setCurrentIndex(window.model.index(3))
    window._move_selected(-1)
    assert window.playlist.currentIndex().row() == 2
    assert window.current_path == playing                  # moving does not change what plays
    window.playlist.setCurrentIndex(window.model.index(0))
    window.remove_from_playlist()                           # removes the playing track
    assert len(window.store) == 4
    assert window.current_path is not None and window.current_path != playing


def test_model_drag_move_and_rows(window, qapp):
    from almp.store import make_entry
    m = window.model
    m.append_entries([make_entry(f"/m/{i}.mp3") for i in range(5)])
    assert m.moveRows(m.index(0).parent(), 0, 1, m.index(0).parent(), 3)     # Qt's "insert before 3"
    assert [os.path.basename(p) for p in window.store.paths] == ["1.mp3", "2.mp3", "0.mp3", "3.mp3", "4.mp3"]
    md = m.mimeData([m.index(4)])
    assert m.dropMimeData(md, None, 0, 0, m.index(0).parent()) is False        # moved, nothing to delete
    assert window.store.paths[0].endswith("4.mp3")
    m.set_filter("3.")
    assert m.rowCount() == 1 and not m.canDropMimeData(md, None, 0, 0, m.index(0).parent())
    m.remove_source(window.store.index_of("/m/3.mp3"))
    assert m.rowCount() == 0
    m.set_filter("")
    assert m.rowCount() == 4


def test_sort_by_name_runs_in_background(window, qapp):
    from almp.store import make_entry
    window.model.append_entries([make_entry(p) for p in ("/m/b 10.mp3", "/m/a.mp3", "/m/b 2.mp3")])
    window.sort_playlist("name")
    assert pump(qapp, lambda: not window._sort_busy)
    assert [os.path.basename(p) for p in window.store.paths] == ["a.mp3", "b 2.mp3", "b 10.mp3"]


def test_high_contrast_applies_live(window, qapp):
    window.set_high_contrast(True)
    assert "#ffff00" in qapp.styleSheet()
    assert window.welcome_widget.high_contrast is True
    assert window.model._accent.name() == "#ffff00"
    window.set_high_contrast(False)
    assert "#ffff00" not in qapp.styleSheet()


def test_track_menus_use_real_check_marks(window, qapp):
    from PyQt6.QtWidgets import QMenu
    window.player.track_list = [
        {"type": "audio", "id": 1, "selected": True, "title": "Main", "lang": "eng"},
        {"type": "audio", "id": 2, "selected": False, "lang": "fra"},
        {"type": "sub", "id": 3, "selected": False, "lang": "eng"},
    ]
    menu = QMenu()
    window._fill_tracks_menu(menu)
    subs = {a.text(): a.menu() for a in menu.actions() if a.menu()}
    audio = {a.text(): a.isChecked() for a in subs["Audio tracks"].actions()}
    assert audio == {"Main (eng)": True, "fra": False}
    subtitle = {a.text(): a.isChecked() for a in subs["Subtitles"].actions() if a.isCheckable()}
    assert subtitle == {"Off": True, "eng": False}
    sub_eng = next(a for a in subs["Subtitles"].actions() if a.text() == "eng")
    sub_eng.trigger()
    assert window.player.sid == 3


def test_every_button_has_an_accessible_name(window):
    from PyQt6.QtWidgets import QAbstractButton, QComboBox, QLineEdit, QSlider
    missing = []
    for kind in (QAbstractButton, QComboBox, QSlider, QLineEdit):
        for w in window.findChildren(kind):
            if isinstance(w.parent(), QLineEdit) or not w.isVisibleTo(window):
                continue                     # Qt's own helper buttons (search clear, table corner)
            name = w.accessibleName() or (w.text() if isinstance(w, QAbstractButton) else "")
            if not name:
                missing.append(w.objectName() or type(w).__name__)
    assert missing == []


def test_control_bar_switches_to_two_rows_when_narrow(window, qapp):
    window.resize(1700, 700)
    window.splitter.setSizes([1400, 300])
    pump(qapp, lambda: window._bar_mode == "wide", timeout=2)
    assert window._bar_mode == "wide"
    window.splitter.setSizes([420, 250])
    window.resize(680, 380)
    assert pump(qapp, lambda: window._bar_mode == "narrow", timeout=3)
    assert window.tools_row.isVisible()
    assert window.play_button.text() == ""
    assert window.play_button.accessibleName() in ("Play", "Pause")


def test_space_on_focused_button_presses_the_button_not_play(window, qapp):
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    pressed = []
    window.clear_playlist_button.clicked.connect(lambda: pressed.append(1))
    window.clear_playlist_button.setFocus()
    calls = []
    window.play_or_resume = lambda: calls.append(1)
    QTest.keyClick(window.clear_playlist_button, Qt.Key.Key_Space)
    qapp.processEvents()
    assert pressed == [1] and calls == []


def test_dialogs_open_and_close(window, qapp):
    from almp.dialogs import AboutDialog, HelpDialog, SettingsDialog
    for dlg in (SettingsDialog(window), HelpDialog(window), AboutDialog(window, "mpv test")):
        dlg.show()
        qapp.processEvents()
        dlg.close()


def test_sleep_end_of_track_stops_after_the_track(window, qapp, tmp_path):
    lib = make_library(tmp_path / "lib", 1, 3)
    window.scan_targets([str(lib)])
    assert pump(qapp, lambda: not window._scan_active and len(window.store) == 3)
    n = len(window.player.loaded)
    window.set_sleep_end_of_track()
    window._handle_end_file("EOF")
    assert len(window.player.loaded) == n               # nothing new started
    assert window._stopped_by_sleep


def test_loop_is_never_saved(window, qapp, tmp_path):
    import json

    from almp import settings
    window.cycle_loop_mode()
    window.cycle_loop_mode()
    window.close()
    saved = json.loads(settings.SETTINGS_PATH.read_text(encoding="utf-8"))
    assert not any("loop" in k for k in saved)


def test_start_screen_gets_bigger_in_fullscreen_only(window, qapp):
    w = window.welcome_widget
    base = w.btn_files.minimumHeight()
    window._is_fullscreen = True
    window.settings["large_buttons"] = "always"
    window._apply_tv_mode()
    assert w.btn_files.minimumHeight() > base
    assert "font-size" in w.btn_files.styleSheet()
    window.set_large_buttons("never")
    assert w.btn_files.minimumHeight() == base
    assert w.btn_files.styleSheet() == ""
    window._is_fullscreen = False
    window.set_large_buttons("auto")
    assert w.btn_files.minimumHeight() == base


# --- fullscreen (see tests/test_fullscreen.py and almp/titlefonts.py) ---
def test_fullscreen_bar_has_room_for_three_buttons_in_every_layout(qapp, window):
    window._toggle_fullscreen()
    try:
        for mode in ("wide", "compact", "narrow"):
            window._apply_bar_mode(mode)
            assert window.right_box.maximumWidth() >= 3 * 44 + 16, mode
            for b in (window.playlist_toggle_button, window.fullscreen_button, window.fs_close_button):
                assert not b.isHidden(), (mode, b.accessibleName())
    finally:
        window._toggle_fullscreen()
    window._apply_bar_mode("compact")
    assert window.right_box.maximumWidth() == 130          # windowed: one button, unchanged


def test_always_play_videos_in_fullscreen(qapp, window, tmp_path):
    video, song = tmp_path / "clip.mp4", tmp_path / "song.mp3"
    video.write_bytes(b"")
    song.write_bytes(b"")
    window.settings["play_fullscreen"] = True
    window.open_external([str(song)], wait_ms=0)
    assert pump(qapp, lambda: window.player.loaded)
    assert not window._is_fullscreen                        # music is not affected
    window._last_ext_time = 0.0                             # a new double-click, not part of a burst
    window.open_external([str(video)], wait_ms=0)
    assert pump(qapp, lambda: len(window.player.loaded) >= 2)
    assert window._is_fullscreen
    window._toggle_fullscreen()


def test_videos_stay_windowed_when_the_setting_is_off(qapp, window, tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"")
    assert window.settings["play_fullscreen"] is False
    window.open_external([str(video)], wait_ms=0)
    assert pump(qapp, lambda: window.player.loaded)
    assert not window._is_fullscreen


# --- playlist panel when ALMP is opened with one file ---
def test_one_file_opens_without_the_playlist_panel_and_it_returns_at_two(qapp, window, tmp_path):
    a, b = tmp_path / "a.mp4", tmp_path / "b.mp4"
    a.write_bytes(b"")
    b.write_bytes(b"")
    window.set_playlist_panel(False, auto=True)            # what app.py does for one double-clicked file
    window.open_external([str(a)], wait_ms=0)
    assert pump(qapp, lambda: window.player.loaded)
    assert window.right_panel.isHidden()
    assert window.playlist_toggle_button.isVisible()        # the way back to the list
    window.open_external([str(b)], wait_ms=0)               # a second file arrives
    assert pump(qapp, lambda: len(window.store) == 2)
    assert not window.right_panel.isHidden()


def test_playlist_panel_can_be_toggled_in_a_normal_window(qapp, window):
    assert not window.right_panel.isHidden()
    window._toggle_fs_playlist()
    assert window.right_panel.isHidden()
    window._toggle_fs_playlist()
    assert not window.right_panel.isHidden()


def test_panel_hidden_by_hand_stays_hidden_when_files_are_added(qapp, window, tmp_path):
    window.set_playlist_panel(False)                        # the user's own choice, not automatic
    for n in ("a.mp4", "b.mp4"):
        (tmp_path / n).write_bytes(b"")
    window.open_external([str(tmp_path / "a.mp4"), str(tmp_path / "b.mp4")], wait_ms=0)
    assert pump(qapp, lambda: len(window.store) == 2)
    assert window.right_panel.isHidden()


def test_leaving_fullscreen_keeps_the_panel_choice(qapp, window):
    window.set_playlist_panel(False)
    window._toggle_fullscreen()
    window._toggle_fullscreen()
    assert window.right_panel.isHidden()
    window.set_playlist_panel(True)
    window._toggle_fullscreen()
    window._toggle_fullscreen()
    assert not window.right_panel.isHidden()


# --- "Add to ALMP playlist" from the right-click menu ---
def test_add_to_playlist_does_not_interrupt_the_current_track(qapp, window, tmp_path):
    first, more = tmp_path / "first.mp3", tmp_path / "more.mp3"
    first.write_bytes(b"")
    more.write_bytes(b"")
    window.open_external([str(first)], wait_ms=0)
    assert pump(qapp, lambda: window.player.loaded)
    window._last_ext_time = 0.0                              # a new right-click, not part of a burst
    window.open_external(["--add", str(more)], wait_ms=0)
    assert pump(qapp, lambda: len(window.store) == 2)
    assert len(window.player.loaded) == 1                    # still playing the first file
    assert window.current_path == str(first)


def test_add_to_playlist_plays_when_nothing_is_playing(qapp, window, tmp_path):
    song = tmp_path / "song.mp3"
    song.write_bytes(b"")
    window.open_external(["--add", str(song)], wait_ms=0)
    assert pump(qapp, lambda: window.player.loaded)

def _select_rows(window, rows):
    from PyQt6.QtCore import QItemSelectionModel
    sm = window.playlist.selectionModel()
    sm.clearSelection()
    flag = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
    for r in rows:
        sm.select(window.model.index(r), flag)


def test_playlist_allows_selecting_several(window):
    from PyQt6.QtWidgets import QAbstractItemView
    assert window.playlist.selectionMode() == QAbstractItemView.SelectionMode.ExtendedSelection


def test_model_remove_sources_with_search_and_playing_track(window, qapp):
    from almp.store import make_entry
    m = window.model
    m.append_entries([make_entry(f"/m/{i} song.mp3") for i in range(8)])
    m.set_current(6)
    m.set_filter("song")
    assert m.remove_sources([1, 4, 2]) == ["/m/1 song.mp3", "/m/2 song.mp3", "/m/4 song.mp3"]
    assert m.current == 3                                        # "6" moved up by three
    assert [m.path_at_view(r) for r in range(m.rowCount())] == [
        "/m/0 song.mp3", "/m/3 song.mp3", "/m/5 song.mp3", "/m/6 song.mp3", "/m/7 song.mp3"]
    assert m.remove_sources([3, 0]) and m.current == -1          # the playing one went
    m.set_filter("")
    assert m.rowCount() == 3


def test_remove_several_selected_items(window, qapp, tmp_path):
    lib = make_library(tmp_path / "lib", 1, 6)
    window.shuffle_checkbox.setChecked(False)
    window.scan_targets([str(lib)])
    assert pump(qapp, lambda: not window._scan_active and len(window.store) == 6)
    playing = window.current_path
    names = list(window.store.paths)
    _select_rows(window, [1, 3, 4])
    assert window._selected_source_rows() == [1, 3, 4]
    window.remove_from_playlist()
    assert window.store.paths == [names[0], names[2], names[5]]
    assert window.current_path == playing                        # untouched: it was not selected
    assert window._selected_source_rows() == [1]                 # selection moves to the next item
    # the playing track among the selected: the next remaining track plays
    window.queue[:] = [names[5]]
    _select_rows(window, [0, 2])
    window.remove_from_playlist()
    assert window.store.paths == [names[2]]
    assert window.queue == []
    assert window.current_path == names[2]


def test_delete_several_selected_files(window, qapp, tmp_path, monkeypatch):
    from almp import platform_win as pw
    from almp import ui
    lib = make_library(tmp_path / "lib", 1, 5)
    window.shuffle_checkbox.setChecked(False)
    window.scan_targets([str(lib)])
    assert pump(qapp, lambda: not window._scan_active and len(window.store) == 5)
    names = list(window.store.paths)
    asked = []

    class Yes:
        def __init__(self, parent, title, message, yes_text=""):
            asked.append((title, message, yes_text))

        def setModal(self, _):
            pass

        def exec(self):
            return ui.QDialog.DialogCode.Accepted

        def deleteLater(self):
            pass

    sent = []

    def fake_bin(path, permanent=False, hwnd=0):
        sent.append((path, permanent))
        return pw.DELETE_FAILED if path == names[3] else pw.DELETE_OK

    monkeypatch.setattr(ui, "CustomConfirmDialog", Yes)
    monkeypatch.setattr(pw, "recycle_bin_available", lambda p: True)
    monkeypatch.setattr(pw, "send_to_recycle_bin", fake_bin)
    errors = []
    monkeypatch.setattr(ui.QMessageBox, "critical", lambda *a, **k: errors.append(a))
    _select_rows(window, [0, 2, 3])                              # 0 is playing; 3 will fail
    window.delete_selected_file()
    assert len(asked) == 1 and asked[0][0] == "Delete 3 Files" and ui.BIN in asked[0][1]
    assert [p for p, _ in sent] == [names[0], names[2], names[3]]
    assert not any(perm for _, perm in sent)                     # all to the Recycle Bin
    assert window.store.paths == [names[1], names[3], names[4]]  # the failed one stays
    assert len(errors) == 1
    assert window.current_path == names[1]                       # playback went on with the next


def test_delete_several_warns_when_no_recycle_bin(window, qapp, tmp_path, monkeypatch):
    from almp import platform_win as pw
    from almp import ui
    lib = make_library(tmp_path / "lib", 1, 4)
    window.scan_targets([str(lib)])
    assert pump(qapp, lambda: not window._scan_active and len(window.store) == 4)
    asked = []

    class No:
        def __init__(self, parent, title, message, yes_text=""):
            asked.append((title, message, yes_text))

        def setModal(self, _):
            pass

        def exec(self):
            return ui.QDialog.DialogCode.Rejected

        def deleteLater(self):
            pass

    sent = []
    monkeypatch.setattr(ui, "CustomConfirmDialog", No)
    monkeypatch.setattr(pw, "recycle_bin_available", lambda p: False)
    monkeypatch.setattr(pw, "send_to_recycle_bin", lambda *a, **k: sent.append(a))
    _select_rows(window, [1, 2])
    window.delete_selected_file()
    assert asked[0][0] == "Delete 2 Files Permanently?" and "PERMANENTLY" in asked[0][1]
    assert sent == [] and len(window.store) == 4                 # "No" deletes nothing


def test_ctrl_and_shift_click_select_several(window, qapp):
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest

    from almp.store import make_entry
    window.model.append_entries([make_entry(f"/m/{i}.mp3") for i in range(6)])
    qapp.processEvents()
    v = window.playlist

    def click(row, mods=Qt.KeyboardModifier.NoModifier):
        QTest.mouseClick(v.viewport(), Qt.MouseButton.LeftButton, mods, v.visualRect(window.model.index(row)).center())

    click(1)
    assert window._selected_source_rows() == [1]
    click(3, Qt.KeyboardModifier.ControlModifier)
    assert window._selected_source_rows() == [1, 3]
    click(5, Qt.KeyboardModifier.ShiftModifier)
    assert window._selected_source_rows() == [1, 3, 4, 5]
    click(2)                                                     # a plain click: just that one again
    assert window._selected_source_rows() == [2]


def test_find_user_shaders(tmp_path):
    from almp.player import MAX_USER_SHADERS, find_user_shaders
    assert find_user_shaders(tmp_path / "missing") == []
    (tmp_path / "b_FSRCNNX.glsl").write_text("x")
    (tmp_path / "A_anime4k.GLSL").write_text("x")
    (tmp_path / "c.hook").write_text("x")
    (tmp_path / "readme.txt").write_text("x")
    (tmp_path / "sub.glsl").mkdir()
    assert [Path(p).name for p in find_user_shaders(tmp_path)] == ["A_anime4k.GLSL", "b_FSRCNNX.glsl", "c.hook"]
    for i in range(MAX_USER_SHADERS + 5):
        (tmp_path / f"z{i:02}.glsl").write_text("x")
    assert len(find_user_shaders(tmp_path)) == MAX_USER_SHADERS


def test_apply_user_shaders_commands():
    from almp.player import apply_user_shaders
    p = FakeMPV()
    assert apply_user_shaders(p, ["C:/s/a.glsl", "C:/s/b.glsl"])
    assert p.commands == [("change-list", "glsl-shaders", "clr", ""),
                          ("change-list", "glsl-shaders", "append", "C:/s/a.glsl"),
                          ("change-list", "glsl-shaders", "append", "C:/s/b.glsl")]
    assert apply_user_shaders(None, []) is False


def test_enhance_and_replaygain_helpers():
    import almp.player as pl
    from almp.player import LOW_QUALITY_MAX_HEIGHT, enhance_shaders, replaygain_mode, too_many_dropped_frames
    b = pl.__file__                                         # any existing file stands in for the shader
    assert enhance_shaders("auto", 480, b, []) == [b]
    assert enhance_shaders("auto", LOW_QUALITY_MAX_HEIGHT, b, []) == [b]
    assert enhance_shaders("auto", 1080, b, []) == []       # HD: left alone
    assert enhance_shaders("auto", None, b, []) == []       # size not known yet
    assert enhance_shaders("auto", 360, "C:/missing.glsl", []) == []
    assert enhance_shaders("own", 360, b, ["x.glsl"]) == ["x.glsl"]
    assert enhance_shaders("off", 360, b, ["x.glsl"]) == []
    assert not too_many_dropped_frames(9, 6, 30)            # at least 10
    assert not too_many_dropped_frames(9, 6, None)
    assert too_many_dropped_frames(11, 6, 30)               # 5% of 180 = 9, so 11 is too many
    assert not too_many_dropped_frames(20, 20, 30) and too_many_dropped_frames(31, 20, 30)
    album = ["/m/A/1.flac", "/m/A/2.flac"]
    assert replaygain_mode("auto", album[0], [None, album[1]], False, False) == "album"
    assert replaygain_mode("auto", album[0], [None, album[1]], True, False) == "track"   # shuffle
    assert replaygain_mode("auto", album[0], [None, "/m/B/1.flac"], False, False) == "track"
    assert replaygain_mode("auto", album[0], [None, album[1]], False, True) == "no"     # bit-perfect
    assert replaygain_mode("album", album[0], [], True, True) == "album"
    assert replaygain_mode("track", album[0], [], False, False) == "track"
    assert replaygain_mode("off", album[0], [None, album[1]], False, False) == "no"


def test_enhance_and_replaygain_settings_defaults_and_migration():
    from almp.settings import effective_settings
    assert effective_settings({})["enhance"] == "auto"
    assert effective_settings({})["replaygain"] == "off"                     # Off by default
    assert effective_settings({"user_shaders": True})["enhance"] == "own"     # 8.2.5 choice kept
    assert effective_settings({"user_shaders": True, "enhance": "off"})["enhance"] == "off"
    assert effective_settings({"enhance": "max", "replaygain": 3})["enhance"] == "auto"
    assert effective_settings({"replaygain": 3})["replaygain"] == "off"
    assert effective_settings({"replaygain": "album"})["replaygain"] == "album"


def _shader_cmds(player):
    return [c for c in player.commands if c[:2] == ("change-list", "glsl-shaders")]


def test_sharpening_only_for_low_quality_video(window, qapp, tmp_path, monkeypatch):
    from almp.store import make_entry
    builtin = tmp_path / "FSRCNNX_x2_16-0-4-1.glsl"
    builtin.write_text("//!HOOK LUMA")
    monkeypatch.setattr(window, "builtin_shader_path", lambda: str(builtin))
    assert window.settings["enhance"] == "auto"
    low, hd = str(tmp_path / "old 480p.mp4"), str(tmp_path / "new 1080p.mp4")
    window.model.append_entries([make_entry(low), make_entry(hd)])
    p = window.player
    window.play_index(window.store.index_of(low))
    p.commands.clear()
    window._poll_player_metrics()                   # height not known yet: nothing decided
    assert _shader_cmds(p) == [] and window._enhance_for is None
    p.height, p.frame_drop_count, p.container_fps = 480, 0, 30.0
    window._poll_player_metrics()
    assert _shader_cmds(p)[-1] == ("change-list", "glsl-shaders", "append", str(builtin))
    assert window._enhance_for == low and window._enhance_watch == (0.0, 0, False)
    p.time_pos, p.frame_drop_count = 2, 56          # the one-off burst while mpv prepares the shader
    window._poll_player_metrics()
    assert window._enhance_watch == (2.0, 56, True) and not window._enhance_blocked
    p.time_pos, p.frame_drop_count = 9, 59          # then 3 drops in 7 s: fine, keeps running
    window._poll_player_metrics()
    assert window._enhance_watch is None and not window._enhance_blocked
    p.commands.clear()
    window.play_index(window.store.index_of(hd))
    p.height = 1080
    window._poll_player_metrics()
    assert _shader_cmds(p) == [("change-list", "glsl-shaders", "clr", "")]   # HD: shader removed
    p.commands.clear()
    window.play_index(window.store.index_of(hd))    # same HD again: mpv is not told twice
    window._poll_player_metrics()
    assert _shader_cmds(p) == []


def test_sharpening_turns_off_when_frames_drop_and_e_key(window, qapp, tmp_path, monkeypatch):
    from almp.store import make_entry
    builtin = tmp_path / "f.glsl"
    builtin.write_text("x")
    monkeypatch.setattr(window, "builtin_shader_path", lambda: str(builtin))
    vids = [str(tmp_path / f"v{i}.mp4") for i in range(2)]
    window.model.append_entries([make_entry(v) for v in vids])
    p = window.player
    window.play_index(0)
    p.height, p.frame_drop_count, p.container_fps = 360, 0, 30.0
    window._poll_player_metrics()
    p.time_pos = 2
    window._poll_player_metrics()                   # starts counting
    p.time_pos, p.frame_drop_count = 8.5, 40        # 40 of ~195 frames dropped
    window._poll_player_metrics()
    assert window._enhance_blocked and window._shaders_loaded == []
    assert "turned off" in window.status_label.text()
    window.play_index(1)                            # stays off for this run
    p.time_pos = 0
    window._poll_player_metrics()
    assert window._shaders_loaded == []
    assert window.toggle_enhance() == [str(builtin)]    # E: try again
    assert not window._enhance_blocked
    assert window.toggle_enhance() == [] and window._enhance_paused             # E: off for now
    assert "off for now" in window.status_label.text()
    window.set_enhance("off")
    assert window.settings["enhance"] == "off" and window.toggle_enhance() is None


def test_own_shaders_mode_uses_the_folder(window, qapp, tmp_path, monkeypatch):
    from almp.store import make_entry
    folder = tmp_path / "shaders"
    folder.mkdir()
    (folder / "Anime4K.glsl").write_text("x")
    monkeypatch.setattr(window, "user_shader_folder", lambda: str(folder))
    v = str(tmp_path / "anime 480p.mkv")
    window.model.append_entries([make_entry(v)])
    window.play_index(0)
    window.player.height = 480
    assert window.set_enhance("own") == [str(folder / "Anime4K.glsl")]
    assert window.settings["enhance"] == "own"


def test_replaygain_follows_album_order(window, qapp, tmp_path, monkeypatch):
    from almp.store import make_entry
    album = [str(tmp_path / "Album" / f"{i:02} song.flac") for i in range(1, 4)]
    single = str(tmp_path / "Singles" / "hit.mp3")
    window.model.append_entries([make_entry(p) for p in album + [single]])
    window.shuffle_checkbox.setChecked(False)
    window.play_index(1)
    assert window.player.props["replaygain"] == "no"         # Off by default
    window.set_replaygain("auto")
    window.play_index(1)
    assert window.player.props["replaygain"] == "album"
    window.play_index(3)
    assert window.player.props["replaygain"] == "track"      # the only file of its folder
    window.shuffle_checkbox.setChecked(True)
    window.play_index(0)
    assert window.player.props["replaygain"] == "track"      # shuffle: tracks of many albums
    from almp import ui
    monkeypatch.setattr(ui, "EXCLUSIVE_AUDIO_SUPPORTED", True)   # Windows behaviour
    window.set_audio_exclusive(True)
    assert window.player.props["replaygain"] == "no"         # bit-perfect stays untouched
    window.set_audio_exclusive(False)
    assert window.set_replaygain("album") == "album" and window.settings["replaygain"] == "album"
    assert window.set_replaygain("off") == "no"


def test_settings_dialog_sharpening_and_replaygain(window, qapp, tmp_path, monkeypatch):
    from almp.dialogs import SettingsDialog
    folder = tmp_path / "shaders"
    monkeypatch.setattr(window, "user_shader_folder", lambda: str(folder))
    dlg = SettingsDialog(window)
    assert dlg.enhance.currentIndex() == 0                  # Automatic
    assert dlg.replaygain.currentText() == "Off"            # Off by default
    assert "No shader files" in dlg.shader_found.text()
    folder.mkdir()
    (folder / "Anime4K_Upscale.glsl").write_text("x")
    dlg.enhance.setCurrentIndex(1)
    assert window.settings["enhance"] == "own"
    assert "Found 1 shader file(s): Anime4K_Upscale.glsl" in dlg.shader_found.text()
    dlg.replaygain.setCurrentIndex(0)
    assert window.settings["replaygain"] == "auto"
    dlg.close()


def test_settings_does_not_block_the_player(window, qapp):
    """Up to 8.2.5 Settings was modal; in fullscreen the control bar showed but ignored every click,
    so the player could not even be closed while Settings was open."""
    from PyQt6.QtWidgets import QApplication
    window._toggle_fullscreen()
    dlg = window.show_settings()
    qapp.processEvents()
    assert dlg.isVisible() and not dlg.isModal()
    assert QApplication.activeModalWidget() is None          # the player's buttons still work
    assert window._dialog_active and not window._is_cursor_hidden
    assert window.show_settings() is dlg                      # a second click: the same window
    w = dlg.width()
    assert w >= dlg._page.sizeHint().width() or w >= int(dlg.screen().availableGeometry().width() * 0.95) - 1
    dlg.close()
    qapp.processEvents()
    assert window._settings_dialog is None and not window._dialog_active
    assert window.show_settings() is not dlg                  # opens again after closing
    window._settings_dialog.close()
    qapp.processEvents()
    window._toggle_fullscreen()
