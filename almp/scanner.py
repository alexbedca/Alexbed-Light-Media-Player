# Alexbed Light Media Player (ALMP)
# Copyright (C) 2026 Alexander Bediako
# SPDX-License-Identifier: GPL-3.0-or-later
"""Folder scanning that streams its results.

The walk runs on a background thread and hands the playlist small batches while it goes, so the
first file can start playing within a moment even on a huge USB drive or a slow network share,
and the window shows a live count. Order: natural order folder by folder (the same order as
sorting all paths at the end, but without waiting for the end).
"""
import os
import time

from PyQt6.QtCore import QThread, pyqtSignal

from .logsetup import log
from .media import PLAYLIST_EXTENSIONS, SUPPORTED_EXTENSIONS, file_ext, read_playlist_file
from .naturalsort import natural_key
from .store import make_entry

SKIP_DIR_NAMES = {"system volume information", "$recycle.bin", "recycler", "found.000"}


def _skip_dir(name):
    n = name.lower()
    return n.startswith("$") or n in SKIP_DIR_NAMES


def _sorted_children(path, should_stop):
    """(files, dirs) of one folder, each in natural order. Unreadable folders give nothing."""
    files, dirs = [], []
    try:
        with os.scandir(path) as it:
            for entry in it:
                if should_stop():
                    break
                name = entry.name
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if not _skip_dir(name):
                            dirs.append(entry.path)
                    elif file_ext(name) in SUPPORTED_EXTENSIONS:
                        files.append(entry.path)
                except OSError:
                    continue
    except OSError:
        log.debug("Cannot read folder %s", path, exc_info=True)
    return files, dirs


def iter_folder(root, should_stop=lambda: False):
    """Every media file below `root`, in natural path order, yielded as soon as it is found.

    Inside one folder, files and sub-folders are merged by natural name order, which is exactly
    the order you get by sorting all full paths folder by folder."""
    stack = [iter(_merged(root, should_stop))]
    while stack:
        if should_stop():
            return
        try:
            kind, path = next(stack[-1])
        except StopIteration:
            stack.pop()
            continue
        if kind == 0:
            yield path
        else:
            stack.append(iter(_merged(path, should_stop)))


def _merged(path, should_stop):
    files, dirs = _sorted_children(path, should_stop)
    items = [(natural_key(os.path.basename(p)), 0, p) for p in files]
    items += [(natural_key(os.path.basename(p)), 1, p) for p in dirs]
    items.sort()
    for _k, kind, p in items:
        yield kind, p


def iter_targets(targets, should_stop=lambda: False):
    """Media files from a mix of dropped/opened items: single files first (natural order),
    then playlist files and folders in the order given."""
    singles, others = [], []
    for t in targets:
        if not t:
            continue
        ext = file_ext(t)
        if ext in SUPPORTED_EXTENSIONS and os.path.isfile(t):
            singles.append(t)
        else:
            others.append(t)
    singles.sort(key=lambda p: natural_key(os.path.basename(p)))
    yield from singles
    for t in others:
        if should_stop():
            return
        if os.path.isdir(t):
            yield from iter_folder(t, should_stop)
        elif file_ext(t) in PLAYLIST_EXTENSIONS and os.path.isfile(t):
            yield from read_playlist_file(t)


class BatchTimer:
    """Decides when to hand a batch over: at once for the very first file (so it can play),
    then whenever `max_items` are waiting or `interval_s` has passed."""

    def __init__(self, max_items=2000, interval_s=0.12, clock=time.monotonic):
        self.max_items = max_items
        self.interval_s = interval_s
        self.clock = clock
        self._last = None

    def due(self, n_waiting):
        if n_waiting <= 0:
            return False
        now = self.clock()
        if self._last is None or n_waiting >= self.max_items or now - self._last >= self.interval_s:
            self._last = now
            return True
        return False


def scan_in_batches(targets, emit, should_stop=lambda: False, max_items=2000, interval_s=0.12,
                    clock=time.monotonic):
    """Walk `targets` and call emit(list_of_entries) in batches. Returns the number of files found.
    Entries are (path, key, search) from store.make_entry, made here so the window does not
    have to. Pure Python: the thread below only wraps it."""
    timer = BatchTimer(max_items, interval_s, clock)
    batch = []
    total = 0
    for path in iter_targets(targets, should_stop):
        if should_stop():
            break
        batch.append(make_entry(path))
        total += 1
        if timer.due(len(batch)):
            emit(batch)
            batch = []
    if batch and not should_stop():
        emit(batch)
    return total


class FolderScanner(QThread):
    """Background scan. Signals:
      batch_found(list)   some new entries (the first one comes right away)
      scan_done(int, bool) total found, and whether it was cancelled
      scan_error(str)"""
    batch_found = pyqtSignal(object)
    scan_done = pyqtSignal(int, bool)
    scan_error = pyqtSignal(str)

    def __init__(self, targets, play_first=False, parent=None):
        super().__init__(parent)
        self.targets = list(targets)
        self.play_first = play_first

    def run(self):
        stop = self.isInterruptionRequested
        try:
            total = scan_in_batches(self.targets, self.batch_found.emit, stop)
            self.scan_done.emit(total, bool(stop()))
        except Exception as exc:          # noqa: BLE001 - reported to the window, never fatal
            log.exception("Folder scan failed")
            self.scan_error.emit(str(exc))
            self.scan_done.emit(0, True)
