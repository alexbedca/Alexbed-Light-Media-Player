# Alexbed Light Media Player (ALMP)
# Copyright (C) 2026 Alexander Bediako
# SPDX-License-Identifier: GPL-3.0-or-later
"""Linux-only answers to things platform_win.py does on Windows. Every function is safe to call
on any system; the pure parts take their inputs as arguments so they are tested on Windows too.

- Trash: the freedesktop.org Trash specification 1.0 (the same Trash that GNOME Files, Dolphin and
  `gio trash` use). Files on the home drive go to ~/.local/share/Trash; files on other drives
  (USB stick, second disk) go to <drive>/.Trash-<uid>, like a file manager does. If no Trash can be
  used, ALMP says so and asks before a permanent delete (never deletes silently).
- Menu entry and default player: a .desktop file in ~/.local/share/applications (user only, no
  root), plus `xdg-mime default` for the audio/video types. Removing it undoes both.
"""
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote

from .logsetup import log

DELETE_OK, DELETE_CANCELLED, DELETE_FAILED = "ok", "cancelled", "failed"   # same values as platform_win


def is_linux(platform=None):
    return (sys.platform if platform is None else platform).startswith("linux")


# --- Trash ---

def _xdg_data_home(environ=None, home=None):
    environ = os.environ if environ is None else environ
    value = environ.get("XDG_DATA_HOME", "")
    if value and os.path.isabs(value):
        return Path(value)
    return Path(home if home is not None else Path.home()) / ".local" / "share"


def home_trash(environ=None, home=None):
    return _xdg_data_home(environ, home) / "Trash"


def _existing_parent_dev(path):
    """st_dev of `path` or of its nearest existing parent (the home Trash may not exist yet)."""
    p = Path(path)
    while True:
        try:
            return os.stat(p).st_dev
        except OSError:
            if p.parent == p:
                return None
            p = p.parent


def mount_point(path):
    """The top folder of the drive that holds `path` (its mount point)."""
    p = Path(os.path.abspath(path))
    try:
        dev = os.lstat(p).st_dev
    except OSError:
        return None
    while p.parent != p:
        try:
            if os.lstat(p.parent).st_dev != dev:
                return p
        except OSError:
            return p
        p = p.parent
    return p


# Drives where ALMP offers no Trash (it warns and asks before a permanent delete instead), like the
# RAM disks and network drives that have no Recycle Bin on Windows: a Trash in RAM is lost at the next
# start, and a Trash on a shared network folder is not the user's own.
NO_TRASH_FS_TYPES = frozenset({
    "tmpfs", "ramfs", "devtmpfs", "nfs", "nfs4", "cifs", "smb3", "smbfs", "9p", "fuse.sshfs", "sshfs",
    "afs", "ceph", "glusterfs", "fuse.rclone", "davfs", "fuse.gvfsd-fuse", "iso9660", "udf", "squashfs",
})


def _unescape_mount(text):
    """/proc/self/mounts writes space, tab, newline and backslash as \\040, \\011, \\012, \\134."""
    for code, ch in (("\\040", " "), ("\\011", "\t"), ("\\012", "\n"), ("\\134", "\\")):
        text = text.replace(code, ch)
    return text


def filesystem_type(mount_dir, mounts_text=None):
    """File system type of the drive mounted at `mount_dir` ('ext4', 'vfat', 'tmpfs', ...), or ''."""
    if mounts_text is None:
        try:
            with open("/proc/self/mounts", encoding="utf-8", errors="replace") as f:
                mounts_text = f.read()
        except OSError:
            return ""
    found = ""
    for line in mounts_text.splitlines():
        parts = line.split()
        if len(parts) >= 3 and _unescape_mount(parts[1]) == str(mount_dir):
            found = parts[2]            # the last mount on a folder is the one in use
    return found


def trash_dir_for(path, environ=None, home=None, uid=None, mounts_text=None):
    """(trash folder, topdir) for `path`. topdir is None for the home Trash (its .trashinfo holds the
    full path) or the drive's top folder (its .trashinfo holds the path relative to it).
    (None, None) when this file cannot go to a Trash (missing file, RAM disk, network drive)."""
    ht = home_trash(environ, home)
    try:
        file_dev = os.lstat(path).st_dev
    except OSError:
        return None, None
    if _existing_parent_dev(ht) == file_dev:
        return ht, None
    top = mount_point(path)
    if top is None or filesystem_type(top, mounts_text) in NO_TRASH_FS_TYPES:
        return None, None
    uid = os.getuid() if uid is None and hasattr(os, "getuid") else (uid or 0)
    return top / f".Trash-{uid}", top


def _usable_trash(folder):
    """Create files/ and info/ if needed (700, as the spec asks) and check they can be written."""
    try:
        for sub in ("files", "info"):
            (Path(folder) / sub).mkdir(parents=True, exist_ok=True, mode=0o700)
        return os.access(Path(folder) / "files", os.W_OK) and os.access(Path(folder) / "info", os.W_OK)
    except OSError:
        return False


def trash_available(path, platform=None, environ=None, home=None, uid=None):
    """True when this file can go to a Trash it can be restored from."""
    if not is_linux(platform):
        return False
    folder, _top = trash_dir_for(path, environ, home, uid)
    return folder is not None and _usable_trash(folder)


def trashinfo_text(original_path, topdir=None, when=None):
    """The .trashinfo file for one trashed file (spec: Path is URL-escaped; relative to topdir for a
    drive Trash, absolute for the home Trash; DeletionDate in local time, no time zone)."""
    original = os.path.abspath(original_path)
    if topdir is not None:
        original = os.path.relpath(original, topdir)
    original = original.replace(os.sep, "/")
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(when))
    return f"[Trash Info]\nPath={quote(original, safe='/')}\nDeletionDate={stamp}\n"


def _reserve_name(info_dir, name):
    """A free name in info/: 'a.mp3', 'a.2.mp3', ... The .trashinfo is created with O_EXCL first, as
    the spec asks, so two programs never pick the same name."""
    stem, ext = os.path.splitext(name)
    for n in range(1, 10000):
        candidate = name if n == 1 else f"{stem}.{n}{ext}"
        try:
            fd = os.open(Path(info_dir) / f"{candidate}.trashinfo", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            return candidate, fd
        except FileExistsError:
            continue
    raise OSError("no free name in the Trash")


def move_to_trash(file_path, environ=None, home=None, uid=None, when=None):
    """Move one file to the Trash. Returns DELETE_OK or DELETE_FAILED; on failure the file is left
    where it was (never deleted)."""
    folder, top = trash_dir_for(file_path, environ, home, uid)
    if folder is None or not _usable_trash(folder):
        return DELETE_FAILED
    info_dir, files_dir = Path(folder) / "info", Path(folder) / "files"
    try:
        name, fd = _reserve_name(info_dir, Path(file_path).name)
    except OSError:
        log.exception("Could not reserve a Trash name for %s", file_path)
        return DELETE_FAILED
    info_file = info_dir / f"{name}.trashinfo"
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(trashinfo_text(file_path, top, when))
        os.rename(file_path, files_dir / name)        # same drive, so this is a move, never a copy
        return DELETE_OK
    except OSError:
        log.exception("Could not move %s to the Trash", file_path)
        try:
            info_file.unlink()
        except OSError:
            pass
        return DELETE_FAILED


# --- Menu entry and default player (.desktop file) ---

DESKTOP_FILE_NAME = "alexbed-almp.desktop"

# Types ALMP plays (the audio, video and playlist extensions in media.py).
MIME_TYPES = (
    "audio/mpeg", "audio/mp3", "audio/flac", "audio/x-flac", "audio/ogg", "audio/x-vorbis+ogg",
    "audio/x-opus+ogg", "audio/opus", "audio/wav", "audio/x-wav", "audio/vnd.wave", "audio/mp4",
    "audio/x-m4a", "audio/aac", "audio/x-aac", "audio/x-ms-wma", "audio/x-ape", "audio/x-wavpack",
    "audio/x-aiff", "audio/x-matroska", "audio/x-mpegurl", "audio/mpegurl", "audio/x-scpls",
    "video/mp4", "video/x-matroska", "video/webm", "video/x-msvideo", "video/quicktime",
    "video/x-ms-wmv", "video/mpeg", "video/x-flv", "video/3gpp", "video/mp2t", "video/ogg",
    "video/x-m4v",
    # Types shared-mime-info on Linux Mint 22.3 gives to extensions ALMP plays, that were missing:
    # .avi is video/vnd.avi there (video/x-msvideo is only an alias), .m4b audiobooks, DSD, Real, DV ...
    "video/vnd.avi", "video/avi", "video/3gpp2", "video/dv", "video/x-nsv", "video/x-ogm+ogg",
    "application/vnd.ms-asf", "application/vnd.rn-realmedia", "application/mxf",
    "audio/ac3", "audio/x-aifc", "audio/AMR", "audio/AMR-WB", "audio/basic", "audio/x-dff", "audio/x-dsf",
    "audio/x-m4b", "audio/x-m4r", "audio/mp2", "audio/x-musepack", "audio/vnd.rn-realaudio", "audio/x-tta",
    "audio/webm", "audio/x-mp3", "audio/x-mpeg",
)


def applications_dir(environ=None, home=None):
    return _xdg_data_home(environ, home) / "applications"


def _desktop_quote(arg):
    """Quote one Exec argument (Desktop Entry spec: double quotes, escape \\ " ` $)."""
    if not any(c in arg for c in ' \t\n"\'\\><~|&;$*?#()`'):
        return arg
    escaped = "".join("\\" + c if c in '"`$\\' else c for c in arg)
    return f'"{escaped}"'


def desktop_entry_text(exe, icon=""):
    """The .desktop file: shows ALMP in the app menu and in "Open With" for audio/video files."""
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.5",
        "Name=ALMP",
        "GenericName=Media Player",
        "Comment=Alexbed Light Media Player: simple offline player for huge playlists",
        f"Exec={_desktop_quote(str(exe))} %F",
        "Terminal=false",
        "Categories=AudioVideo;Audio;Video;Player;",
        "MimeType=" + ";".join(MIME_TYPES) + ";",
        "StartupWMClass=ALMP",
    ]
    if icon:
        lines.append(f"Icon={icon}")
    return "\n".join(lines) + "\n"


def can_register(exe, platform=None):
    """Only the built ALMP program (not `python main.py`) is registered."""
    return is_linux(platform) and bool(exe) and os.path.basename(exe) == "ALMP" and os.path.isfile(exe) \
        and os.access(exe, os.X_OK)


def _run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False).returncode == 0
    except (OSError, subprocess.SubprocessError):
        log.debug("Could not run %s", cmd[0], exc_info=True)
        return False


def desktop_entry_installed(environ=None, home=None):
    return (applications_dir(environ, home) / DESKTOP_FILE_NAME).is_file()


def install_desktop_entry(exe, icon="", make_default=False, environ=None, home=None, run=_run):
    """Write the .desktop file (and, when asked, make ALMP the default for its types).
    Returns (ok, message)."""
    target = applications_dir(environ, home) / DESKTOP_FILE_NAME
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        tmp.write_text(desktop_entry_text(exe, icon), encoding="utf-8")
        os.replace(tmp, target)
    except OSError as e:
        log.exception("Could not write %s", target)
        return False, str(e)
    run(["update-desktop-database", str(target.parent)])     # optional: refreshes the "Open With" cache
    if make_default and not run(["xdg-mime", "default", DESKTOP_FILE_NAME, *MIME_TYPES]):
        return False, "xdg-mime is missing or failed (package xdg-utils)."
    return True, ""


def remove_desktop_entry(environ=None, home=None, run=_run):
    """Remove the .desktop file. The desktop then falls back to its own default player."""
    target = applications_dir(environ, home) / DESKTOP_FILE_NAME
    try:
        if target.exists():
            target.unlink()
    except OSError as e:
        log.exception("Could not remove %s", target)
        return False, str(e)
    run(["update-desktop-database", str(target.parent)])
    return True, ""
