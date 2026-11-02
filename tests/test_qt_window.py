"""The real window with real Qt (offscreen) and a stand-in for mpv.

Skipped when PyQt6 is not installed (the plain-logic tests still run). In CI PyQt6 is installed,
so these run there. Nothing here plays sound or opens a visible window."""
import os
import time
import types

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
