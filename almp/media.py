# Alexbed Light Media Player (ALMP)
# Copyright (C) 2026 Alexander Bediako
# SPDX-License-Identifier: GPL-3.0-or-later
"""File types ALMP plays, and reading/writing M3U and PLS playlists. No Qt here."""
import locale
import os
import re
import sys
import urllib.parse

from .logsetup import log

AUDIO_EXTENSIONS = {
    ".mp3", ".flac", ".wav", ".aac", ".m4a", ".ogg", ".oga", ".opus", ".wma",
    ".aiff", ".aif", ".aifc", ".ape", ".alac", ".amr", ".awb", ".mp2", ".mp1",
    ".mpa", ".ac3", ".eac3", ".dts", ".wv", ".mka", ".mpc", ".tta", ".spx",
    ".caf", ".au", ".snd", ".m4r", ".m4b", ".weba", ".ra", ".dsf", ".dff",
}
VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".mpeg", ".mpg", ".mpe",
    ".m4v", ".3gp", ".3g2", ".ts", ".m2ts", ".mts", ".m2t", ".tp", ".trp",
    ".vob", ".ogv", ".ogm", ".flv", ".f4v", ".rm", ".rmvb", ".asf", ".divx",
    ".xvid", ".dv", ".mxf", ".qt", ".wtv", ".dvr-ms", ".amv", ".nsv", ".ivf",
}
SUPPORTED_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
PLAYLIST_EXTENSIONS = {".m3u", ".m3u8", ".pls"}


def file_ext(name):
    """Lower-case extension with the dot ('' if none). Faster than pathlib for 100,000 names.
    '.dvr-ms' is the only two-part one ALMP knows, and it has a single dot, so splitext is enough."""
    return os.path.splitext(name)[1].lower()


def is_media_name(name):
    return file_ext(name) in SUPPORTED_EXTENSIONS


def is_audio_path(path):
    return file_ext(path) in AUDIO_EXTENSIONS


def decode_playlist_bytes(raw, fallback_encoding=None):
    """Playlists from Windows Media Player, Winamp and older tools are often in the old Windows
    ("ANSI") code page instead of UTF-8. Try UTF-8 (with or without BOM) first, then fall back."""
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", errors="replace")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    if fallback_encoding is None:
        fallback_encoding = "mbcs" if sys.platform == "win32" else (locale.getpreferredencoding(False) or "cp1252")
    for enc in (fallback_encoding, "cp1252"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("latin-1")


def _playlist_entry_to_path(line, base):
    if line.lower().startswith("file:"):
        parsed = urllib.parse.urlparse(line)
        p = parsed.path
        if parsed.netloc and parsed.netloc.lower() != "localhost":
            p = "//" + parsed.netloc + p          # file://server/share/song.mp3
        p = urllib.parse.unquote(p)
        if re.match(r"/[A-Za-z]:", p):            # file:///C:/Music/song.mp3
            p = p[1:]
        return os.path.normpath(p)
    entry = line if os.path.isabs(line) else os.path.join(base, line)
    return os.path.normpath(entry)


def read_playlist_file(path, fallback_encoding=None):
    """Existing local media files listed in an M3U/M3U8/PLS file (anything else is skipped)."""
    out = []
    base = os.path.dirname(path)
    is_pls = path.lower().endswith(".pls")
    try:
        with open(path, "rb") as f:
            text = decode_playlist_bytes(f.read(), fallback_encoding)
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if is_pls:
                if not line.lower().startswith("file"):
                    continue
                line = line.split("=", 1)[-1].strip()
            entry = _playlist_entry_to_path(line, base)
            if file_ext(entry) in SUPPORTED_EXTENSIONS and os.path.isfile(entry):
                out.append(entry)
    except Exception:          # noqa: BLE001 - a broken playlist must not stop the import
        log.exception("Could not read playlist %s", path)
    return out


def write_playlist_file(path, files):
    """.m3u8 is UTF-8 by definition. Plain .m3u gets a UTF-8 BOM so other players
    do not show accented names as garbage."""
    encoding = "utf-8" if path.lower().endswith(".m3u8") else "utf-8-sig"
    with open(path, "w", encoding=encoding, newline="\n") as f:
        f.write("#EXTM3U\n")
        for item in files:
            f.write(item + "\n")
