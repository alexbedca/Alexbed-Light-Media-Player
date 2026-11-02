"""Version checks, single-instance retry, sleep timer maths and old-file clean-up."""
import subprocess
import sys

import pytest

import main

from conftest import ROOT

sys.path.insert(0, str(ROOT / "tools"))
import get_version  # noqa: E402

# --- version -------------------------------------------------------------

@pytest.mark.parametrize("text", ["8.0.1", "10.20.30", "0.0.0"])
def test_valid_versions(text):
    assert main.is_valid_version(text)
    assert get_version.VERSION_RE.fullmatch(text)


@pytest.mark.parametrize("text", [
    "8.0", "v8.0.1", "8.0.1 ", " 8.0.1", "8.0.1\n", "8.0.1.0", "8.0.1 & calc", "8.0.1|x",
    "8.0.1%VER%", "", "8.0.a", "٨.٠.١",   # last one: Arabic-Indic digits must not count
])
def test_invalid_versions(text):
    assert not main.is_valid_version(text)
    assert get_version.VERSION_RE.fullmatch(text) is None


def test_get_version_reads_the_package_version():
    assert get_version.read_version(ROOT / "almp" / "__init__.py") == main.__version__
    assert get_version.read_version() == main.__version__
    out = subprocess.run([sys.executable, str(ROOT / "tools" / "get_version.py")],
                         capture_output=True, text=True, check=True).stdout.strip()
    assert out == main.__version__


def test_get_version_rejects_bad_value(tmp_path):
    bad = tmp_path / "__init__.py"
    bad.write_text('__version__ = "8.0.1 & echo hacked"\n', encoding="utf-8")
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "get_version.py"), str(bad)],
                       capture_output=True, text=True)
    assert r.returncode == 1 and r.stdout == ""


def test_version_is_the_same_in_the_docs():
    v = main.__version__
    assert f"**Version:** {v}" in (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"Version:       v{v}" in (ROOT / "README.txt").read_text(encoding="utf-8")
    assert (ROOT / "docs" / "release-notes" / f"v{v}.md").exists()


# --- single instance -----------------------------------------------------

class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def test_retry_succeeds_when_the_first_window_is_ready():
    clock = FakeClock()
    attempts = []

    def try_connect():
        attempts.append(clock.t)
        return clock.t >= 2.0          # the running ALMP needs 2 s to open its window

    assert main.connect_with_retry(try_connect, timeout_s=10, interval_s=0.25,
                                   sleep=clock.sleep, clock=clock)
    assert len(attempts) == 9 and attempts[-1] == pytest.approx(2.0)


def test_retry_gives_up_after_about_ten_seconds():
    clock = FakeClock()
    calls = []
    ok = main.connect_with_retry(lambda: calls.append(1) and False, timeout_s=10, interval_s=0.25,
                                 sleep=clock.sleep, clock=clock)
    assert not ok
    assert 10.0 <= clock.t <= 10.25
    assert len(calls) == 41


def test_retry_treats_errors_as_a_failed_attempt():
    clock = FakeClock()
    state = {"n": 0}

    def flaky():
        state["n"] += 1
        if state["n"] < 3:
            raise OSError("pipe busy")
        return True

    assert main.connect_with_retry(flaky, sleep=clock.sleep, clock=clock)
    assert state["n"] == 3


def test_ipc_name_is_per_user_and_safe():
    assert main.make_ipc_name("alice") == "ALMP-IPC-alice"
    assert main.make_ipc_name("alice") != main.make_ipc_name("bob")
    name = main.make_ipc_name("DOMAIN\\Jo Smith/../x")
    assert name.startswith("ALMP-IPC-") and "\\" not in name and "/" not in name and " " not in name
    assert main.make_ipc_name("") == "ALMP-IPC-user"


# --- sleep timer ---------------------------------------------------------

@pytest.mark.parametrize("ms,minutes", [
    (None, 0), (0, 0), (-5, 0), (1, 1), (59_000, 1), (60_000, 1), (60_001, 2),
    (23 * 60_000, 23), (3_600_000, 60), (7_200_000, 120),
])
def test_sleep_minutes_left(ms, minutes):
    assert main.sleep_minutes_left(ms) == minutes


# --- legacy history files ------------------------------------------------

def test_only_old_history_files_are_removed(tmp_path):
    for name in ("resume.json", "last_playlist.json", "last_playlist.tmp", "settings.json",
                 "startup_target.txt", "my-notes.txt"):
        (tmp_path / name).write_text("x", encoding="utf-8")
    removed = main.remove_legacy_history_files(tmp_path)
    assert sorted(removed) == ["last_playlist.json", "last_playlist.tmp", "resume.json"]
    left = sorted(p.name for p in tmp_path.iterdir())
    assert left == ["my-notes.txt", "settings.json", "startup_target.txt"]


def test_legacy_cleanup_ignores_missing_folder(tmp_path):
    assert main.remove_legacy_history_files(tmp_path / "nope") == []


def test_legacy_cleanup_does_not_follow_a_folder_named_like_the_file(tmp_path):
    (tmp_path / "resume.json").mkdir()
    assert main.remove_legacy_history_files(tmp_path) == []
    assert (tmp_path / "resume.json").is_dir()


# --- shuffle (unchanged behaviour, guarded by a test) ----------------------

def test_shuffle_never_repeats_the_current_track():
    import random
    files = [f"t{i}" for i in range(5)]
    played = set()
    rng = random.Random(1)
    seen = []
    cur = 0
    played.add(files[cur])
    for _ in range(4):
        cur = main.pick_shuffle_index(files, played, cur, rng)
        played.add(files[cur])
        seen.append(cur)
    assert sorted(seen) == [1, 2, 3, 4]


def test_tv_scale_auto_only_in_fullscreen():
    from almp.logic import tv_scale
    assert tv_scale("auto", False, 1080) == 1.0
    assert tv_scale("auto", True, 1080) == 2.0
    assert 1.4 < tv_scale("auto", True, 768) < 1.5
    assert tv_scale("auto", True, 4000) == 3.0           # capped
    assert tv_scale("auto", True, 300) == 1.0            # never smaller than normal


def test_tv_scale_modes_and_bad_input():
    from almp.logic import tv_scale
    assert tv_scale("never", True, 1080) == 1.0
    assert tv_scale("always", False, 1080) == 2.0
    assert tv_scale("always", False, 600) == 1.5          # at least 1.5x
    assert tv_scale("nonsense", True, 1080) == 2.0        # unknown -> auto
    assert tv_scale("auto", True, None) == 1.0
    assert tv_scale("auto", True, 0) == 1.0


def test_large_buttons_setting_default_and_validation():
    from almp.settings import effective_settings
    assert effective_settings({})["large_buttons"] == "auto"
    assert effective_settings({"large_buttons": "never"})["large_buttons"] == "never"
    assert effective_settings({"large_buttons": "x"})["large_buttons"] == "auto"
