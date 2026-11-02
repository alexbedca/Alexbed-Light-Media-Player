"""Loop Off / One / All: cycling, what plays after a track ends, and that the loop is never saved."""
import json
import random

import pytest

import main
from almp import settings as almp_settings
from main import LOOP_ALL, LOOP_OFF, LOOP_ONE
from main import decide_after_track_end as decide

from conftest import ROOT

# --- cycling ---------------------------------------------------------------

def test_loop_cycles_off_one_all_off():
    assert main.next_loop_mode(LOOP_OFF) == LOOP_ONE
    assert main.next_loop_mode(LOOP_ONE) == LOOP_ALL
    assert main.next_loop_mode(LOOP_ALL) == LOOP_OFF


def test_unknown_loop_mode_counts_as_off():
    assert main.next_loop_mode("loop_single") == LOOP_ONE
    assert main.next_loop_mode(None) == LOOP_ONE


def test_every_mode_has_a_clear_label_and_tooltip():
    assert main.LOOP_LABELS == {LOOP_OFF: "Loop: Off", LOOP_ONE: "Loop: One", LOOP_ALL: "Loop: All"}
    for mode in main.LOOP_MODES:
        assert "(L)" in main.LOOP_TIPS[mode]
    assert "Remove played" in main.LOOP_TIPS[LOOP_ALL]


# --- empty and single-track lists -----------------------------------------

@pytest.mark.parametrize("mode", main.LOOP_MODES)
@pytest.mark.parametrize("shuffle", [False, True])
@pytest.mark.parametrize("remove", [False, True])
def test_empty_list_always_stops(mode, shuffle, remove):
    assert decide(0, -1, mode, shuffle, remove, True) == ("stop", -1)
    assert decide(0, 3, mode, shuffle, remove, False) == ("stop", -1)


@pytest.mark.parametrize("shuffle", [False, True])
def test_single_track(shuffle):
    assert decide(1, 0, LOOP_OFF, shuffle, False, all_played=True) == ("stop", -1)
    assert decide(1, 0, LOOP_ONE, shuffle, False, all_played=True) == ("replay", 0)
    assert decide(1, 0, LOOP_ONE, shuffle, True, all_played=True) == ("replay", 0)
    expected = ("new_round", -1) if shuffle else ("play", 0)
    assert decide(1, 0, LOOP_ALL, shuffle, False, all_played=True) == expected
    assert decide(1, 0, LOOP_ALL, shuffle, True, all_played=True) == expected
    # Remove played with Loop Off: the last track is removed and the list is finished
    assert decide(1, 0, LOOP_OFF, shuffle, True, all_played=True) == ("remove", 0)


def test_single_track_shuffle_new_round_picks_the_only_track():
    played = {"a"}
    assert main.pick_shuffle_index(["a"], played, 0) == 0


# --- Loop Off ----------------------------------------------------------------

def test_off_in_order_plays_next_then_stops_at_the_end():
    assert decide(3, 0, LOOP_OFF, False, False) == ("play", 1)
    assert decide(3, 1, LOOP_OFF, False, False) == ("play", 2)
    assert decide(3, 2, LOOP_OFF, False, False) == ("stop", -1)


def test_off_shuffle_stops_when_every_track_was_played():
    assert decide(5, 2, LOOP_OFF, True, False, all_played=False) == ("shuffle", -1)
    assert decide(5, 2, LOOP_OFF, True, False, all_played=True) == ("stop", -1)


@pytest.mark.parametrize("shuffle", [False, True])
def test_off_with_remove_played_removes(shuffle):
    assert decide(4, 3, LOOP_OFF, shuffle, True, all_played=True) == ("remove", 3)


# --- Loop One ------------------------------------------------------------------

@pytest.mark.parametrize("shuffle", [False, True])
@pytest.mark.parametrize("remove", [False, True])
def test_one_replays_the_playing_track(shuffle, remove):
    for i in range(4):
        assert decide(4, i, LOOP_ONE, shuffle, remove, all_played=False) == ("replay", i)


def test_one_without_a_playing_track_falls_back_safely():
    # nothing valid is playing (e.g. it was removed): behave like Off, never crash
    assert decide(3, -1, LOOP_ONE, False, False) == ("play", 0)
    assert decide(3, 7, LOOP_ONE, False, True) == ("play", 0)
    assert decide(3, -1, LOOP_ONE, True, False, all_played=False) == ("shuffle", -1)


# --- Loop All ------------------------------------------------------------------

def test_all_in_order_goes_back_to_the_first_track():
    assert decide(3, 1, LOOP_ALL, False, False) == ("play", 2)
    assert decide(3, 2, LOOP_ALL, False, False) == ("play", 0)


def test_all_never_removes_played_tracks():
    assert decide(3, 1, LOOP_ALL, False, True) == ("play", 2)
    assert decide(3, 2, LOOP_ALL, False, True) == ("play", 0)
    assert decide(3, 2, LOOP_ALL, True, True, all_played=False) == ("shuffle", -1)
    assert decide(3, 2, LOOP_ALL, True, True, all_played=True) == ("new_round", -1)


def test_all_shuffle_plays_everything_then_starts_a_new_round():
    files = [f"t{i}" for i in range(6)]
    rng = random.Random(7)
    played = set()
    current = 0
    played.add(files[current])
    heard = [files[current]]
    rounds = 0
    for _ in range(len(files) * 3 - 1):
        all_played = all(p in played for p in files)
        action, _ = decide(len(files), current, LOOP_ALL, True, True, all_played)
        assert action in ("shuffle", "new_round")
        if action == "new_round":
            rounds += 1
            played.clear()
        nxt = main.pick_shuffle_index(files, played, current, rng)
        assert nxt != current                    # never the same track twice in a row
        current = nxt
        played.add(files[current])
        heard.append(files[current])
    # every round of 6 contains every track exactly once
    for r in range(3):
        assert sorted(heard[r * 6:(r + 1) * 6]) == sorted(files)
    assert rounds == 2


# --- safety -----------------------------------------------------------------------

@pytest.mark.parametrize("mode", [LOOP_ONE, LOOP_ALL])
def test_loop_stops_when_files_keep_ending_at_once(mode):
    limit = main.LOOP_QUICK_END_LIMIT
    assert decide(1, 0, mode, False, False, True, quick_end_streak=limit - 1)[0] != "stop"
    assert decide(1, 0, mode, False, False, True, quick_end_streak=limit) == ("stop", -1)


def test_out_of_range_index_never_returns_a_bad_index():
    for n in range(0, 4):
        for cur in (-5, -1, 0, 1, 2, 3, 10):
            for mode in main.LOOP_MODES:
                for shuffle in (False, True):
                    for remove in (False, True):
                        for allp in (False, True):
                            action, idx = decide(n, cur, mode, shuffle, remove, allp)
                            if action in ("play", "replay", "remove"):
                                assert 0 <= idx < n


# --- not saved ------------------------------------------------------------------

def test_settings_to_save_never_contains_loop():
    old = {"volume": 40, "loop_single": True, "remember_playlist": True,
           "high_contrast": True, "ui_scale": 1.5}
    data = main.settings_to_save(old, 70, False, True)
    assert data == {"volume": 70, "shuffle": False, "remove_played": True,
                    "high_contrast": True, "ui_scale": 1.5}
    assert not any("loop" in k for k in data)
    assert old["loop_single"] is True          # the input dict is not changed


def test_legacy_keys_include_loop_single():
    assert "loop_single" in main.LEGACY_SETTINGS_KEYS
    assert "remember_playlist" in main.LEGACY_SETTINGS_KEYS


def test_old_settings_file_loses_loop_single(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"volume": 55, "loop_single": True, "shuffle": True}), encoding="utf-8")
    monkeypatch.setattr(almp_settings, "SETTINGS_PATH", path)
    main.save_settings(main.settings_to_save(main.load_settings(), 55, True, False))
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert "loop_single" not in saved
    assert saved["volume"] == 55


def test_settings_to_save_handles_a_broken_file():
    assert main.settings_to_save(None, 100, True, True) == {"volume": 100, "shuffle": True, "remove_played": True}
    assert main.settings_to_save(["x"], 100, True, True)["volume"] == 100


def test_loop_mode_is_not_read_from_settings():
    src = (ROOT / "almp" / "ui.py").read_text(encoding="utf-8")
    apply_part = src.split("def _apply_settings", 1)[1].split("\n    def ", 1)[0]
    assert "loop" not in apply_part


# --- Loop All switches "Remove played" off for a while ----------------------------

def test_loop_all_turns_remove_played_off_and_greys_it_out():
    assert main.remove_played_for_loop(LOOP_ALL, True, None) == (False, False, True)
    assert main.remove_played_for_loop(LOOP_ALL, False, None) == (False, False, False)


@pytest.mark.parametrize("leave_to", [LOOP_OFF, LOOP_ONE])
@pytest.mark.parametrize("before", [True, False])
def test_leaving_loop_all_restores_remove_played(before, leave_to):
    checked, enabled, saved = main.remove_played_for_loop(LOOP_ALL, before, None)
    assert main.remove_played_for_loop(leave_to, checked, saved) == (before, True, None)


def test_full_cycle_restores_and_never_loses_the_choice():
    checked, saved, mode = True, None, LOOP_OFF
    for _ in range(7):                                   # Off > One > All > Off > ...
        mode = main.next_loop_mode(mode)
        checked, enabled, saved = main.remove_played_for_loop(mode, checked, saved)
        assert enabled == (mode != LOOP_ALL)
        assert main.remove_played_to_save(checked, saved) is True
    # user unticks it outside Loop All: that is kept too
    checked, enabled, saved = main.remove_played_for_loop(LOOP_OFF, False, None)
    assert (checked, enabled, saved) == (False, True, None)


def test_entering_loop_all_twice_keeps_the_first_saved_value():
    _, _, saved = main.remove_played_for_loop(LOOP_ALL, True, None)
    assert main.remove_played_for_loop(LOOP_ALL, False, saved) == (False, False, True)


@pytest.mark.parametrize("before", [True, False])
def test_closing_during_loop_all_saves_the_real_preference(before):
    checked, _, saved = main.remove_played_for_loop(LOOP_ALL, before, None)
    value = main.remove_played_to_save(checked, saved)
    assert value is before
    assert main.settings_to_save({}, 80, True, value)["remove_played"] is before


def test_remove_played_to_save_without_override():
    assert main.remove_played_to_save(True, None) is True
    assert main.remove_played_to_save(False, None) is False
