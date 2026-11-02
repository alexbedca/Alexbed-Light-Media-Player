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


def mpv_options(wid, boost=False, subtitle_scale=1.0, platform=None, environ=None, proc_version=None):
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
    )
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
