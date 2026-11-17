"""8.2.4: subtitles on/off, Data folder + migration + log clean-up, All/Video/Audio filter, saving what is
shown, lossless extras (format text, gapless, exclusive), video upscaling, the Releases link in About.
Plain-logic tests run everywhere; window tests use real Qt (offscreen) and the FakeMPV stand-in."""
import logging
import os
import time
import types
from pathlib import Path

import pytest

from almp import datafolder, logsetup, paths, player, settings
from almp.store import PlaylistStore, kind_of, make_entry

from conftest import HAVE_QT

ROOT = Path(__file__).resolve().parent.parent


# ------------------------------------------------------------------ settings and mpv options

def test_new_settings_defaults():
    s = settings.effective_settings({})
    assert s["show_subtitles"] is False          # decided: hidden until turned on
    assert s["log_mode"] == "clear"
    assert s["gapless"] is False and s["audio_exclusive"] is False
    assert s["upscaling"] == "standard"


@pytest.mark.parametrize("raw, key, expected", [
    ({"show_subtitles": "yes"}, "show_subtitles", False),
    ({"show_subtitles": True}, "show_subtitles", True),
    ({"log_mode": "forever"}, "log_mode", "clear"),
    ({"log_mode": "off"}, "log_mode", "off"),
    ({"upscaling": "fsrcnnx"}, "upscaling", "standard"),
    ({"upscaling": "high"}, "upscaling", "high"),
    ({"audio_exclusive": 1}, "audio_exclusive", True),
])
def test_new_settings_are_checked(raw, key, expected):
    assert settings.effective_settings(raw)[key] == expected


def test_show_subtitles_is_remembered(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "settings.json")
    settings.update_settings(show_subtitles=True)
    assert settings.effective_settings(settings.load_settings())["show_subtitles"] is True


def test_mpv_options_subtitles_gapless_exclusive():
    o = player.mpv_options(1)
    assert o["sub_visibility"] == "no"
    assert o["gapless_audio"] == "weak" and o["prefetch_playlist"] == "no"
    assert "audio_exclusive" not in o
    o = player.mpv_options(1, show_subtitles=True, gapless=True, audio_exclusive=True)
    assert o["sub_visibility"] == "yes"
    assert o["gapless_audio"] == "yes" and o["prefetch_playlist"] == "yes"
    assert o["audio_exclusive"] == "yes"
    # still offline and locked down
    assert o["ytdl"] == "no" and o["config"] == "no" and o["load_scripts"] == "no"


def test_upscaling_uses_only_built_in_scalers():
    std = {"scale": "lanczos", "cscale": "lanczos", "dscale": "hermite"}
    assert player.upscaling_properties("standard", std) == std
    assert player.upscaling_properties("standard") == {}
    assert player.upscaling_properties("sharp") == {"scale": "spline36", "cscale": "spline36", "dscale": "mitchell"}
    assert player.upscaling_properties("high") == {
        "scale": "ewa_lanczossharp", "cscale": "ewa_lanczossharp", "dscale": "mitchell",
        "correct-downscaling": True, "sigmoid-upscaling": True, "deband": True}
    # every key High quality changes is one "Standard" puts back
    assert set(player.upscaling_properties("high")) <= set(player.SCALER_KEYS)
    assert player.upscaling_properties("nonsense", std) == std
    for level in ("sharp", "high"):              # never a shader file or anything to download
        assert "glsl-shaders" not in player.upscaling_properties(level)


@pytest.mark.parametrize("args, text", [
    ((".flac", "flac", 96000, 24), "FLAC - 24-bit / 96 kHz"),
    ((".flac", "flac", 44100, 16), "FLAC - 16-bit / 44.1 kHz"),
    ((".flac", "flac", 44100, None, "s16"), "FLAC - 16-bit / 44.1 kHz"),
    ((".flac", "flac", 96000, None, "s32"), "FLAC - 96 kHz"),        # s32 does not tell 24 from 32 bit
    ((".mp3", "mp3float", 44100, None, "floatp"), "MP3FLOAT - 44.1 kHz"),
    ((".m4a", "alac", 48000, 24), "ALAC - 24-bit / 48 kHz"),
    ((".wav", "pcm_s24le", 192000, 24), "WAV - 24-bit / 192 kHz"),
    ((".ogg", "", None, None), "OGG"),
])
def test_audio_format_text(args, text):
    assert player.audio_format_text(*args) == text


# ------------------------------------------------------------------ Data folder

@pytest.fixture
def clean_paths(monkeypatch):
    monkeypatch.delenv(paths.DATA_DIR_ENV, raising=False)
    paths.reset_data_dir()
    yield
    paths.reset_data_dir()


def test_data_folder_next_to_the_app_when_writable(tmp_path, clean_paths):
    folder, portable = paths.init_data_dir(base=tmp_path)
    assert portable and folder == tmp_path / "Data" and folder.is_dir()
    assert paths.get_settings_dir() == folder and paths.get_log_dir() == folder
    assert list(folder.iterdir()) == []                  # the write test left nothing behind


def test_read_only_folder_falls_back_to_the_old_folders(tmp_path, monkeypatch, clean_paths):
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("x")                               # Data cannot be made inside a file
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    folder, portable = paths.init_data_dir(base=blocker)
    assert not portable
    assert folder == tmp_path / "roaming" / "ALMP"
    assert paths.get_log_dir() == tmp_path / "local" / "ALMP"
    from almp.dialogs import data_folder_text
    assert "cannot be written" in data_folder_text()


def test_folder_is_writable_false_when_writing_fails(tmp_path, monkeypatch):
    def refuse(self, data):
        raise PermissionError("read-only")
    monkeypatch.setattr(Path, "write_bytes", refuse)
    assert paths.folder_is_writable(tmp_path / "Data") is False


def test_env_override_for_tests_and_benchmarks(tmp_path, monkeypatch, clean_paths):
    monkeypatch.setenv(paths.DATA_DIR_ENV, str(tmp_path / "elsewhere"))
    folder, portable = paths.init_data_dir()
    assert portable and folder == tmp_path / "elsewhere"


def test_startup_marker_follows_the_data_folder(tmp_path, clean_paths):
    from almp import platform_win
    paths.init_data_dir(base=tmp_path)
    assert platform_win.startup_marker() == tmp_path / "Data" / "startup_target.txt"


def _old_install(tmp_path):
    roaming = tmp_path / "roaming" / "ALMP"
    local = tmp_path / "local" / "ALMP"
    roaming.mkdir(parents=True)
    local.mkdir(parents=True)
    (roaming / "settings.json").write_text('{"volume": 42, "show_subtitles": true}', encoding="utf-8")
    (roaming / "positions.json").write_text('{"a": 1}', encoding="utf-8")
    (roaming / "resume.json").write_text("{}", encoding="utf-8")
    (local / "almp.log").write_text("old log\n", encoding="utf-8")
    (local / "media-controls-starting.flag").write_text("", encoding="utf-8")
    return roaming, local


def test_migration_copies_verifies_and_removes_only_almp_files(tmp_path):
    roaming, local = _old_install(tmp_path)
    data = tmp_path / "app" / "Data"
    r = datafolder.migrate_legacy_files(data, roaming, local)
    assert r["error"] == ""
    assert sorted(r["copied"]) == ["positions.json", "settings.json"]
    assert (data / "settings.json").read_text(encoding="utf-8") == '{"volume": 42, "show_subtitles": true}'
    assert (data / "positions.json").read_text(encoding="utf-8") == '{"a": 1}'
    assert not roaming.exists() and not local.exists()      # empty afterwards, so removed
    assert not list(data.glob("*.migrating"))


def test_migration_never_touches_other_files(tmp_path):
    roaming, local = _old_install(tmp_path)
    (roaming / "my-notes.txt").write_text("mine", encoding="utf-8")
    (local / "other.log").write_text("not ALMP's", encoding="utf-8")
    r = datafolder.migrate_legacy_files(tmp_path / "Data", roaming, local)
    assert (roaming / "my-notes.txt").read_text(encoding="utf-8") == "mine"
    assert (local / "other.log").exists()
    assert sorted(p.name for p in roaming.iterdir()) == ["my-notes.txt"]
    assert sorted(p.name for p in local.iterdir()) == ["other.log"]
    assert set(r["kept_folders"]) == {str(roaming), str(local)}


def test_migration_does_nothing_when_data_already_has_settings(tmp_path):
    roaming, local = _old_install(tmp_path)
    data = tmp_path / "Data"
    data.mkdir()
    (data / "settings.json").write_text("{}", encoding="utf-8")
    r = datafolder.migrate_legacy_files(data, roaming, local)
    assert r["copied"] == [] and r["removed"] == []
    assert (roaming / "settings.json").exists() and (local / "almp.log").exists()


def test_migration_keeps_the_old_files_when_the_copy_fails(tmp_path, monkeypatch):
    roaming, local = _old_install(tmp_path)

    def broken_copy(src, dst):
        Path(dst).write_text("garbage", encoding="utf-8")
    monkeypatch.setattr(datafolder.shutil, "copyfile", broken_copy)
    r = datafolder.migrate_legacy_files(tmp_path / "Data", roaming, local)
    assert r["error"] and r["removed"] == []
    assert (roaming / "settings.json").exists() and (local / "almp.log").exists()
    assert not (tmp_path / "Data" / "settings.json").exists()


def test_migration_skips_when_data_is_the_old_folder(tmp_path):
    roaming, local = _old_install(tmp_path)
    r = datafolder.migrate_legacy_files(roaming, roaming, local)
    assert r == {"copied": [], "removed": [], "kept_folders": [], "error": ""}
    assert (roaming / "settings.json").exists()


def test_migration_list_matches_the_uninstall_script():
    bat = (ROOT / "Remove-ALMP-Defaults.bat").read_text(encoding="utf-8")
    for name in datafolder.OLD_SETTINGS_FILES + datafolder.OLD_LOG_FILES:
        assert name in bat, name
    assert "%~dp0Data" in bat                       # the new Data folder is cleaned up too


def test_prepare_data_folder_end_to_end(tmp_path, monkeypatch, clean_paths):
    from almp import app
    roaming, local = _old_install(tmp_path)
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv(paths.DATA_DIR_ENV, str(tmp_path / "app" / "Data"))
    old = (settings.SETTINGS_DIR, settings.SETTINGS_PATH)
    try:
        folder, portable, moved, mode = app.prepare_data_folder()
        assert portable and folder == tmp_path / "app" / "Data"
        assert settings.SETTINGS_PATH == folder / "settings.json"
        assert settings.effective_settings(settings.load_settings())["volume"] == 42
        assert mode == "clear" and moved["copied"]
        assert not roaming.exists() and not local.exists()
    finally:
        logsetup.reset_for_tests()
        settings.SETTINGS_DIR, settings.SETTINGS_PATH = old


# ------------------------------------------------------------------ log clean-up

@pytest.fixture
def fresh_log():
    logsetup.reset_for_tests()
    yield
    logsetup.reset_for_tests()


def test_log_is_cleared_after_a_normal_close(tmp_path, fresh_log):
    p = logsetup.setup_logging("clear", log_dir=tmp_path)
    logsetup.log.info("Start-up: window shown after 0.9 s")
    assert p.exists() and "window shown" in p.read_text(encoding="utf-8")   # readable while running
    assert logsetup.finish_logging("clear", log_dir=tmp_path) is True
    assert not p.exists() and not (tmp_path / "almp.log.1").exists()


def test_log_is_kept_after_an_error(tmp_path, fresh_log):
    p = logsetup.setup_logging("clear", log_dir=tmp_path)
    logsetup.log.error("something broke")
    assert logsetup.finish_logging("clear", log_dir=tmp_path) is False
    assert "something broke" in p.read_text(encoding="utf-8")


def test_log_is_kept_after_an_uncaught_error(tmp_path, fresh_log):
    p = logsetup.setup_logging("clear", log_dir=tmp_path)
    try:
        raise ValueError("boom")
    except ValueError as e:
        logsetup.almp_excepthook(ValueError, e, e.__traceback__)
    logsetup.finish_logging("clear", log_dir=tmp_path)
    assert "boom" in p.read_text(encoding="utf-8")


def test_keep_mode_keeps_the_last_run(tmp_path, fresh_log):
    (tmp_path / "almp.log").write_text("previous run\n", encoding="utf-8")
    p = logsetup.setup_logging("keep", log_dir=tmp_path)
    assert logsetup.start_new_run_log() is True
    logsetup.log.info("this run")
    assert logsetup.finish_logging("keep", log_dir=tmp_path) is False
    assert "this run" in p.read_text(encoding="utf-8")
    assert "previous run" in (tmp_path / "almp.log.1").read_text(encoding="utf-8")


def test_off_mode_writes_no_file(tmp_path, fresh_log):
    assert logsetup.setup_logging("off", log_dir=tmp_path) is None
    logsetup.log.error("not written")
    logsetup.finish_logging("off", log_dir=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_log_size_is_capped(tmp_path, fresh_log):
    p = logsetup.setup_logging("keep", log_dir=tmp_path)
    line = "x" * 1000
    for _ in range(800):                       # ~800 KB written
        logsetup.log.info(line)
    logsetup.finish_logging("keep", log_dir=tmp_path)
    total = sum(f.stat().st_size for f in tmp_path.iterdir())
    assert p.stat().st_size <= logsetup.LOG_MAX_BYTES
    assert total <= 2 * logsetup.LOG_MAX_BYTES + 2048
    assert sorted(f.name for f in tmp_path.iterdir()) == ["almp.log", "almp.log.1"]
    logging.getLogger("almp").handlers[:] = [h for h in logging.getLogger("almp").handlers
                                             if isinstance(h, logging.NullHandler)]


def test_bench_startup_watches_the_data_folder(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("bench_startup", ROOT / "tools" / "bench_startup.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    exe = tmp_path / "ALMP" / "ALMP.exe"
    found = mod.log_paths(str(exe), {"LOCALAPPDATA": str(tmp_path / "local")})
    assert found[0] == exe.parent.resolve() / "Data" / "almp.log"
    assert found[-1] == tmp_path / "local" / "ALMP" / "almp.log"
    assert mod.log_paths(None, {})[0] == ROOT / "Data" / "almp.log"


# ------------------------------------------------------------------ All / Video / Audio filter

def test_kind_of_uses_the_extension_only():
    assert kind_of(r"C:\m\song.FLAC") == 1
    assert kind_of(r"C:\m.v\clip.mkv") == 2
    assert kind_of(r"C:\m\file.dvr-ms") == 2
    assert kind_of(r"C:\m\notes.txt") == 0


def test_store_kind_filter_combines_with_words():
    st = PlaylistStore()
    st.extend([r"C:\a\Live song.flac", r"C:\a\Live clip.mp4", r"C:\b\Other.mp3", r"C:\b\Live.mkv"])
    assert st.filter_rows([], kind="audio") == [0, 2]
    assert st.filter_rows([], kind="video") == [1, 3]
    assert st.filter_rows(["live"], kind="video") == [1, 3]
    assert st.filter_rows(["live"], kind="audio") == [0]
    assert st.filter_rows(["live"]) == [0, 1, 3]
    # kinds stay right after removing and moving rows
    st.remove_at(0)
    assert st.filter_rows([], kind="audio") == [1]
    st.move(2, 0)
    assert st.paths[0].endswith("Live.mkv") and st.filter_rows([], kind="video") == [0, 1]


def test_kind_filter_is_fast_on_100000_items():
    st = PlaylistStore()
    st.commit(st.new_entries([make_entry(rf"D:\Music\Artist {i % 300}\Track {i}.{'flac' if i % 3 else 'mp4'}")
                              for i in range(100_000)]))
    t = time.perf_counter()
    first = st.filter_rows([], kind="audio")             # builds the type list once
    t_first = time.perf_counter() - t
    t = time.perf_counter()
    again = st.filter_rows([], kind="video")
    t_again = time.perf_counter() - t
    assert len(first) == 66_666 and len(again) == 33_334
    assert t_first < 1.0 and t_again < 0.5               # generous limits for slow CI machines


# ------------------------------------------------------------------ the window (real Qt, fake mpv)

qt = pytest.mark.skipif(not HAVE_QT, reason="PyQt6 is not installed")


@pytest.fixture
def win(qapp, tmp_path, monkeypatch):
    from test_qt_window import FakeMPV

    from almp import smtc, ui
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


@pytest.fixture(scope="module")
def qapp():
    if not HAVE_QT:
        pytest.skip("PyQt6 is not installed")
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(["almp-test"])
    from almp.theme import stylesheet
    app.setStyleSheet(stylesheet(False))
    return app


def _add(w, paths_):
    w.model.append_entries([make_entry(p) for p in paths_])
    w._update_playlist_count()


@qt
def test_subtitles_start_hidden_and_the_setting_reaches_mpv(win):
    assert win.player.opts["sub_visibility"] == "no"
    win.set_show_subtitles(True)
    assert win.player.props["sub-visibility"] is True
    assert settings.effective_settings(settings.load_settings())["show_subtitles"] is True
    win.set_show_subtitles(False)
    assert settings.effective_settings(settings.load_settings())["show_subtitles"] is False


@qt
def test_subtitle_menu_and_setting_agree(win, qapp):
    from PyQt6.QtWidgets import QMenu
    win.player.track_list = [{"type": "sub", "id": 1, "title": "English", "selected": True}]
    win.player.idle_active = False

    keep = []

    def menu_state():
        m = QMenu()
        keep.append(m)                               # the submenu lives as long as its parent menu
        win._fill_tracks_menu(m)
        sub = [a.menu() for a in m.actions() if a.text() == "Subtitles"][0]
        return {a.text(): a.isChecked() for a in sub.actions() if a.isCheckable()}, sub

    state, _ = menu_state()
    assert state["Off"] is True and state["English"] is False       # default: hidden
    _, sub = menu_state()
    [a for a in sub.actions() if a.text() == "English"][0].trigger()
    assert win.settings["show_subtitles"] is True and win.player.sid == 1
    state, sub = menu_state()
    assert state["Off"] is False and state["English"] is True
    [a for a in sub.actions() if a.text() == "Off"][0].trigger()
    assert win.settings["show_subtitles"] is False
    assert settings.effective_settings(settings.load_settings())["show_subtitles"] is False


@qt
def test_settings_checkbox_and_menu_share_one_setting(win, qapp):
    from almp.dialogs import SettingsDialog
    d = SettingsDialog(win)
    assert d.show_subs.isChecked() is False
    d.show_subs.setChecked(True)
    assert win.settings["show_subtitles"] is True
    d.close()
    d2 = SettingsDialog(win)                         # the menu changed it: the box shows the same
    win.set_show_subtitles(False)
    d3 = SettingsDialog(win)
    assert d3.show_subs.isChecked() is False
    for x in (d2, d3):
        x.close()


@qt
def test_every_new_file_gets_the_subtitle_choice(win):
    _add(win, ["/v/a.mkv", "/v/b.mkv"])
    win.set_show_subtitles(True)
    win.player.props.pop("sub-visibility", None)
    win.play_index(1)
    assert win.player.props["sub-visibility"] is True


@qt
def test_kind_buttons_filter_and_combine_with_search(win, qapp):
    _add(win, ["/m/live song.flac", "/m/live clip.mp4", "/m/other.mp3", "/m/live.mkv"])
    win.kind_buttons["video"].click()
    assert win.model.rowCount() == 2 and win.playlist_count_label.text() == "2 of 4"
    win.search_edit.setText("live")
    win._apply_filter()
    assert win.model.rowCount() == 2
    win.kind_buttons["audio"].click()
    assert [win.model.path_at_view(i) for i in range(win.model.rowCount())] == ["/m/live song.flac"]
    win.search_edit.setText("")
    win._apply_filter()
    assert win.model.rowCount() == 2
    win.kind_buttons[None].click()
    assert not win.model.filtered and win.playlist_count_label.text() == "4 items"


@qt
def test_save_writes_only_what_is_shown(win, tmp_path, monkeypatch):
    from almp import ui
    _add(win, ["/m/a.flac", "/m/b.mp4", "/m/c.mp3"])
    assert win.files_to_save() == ["/m/a.flac", "/m/b.mp4", "/m/c.mp3"]
    win.kind_buttons["audio"].click()
    assert win.files_to_save() == ["/m/a.flac", "/m/c.mp3"]
    seen = {}

    def fake_dialog(parent, title, start, filt):
        seen["title"] = title
        return str(tmp_path / "out.m3u8"), ""
    monkeypatch.setattr(ui.QFileDialog, "getSaveFileName", staticmethod(fake_dialog))
    win.save_playlist_m3u()
    assert "2 items shown" in seen["title"]
    text = (tmp_path / "out.m3u8").read_text(encoding="utf-8")
    assert "a.flac" in text and "c.mp3" in text and "b.mp4" not in text


@qt
def test_ctrl_s_saves_the_playlist(win):
    from PyQt6.QtGui import QKeySequence, QShortcut
    keys = {s.key().toString() for s in win.findChildren(QShortcut)}
    assert QKeySequence("Ctrl+S").toString() in keys


@qt
def test_gapless_queues_the_next_track_and_skips_reloading(win):
    _add(win, ["/m/1.flac", "/m/2.flac", "/m/3.flac"])
    win.shuffle_checkbox.setChecked(False)
    win.set_gapless(True)
    assert win.player.props["gapless-audio"] == "yes" and win.player.props["prefetch-playlist"] == "yes"
    win.play_index(0)
    assert ("loadfile", "/m/2.flac", "append") in win.player.commands
    loads = len(win.player.loaded)
    win._handle_end_file("EOF")                      # mpv went on to 2.flac by itself
    assert win.current_index == 1
    assert len(win.player.loaded) == loads           # no second load: no gap
    assert ("loadfile", "/m/3.flac", "append") in win.player.commands
    win._handle_end_file("EOF")
    assert win.current_index == 2
    assert win._gapless_next is None                 # end of the list with Loop Off: nothing queued


@qt
def test_gapless_with_shuffle_plays_the_planned_track(win):
    _add(win, [f"/m/{i}.flac" for i in range(6)])
    win.shuffle_checkbox.setChecked(True)
    win.set_gapless(True)
    win.play_index(0)
    planned = win._gapless_next
    assert planned and planned != "/m/0.flac"
    loads = len(win.player.loaded)
    win._handle_end_file("EOF")
    assert win.current_path == planned and len(win.player.loaded) == loads


@qt
def test_gapless_stops_mpv_when_almp_decides_to_stop(win):
    _add(win, ["/m/1.flac", "/m/2.flac"])
    win.shuffle_checkbox.setChecked(False)
    win.set_gapless(True)
    win.play_index(0)
    assert win._gapless_next == "/m/2.flac"
    win.set_sleep_end_of_track()                      # drops the queued track
    assert win._gapless_next is None
    win._handle_end_file("EOF")
    assert win.current_index == 0


@qt
def test_gapless_off_by_default_queues_nothing(win):
    _add(win, ["/m/1.flac", "/m/2.flac"])
    win.play_index(0)
    assert not any(c[:1] == ("loadfile",) for c in win.player.commands)


@qt
def test_exclusive_audio_and_upscaling_reach_mpv(win):
    win.set_audio_exclusive(True)
    assert win.player.props["audio-exclusive"] is True and ("ao-reload",) in win.player.commands
    assert settings.effective_settings(settings.load_settings())["audio_exclusive"] is True
    win._scaler_defaults = {"scale": "lanczos", "deband": False}
    win.set_upscaling("high")
    assert win.player.props["scale"] == "ewa_lanczossharp" and win.player.props["dscale"] == "mitchell"
    assert win.player.props["deband"] is True
    win.set_upscaling("standard")
    assert win.player.props["scale"] == "lanczos" and win.player.props["deband"] is False
    assert settings.effective_settings(settings.load_settings())["upscaling"] == "standard"


@qt
def test_format_text_for_the_playing_track_only(win, qapp):
    _add(win, ["/m/song.flac", "/m/clip.mp4"])
    win.play_index(0)
    win._tag_format = (24, 96000)
    win.player.audio_params = {"samplerate": 96000, "format": "s32"}     # runtime properties, not options
    win.player.audio_codec_name = "flac"
    win._poll_player_metrics()
    assert win.format_label.text() == "FLAC - 24-bit / 96 kHz" and not win.format_label.isHidden()
    win.play_index(1)
    win._poll_player_metrics()
    assert win.format_label.isHidden()               # videos: no format text


@qt
def test_about_copy_link_puts_the_releases_address_on_the_clipboard(win, qapp):
    from PyQt6.QtGui import QGuiApplication

    from almp.dialogs import RELEASES_URL, AboutDialog
    d = AboutDialog(win)
    assert "never connects to the internet" in d.releases_text
    assert "github.com/alexbedca/Alexbed-Light-Media-Player/releases" in d.releases_text
    QGuiApplication.clipboard().setText("")
    d.copy_link.click()
    assert QGuiApplication.clipboard().text() == RELEASES_URL
    assert RELEASES_URL == "https://github.com/alexbedca/Alexbed-Light-Media-Player/releases"
    d.close()


@qt
def test_settings_dialog_has_the_new_choices(win):
    from almp.dialogs import SettingsDialog
    d = SettingsDialog(win)
    assert d.gapless.isChecked() is False and d.exclusive.isChecked() is False
    assert d.upscaling.currentText() == "Standard"
    assert d.log_mode.currentIndex() == 0
    d.log_mode.setCurrentIndex(1)
    assert settings.effective_settings(settings.load_settings())["log_mode"] == "keep"
    d.upscaling.setCurrentIndex(1)
    assert win.settings["upscaling"] == "sharp"
    d.close()


def test_no_network_code_was_added():
    """ALMP never connects to the internet: no networking modules in ALMP's own code."""
    banned = ("urllib.request", "http.client", "import requests", "QNetworkAccessManager",
              "socket.create_connection", "QTcpSocket", "QSslSocket")
    for f in (ROOT / "almp").glob("*.py"):
        text = f.read_text(encoding="utf-8")
        for b in banned:
            assert b not in text, f"{b} in {f.name}"
    assert os.path.exists(ROOT / "almp" / "ipc.py")      # local single-instance channel only (QLocalSocket)
