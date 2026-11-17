#!/usr/bin/env python3
# Alexbed Light Media Player (ALMP)
# Copyright (C) 2026 Alexander Bediako
# SPDX-License-Identifier: GPL-3.0-or-later
"""Start-up benchmark: how long from starting ALMP with a file until the window shows and the file plays.

It starts the real ALMP (ALMP.exe, or `python main.py` from this folder) the way Explorer does when
you double-click a file, waits for the two start-up lines ALMP writes to almp.log
("Start-up: window shown after X s" and "Start-up: playing after Y s"), then closes ALMP.
It also prints the wall-clock time until the "playing" line appeared, which includes the time
before Python starts (loading the program files, antivirus checks).

Usage (Windows, with a real screen; sound plays briefly):
  python tools/bench_startup.py "D:\\Videos\\clip.mp4"                      # from source, 3 runs
  python tools/bench_startup.py "D:\\Videos\\clip.mp4" --exe "C:\\ALMP\\ALMP.exe" --runs 5
  python tools/bench_startup.py clip.mp4 --qt-platform windows             # Qt's own font list (old behaviour)

Close ALMP before running it: an open ALMP would receive the file instead of starting fresh.
The first run is usually slower (files not in the disk cache yet). Report the PC with the numbers.
Needs ALMP 8.2.2 or newer (older versions do not write the start-up lines).
"""
import argparse
import os
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINE = re.compile(r"Start-up: (window shown|playing) after ([0-9.]+) s")


def log_paths(exe=None, environ=None):
    """Where ALMP may write almp.log: the Data folder next to ALMP.exe (or main.py) since 8.2.4,
    the folder in ALMP_DATA_DIR, and the old %LOCALAPPDATA%\\ALMP (used before 8.2.4, and by 8.2.4
    when its own folder cannot be written to). All are watched; the lines are found in whichever is used."""
    environ = os.environ if environ is None else environ
    folder = Path(exe).resolve().parent if exe else ROOT
    paths = [folder / "Data" / "almp.log"]
    if environ.get("ALMP_DATA_DIR"):
        paths.insert(0, Path(environ["ALMP_DATA_DIR"]) / "almp.log")
    base = environ.get("LOCALAPPDATA") or environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    paths.append(Path(base) / "ALMP" / "almp.log")
    return paths


def read_new(path, offset):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            f.seek(offset)
            return f.read()
    except OSError:
        return ""


def one_run(cmd, env, timeout_s, logs):
    offsets = {p: (p.stat().st_size if p.exists() else 0) for p in logs}
    t0 = time.perf_counter()
    proc = subprocess.Popen(cmd, env=env, cwd=str(ROOT))
    found, wall = {}, None
    try:
        while time.perf_counter() - t0 < timeout_s:
            for p, offset in offsets.items():
                for kind, secs in LINE.findall(read_new(p, offset)):
                    found[kind] = float(secs)
            if "playing" in found:
                wall = time.perf_counter() - t0
                break
            if proc.poll() is not None:
                break
            time.sleep(0.05)
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
    time.sleep(4.0)       # ALMP is force-closed; give its single-instance lock time to go stale
    return found.get("window shown"), found.get("playing"), wall


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("media", help="a video or audio file to open")
    ap.add_argument("--exe", help="ALMP.exe to test (default: python main.py from this folder)")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--timeout", type=float, default=150.0, help="seconds to wait for each run")
    ap.add_argument("--qt-platform", help="set QT_QPA_PLATFORM for ALMP (for example 'windows' for Qt's default font list)")
    a = ap.parse_args()

    media = os.path.abspath(a.media)
    cmd = [a.exe, media] if a.exe else [sys.executable, str(ROOT / "main.py"), media]
    env = dict(os.environ)
    env.pop("QT_QPA_PLATFORM", None)
    if a.qt_platform:
        env["QT_QPA_PLATFORM"] = a.qt_platform
    print(f"ALMP: {' '.join(cmd[:-1])}\nFile: {media}\nQT_QPA_PLATFORM: {a.qt_platform or '(ALMP decides)'}\n")
    print("run   window shown   playing   (wall clock until playing)")
    playing = []
    for i in range(1, a.runs + 1):
        win, play, wall = one_run(cmd, env, a.timeout, log_paths(a.exe, env))
        fmt = lambda v: "   -   " if v is None else f"{v:6.1f} s"   # noqa: E731
        print(f"{i:>3}   {fmt(win):>12}   {fmt(play):>7}   ({fmt(wall).strip()})")
        if play is not None:
            playing.append(play)
    if playing:
        print(f"\nplaying after: median {statistics.median(playing):.1f} s, "
              f"best {min(playing):.1f} s, worst {max(playing):.1f} s ({len(playing)} of {a.runs} runs)")
    else:
        print("\nNo start-up lines found. Is this ALMP 8.2.2 or newer, and was ALMP closed before the test?")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
