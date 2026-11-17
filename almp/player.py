# Alexbed Light Media Player (ALMP)
# Copyright (C) 2026 Alexander Bediako
# SPDX-License-Identifier: GPL-3.0-or-later
"""mpv (libmpv) settings and small helpers. The window code calls these; nothing here draws.

Offline and locked down on purpose: no web-video plug-in (ytdl), no Lua/JS scripts, no user
mpv.conf, no network protocols are ever used by ALMP itself (only local files are loaded).
"""
import os
import sys

from .logsetup import log

try:
    import mpv
    MPV_IMPORT_ERROR = None
except Exception as _mpv_exc:          # noqa: BLE001 - mpv-2.dll missing, blocked by antivirus, or wrong build
    mpv = None
    MPV_IMPORT_ERROR = _mpv_exc

# "Even out loud and quiet parts": FFmpeg's dynamic audio normaliser (gentle settings, ~0.5 s delay).
NORMALIZE_FILTER = "lavfi=[dynaudnorm=f=250:g=15:p=0.9:m=8]"
BOOST_MAX_VOLUME = 150
NORMAL_MAX_VOLUME = 100
VIDEO_SIZES = ("fit", "fill", "stretch")
VIDEO_SIZE_NAMES = {"fit": "Fit", "fill": "Fill (cropped)", "stretch": "Stretch"}

# Video upscaling (Settings > Playback). Only mpv's own built-in scalers: no shader files, no downloads.
# "standard" puts back whatever mpv used when ALMP started (read once, see _init_player).
SCALER_KEYS = ("scale", "cscale", "dscale", "correct-downscaling", "sigmoid-upscaling", "deband")
UPSCALING_PROPERTIES = {
    "standard": {},
    "sharp": {"scale": "spline36", "cscale": "spline36", "dscale": "mitchell"},
    # The three extras were measured on a GTX 960 (720p and 360p on a 1080p screen): 0 dropped frames,
    # no measurable extra GPU load on top of ewa_lanczossharp.
    "high": {"scale": "ewa_lanczossharp", "cscale": "ewa_lanczossharp", "dscale": "mitchell",
             "correct-downscaling": True, "sigmoid-upscaling": True, "deband": True},
}


def mpv_options(wid, boost=False, subtitle_scale=1.0, platform=None, environ=None, proc_version=None,
                show_subtitles=False, gapless=False, audio_exclusive=False):
    """The options ALMP starts mpv with. Pure: easy to check in tests.
    The volume normaliser and the subtitle box are switched on after start (set_audio_filter,
    subtitle_background_options), so an mpv build without them can never stop playback from starting."""
    platform = sys.platform if platform is None else platform
    environ = os.environ if environ is None else environ
    opts = dict(
        wid=str(int(wid)),
        osc=False,
        input_default_bindings=False,
        input_vo_keyboard=False,
        keep_open="no",
        idle="yes",
        hwdec="auto",
        cursor_autohide="no",
        # Lean, offline-only engine: no web-video plugin, no Lua scripts, ignore any
        # user mpv.conf, and keep the read-ahead buffers small (less memory, faster start).
        ytdl="no",
        load_scripts="no",
        config="no",
        demuxer_max_bytes="48MiB",
        demuxer_max_back_bytes="8MiB",
        volume_max=str(BOOST_MAX_VOLUME if boost else NORMAL_MAX_VOLUME),
        sub_scale=str(float(subtitle_scale)),
        sub_auto="fuzzy",
        # Subtitles are loaded (so they can be switched on at any time) but only shown when wanted.
        sub_visibility="yes" if show_subtitles else "no",
    )
    opts.update(gapless_options(gapless))
    if audio_exclusive:
        opts["audio_exclusive"] = "yes"
    if platform.startswith("linux"):
        forced_vo = environ.get("ALMP_VO")
        if forced_vo:
            opts["vo"] = forced_vo
        else:
            if proc_version is None:
                try:
                    with open("/proc/version", encoding="utf-8") as f:
                        proc_version = f.read()
                except OSError:
                    proc_version = ""
            if "microsoft" in proc_version.lower():
                opts.update(vo="x11", hwdec="no", profile="fast", vd_lavc_fast=True)
    return opts


def gapless_options(on):
    """mpv options for "Gapless playback": keep the sound device open between tracks of the same
    format, and read the start of the next track while this one plays."""
    if on:
        return {"gapless_audio": "yes", "prefetch_playlist": "yes"}
    return {"gapless_audio": "weak", "prefetch_playlist": "no"}


# Optional user shaders (Settings > Playback): mpv shader files (.glsl / .hook) the user puts in a
# "shaders" folder next to ALMP.exe, for example FSRCNNX or Anime4K. ALMP ships none and downloads
# none; it only hands the files it finds to mpv (glsl-shaders). Off by default.
SHADER_FOLDER = "shaders"
SHADER_EXTENSIONS = (".glsl", ".hook")
MAX_USER_SHADERS = 16


def find_user_shaders(folder):
    """Shader files in `folder` (not its subfolders), sorted by name, at most MAX_USER_SHADERS.
    A missing or unreadable folder gives an empty list."""
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    found = []
    for name in sorted(names, key=str.casefold):
        full = os.path.join(folder, name)
        if name.lower().endswith(SHADER_EXTENSIONS) and os.path.isfile(full):
            found.append(full)
    return found[:MAX_USER_SHADERS]


def apply_user_shaders(player, paths):
    """Make mpv use exactly these shader files (an empty list removes them). mpv itself skips a file
    it cannot compile, so a broken file never stops playback. Returns False if mpv refused."""
    if player is None:
        return False
    try:
        player.command("change-list", "glsl-shaders", "clr", "")
        for path in paths:
            player.command("change-list", "glsl-shaders", "append", path)
        return True
    except Exception:          # noqa: BLE001 - mpv raises its own error types
        log.warning("mpv did not accept the shader list %r", paths, exc_info=True)
        return False


def upscaling_properties(level, standard=None):
    """mpv properties for Standard / Sharp / High quality. `standard` = mpv's own values at start."""
    if level in ("sharp", "high"):
        return dict(UPSCALING_PROPERTIES[level])
    return dict(standard or {})


_SAMPLE_FORMAT_BITS = {"u8": 8, "s16": 16, "s24": 24, "s32": 32, "u8p": 8, "s16p": 16, "s32p": 32,
                       "float": "32-bit float", "floatp": "32-bit float", "double": "64-bit float",
                       "doublep": "64-bit float"}
_LOSSLESS_EXT = {".flac": "FLAC", ".wav": "WAV", ".aiff": "AIFF", ".aif": "AIFF", ".aifc": "AIFF",
                 ".ape": "APE", ".alac": "ALAC", ".wv": "WavPack", ".tta": "TTA", ".dsf": "DSD", ".dff": "DSD"}


def audio_format_text(ext, codec=None, samplerate=None, bits=None, sample_format=None):
    """'FLAC - 24-bit / 96 kHz' for the playing bar, from what is known about the playing track only.
    `bits` comes from the file's own header (exact); without it the decoder's sample format is used,
    except s32/float, which decoders also use for 24-bit or lossy audio (so they would mislead)."""
    ext = (ext or "").lower()
    name = _LOSSLESS_EXT.get(ext)
    if name is None:
        c = (codec or "").strip()
        name = c.upper() if c else ext.lstrip(".").upper()
    if (codec or "").lower() == "alac":
        name = "ALAC"                  # Apple Lossless inside an .m4a file
    parts = []
    depth = None
    if isinstance(bits, int) and bits > 0:
        depth = f"{bits}-bit"
    elif ext in _LOSSLESS_EXT and sample_format in ("s16", "s16p", "s24", "u8", "u8p"):
        depth = f"{_SAMPLE_FORMAT_BITS[sample_format]}-bit"
    if depth:
        parts.append(depth)
    try:
        rate = int(samplerate or 0)
    except (TypeError, ValueError):
        rate = 0
    if rate > 0:
        khz = rate / 1000
        parts.append(f"{khz:g} kHz" if khz != int(khz) else f"{int(khz)} kHz")
    if not name:
        return ""
    return f"{name} - {' / '.join(parts)}" if parts else name


def subtitle_background_options(on):
    """mpv properties for a dark box behind subtitles (easier to read on bright pictures)."""
    if on:
        return {"sub-border-style": "background-box", "sub-back-color": "#C0000000"}
    return {"sub-border-style": "outline-and-shadow", "sub-back-color": "#00000000"}


def video_size_properties(mode):
    """mpv properties for Fit / Fill (cropped) / Stretch."""
    if mode == "fill":
        return {"keepaspect": True, "panscan": 1.0}
    if mode == "stretch":
        return {"keepaspect": False, "panscan": 0.0}
    return {"keepaspect": True, "panscan": 0.0}


def next_video_size(mode):
    try:
        return VIDEO_SIZES[(VIDEO_SIZES.index(mode) + 1) % len(VIDEO_SIZES)]
    except ValueError:
        return "fit"


def get_mpv_end_reason(event):
    """'EOF', 'STOP', 'QUIT', 'ERROR', 'REDIRECT' or 'UNKNOWN' from a python-mpv end-file event
    (the shape of that event changed between python-mpv versions)."""
    try:
        data = getattr(event, "data", None)
        reason = None
        if isinstance(data, dict):
            reason = data.get("reason")
        elif data is not None:
            reason = getattr(data, "reason", None)
        if reason is None:
            reason = getattr(event, "reason", None)
        if reason is None:
            return "UNKNOWN"

        enum_name = getattr(reason, "name", None)
        if enum_name:
            return str(enum_name).upper()

        enum_value = getattr(reason, "value", reason)
        try:
            numeric_reason = int(enum_value)
            reason_map = {0: "EOF", 2: "STOP", 3: "QUIT", 4: "ERROR", 5: "REDIRECT"}
            return reason_map.get(numeric_reason, f"UNKNOWN_{numeric_reason}")
        except (TypeError, ValueError):
            pass

        reason_text = str(enum_value).upper()
        for word in ("EOF", "STOP", "QUIT", "ERROR", "REDIRECT"):
            if word in reason_text:
                return word
        return reason_text
    except Exception:          # noqa: BLE001 - must never break the event thread
        log.debug("Could not read the end-file reason", exc_info=True)
        return "UNKNOWN"


def set_prop(player, name, value):
    """Set an mpv property; returns False (and logs) instead of raising."""
    if player is None:
        return False
    try:
        player[name] = value
        return True
    except Exception:          # noqa: BLE001 - mpv raises its own error types
        log.debug("mpv property %s=%r was refused", name, value, exc_info=True)
        return False


def set_audio_filter(player, normalize):
    """Switch the volume normaliser on or off while playing."""
    if player is None:
        return False
    try:
        if normalize:
            player.command("af", "set", NORMALIZE_FILTER)
        else:
            player.command("af", "set", "")
        return True
    except Exception:          # noqa: BLE001
        log.warning("Could not change the audio filter", exc_info=True)
        return False
