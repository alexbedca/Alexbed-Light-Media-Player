# Alexbed Light Media Player (ALMP)
# Copyright (C) 2026 Alexander Bediako
# SPDX-License-Identifier: GPL-3.0-or-later
"""settings.json in %APPDATA%\\ALMP: defaults, safe loading, migration from older versions, saving.

Rules that never change:
  * The loop mode is never saved (always Off at start).
  * The playlist is never saved (ALMP always starts clean).
  * Keys written by older versions keep working; unknown keys are kept as they are.
"""
import json
import os
from pathlib import Path

from .logsetup import log
from .paths import get_settings_dir

SETTINGS_DIR = get_settings_dir()
SETTINGS_PATH = SETTINGS_DIR / "settings.json"
# Optional "continue long files" positions (only written when that setting is switched on).
POSITIONS_FILE_NAME = "positions.json"

# Older versions (v7) could save the last playlist and video positions here. ALMP now always
# starts clean, so these files are removed once at start-up: they only held file history.
LEGACY_HISTORY_FILES = ("resume.json", "last_playlist.json", "last_playlist.tmp")
# "loop_single" was saved by v7/v8.0.0. The loop choice is now temporary (always Off at start),
# so an old value is dropped from settings.json the next time settings are saved.
LEGACY_SETTINGS_KEYS = ("remember_playlist", "loop_single")

SETTINGS_VERSION = 2          # 1 = v8.0.x (no "settings_version" key), 2 = v8.1

SCALE_CHOICES = [("Normal (100%)", 1.0), ("Large (125%)", 1.25), ("Extra large (150%)", 1.5), ("Huge (200%)", 2.0)]
VIDEO_SIZE_CHOICES = [("Fit (whole picture)", "fit"), ("Fill (cropped)", "fill"), ("Stretch", "stretch")]
LARGE_BUTTON_CHOICES = [("Automatic (big in fullscreen)", "auto"), ("Always big", "always"), ("Never", "never")]
SUBTITLE_SIZE_CHOICES = [("Small", 0.8), ("Normal", 1.0), ("Large", 1.3), ("Huge", 1.7)]

DEFAULTS = {
    "volume": 100,
    "shuffle": True,
    "remove_played": False,        # v8.1: Off for new installs (a list that shrinks surprised people)
    "high_contrast": False,
    "ui_scale": 1.0,
    "video_size": "fit",
    "keep_speed": True,            # the chosen speed stays for the next tracks (until ALMP closes)
    "normalize_volume": False,     # "Even out loud and quiet parts"
    "volume_boost": False,         # allow the volume up to 150%
    "subtitle_scale": 1.0,
    "subtitle_background": False,  # dark box behind subtitles
    "media_controls": True,        # Windows media controls / media keys while ALMP is in the background
    "resume_long_files": False,    # optional, off by default; only files of 20 minutes or more
    "sleep_fade": True,            # fade out during the last minute of the sleep timer
    "large_buttons": "auto",       # v8.2: start screen size in fullscreen: auto / always / never
}


def remove_legacy_history_files(folder=None):
    """Delete only the exact old history files listed above (never anything else). Returns what was removed."""
    folder = Path(folder) if folder is not None else SETTINGS_DIR
    removed = []
    for name in LEGACY_HISTORY_FILES:
        p = folder / name
        try:
            if p.is_file() and not p.is_symlink():
                p.unlink()
                removed.append(name)
        except OSError:
            log.warning("Could not remove old history file %s", p)
    return removed


def load_settings():
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        log.warning("settings.json could not be read; using defaults", exc_info=True)
        return {}


def save_settings(data):
    """Write settings.json (through a temporary file, so a power cut cannot leave half a file)."""
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = SETTINGS_PATH.with_name(SETTINGS_PATH.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, SETTINGS_PATH)
        return True
    except OSError:
        log.warning("Could not save settings", exc_info=True)
        return False


def update_settings(**changes):
    """Read, change a few keys, write back. Used when a setting changes in the Settings window."""
    data = load_settings()
    data.update(changes)
    for key in LEGACY_SETTINGS_KEYS:
        data.pop(key, None)
    return save_settings(data)


def settings_to_save(old, volume, shuffle, remove_played):
    """The settings.json content to write on close. The loop mode is never saved."""
    data = dict(old) if isinstance(old, dict) else {}
    data.update({"volume": int(volume), "shuffle": bool(shuffle), "remove_played": bool(remove_played)})
    for key in LEGACY_SETTINGS_KEYS:
        data.pop(key, None)
    return data


def _as_bool(v, default):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)) and v in (0, 1):
        return bool(v)
    return default


def _as_float(v, default, lo, hi):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    if f != f or not (lo <= f <= hi):          # NaN or out of range
        return default
    return f


def effective_settings(raw):
    """Settings with every key present and every value sane. `raw` is what settings.json held
    (any version, possibly broken). The result is only used in memory; unknown keys are not copied.

    Migration notes:
      * v8.0.x files always contain "remove_played" (it was saved on every close), so people who
        updated keep exactly what they had. Only new installs get the new default (Off).
      * "loop_single" / "remember_playlist" are ignored.
    """
    raw = raw if isinstance(raw, dict) else {}
    out = dict(DEFAULTS)
    for key in ("shuffle", "remove_played", "high_contrast", "keep_speed", "normalize_volume",
                "volume_boost", "subtitle_background", "media_controls", "resume_long_files", "sleep_fade"):
        out[key] = _as_bool(raw.get(key, DEFAULTS[key]), DEFAULTS[key])
    max_volume = 150 if out["volume_boost"] else 100
    try:
        vol = int(raw.get("volume", DEFAULTS["volume"]))
    except (TypeError, ValueError):
        vol = DEFAULTS["volume"]
    out["volume"] = max(0, min(max_volume, vol))
    scale = _as_float(raw.get("ui_scale", 1.0), 1.0, 0.75, 3.0)
    out["ui_scale"] = scale
    vs = raw.get("video_size", "fit")
    out["video_size"] = vs if vs in {v for _l, v in VIDEO_SIZE_CHOICES} else "fit"
    lb = raw.get("large_buttons", "auto")
    out["large_buttons"] = lb if lb in ("auto", "always", "never") else "auto"
    out["subtitle_scale"] = _as_float(raw.get("subtitle_scale", 1.0), 1.0, 0.5, 3.0)
    return out


def migrate_settings_file():
    """Bring settings.json up to the current version once (drops old loop/playlist keys).
    Returns the effective settings. Safe to call on every start."""
    raw = load_settings()
    if raw and raw.get("settings_version") != SETTINGS_VERSION:
        data = dict(raw)
        for key in LEGACY_SETTINGS_KEYS:
            data.pop(key, None)
        data["settings_version"] = SETTINGS_VERSION
        save_settings(data)
        raw = data
    return effective_settings(raw)


# --- optional resume positions -------------------------------------------------

def positions_path(folder=None):
    return (Path(folder) if folder is not None else SETTINGS_DIR) / POSITIONS_FILE_NAME


def load_positions(folder=None):
    try:
        data = json.loads(positions_path(folder).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        return {}


def save_positions(table, folder=None):
    p = positions_path(folder)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(table), encoding="utf-8")
        os.replace(tmp, p)
        return True
    except OSError:
        log.warning("Could not save positions", exc_info=True)
        return False


def forget_positions(folder=None):
    """Delete the positions file (when the option is off, or 'Forget' is pressed)."""
    p = positions_path(folder)
    try:
        if p.is_file() and not p.is_symlink():
            p.unlink()
            return True
    except OSError:
        log.warning("Could not delete %s", p)
    return False
