# Alexbed Light Media Player (ALMP)
# Copyright (C) 2026 Alexander Bediako
# SPDX-License-Identifier: GPL-3.0-or-later
"""Moving ALMP's files from the old per-user folders into the Data folder next to ALMP.exe (8.2.4).

Up to 8.2.3 ALMP kept settings in %APPDATA%\\ALMP and its log in %LOCALAPPDATA%\\ALMP. From 8.2.4 on
everything lives in the Data folder, so deleting the ALMP folder leaves nothing behind.

On the first start with a writable Data folder that has no settings yet:
  1. settings.json, positions.json and startup_target.txt are COPIED into Data;
  2. each copy is read back and compared byte for byte;
  3. only if every copy is good, ALMP's own files in the old folders are deleted BY NAME
     (the same list as Remove-ALMP-Defaults.bat), and each old folder is removed only if it is empty.
Nothing else is ever touched: other files in those folders stay, and so does the folder then.
"""
import shutil
from pathlib import Path

from .logsetup import log

# Files copied into Data (kept); the rest of ALMP's old files are only removed.
FILES_TO_COPY = ("settings.json", "positions.json", "startup_target.txt")
# Exactly the names Remove-ALMP-Defaults.bat deletes.
OLD_SETTINGS_FILES = ("settings.json", "settings.json.tmp", "positions.json", "positions.json.tmp",
                      "startup_target.txt", "resume.json", "last_playlist.json", "last_playlist.tmp")
OLD_LOG_FILES = ("almp.log", "almp.log.1", "media-controls-starting.flag")


def _same_folder(a, b):
    try:
        return Path(a).resolve() == Path(b).resolve()
    except OSError:
        return False


def _old_files(folder, names):
    folder = Path(folder)
    out = []
    for n in names:
        p = folder / n
        try:
            if p.is_file() and not p.is_symlink():
                out.append(p)
        except OSError:
            pass
    return out


def migrate_legacy_files(data_dir, old_settings_dir, old_log_dir):
    """Returns a dict: copied (names), removed (paths as text), kept_folders, error (text or "").
    Safe to call on every start: it does nothing once Data has settings or the old folders are empty."""
    result = {"copied": [], "removed": [], "kept_folders": [], "error": ""}
    data_dir = Path(data_dir)
    if _same_folder(data_dir, old_settings_dir) or _same_folder(data_dir, old_log_dir):
        return result
    old_settings = _old_files(old_settings_dir, OLD_SETTINGS_FILES)
    old_logs = _old_files(old_log_dir, OLD_LOG_FILES)
    if not old_settings and not old_logs:
        return result
    if (data_dir / "settings.json").exists():
        return result              # this copy of ALMP already has its own settings: leave the old ones alone

    # 1 + 2: copy and verify
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        for name in FILES_TO_COPY:
            src = Path(old_settings_dir) / name
            if not (src.is_file() and not src.is_symlink()):
                continue
            dst = data_dir / name
            tmp = data_dir / (name + ".migrating")
            shutil.copyfile(src, tmp)
            if tmp.read_bytes() != src.read_bytes():
                tmp.unlink()
                raise OSError(f"the copy of {name} is not the same as the original")
            tmp.replace(dst)
            if dst.read_bytes() != src.read_bytes():
                raise OSError(f"{name} changed while it was copied")
            result["copied"].append(name)
    except OSError as e:
        result["error"] = str(e)
        log.warning("Moving ALMP's settings into %s failed; the old files were left in place: %s", data_dir, e)
        return result

    # 3: delete only ALMP's own files, by name; remove the folders only if empty
    for p in old_settings + old_logs:
        try:
            p.unlink()
            result["removed"].append(str(p))
        except OSError:
            log.warning("Could not remove the old file %s", p)
    for folder in (old_settings_dir, old_log_dir):
        folder = Path(folder)
        try:
            if folder.is_dir() and not folder.is_symlink():
                if any(folder.iterdir()):
                    result["kept_folders"].append(str(folder))
                else:
                    folder.rmdir()
        except OSError:
            result["kept_folders"].append(str(folder))
    log.info("Moved ALMP's files into %s (copied: %s; removed %d old file(s))",
             data_dir, ", ".join(result["copied"]) or "none", len(result["removed"]))
    return result
