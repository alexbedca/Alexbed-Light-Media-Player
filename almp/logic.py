# Alexbed Light Media Player (ALMP)
# Copyright (C) 2026 Alexander Bediako
# SPDX-License-Identifier: GPL-3.0-or-later
"""Plain decisions with no Qt and no mpv, so every rule can be tested on its own:
loop, shuffle, "Play next" queue, sleep timer, media-key de-duplication and the optional resume."""
import math
import random
import time

# --- Loop: Off / One / All ---
# Temporary choice: it is never saved and is always Off when ALMP starts.
LOOP_OFF, LOOP_ONE, LOOP_ALL = "off", "one", "all"
LOOP_MODES = (LOOP_OFF, LOOP_ONE, LOOP_ALL)
LOOP_LABELS = {LOOP_OFF: "Loop: Off", LOOP_ONE: "Loop: One", LOOP_ALL: "Loop: All"}
LOOP_TIPS = {
    LOOP_OFF: "Loop is off: playback stops after the last track.\nClick to change  (L)",
    LOOP_ONE: "Loop One: the track that is playing now repeats.\nNext and Prev still move on.\nClick to change  (L)",
    LOOP_ALL: "Loop All: the whole playlist starts again after the last track.\n"
              "\"Remove played\" is switched off while Loop All is on, so tracks are not removed;\n"
              "it comes back as it was when you leave Loop All.\nClick to change  (L)",
}
# If tracks keep ending almost at once (broken or empty files) while looping, stop instead of spinning.
LOOP_QUICK_END_SECONDS = 1.0
LOOP_QUICK_END_LIMIT = 8

REMOVE_PLAYED_TIP = "Take each track off the list after it has played to the end."
REMOVE_PLAYED_LOOP_ALL_TIP = "Not used while Loop All is on (it comes back when you leave Loop All)."


def sleep_minutes_left(remaining_ms):
    """Whole minutes left on the sleep timer, rounded up (59 s left shows as 1 min)."""
    if remaining_ms is None or remaining_ms <= 0:
        return 0
    return int(math.ceil(remaining_ms / 60000.0))


def pick_shuffle_index(files, played, current_index, rng=random):
    """Random track that has not been played yet (never the current one).
    `played` is a set of paths; when everything was played it starts over."""
    n = len(files)
    if n == 0:
        return -1
    if n == 1:
        return 0
    if len(played) >= n:
        played.clear()
        if 0 <= current_index < n:
            played.add(files[current_index])
    for _ in range(24):                       # fast path: almost always succeeds
        i = rng.randrange(n)
        if i != current_index and files[i] not in played:
            return i
    candidates = [i for i, p in enumerate(files) if i != current_index and p not in played]
    if not candidates:
        played.clear()
        candidates = [i for i in range(n) if i != current_index]
    return rng.choice(candidates)


def remove_played_for_loop(new_mode, checked, saved):
    """Owner rule: Loop All switches "Remove played" off (unticked and greyed out); leaving Loop All
    puts back what the user had. `saved` is the user's own value while it is overridden, else None.
    Returns (checked, enabled, saved)."""
    if new_mode == LOOP_ALL:
        if saved is None:
            saved = bool(checked)
        return (False, False, saved)
    if saved is not None:
        return (saved, True, None)
    return (bool(checked), True, None)


def remove_played_to_save(checked, saved):
    """The user's real choice: never the temporary Loop All override."""
    return bool(checked) if saved is None else bool(saved)


def next_loop_mode(mode):
    """Off -> One -> All -> Off. Anything unknown counts as Off."""
    try:
        i = LOOP_MODES.index(mode)
    except ValueError:
        return LOOP_ONE
    return LOOP_MODES[(i + 1) % len(LOOP_MODES)]


def decide_after_track_end(n_files, current_index, loop_mode, shuffle, remove_played,
                           all_played=False, quick_end_streak=0):
    """What to do when a track has played to its end. Returns (action, index):
      ("stop", -1)      nothing more to play: empty list, or end of the playlist with Loop Off
      ("replay", i)     Loop One: play track i (the one that just ended) again
      ("remove", i)     "Remove played" (not with Loop All): remove track i, then go on as before
      ("play", i)       play track i (next in order; back to 0 with Loop All)
      ("shuffle", -1)   play a random track not played yet in this round
      ("new_round", -1) shuffle with Loop All: every track was played, start a new round
    `all_played` (shuffle only): every track in the list was played in this round.
    A "Play next" queue is handled by the caller before this (see next_from_queue)."""
    if n_files <= 0:
        return ("stop", -1)
    if loop_mode != LOOP_OFF and quick_end_streak >= LOOP_QUICK_END_LIMIT:
        return ("stop", -1)
    valid = 0 <= current_index < n_files
    if loop_mode == LOOP_ONE and valid:
        return ("replay", current_index)
    if remove_played and loop_mode != LOOP_ALL and valid:
        return ("remove", current_index)
    if shuffle:
        if not all_played:
            return ("shuffle", -1)
        if loop_mode == LOOP_ALL:
            return ("new_round", -1)
        return ("stop", -1)
    nxt = current_index + 1 if valid else 0
    if nxt < n_files:
        return ("play", nxt)
    if loop_mode == LOOP_ALL:
        return ("play", 0)
    return ("stop", -1)


# --- "Play next" queue ---

def next_from_queue(queue, contains):
    """Take the first queued path that is still in the playlist. `queue` is a list (changed in place),
    `contains(path)` tells whether a path is still in the playlist. Returns the path or None."""
    while queue:
        path = queue.pop(0)
        if contains(path):
            return path
    return None


def add_to_queue(queue, path, limit=1000):
    """Queue a path to play after the current track. A path already queued moves to the end.
    Returns the queue position (1 = next)."""
    try:
        queue.remove(path)
    except ValueError:
        pass
    queue.append(path)
    if len(queue) > limit:
        del queue[: len(queue) - limit]
    return len(queue)


# --- Playback speed ---

SPEED_CHOICES = ("0.5x", "0.75x", "1.0x", "1.25x", "1.5x", "2.0x")


def parse_speed(text, default=1.0):
    try:
        value = float(str(text).strip().lower().rstrip("x"))
    except (TypeError, ValueError):
        return default
    if not (0.25 <= value <= 4.0) or math.isnan(value):
        return default
    return value


def speed_for_new_track(current_text, keep_speed):
    """The speed text for the next track: kept for the session, or back to 1.0x."""
    return current_text if keep_speed and current_text in SPEED_CHOICES else "1.0x"


# --- Sleep timer ---

SLEEP_PAUSE, SLEEP_CLOSE, SLEEP_END_OF_TRACK = "pause", "close", "end_of_track"
SLEEP_FADE_MS = 60_000


def sleep_fade_factor(remaining_ms, fade_ms=SLEEP_FADE_MS):
    """Volume factor (0..1) for a gentle fade-out over the last minute of the sleep timer."""
    if remaining_ms is None or remaining_ms >= fade_ms:
        return 1.0
    if remaining_ms <= 0:
        return 0.0
    return max(0.0, min(1.0, remaining_ms / float(fade_ms)))


def extend_sleep_ms(remaining_ms, add_minutes=15, cap_minutes=600):
    """'+15 min': the new timer length in ms (never more than 10 hours)."""
    remaining_ms = max(0, int(remaining_ms or 0))
    return min(cap_minutes * 60_000, remaining_ms + add_minutes * 60_000)


# --- Media keys: the same key can arrive twice (window key + Windows media controls) ---

MEDIA_DEDUPE_SECONDS = 0.4


class MediaCommandFilter:
    """Lets one press through. When the same command arrives from a *different* source within
    0.4 s (for example the keyboard key and the Windows media controls both report it), the
    second one is ignored so Play/Pause does not toggle twice."""

    def __init__(self, window_s=MEDIA_DEDUPE_SECONDS, clock=time.monotonic):
        self.window_s = window_s
        self.clock = clock
        self._last = None          # (command, source, time)

    def accept(self, command, source):
        now = self.clock()
        last = self._last
        if last is not None and last[0] == command and last[1] != source and now - last[2] < self.window_s:
            return False
        self._last = (command, source, now)
        return True


# --- Optional "continue long files where I stopped" (off by default) ---

RESUME_MIN_DURATION_S = 20 * 60      # only files of 20 minutes or longer (films, audiobooks, talks)
RESUME_MIN_POSITION_S = 60           # less than a minute in: start from the beginning next time
RESUME_END_MARGIN_S = 90             # nearly finished: start from the beginning next time
RESUME_MAX_ENTRIES = 200


def resume_position_to_store(position_s, duration_s):
    """The position worth remembering for a file, or None (forget it)."""
    try:
        pos = float(position_s)
        dur = float(duration_s)
    except (TypeError, ValueError):
        return None
    if math.isnan(pos) or math.isnan(dur) or dur < RESUME_MIN_DURATION_S:
        return None
    if pos < RESUME_MIN_POSITION_S or pos > dur - RESUME_END_MARGIN_S:
        return None
    return int(pos)


def update_resume_table(table, key, position_s, duration_s, now=None, limit=RESUME_MAX_ENTRIES):
    """Store or forget one file's position in `table` ({key: [seconds, last_used]}). Keeps at most
    `limit` entries (oldest dropped). Returns the table (changed in place)."""
    pos = resume_position_to_store(position_s, duration_s)
    if pos is None:
        table.pop(key, None)
        return table
    table[key] = [pos, float(now if now is not None else time.time())]
    if len(table) > limit:
        oldest = sorted(table.items(), key=lambda kv: kv[1][1] if isinstance(kv[1], list) else 0)
        for k, _v in oldest[: len(table) - limit]:
            table.pop(k, None)
    return table


def resume_start_for(table, key):
    """Seconds to start at for this file, or None."""
    v = table.get(key)
    if isinstance(v, list) and v and isinstance(v[0], (int, float)) and v[0] >= RESUME_MIN_POSITION_S:
        return int(v[0])
    return None


def fmt_time(seconds):
    seconds = int(max(0, seconds or 0))
    h, rem = divmod(seconds, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


LARGE_BUTTON_MODES = ("auto", "always", "never")


def tv_scale(mode, fullscreen, screen_height_px):
    """How much bigger the start-screen text and buttons get in fullscreen (1.0 = normal size).

    * "never"  -> always 1.0
    * "auto"   -> only in fullscreen; grows with the screen height (about 2x on a 1080p TV)
    * "always" -> like auto, but also in a normal window, and at least 1.5x
    The screen height is the logical height Qt reports, so ALMP's own interface size is already included."""
    if mode not in LARGE_BUTTON_MODES:
        mode = "auto"
    if mode == "never":
        return 1.0
    try:
        h = float(screen_height_px)
    except (TypeError, ValueError):
        return 1.0
    if h <= 0:
        return 1.0
    f = max(1.0, min(3.0, h / 540.0))
    if mode == "always":
        return max(1.5, f)
    return f if fullscreen else 1.0
