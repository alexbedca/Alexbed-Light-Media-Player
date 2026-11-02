"""Settings migration and the v8.1 features that are plain logic: Play next queue, speed memory,
sleep-timer extras, media-key de-duplication, optional resume, registry entries, mpv options,
and the Windows media controls interface IDs. Windows itself is never touched here."""
import json

import pytest

from almp import logic, platform_win, player, settings, smtc

from conftest import ROOT

# --- settings migration ---------------------------------------------------------


def test_new_install_gets_remove_played_off_and_safe_defaults():
    s = settings.effective_settings({})
    assert s["remove_played"] is False
    assert s["shuffle"] is True
    assert s["volume"] == 100
    assert s["resume_long_files"] is False
    assert s["media_controls"] is True
    assert "loop" not in " ".join(s)


def test_v801_file_keeps_what_the_user_had():
    old = {"volume": 40, "shuffle": False, "remove_played": True, "high_contrast": True, "ui_scale": 1.5}
    s = settings.effective_settings(old)
    assert (s["volume"], s["shuffle"], s["remove_played"], s["high_contrast"], s["ui_scale"]) == (40, False, True, True, 1.5)


@pytest.mark.parametrize("raw,key,expected", [
    ({"volume": "loud"}, "volume", 100),
    ({"volume": 999}, "volume", 100),
    ({"volume": 140, "volume_boost": True}, "volume", 140),
    ({"volume": -3}, "volume", 0),
    ({"ui_scale": "huge"}, "ui_scale", 1.0),
    ({"ui_scale": 9}, "ui_scale", 1.0),
    ({"ui_scale": float("nan")}, "ui_scale", 1.0),
    ({"video_size": "zoom"}, "video_size", "fit"),
    ({"subtitle_scale": 0}, "subtitle_scale", 1.0),
    ({"shuffle": "yes"}, "shuffle", True),
    ({"remove_played": 1}, "remove_played", True),
])
def test_broken_values_fall_back(raw, key, expected):
    assert settings.effective_settings(raw)[key] == expected


def test_effective_settings_handles_non_dict():
    assert settings.effective_settings(["x"]) == settings.effective_settings({})
    assert settings.effective_settings(None)["volume"] == 100


def test_migration_drops_old_keys_once_and_marks_version(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"volume": 55, "loop_single": True, "remember_playlist": True,
                                "my_own_key": 1}), encoding="utf-8")
    monkeypatch.setattr(settings, "SETTINGS_PATH", path)
    eff = settings.migrate_settings_file()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert "loop_single" not in saved and "remember_playlist" not in saved
    assert saved["my_own_key"] == 1 and saved["settings_version"] == settings.SETTINGS_VERSION
    assert eff["volume"] == 55


def test_migration_does_not_create_a_file_for_new_installs(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(settings, "SETTINGS_PATH", path)
    settings.migrate_settings_file()
    assert not path.exists()


def test_update_settings_keeps_other_keys_and_never_writes_loop(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"volume": 70, "loop_single": True}), encoding="utf-8")
    monkeypatch.setattr(settings, "SETTINGS_PATH", path)
    assert settings.update_settings(normalize_volume=True)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved == {"volume": 70, "normalize_volume": True}


def test_broken_settings_file_is_ignored(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(settings, "SETTINGS_PATH", path)
    assert settings.load_settings() == {}


def test_save_is_atomic_no_tmp_left(tmp_path, monkeypatch):
    path = tmp_path / "sub" / "settings.json"
    monkeypatch.setattr(settings, "SETTINGS_PATH", path)
    assert settings.save_settings({"a": 1})
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1}
    assert [p.name for p in path.parent.iterdir()] == ["settings.json"]


def test_positions_file_is_separate_from_old_history_and_can_be_forgotten(tmp_path):
    assert settings.POSITIONS_FILE_NAME not in settings.LEGACY_HISTORY_FILES
    assert settings.save_positions({"k": [100, 1.0]}, tmp_path)
    assert settings.load_positions(tmp_path) == {"k": [100, 1.0]}
    assert settings.forget_positions(tmp_path)
    assert settings.load_positions(tmp_path) == {}


# --- Play next queue -------------------------------------------------------------


def test_queue_order_and_requeue_moves_to_end():
    q = []
    assert logic.add_to_queue(q, "a") == 1
    assert logic.add_to_queue(q, "b") == 2
    assert logic.add_to_queue(q, "a") == 2
    assert q == ["b", "a"]


def test_queue_skips_tracks_no_longer_in_the_list():
    q = ["gone", "b", "c"]
    assert logic.next_from_queue(q, lambda p: p != "gone") == "b"
    assert q == ["c"]
    assert logic.next_from_queue([], lambda p: True) is None


def test_queue_limit():
    q = []
    for i in range(20):
        logic.add_to_queue(q, str(i), limit=5)
    assert q == ["15", "16", "17", "18", "19"]


# --- speed ---------------------------------------------------------------------


@pytest.mark.parametrize("text,value", [("1.25x", 1.25), ("0.75x", 0.75), ("2.0X", 2.0), ("fast", 1.0),
                                        ("9x", 1.0), ("nanx", 1.0), (None, 1.0)])
def test_parse_speed(text, value):
    assert logic.parse_speed(text) == value


def test_speed_is_kept_for_the_session_or_reset():
    assert logic.speed_for_new_track("1.5x", True) == "1.5x"
    assert logic.speed_for_new_track("1.5x", False) == "1.0x"
    assert logic.speed_for_new_track("weird", True) == "1.0x"
    assert "0.75x" in logic.SPEED_CHOICES and "1.25x" in logic.SPEED_CHOICES


# --- sleep timer extras --------------------------------------------------------------


@pytest.mark.parametrize("ms,factor", [(None, 1.0), (120_000, 1.0), (60_000, 1.0), (30_000, 0.5),
                                       (0, 0.0), (-5, 0.0)])
def test_sleep_fade(ms, factor):
    assert logic.sleep_fade_factor(ms) == pytest.approx(factor)


def test_extend_sleep():
    assert logic.extend_sleep_ms(60_000, 15) == 16 * 60_000
    assert logic.extend_sleep_ms(None, 15) == 15 * 60_000
    assert logic.extend_sleep_ms(599 * 60_000, 15) == 600 * 60_000


# --- media keys: no double toggles -------------------------------------------------


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def test_same_press_from_two_sources_counts_once():
    c = Clock()
    f = logic.MediaCommandFilter(clock=c)
    assert f.accept("playpause", "key")
    c.t += 0.1
    assert not f.accept("playpause", "smtc")
    c.t += 1.0
    assert f.accept("playpause", "smtc")


def test_repeated_presses_from_one_source_all_count():
    c = Clock()
    f = logic.MediaCommandFilter(clock=c)
    assert f.accept("next", "key")
    c.t += 0.05
    assert f.accept("next", "key")
    assert f.accept("previous", "smtc")


# --- optional resume ----------------------------------------------------------------


@pytest.mark.parametrize("pos,dur,expected", [
    (600, 3600, 600),          # film, 10 minutes in
    (30, 3600, None),          # less than a minute in
    (3550, 3600, None),        # almost finished
    (300, 600, None),          # short file (10 min): never remembered
    (None, 3600, None),
    (600, None, None),
    (float("nan"), 3600, None),
])
def test_resume_position_rules(pos, dur, expected):
    assert logic.resume_position_to_store(pos, dur) == expected


def test_resume_table_keeps_newest_200():
    table = {}
    for i in range(250):
        logic.update_resume_table(table, f"f{i}", 600, 3600, now=float(i))
    assert len(table) == logic.RESUME_MAX_ENTRIES
    assert "f0" not in table and "f249" in table
    assert logic.resume_start_for(table, "f249") == 600
    logic.update_resume_table(table, "f249", 3599, 3600)
    assert "f249" not in table
    assert logic.resume_start_for({"x": "junk"}, "x") is None


# --- Windows registry entries (built as data; nothing is written in the tests) -------------


def test_default_player_entries_match_the_bat_file():
    exe = r"C:\Users\Ann\Documents\ALMP\ALMP.exe"
    entries = platform_win.default_player_entries(exe, extensions=(".mp3", ".mp4"))
    keys = {(k, n) for k, n, _d, _t in entries}
    assert (r"Software\Classes\ALMP.Media\shell\open", "MultiSelectModel") in keys
    assert (r"Software\RegisteredApplications", "ALMP") in keys
    cmd = [d for k, n, d, _t in entries if k.endswith(r"ALMP.Media\shell\open\command")][0]
    assert cmd == f'"{exe}" "%1"'
    assert all(k.startswith("Software\\") for k, *_ in entries)         # current user only (HKCU)
    bat = (ROOT / "Set-ALMP-Defaults.bat").read_text(encoding="utf-8")
    for ext in platform_win.ALL_ASSOC_EXTENSIONS:
        assert f" {ext}" in bat


def test_every_registry_change_has_a_removal():
    exe = r"C:\ALMP\ALMP.exe"
    removals = platform_win.default_player_removals()
    removed_keys = [k for k, _n in removals]
    for key, name, _d, _t in platform_win.default_player_entries(exe):
        assert any(key == rk or key.startswith(rk + "\\") for rk in removed_keys) or (key, name) in removals
    verb = platform_win.folder_verb_entries(exe)
    assert all(k.startswith(platform_win.folder_verb_removals()[0][0]) for k, *_ in verb)
    assert any(n == "MUIVerb" and d == "Play with ALMP" for _k, n, d, _t in verb)


def test_register_refuses_without_the_real_exe(monkeypatch):
    monkeypatch.setattr(platform_win.sys, "platform", "win32")
    assert platform_win.can_register(None) is False
    assert platform_win.can_register(r"C:\Python\python.exe") is False
    ok, _msg = platform_win.register_default_player(r"C:\nope\ALMP.exe")
    assert ok is False


def test_windows_only_helpers_do_nothing_elsewhere(monkeypatch):
    monkeypatch.setattr(platform_win.sys, "platform", "linux")
    assert platform_win.show_in_explorer("/x") is False
    assert platform_win.folder_verb_installed() is False
    assert platform_win.set_app_user_model_id() is False
    assert platform_win.open_default_apps_settings() is False
    assert platform_win.set_folder_verb("x", True)[0] is False
    assert platform_win.APP_USER_MODEL_ID == "Alexbed.ALMP"          # no version: pins survive updates


# --- mpv options: offline and locked down ---------------------------------------------


def test_mpv_is_locked_down_and_offline():
    o = player.mpv_options(1234, platform="win32", environ={})
    assert o["ytdl"] == "no" and o["load_scripts"] == "no" and o["config"] == "no"
    assert o["input_default_bindings"] is False and o["osc"] is False
    assert o["wid"] == "1234"
    assert o["volume_max"] == "100"
    assert "af" not in o                       # the normaliser is switched on after start


def test_mpv_boost_and_subtitles():
    o = player.mpv_options(1, boost=True, subtitle_scale=1.3, platform="win32", environ={})
    assert o["volume_max"] == "150" and o["sub_scale"] == "1.3"
    assert "dynaudnorm" in player.NORMALIZE_FILTER
    assert player.subtitle_background_options(True)["sub-border-style"] == "background-box"


def test_wsl_gets_the_safe_video_output():
    o = player.mpv_options(1, platform="linux", environ={}, proc_version="Linux 5.15 microsoft-standard-WSL2")
    assert o["vo"] == "x11" and o["hwdec"] == "no"
    assert player.mpv_options(1, platform="linux", environ={"ALMP_VO": "gpu"}, proc_version="")["vo"] == "gpu"


def test_video_sizes():
    assert player.video_size_properties("fill") == {"keepaspect": True, "panscan": 1.0}
    assert player.video_size_properties("stretch")["keepaspect"] is False
    assert player.video_size_properties("bogus") == {"keepaspect": True, "panscan": 0.0}
    assert [player.next_video_size(m) for m in ("fit", "fill", "stretch", "?")] == ["fill", "stretch", "fit", "fit"]


class _Ev:
    def __init__(self, data):
        self.data = data


@pytest.mark.parametrize("data,expected", [({"reason": 0}, "EOF"), ({"reason": 4}, "ERROR"), (None, "UNKNOWN"),
                                           ({"reason": "end-file-reason.STOP"}, "STOP")])
def test_end_reason(data, expected):
    assert player.get_mpv_end_reason(_Ev(data)) == expected


# --- Windows media controls -------------------------------------------------------------


def test_button_handler_iid_is_the_winrt_one():
    # Known value from the Windows SDK headers for
    # TypedEventHandler<SystemMediaTransportControls, SystemMediaTransportControlsButtonPressedEventArgs>.
    assert smtc.IID_ButtonPressedHandler == "0557e996-7b23-5bae-aa81-ea0d671143a4"


def test_button_names():
    assert [smtc.button_name(i) for i in (0, 1, 6, 7, 2)] == ["play", "pause", "next", "previous", "stop"]
    assert smtc.button_name(42) == "unknown"


def test_crash_marker_is_detected_once(tmp_path):
    assert smtc.previous_start_crashed(tmp_path) is False
    smtc.marker_path(tmp_path).write_text("x", encoding="utf-8")
    assert smtc.previous_start_crashed(tmp_path) is True
    assert smtc.previous_start_crashed(tmp_path) is False


def test_media_controls_do_nothing_off_windows(monkeypatch):
    monkeypatch.setattr(smtc.sys, "platform", "linux")
    mc = smtc.WindowsMediaControls()
    assert mc.start(123) is False
    mc.set_status("playing")            # all safe no-ops without Windows
    mc.set_track("x")
    mc.stop()
