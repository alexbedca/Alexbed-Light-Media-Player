"""Linux smoke test of the REAL ALMP window with the REAL mpv engine on a real desktop (X11).

Not a pytest test: it needs a display, libmpv and test media. It drives ALMP the way the user would
(through the same window methods the buttons and keys call), checks mpv's own state after each step,
saves screenshots, and prints one PASS/FAIL line per function. Nothing is downloaded; files are only
created/deleted under the --work folder (the delete test uses a copy).

    DISPLAY=:0 python tools/linux_smoke.py --media ~/testmedia --work /tmp/almp-smoke [--big 100000]
"""
import argparse
import locale
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RESULTS = []


def record(name, ok, detail=""):
    RESULTS.append((name, "PASS" if ok else "FAIL", detail))
    print(f"{'PASS' if ok else 'FAIL'} | {name} | {detail}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--media", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--big", type=int, default=100000, help="files in the huge-playlist test (0 = skip)")
    ap.add_argument("--shots", default=str(Path.home() / "shots"))
    args = ap.parse_args()

    work = Path(args.work)
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    shots = Path(args.shots)
    shots.mkdir(parents=True, exist_ok=True)
    os.environ["ALMP_DATA_DIR"] = str(work / "Data")
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

    from PyQt6.QtCore import QEventLoop, Qt, QTimer
    from PyQt6.QtGui import QGuiApplication
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication

    from almp import paths
    paths.init_data_dir()
    app = QApplication(["ALMP"])
    app.setApplicationName("ALMP")
    locale.setlocale(locale.LC_NUMERIC, "C")
    from almp.theme import stylesheet
    app.setStyleSheet(stylesheet(False))
    from almp import ui

    def wait(ms):
        loop = QEventLoop()
        QTimer.singleShot(int(ms), loop.quit)
        loop.exec()

    def wait_for(cond, timeout=10.0, step=50):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                if cond():
                    return True
            except Exception:          # noqa: BLE001, S110 - not ready yet
                pass
            wait(step)
        return False

    def shot(name):
        screen = QGuiApplication.primaryScreen()
        pix = screen.grabWindow(0)
        out = shots / f"{name}.png"
        pix.save(str(out))
        return out

    media = Path(args.media).expanduser()
    lib = work / "lib"
    shutil.copytree(media, lib)
    music = sorted((lib / "music").glob("*.mp3"))
    flac = lib / "music" / "Tone 24-96.flac"
    video = lib / "video" / "big-buck-bunny-480p-30sec.mp4"
    small = lib / "video" / "sample-5s-360p.mp4"

    t0 = time.perf_counter()
    w = ui.MediaWindow()
    w.show()
    wait_for(lambda: w.isVisible() and w.player is not None, 10)
    record("Window + mpv engine start", w.player is not None, f"{time.perf_counter() - t0:.2f} s to window + engine")

    # --- open a folder, play music
    w.scan_targets([str(lib / "music")])
    ok = wait_for(lambda: w.model.rowCount() == 4, 10)
    record("Add folder (4 songs)", ok, f"{w.model.rowCount()} rows")
    w.shuffle_checkbox.setChecked(False)
    w.play_index(0)
    ok = wait_for(lambda: (w.player.time_pos or 0) > 1.0, 10)
    record("Music plays (clock moves)", ok, f"time-pos {w.player.time_pos:.1f} s, ao={w.player.current_ao}")
    ok = wait_for(lambda: w.format_label.isVisible() and "MP3" in w.format_label.text(), 5)
    record("Format label MP3", ok, w.format_label.text())
    ok = wait_for(lambda: "Sympathique" in w.time_label.text() or w.time_label.text() != "00:00 / 00:00", 3)
    record("Time label updates", ok, w.time_label.text())

    i = w.store.paths.index(str(flac))
    w.play_index(i)
    ok = wait_for(lambda: "FLAC" in w.format_label.text() and "96" in w.format_label.text(), 6)
    record("Format label FLAC 24/96", ok, w.format_label.text())
    shot("01-music")

    # --- volume, mute, speed, ReplayGain
    w.volume_slider.setValue(40)
    ok = wait_for(lambda: abs(float(w.player.volume) - 40) < 0.5, 3)
    record("Volume slider -> mpv volume", ok, f"mpv volume {w.player.volume}")
    w._toggle_mute()                       # ALMP mutes by setting the volume to 0 (as on Windows)
    m1 = float(w.player.volume)
    w._toggle_mute()
    record("Mute on/off (M)", m1 == 0 and abs(float(w.player.volume) - 40) < 0.5,
           f"volume 40 -> {m1:g} -> {float(w.player.volume):g}")
    w.set_replaygain("track")
    w.play_index(0)
    wait_for(lambda: (w.player.time_pos or 0) > 0.3, 6)
    rg = w.player._get_property("replaygain")
    record("ReplayGain setting reaches mpv", rg == "track", f"replaygain={rg}")
    w.set_replaygain("off")

    # --- video, subtitles, fullscreen
    w.scan_targets([str(lib / "video")])
    wait_for(lambda: w.model.rowCount() == 7, 10)      # 4 songs + 3 videos
    w.play_index(w.store.paths.index(str(video)))
    ok = wait_for(lambda: (w.player.width or 0) > 0 and (w.player.time_pos or 0) > 1.0, 15)
    vo = w.player._get_property("current-vo")
    try:
        ctx = w.player._get_property("current-gpu-context")
    except Exception:          # noqa: BLE001 - older mpv
        ctx = "?"
    # On Wayland mpv's own Wayland output means a second window: the video would not be inside ALMP.
    inside = not str(ctx).startswith("wayland")
    record("Video plays in the window", ok and inside, f"{w.player.width}x{w.player.height}, vo={vo}, "
           f"gpu-context={ctx}, hwdec={w.player._get_property('hwdec-current')}")
    w.set_show_subtitles(True, announce=False)
    ok = wait_for(lambda: any(t.get("type") == "sub" for t in w.player.track_list), 5)
    vis = w.player._get_property("sub-visibility")
    record("Subtitles (.srt next to video) loaded and shown", ok and vis, f"sub tracks found={ok}, visible={vis}")
    wait(1500)
    shot("02-video-subtitles")

    w._toggle_fullscreen()
    ok = wait_for(lambda: w.isFullScreen(), 5)
    wait(800)
    w._show_fs_overlays()
    wait(300)
    shot("03-fullscreen-controls")
    record("Fullscreen on", ok, f"{w.width()}x{w.height()}")
    QTest.keyClick(w.video, Qt.Key.Key_Space)
    p1 = bool(w.player.pause)
    QTest.keyClick(w.video, Qt.Key.Key_Space)
    record("Space pauses/plays (fullscreen)", p1 and not bool(w.player.pause), f"pause {p1} -> {w.player.pause}")
    pos = w.player.time_pos or 0
    QTest.keyClick(w.video, Qt.Key.Key_Right)
    ok = wait_for(lambda: (w.player.time_pos or 0) > pos + 3, 4)
    record("Right arrow seeks forward", ok, f"{pos:.1f} -> {w.player.time_pos:.1f}")
    w._toggle_fullscreen()
    ok = wait_for(lambda: not w.isFullScreen(), 5)
    record("Fullscreen off", ok, f"{w.width()}x{w.height()}")

    # --- sharpening (FSRCNNX) on the 360p video
    w.set_enhance("auto")
    w.play_index(w.store.paths.index(str(small)))
    ok = wait_for(lambda: (w.player.width or 0) > 0 and (w.player.time_pos or 0) > 0.5, 15)
    wait_for(lambda: bool(w.player._get_property("glsl-shaders")), 6)
    shaders = w.player._get_property("glsl-shaders") or []
    wait(4500)
    drops = w.player._get_property("frame-drop-count")
    record("Sharpening (FSRCNNX) applied to 360p video", bool(shaders),
           f"shaders={[os.path.basename(s) for s in shaders]}, dropped frames={drops}, "
           f"still on={bool(w.player._get_property('glsl-shaders'))}")

    # --- search and filters
    w.search_edit.setText("lemonade")
    wait_for(lambda: w.model.rowCount() == 1, 3)
    record("Search 'lemonade'", w.model.rowCount() == 1, f"{w.model.rowCount()} row(s)")
    w.search_edit.setText("")
    wait_for(lambda: w.model.rowCount() == 7, 3)
    w.set_kind_filter("video")
    nv = w.model.rowCount()
    w.set_kind_filter("audio")
    na = w.model.rowCount()
    w.set_kind_filter("all")
    record("Filters Video / Audio / All", (nv, na, w.model.rowCount()) == (3, 4, 7),
           f"video={nv} audio={na} all={w.model.rowCount()}")

    # --- multi-select remove from list (files kept)
    from PyQt6.QtCore import QItemSelectionModel
    sm = w.playlist.selectionModel()

    def select(rows):
        sm.clearSelection()
        flag = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
        for r in rows:
            sm.select(w.model.index(r), flag)
    before = list(w.store.paths)
    select([1, 2])
    w.remove_from_playlist()
    removed = [p for p in before if p not in w.store.paths]
    record("Multi-select remove from list", len(removed) == 2 and all(os.path.exists(p) for p in removed),
           f"{len(w.store.paths)} left, files kept={all(os.path.exists(p) for p in removed)}")

    # --- delete to Trash (a copy made for the test), question answered Yes
    victim = lib / "music" / "Trash test ｜ copy.mp3"
    shutil.copy(music[0], victim)
    w.scan_targets([str(victim)])
    wait_for(lambda: str(victim) in w.store.paths, 5)
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
    real_dialog = ui.CustomConfirmDialog
    ui.CustomConfirmDialog = Yes
    try:
        row = w.model.view_row(w.store.paths.index(str(victim)))
        select([row])
        w.playlist.setCurrentIndex(w.model.index(row))
        w.delete_selected_file()
        wait(500)
    finally:
        ui.CustomConfirmDialog = real_dialog
    trash = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "Trash"
    in_trash = (trash / "files" / victim.name).exists() and (trash / "info" / f"{victim.name}.trashinfo").exists()
    record("Delete -> Trash (restorable)", in_trash and not victim.exists(),
           f"asked: {asked[0][0] if asked else None!r} / {asked[0][2] if asked else ''!r}; in Trash={in_trash}")
    if in_trash:      # leave no test files in the user's Trash
        (trash / "files" / victim.name).unlink()
        (trash / "info" / f"{victim.name}.trashinfo").unlink()

    # --- a file on a RAM disk (/tmp is tmpfs on Debian 13): no Trash, the permanent-delete question
    from almp import platform_win as pw
    ram = Path("/dev/shm/almp-smoke-ram.mp3")
    shutil.copy(music[0], ram)
    record("RAM disk file: no Trash offered", not pw.recycle_bin_available(str(ram)),
           f"recycle_bin_available={pw.recycle_bin_available(str(ram))}")
    ram.unlink()

    # --- sleep timer
    w.set_sleep_timer(5)
    on = w._sleep_timer.isActive()
    left = w._sleep_minutes_left()
    w.extend_sleep_timer()
    left2 = w._sleep_minutes_left()
    w.set_sleep_timer(0)
    record("Sleep timer 5 min, +15, off", on and left2 > left and not w._sleep_timer.isActive(),
           f"left {left} -> {left2} min")

    # --- high contrast + Settings window
    w.set_high_contrast(True)
    wait(400)
    shot("04-high-contrast")
    record("High contrast on", bool(w.settings["high_contrast"]), "see 04-high-contrast.png")
    w.set_high_contrast(False)
    w.show_settings()
    wait(800)
    shot("05-settings")
    from PyQt6.QtWidgets import QDialog
    dlg = [d for d in app.topLevelWidgets() if isinstance(d, QDialog) and d.isVisible()]
    has_linux = bool(dlg) and hasattr(dlg[0], "menu_entry")
    record("Settings opens with the Linux section", has_linux, f"dialogs={[type(d).__name__ for d in dlg]}")
    for d in dlg:
        d.close()

    # --- continue long files (20+ minutes) where they stopped
    long_dir = lib / "long"
    if long_dir.is_dir():
        long_file = next(long_dir.glob("*.mp3"))
        w.scan_targets([str(long_dir)])
        wait_for(lambda: str(long_file) in w.store.paths, 5)
        w.set_resume_long_files(True)
        w.play_index(w.store.paths.index(str(long_file)))
        wait_for(lambda: (w.player.duration or 0) > 1200 and (w.player.time_pos or 0) > 0.2, 10)
        w.player.seek(600, reference="absolute")
        wait_for(lambda: (w.player.time_pos or 0) > 600, 5)
        other = next(p for p in w.store.paths if p != str(long_file))
        w.play_index(w.store.paths.index(other))                   # switch away: the place is saved
        wait_for(lambda: w.current_path == other and (w.player.time_pos or 0) > 0.2, 6)
        w.play_index(w.store.paths.index(str(long_file)))
        ok = wait_for(lambda: w.current_path == str(long_file) and 595 < (w.player.time_pos or 0) < 620, 8)
        record("Continue long files where stopped", ok,
               f"started again at {w.player.time_pos or 0:.0f} s (stopped at ~600 s)")
        w.set_resume_long_files(False)

    # --- huge playlist
    if args.big:
        big = work / "big"
        os.system(f'"{sys.executable}" "{ROOT / "tools" / "make_test_library.py"}" "{big}" {args.big} > /dev/null')
        t = time.perf_counter()
        w.scan_targets([str(big)])
        first = wait_for(lambda: w.model.rowCount() > 0, 30, 10)
        t_first = time.perf_counter() - t
        done = wait_for(lambda: not w.any_scan_running() and len(w.store) >= args.big, 300, 100)
        t_all = time.perf_counter() - t
        record(f"Huge playlist ({args.big:,} files)", first and done,
               f"first rows after {t_first:.2f} s, all {len(w.store):,} after {t_all:.1f} s")
        t = time.perf_counter()
        w.search_edit.setText("love")
        wait_for(lambda: w.model.rowCount() < len(w.store), 10, 10)
        record("Search in huge playlist", w.model.rowCount() < len(w.store),
               f"{w.model.rowCount():,} hits in {time.perf_counter() - t:.2f} s")
        w.search_edit.setText("")

    t = time.perf_counter()
    w.close()
    wait(200)
    record("Close", not w.isVisible(), f"{time.perf_counter() - t:.2f} s")
    print("SUMMARY", sum(r[1] == "PASS" for r in RESULTS), "pass,", sum(r[1] == "FAIL" for r in RESULTS), "fail")
    return 0


if __name__ == "__main__":
    sys.exit(main())
