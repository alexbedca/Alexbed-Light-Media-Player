"""Checks of the built ALMP on a real Linux PC without extra tools or sudo (Linux Mint 22 Cinnamon, Xorg).
Uses only: gdbus (MPRIS), pactl (sound stream), wmctrl, python3-xlib (XTEST key presses through Xorg,
so the desktop's own media-key handling is used) and Pillow (screen grab).
Everything stays in the ALMP folder (portable Data folder). ALMP is closed after each part.
    python3 mint_check.py <ALMP folder> <testmedia folder> <shots folder>
Safety: another player (e.g. Chrome) may also offer MPRIS. If a media key starts it, it is paused at once."""
import os
import re
import subprocess
import sys
import time

D, M, S = sys.argv[1].rstrip("/"), sys.argv[2], sys.argv[3]
os.makedirs(S, exist_ok=True)
ENV = dict(os.environ, DISPLAY=":0", XAUTHORITY=os.path.expanduser("~/.Xauthority"),
           DBUS_SESSION_BUS_ADDRESS=f"unix:path=/run/user/{os.getuid()}/bus", XDG_RUNTIME_DIR=f"/run/user/{os.getuid()}")
NAME = "org.mpris.MediaPlayer2.almp"
PATH = "/org/mpris/MediaPlayer2"
PLAYER = "org.mpris.MediaPlayer2.Player"
results = []


def run(*cmd, timeout=10):
    try:
        return subprocess.run(cmd, env=ENV, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except subprocess.TimeoutExpired:
        return ""


def record(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'} | {name} | {detail}", flush=True)


def prop(name, bus=NAME):
    out = run("gdbus", "call", "--session", "-d", bus, "-o", PATH, "-m", "org.freedesktop.DBus.Properties.Get",
              PLAYER, name)
    return out


def status(bus=NAME):
    m = re.search(r"'(\w+)'", prop("PlaybackStatus", bus))
    return m.group(1) if m else ""


def title():
    m = re.search(r"'xesam:title': <'(.*?)'>", prop("Metadata"))
    return m.group(1) if m else ""


def position():
    m = re.search(r"<(?:int64 )?(\d+)>", prop("Position"))
    return int(m.group(1)) / 1e6 if m else -1


def call(method, *args):
    return run("gdbus", "call", "--session", "-d", NAME, "-o", PATH, "-m", f"{PLAYER}.{method}", *args)


def set_volume(v):
    run("gdbus", "call", "--session", "-d", NAME, "-o", PATH, "-m", "org.freedesktop.DBus.Properties.Set",
        PLAYER, "Volume", f"<{v}>")


def other_players():
    out = run("gdbus", "call", "--session", "-d", "org.freedesktop.DBus", "-o", "/org/freedesktop/DBus", "-m",
              "org.freedesktop.DBus.ListNames")
    return [n for n in re.findall(r"'(org\.mpris\.MediaPlayer2\.[^']+)'", out) if not n.startswith(NAME)]


def guard_others(before):
    """Pause any other player a key press started (for example a browser)."""
    for bus, st in before.items():
        if st != "Playing" and status(bus) == "Playing":
            run("gdbus", "call", "--session", "-d", bus, "-o", PATH, "-m", f"{PLAYER}.Pause")
            return f"{bus} started and was paused again"
    return ""


def press(keysym_name):
    from Xlib import XK, display
    from Xlib.ext import xtest
    d = display.Display(":0")
    # python-xlib does not know the XF86 media-key names; use their keysym numbers
    keysym = {"XF86AudioPlay": 0x1008FF14, "XF86AudioPrev": 0x1008FF16, "XF86AudioNext": 0x1008FF17}.get(
        keysym_name) or XK.string_to_keysym(keysym_name)
    code = d.keysym_to_keycode(keysym)
    if not code:
        d.close()
        raise RuntimeError(f"{keysym_name} has no key code on this X server")
    xtest.fake_input(d, 2, code)       # KeyPress
    d.sync()
    time.sleep(0.05)
    xtest.fake_input(d, 3, code)       # KeyRelease
    d.sync()
    d.close()


def win():
    for line in run("wmctrl", "-lG").splitlines():
        if "Light Media" in line:
            return line.split()
    return None


def start(*args):
    t0 = time.monotonic()
    p = subprocess.Popen([f"{D}/ALMP", *args], env=ENV, stdout=open("/tmp/almp-mint.out", "w"),
                         stderr=subprocess.STDOUT, cwd=D)
    while time.monotonic() - t0 < 15 and not win():
        time.sleep(0.05)
    return p, time.monotonic() - t0


def close(p):
    run("wmctrl", "-c", "Light Media")
    try:
        p.wait(5)
        return True
    except subprocess.TimeoutExpired:
        p.terminate()
        return False


def almp_stream():
    """ALMP/mpv's sound stream: (sink name, state) from pactl."""
    sinks = dict(line.split("\t")[:2] for line in run("pactl", "list", "sinks", "short").splitlines() if "\t" in line)
    out = run("pactl", "list", "sink-inputs")
    for block in out.split("Sink Input #")[1:]:
        if re.search(r'application\.(name|process\.binary) = "(ALMP|mpv)', block, re.I) or "ALMP" in block:
            sink = re.search(r"Sink: (\d+)", block)
            corked = re.search(r"Corked: (\w+)", block)
            return sinks.get(sink.group(1) if sink else "", "?"), ("paused" if corked and corked.group(1) == "yes" else "running")
    return None, None


# --- 1. music, sound stream, MPRIS ---
others = {b: status(b) for b in other_players()}
print("INFO other MPRIS players:", others, flush=True)
p, t = start(f"{M}/music")
record("Start (window listed)", win() is not None, f"{t:.2f} s")
for _ in range(60):
    if status() == "Playing":
        break
    time.sleep(0.25)
set_volume(0.35)                       # quieter than normal: a few seconds of music on the TV
record("Music plays (MPRIS)", status() == "Playing", title())
meta = prop("Metadata")
record("Applet details: artist and picture for music", "'xesam:artist'" in meta and "mpris:artUrl" in meta,
       (re.search(r"'xesam:artist': <\[(.*?)\]>", meta) or re.search("$", "")).group(0)[:80])
p1 = position()
time.sleep(2)
p2 = position()
record("Clock moves", p2 > p1, f"{p1:.1f} -> {p2:.1f} s")
try:
    maps = open(f"/proc/{p.pid}/maps", encoding="utf-8").read()
except OSError:
    maps = ""
libmpv = sorted({line.split()[-1] for line in maps.splitlines() if "libmpv.so" in line})
record("Engine = libmpv bundled in mpv-libs (not the system's)", bool(libmpv) and all("/mpv-libs/" in x for x in libmpv),
       ", ".join(libmpv))
sink, state = almp_stream()
record("Sound stream goes to the default output", sink is not None, f"{sink}, {state}")
vol = re.search(r"<([\d.]+)>", prop("Volume"))
record("Volume from the desktop (MPRIS)", bool(vol) and abs(float(vol.group(1)) - 0.35) < 0.01, prop("Volume"))
call("Pause")
time.sleep(1)
record("MPRIS pause", status() == "Paused", status())
call("Play")
time.sleep(1)
record("MPRIS play", status() == "Playing", status())
t1 = title()
call("Next")
time.sleep(2)
record("MPRIS next", title() != t1, f"{t1} -> {title()}")
call("Previous")
time.sleep(2)
record("MPRIS previous", title() == t1, title())
# Real media keys through Xorg (Cinnamon's media-keys service decides which player gets them).
# Off unless --keys is given: on a PC someone else uses, a person should press the real keys.
if "--keys" in sys.argv:
    for key, want in (("XF86AudioPlay", "Paused"), ("XF86AudioPlay", "Playing")):
        before = {b: status(b) for b in other_players()}
        press(key)
        time.sleep(1.5)
        note = guard_others(before)
        record(f"Media key {key} with ALMP in the background -> {want}", status() == want and not note,
               note or status())
    t1 = title()
    before = {b: status(b) for b in other_players()}
    press("XF86AudioNext")
    time.sleep(2)
    note = guard_others(before)
    record("Media key XF86AudioNext", title() != t1 and not note, note or f"{t1} -> {title()}")
else:
    print("INFO media keys not pressed (needs a person, or --keys)", flush=True)
w = win()
if w:
    from PIL import ImageGrab
    x, y, ww, hh = map(int, w[2:6])
    ImageGrab.grab(bbox=(x, y, x + ww, y + hh), xdisplay=":0").save(f"{S}/mint-music.png")
record("Close", close(p))

# --- 2. video inside the window ---
dots = f"{M}/video/Big Buck Bunny.2008..mp4"       # a name ending in dots, like Film.2010..mp4
p, t = start(dots if os.path.exists(dots) else f"{M}/video/big-buck-bunny-480p-30sec.mp4")
time.sleep(1)
set_volume(0.35)
time.sleep(4)
w = win()
# Read-only X checks (no input): the dark-frame hint, and that mpv's own window does not take the mouse.
if w:
    hint = run("xprop", "-id", w[0], "_GTK_THEME_VARIANT")
    record("Dark window frame asked for (_GTK_THEME_VARIANT)", '"dark"' in hint, hint)
    try:
        from Xlib import X, display
        d = display.Display(":0")
        top = int(w[0], 16)
        base = top & 0xFFE00000                       # X ids of one client share their high bits
        grabbing = []

        def walk(win_):
            for child in win_.query_tree().children:
                if (child.id & 0xFFE00000) != base:     # a window of another client: mpv's
                    mask = child.get_attributes().all_event_masks
                    if mask & (X.PointerMotionMask | X.ButtonPressMask):
                        grabbing.append(hex(child.id))
                walk(child)
        walk(d.create_resource_object("window", top))
        d.close()
        record("mpv's window does not take mouse events (fullscreen mouse fix)", not grabbing,
               ", ".join(grabbing) or "no other window selects pointer/button events")
    except Exception as exc:          # noqa: BLE001
        record("mpv's window does not take mouse events (fullscreen mouse fix)", False, repr(exc))
colours = 0
if w:
    from PIL import ImageGrab
    x, y, ww, hh = map(int, w[2:6])
    im = ImageGrab.grab(bbox=(x, y, x + ww, y + hh), xdisplay=":0")
    im.save(f"{S}/mint-video.png")
    colours = len(set(im.crop((ww // 4, hh // 6, 3 * ww // 4, hh // 2)).resize((40, 20)).getdata()))
n = sum(1 for line in run("wmctrl", "-l").splitlines() if "Light Media" in line or "mpv" in line.lower())
record("Video drawn inside ALMP", colours > 20 and n == 1, f"{colours} colours, ALMP/mpv windows: {n}")
sink, state = almp_stream()
record("Video sound stream", sink is not None, f"{sink}, {state}")
meta = prop("Metadata")
record("Applet details: video title without trailing dots, no artist, ALMP icon",
       not title().endswith(".") and "'xesam:artist'" not in meta and "icon.png" in meta, title())
record("Close after video", close(p))

time.sleep(1)
left = run("pgrep", "-x", "ALMP")
record("Nothing left running", left == "", left)
after = {b: status(b) for b in other_players()}
record("Other players unchanged", all(after.get(b) == s for b, s in others.items()), str(after))
print(f"{sum(results)}/{len(results)} PASS")
