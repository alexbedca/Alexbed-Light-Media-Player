#!/usr/bin/env python3
# Alexbed Light Media Player (ALMP)
# Copyright (C) 2026 Alexander Bediako
# SPDX-License-Identifier: GPL-3.0-or-later
"""Reproducible playlist benchmark for ALMP (no screen needed, no sound, no network).

What it measures, for each size (default 100,000 and 250,000 files):
  1. window   The real ALMP window (mpv replaced by a stand-in) scans a folder of empty, generated
              files on disk: time until the first track is handed to the player, time until all are
              in the list, and the longest time the window thread was busy without a break
              ("UI stall", measured with a 5 ms heartbeat timer).
  2. model    Adding the same number of entries straight to the list model (no disk).
  3. filter   Search times (debounce not included) for a few typical queries.
  4. scroll   Jumping to random rows and repainting the list.
  5. sort     Natural sort keys + sort (this runs on a background thread in ALMP).
  6. memory   Process memory (RSS) before and after the list is filled.

Usage:
  python tools/bench_playlist.py                     # 100k and 250k, disk scan for 100k only
  python tools/bench_playlist.py --sizes 100000 --disk-sizes 100000 --json out.json
  python tools/bench_playlist.py --keep D:\\bench      # keep the generated folders for a manual test

Runs with QT_QPA_PLATFORM=offscreen. Numbers depend on the PC; report the machine with them.
The generated files are empty (0 bytes) and are deleted at the end unless --keep is given.
"""
import argparse
import gc
import json
import os
import platform
import random
import shutil
import statistics
import sys
import tempfile
import time
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

WORDS = ["Love", "Night", "Road", "Fire", "Rain", "Dream", "Gold", "Blue", "River", "Home",
         "Light", "Heart", "Dance", "Sky", "Moon", "Soul", "Wave", "Stone", "Wind", "Star"]


def rss_mb():
    """Resident memory of this process in MB (Linux /proc, Windows psapi, else 0)."""
    try:
        if sys.platform.startswith("linux"):
            with open("/proc/self/status", encoding="ascii") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1]) / 1024.0
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            class PMC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
            pmc = PMC()
            pmc.cb = ctypes.sizeof(PMC)
            ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(),
                                                     ctypes.byref(pmc), pmc.cb)
            return pmc.WorkingSetSize / (1024 * 1024)
    except Exception:          # noqa: BLE001
        return 0.0
    return 0.0


def synthetic_paths(n, seed=1234, per_folder=250, root="D:\\Music"):
    rng = random.Random(seed)
    out = []
    for i in range(n):
        album = i // per_folder + 1
        out.append(f"{root}\\Artist {album % 400:03d}\\Album {album:04d}\\"
                   f"{i % per_folder + 1:03d} - {rng.choice(WORDS)} {rng.choice(WORDS)} {i + 1:06d}.mp3")
    return out


def make_disk_library(folder, n, per_folder=250, seed=1234):
    rng = random.Random(seed)
    t = time.perf_counter()
    for i in range(n):
        if i % per_folder == 0:
            sub = os.path.join(folder, f"Album {i // per_folder + 1:04d}")
            os.makedirs(sub, exist_ok=True)
        name = f"{i % per_folder + 1:03d} - {rng.choice(WORDS)} {rng.choice(WORDS)} {i + 1:06d}.mp3"
        open(os.path.join(sub, name), "wb").close()
    return time.perf_counter() - t


class Heartbeat:
    """A 5 ms timer on the window thread. Gaps between its ticks show how long the thread was busy."""

    def __init__(self):
        from PyQt6.QtCore import QTimer
        self.gaps = []
        self._last = None
        self.timer = QTimer()
        self.timer.setInterval(5)
        self.timer.timeout.connect(self._tick)

    def _tick(self):
        now = time.perf_counter()
        if self._last is not None:
            self.gaps.append((now - self._last) * 1000.0)
        self._last = now

    def start(self):
        self.gaps = []
        self._last = time.perf_counter()
        self.timer.start()

    def stop(self):
        self.timer.stop()
        g = sorted(self.gaps) or [0.0]
        return {"max_ms": round(g[-1], 1), "p99_ms": round(g[int(len(g) * 0.99) - 1 if len(g) > 1 else 0], 1),
                "over_50ms": sum(1 for x in g if x > 50.0), "ticks": len(g)}


class FakeMPV:
    def __init__(self, **opts):
        self.volume = 100
        self.pause = False
        self.idle_active = True
        self.time_pos = None
        self.duration = None
        self.speed = 1.0
        self.track_list = []
        self.first_load_time = None

    def event_callback(self, name):
        return lambda fn: fn

    def loadfile(self, path, mode="replace", **o):
        if self.first_load_time is None:
            self.first_load_time = time.perf_counter()
        self.idle_active = False

    def stop(self):
        self.idle_active = True

    def terminate(self):
        pass

    def command(self, *a):
        pass

    def command_async(self, *a):
        pass

    def __setitem__(self, k, v):
        pass

    def __getitem__(self, k):
        return ""


def pump_until(app, cond, timeout):
    end = time.perf_counter() + timeout
    while time.perf_counter() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.001)
    return False


def bench_window(app, folder, n, tmp_settings):
    """End to end: the real window scans the folder."""
    from almp import settings, ui
    settings.SETTINGS_DIR = Path(tmp_settings)
    settings.SETTINGS_PATH = Path(tmp_settings) / "settings.json"
    ui.mpv = types.SimpleNamespace(MPV=FakeMPV)
    ui.load_positions = lambda folder=None: {}
    ui.forget_positions = lambda folder=None: False
    w = ui.MediaWindow()
    w.resize(1200, 700)
    w.show()
    app.processEvents()
    gc.collect()
    mem0 = rss_mb()
    hb = Heartbeat()
    hb.start()
    t0 = time.perf_counter()
    w.scan_targets([folder])
    done = pump_until(app, lambda: not w._scan_active and not w._pending and not w._chunk_running, 600)
    t_all = time.perf_counter() - t0
    stall = hb.stop()
    first = (w.player.first_load_time - t0) if w.player.first_load_time else None
    mem1 = rss_mb()
    res = {"files": len(w.store), "complete": done, "first_track_s": round(first, 3) if first else None,
           "all_in_list_s": round(t_all, 2), "ui_stall": stall,
           "rss_before_mb": round(mem0, 1), "rss_after_mb": round(mem1, 1)}
    # search through the window's own path (model + count label)
    times = []
    for q in ("love", "night 0001", "zzz", "album 0042"):
        w.search_edit.blockSignals(True)
        w.search_edit.setText(q)
        w.search_edit.blockSignals(False)
        t = time.perf_counter()
        w._apply_filter()
        app.processEvents()
        times.append(round((time.perf_counter() - t) * 1000, 1))
    w.search_edit.blockSignals(True)
    w.search_edit.setText("")
    w.search_edit.blockSignals(False)
    w._apply_filter()
    res["window_filter_ms"] = times
    w.close()
    app.processEvents()
    w.deleteLater()
    app.processEvents()
    return res


def bench_model(app, n):
    from PyQt6.QtWidgets import QAbstractItemView

    from almp.naturalsort import natural_name_key, natural_path_key
    from almp.playlist_model import PlaylistModel
    from almp.store import make_entry
    from almp.widgets import PlaylistView

    paths = synthetic_paths(n)
    gc.collect()
    mem0 = rss_mb()
    t = time.perf_counter()
    entries = [make_entry(p) for p in paths]
    t_entries = time.perf_counter() - t           # done on the scanner thread in ALMP

    model = PlaylistModel()
    view = PlaylistView()
    view.setModel(model)
    view.resize(400, 700)
    view.show()
    app.processEvents()
    chunk = 5000
    chunk_ms = []
    t = time.perf_counter()
    first_row = None
    for i in range(0, n, chunk):
        c0 = time.perf_counter()
        model.append_entries(entries[i:i + chunk])
        app.processEvents()
        chunk_ms.append((time.perf_counter() - c0) * 1000)
        if first_row is None:
            first_row = time.perf_counter() - t
    t_model = time.perf_counter() - t
    del entries
    gc.collect()
    mem1 = rss_mb()

    filt = {}
    for q in ("e", "love", "love night", "zzz", "album 0042", "000123"):
        t = time.perf_counter()
        shown = model.set_filter(q)
        app.processEvents()
        filt[q] = {"ms": round((time.perf_counter() - t) * 1000, 1), "shown": shown}
    # typing one more letter: only the previous matches are searched
    model.set_filter("lo")
    t = time.perf_counter()
    model.set_filter("lov")
    filt["lo -> lov (refine)"] = {"ms": round((time.perf_counter() - t) * 1000, 1), "shown": model.rowCount()}
    model.set_filter("")
    app.processEvents()

    rng = random.Random(5)
    scroll = []
    for _ in range(200):
        row = rng.randrange(n)
        t = time.perf_counter()
        view.scrollTo(model.index(row), QAbstractItemView.ScrollHint.PositionAtCenter)
        view.viewport().repaint()
        scroll.append((time.perf_counter() - t) * 1000)

    model.set_current(n // 2)
    t = time.perf_counter()
    src = n // 3
    model.remove_source(src)
    t_remove = (time.perf_counter() - t) * 1000
    t = time.perf_counter()
    model.move_source(10, n // 2)
    t_move = (time.perf_counter() - t) * 1000

    snapshot = list(model.store.paths)
    t = time.perf_counter()
    keys = [natural_name_key(p) for p in snapshot]
    order = sorted(range(len(snapshot)), key=keys.__getitem__)
    t_sort_name = time.perf_counter() - t
    t = time.perf_counter()
    keys = [natural_path_key(p) for p in snapshot]
    order = sorted(range(len(snapshot)), key=keys.__getitem__)
    t_sort_path = time.perf_counter() - t
    t = time.perf_counter()
    model.reorder(order)
    app.processEvents()
    t_apply = (time.perf_counter() - t) * 1000
    view.close()

    return {
        "entries_s_scanner_thread": round(t_entries, 3),
        "model_add_all_s": round(t_model, 3),
        "first_rows_visible_ms": round(first_row * 1000, 1),
        "chunk_ms_max": round(max(chunk_ms), 1),
        "chunk_ms_median": round(statistics.median(chunk_ms), 1),
        "rss_growth_mb": round(mem1 - mem0, 1),
        "filter": filt,
        "scroll_ms_avg": round(statistics.mean(scroll), 2),
        "scroll_ms_max": round(max(scroll), 2),
        "remove_one_ms": round(t_remove, 2),
        "move_one_ms": round(t_move, 2),
        "sort_by_name_s_background": round(t_sort_name, 2),
        "sort_by_folder_s_background": round(t_sort_path, 2),
        "apply_sorted_order_ms": round(t_apply, 1),
    }


def compare_views(app, n):
    """Why ALMP uses a one-column table: rows added to a QListView vs a QTableView (same model)."""
    from PyQt6.QtWidgets import QListView

    from almp.playlist_model import PlaylistModel
    from almp.store import make_entry
    from almp.widgets import PlaylistView

    entries = [make_entry(p) for p in synthetic_paths(n, seed=99, root="E:\\Cmp")]
    out = {}
    for name in ("QListView (uniform sizes)", "PlaylistView (QTableView, fixed rows)"):
        model = PlaylistModel()
        if name.startswith("QListView"):
            view = QListView()
            view.setUniformItemSizes(True)
        else:
            view = PlaylistView()
        view.setModel(model)
        view.resize(400, 700)
        view.show()
        app.processEvents()
        times = []
        for i in range(0, n, 5000):
            t = time.perf_counter()
            model.append_entries(entries[i:i + 5000])
            app.processEvents()
            times.append((time.perf_counter() - t) * 1000)
        t = time.perf_counter()
        model.set_filter("e")
        app.processEvents()
        f = (time.perf_counter() - t) * 1000
        out[name] = {"add_chunk_ms_median": round(statistics.median(times), 1),
                     "add_chunk_ms_last": round(times[-1], 1), "filter_e_ms": round(f, 1)}
        view.close()
        view.deleteLater()
        app.processEvents()
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sizes", default="100000,250000", help="list sizes for the model tests")
    ap.add_argument("--disk-sizes", default="100000", help="sizes for the end-to-end disk scan ('' to skip)")
    ap.add_argument("--json", help="write the results to this file")
    ap.add_argument("--keep", help="create the disk library here and keep it (for a manual test in ALMP)")
    args = ap.parse_args(argv)

    from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR
    from PyQt6.QtWidgets import QApplication

    from almp import __version__
    from almp.theme import stylesheet
    app = QApplication.instance() or QApplication(["almp-bench"])
    app.setStyleSheet(stylesheet(False))

    info = {"almp": __version__, "python": platform.python_version(), "qt": QT_VERSION_STR, "pyqt": PYQT_VERSION_STR,
            "platform": platform.platform(), "machine": platform.machine(), "cpu_count": os.cpu_count(),
            "qpa": app.platformName()}
    results = {"info": info, "model": {}, "window": {}}
    print(json.dumps(info))

    for n in [int(x) for x in args.sizes.split(",") if x.strip()]:
        r = bench_model(app, n)
        results["model"][str(n)] = r
        print(f"\n== model, {n:,} entries ==")
        print(json.dumps(r, indent=1))

    results["view_comparison_100k"] = compare_views(app, 100_000)
    print("\n== view comparison, 100,000 rows added 5,000 at a time ==")
    print(json.dumps(results["view_comparison_100k"], indent=1))

    for n in [int(x) for x in args.disk_sizes.split(",") if x.strip()]:
        base = args.keep or tempfile.mkdtemp(prefix="almp-bench-")
        folder = os.path.join(base, f"lib-{n}")
        tmp_settings = tempfile.mkdtemp(prefix="almp-bench-settings-")
        try:
            t_make = make_disk_library(folder, n)
            r = bench_window(app, folder, n, tmp_settings)
            r["create_files_s"] = round(t_make, 1)
            results["window"][str(n)] = r
            print(f"\n== window, scan {n:,} files on disk ==")
            print(json.dumps(r, indent=1))
        finally:
            shutil.rmtree(tmp_settings, ignore_errors=True)
            if not args.keep:
                shutil.rmtree(base, ignore_errors=True)

    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
