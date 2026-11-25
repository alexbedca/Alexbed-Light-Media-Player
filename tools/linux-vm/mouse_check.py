"""Real mouse checks of ALMP on an X11 / XWayland desktop (test VMs). Real input, NOT Qt events:
Xorg: xdotool (XTEST, real X pointer events); Wayland: a kernel uinput mouse/keyboard (uinput_input.py,
needs passwordless sudo), because XTEST events do not reach a Wayland desktop. Results are read from outside: MPRIS
(playerctl), the window list (wmctrl/xdotool) and screen grabs (ImageMagick import + Pillow).
    ~/x.sh python3 mouse_check.py <ALMP program or "src"> <video.mp4> <music folder> <shots folder>
Not for a PC someone is using: it moves the pointer and clicks.
Without xdotool / playerctl / ImageMagick (e.g. Linux Mint without sudo) it uses python-xlib (XTEST),
gdbus and Pillow's ImageGrab instead."""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

from PIL import Image

PROG, VIDEO, MUSIC, SHOTS = sys.argv[1:5]
os.makedirs(SHOTS, exist_ok=True)
SESSION = "wayland" if os.environ.get("WAYLAND_DISPLAY") else "x11"   # (over SSH XDG_SESSION_TYPE is "tty")
results = []


def run(*cmd, timeout=10):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except subprocess.TimeoutExpired:
        return ""


def record(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'} | {name} | {detail}", flush=True)


def win():
    """(id, x, y, width, height) of ALMP's main window on the screen. The position comes from xwininfo:
    wmctrl -lG gave a y that was off by the title bar height on GNOME."""
    for line in run("wmctrl", "-l").splitlines():
        if "Light Media" in line:
            wid = line.split()[0]
            info = run("xwininfo", "-id", wid)
            val = {k: int(v) for k, v in re.findall(r"(Absolute upper-left [XY]|Width|Height):\s+(-?\d+)", info)}
            if len(val) == 4:
                return wid, val["Absolute upper-left X"], val["Absolute upper-left Y"], val["Width"], val["Height"]
    return None


def grab(name):
    """Picture of ALMP's window. Xorg: cut from the screen (a window grab leaves out mpv's GL picture);
    XWayland: grab the window (the X root window is empty there)."""
    w = win()
    path = os.path.join(SHOTS, name + ".png")
    if not shutil.which("import"):
        from PIL import ImageGrab
        ImageGrab.grab(bbox=(w[1], w[2], w[1] + w[3], w[2] + w[4]), xdisplay=os.environ.get("DISPLAY")).save(path)
    elif SESSION == "x11":
        run("import", "-window", "root", "-crop", f"{w[3]}x{w[4]}+{w[1]}+{w[2]}", path)
    else:
        run("import", "-window", w[0], path)
    return Image.open(path).convert("RGB")


def is_accent(r, g, b):
    """ALMP's cyan accent (default settings: each run uses a fresh, empty Data folder)."""
    return b > 170 and g > 150 and r < 110


def accent_pixels(im, box):
    """ALMP's cyan accent (the Play/Pause button) in an area: shows whether the control bar is there."""
    part = im.crop(box).resize((max(1, (box[2] - box[0]) // 4), max(1, (box[3] - box[1]) // 4)))
    return sum(1 for r, g, b in part.getdata() if is_accent(r, g, b))


def play_button(im, box):
    """Box (left, top, right, bottom) of the Play/Pause button: the largest TALL cyan block in the area
    (the filled seek bar and the volume slider are cyan too, but thin)."""
    step = 2
    cyan = set()
    for y in range(box[1], box[3], step):
        for x in range(box[0], box[2], step):
            r, g, b = im.getpixel((x, y))
            if is_accent(r, g, b):
                cyan.add((x, y))
    best = None
    seen = set()
    for start in cyan:
        if start in seen:
            continue
        stack, blob = [start], []
        seen.add(start)
        while stack:
            px, py = stack.pop()
            blob.append((px, py))
            for n in ((px + step, py), (px - step, py), (px, py + step), (px, py - step)):
                if n in cyan and n not in seen:
                    seen.add(n)
                    stack.append(n)
        xs, ys = [q[0] for q in blob], [q[1] for q in blob]
        if max(ys) - min(ys) >= 20 and (best is None or len(blob) > best[0]):
            best = (len(blob), (min(xs), min(ys), max(xs), max(ys)))
    return best[1] if best else None


def bar_shown(im, box):
    """Is ALMP's control bar there? Its dark grey band (most of the bottom area) AND a Play/Pause-shaped
    cyan button. Cyan pixels alone are not enough: teal leaves in a film matched them (on a 1080p TV)."""
    part = im.crop((box[0], box[3] - 90, box[2], box[3])).resize((max(1, (box[2] - box[0]) // 8), 12))
    px = list(part.getdata())
    dark = sum(1 for r, g, b in px if max(r, g, b) < 60 and max(r, g, b) - min(r, g, b) < 12) / len(px)
    return dark > 0.5 and play_button(im, box) is not None, dark


def accent_centre(im, box):
    b = play_button(im, box)
    return ((b[0] + b[2]) // 2, (b[1] + b[3]) // 2) if b else None


def _gdbus(method, *args):
    return run("gdbus", "call", "--session", "-d", "org.mpris.MediaPlayer2.almp", "-o", "/org/mpris/MediaPlayer2",
               "-m", method, *args)


def _get(prop):
    return _gdbus("org.freedesktop.DBus.Properties.Get", "org.mpris.MediaPlayer2.Player", prop)


def mpris(*args):
    """playerctl -p almp <args>, or the same through gdbus when playerctl is not installed."""
    if shutil.which("playerctl"):
        return run("playerctl", "-p", "almp", *args)
    cmd = args[0]
    if cmd == "status":
        m = re.search(r"'(\w+)'", _get("PlaybackStatus"))
        return m.group(1) if m else ""
    if cmd == "volume" and len(args) > 1:
        return _gdbus("org.freedesktop.DBus.Properties.Set", "org.mpris.MediaPlayer2.Player", "Volume",
                      f"<{float(args[1])}>")
    if cmd == "volume":
        m = re.search(r"<([\d.]+)>", _get("Volume"))
        return m.group(1) if m else ""
    if cmd == "position":
        m = re.search(r"<(?:int64 )?(-?\d+)>", _get("Position"))
        return f"{int(m.group(1)) / 1e6:.6f}" if m else ""
    if cmd == "metadata":
        m = re.search(r"'xesam:title': <'(.*?)'>", _get("Metadata"))
        return m.group(1) if m else ""
    return _gdbus("org.mpris.MediaPlayer2.Player." + {"play": "Play", "pause": "Pause", "next": "Next",
                                                       "previous": "Previous"}[cmd])


class _Uinput:
    """Wayland: a root helper with a uinput tablet + keyboard (one device for the whole run)."""

    def __init__(self):
        size = run("xdotool", "getdisplaygeometry").split()
        here = os.path.dirname(os.path.abspath(__file__))
        py = "/usr/bin/python3"                    # needs evdev (python3-evdev, or ~/venv with evdev)
        if subprocess.run([py, "-c", "import evdev"], capture_output=True).returncode:
            py = os.path.expanduser("~/venv/bin/python")
        self.p = subprocess.Popen(["sudo", py, os.path.join(here, "uinput_input.py"), *size],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self.p.stdout.readline()                   # "ready"

    def send(self, line):
        self.p.stdin.write(line + "\n")
        self.p.stdin.flush()
        self.p.stdout.readline()


class _Xtest:
    """Xorg without xdotool: real X input through python-xlib's XTEST extension."""

    def __init__(self):
        from Xlib import XK, X, display
        from Xlib.ext import xtest
        self.X, self.XK, self.xtest = X, XK, xtest
        self.d = display.Display()

    def _flush(self):
        self.d.sync()

    def move(self, x, y):
        self.xtest.fake_input(self.d, self.X.MotionNotify, x=int(x), y=int(y))
        self._flush()

    def button(self, b, down):
        self.xtest.fake_input(self.d, self.X.ButtonPress if down else self.X.ButtonRelease, int(b))
        self._flush()

    def key(self, name):
        code = self.d.keysym_to_keycode(self.XK.string_to_keysym(name))
        self.xtest.fake_input(self.d, self.X.KeyPress, code)
        self._flush()
        time.sleep(0.05)
        self.xtest.fake_input(self.d, self.X.KeyRelease, code)
        self._flush()

    def visible_toplevels(self):
        n = 0
        for w in self.d.screen().root.query_tree().children:
            try:
                if w.get_attributes().map_state == self.X.IsViewable:
                    n += 1
            except Exception:          # noqa: BLE001, S110 - a window that just went away
                pass
        return n


UINPUT = _Uinput() if SESSION != "x11" else None
XT = _Xtest() if UINPUT is None and not shutil.which("xdotool") else None
KEYNAMES = {"f": "KEY_F", "Escape": "KEY_ESC", "space": "KEY_SPACE"}


def move(x, y):
    if UINPUT:
        UINPUT.send(f"move {x} {y}")
    elif XT:
        XT.move(x, y)
    else:
        run("xdotool", "mousemove", str(x), str(y))


def press_button(button, down):
    if UINPUT:
        UINPUT.send(f"{'down' if down else 'up'} {button}")
    elif XT:
        XT.button(button, down)
    else:
        run("xdotool", "mousedown" if down else "mouseup", str(button))


def visible_windows():
    """Mapped X windows with a class (a Qt pop-up menu is one): +1 when the menu opens."""
    if XT:
        return XT.visible_toplevels()             # a Qt pop-up menu is a new mapped top-level window
    return len(run("xdotool", "search", "--onlyvisible", "--class", ".").split())


def click(x, y, button=1, repeat=1):
    move(x, y)
    time.sleep(0.4)                                # let the pointer arrive before the button
    if UINPUT:
        UINPUT.send(f"click {button} {repeat}")
    elif XT:
        for i in range(repeat):
            XT.button(button, True)
            time.sleep(0.04)
            XT.button(button, False)
            if i + 1 < repeat:
                time.sleep(0.12)
    else:
        run("xdotool", "click", "--repeat", str(repeat), "--delay", "120", str(button))


def wheel_up():
    if UINPUT:
        UINPUT.send("wheel up")
    elif XT:
        XT.button(4, True)
        XT.button(4, False)
    else:
        run("xdotool", "click", "4")


def key(name):
    if UINPUT:
        UINPUT.send(f"key {KEYNAMES[name]}")
    elif XT:
        XT.key(name)
    else:
        run("xdotool", "key", name)


def start(*args):
    cmd = [PROG, *args] if PROG != "src" else [os.path.expanduser("~/venv/bin/python"), "main.py", *args]
    data = tempfile.mkdtemp(prefix="almp-mouse-data-")     # default settings, nothing left behind
    p = subprocess.Popen(cmd, stdout=open("/tmp/mouse-check.out", "w"), stderr=subprocess.STDOUT,
                         env=dict(os.environ, ALMP_DATA_DIR=data),
                         cwd=os.path.expanduser("~/ALMP-Linux") if PROG == "src" else None)
    for _ in range(150):
        if win():
            break
        time.sleep(0.1)
    for _ in range(40):
        if mpris("status") == "Playing":
            break
        time.sleep(0.25)
    return p


def close(p):
    run("wmctrl", "-c", "Light Media")
    try:
        p.wait(5)
        return True
    except subprocess.TimeoutExpired:
        p.kill()
        return False


# ---------- 1. a video: fullscreen, pointer, double-click, right-click, scroll
p = start(VIDEO)
mpris("volume", "0.5")
wid, x, y, w, h = win()
if not UINPUT and not XT:
    run("xdotool", "windowactivate", "--sync", wid)
click(x + w // 2, y + h // 3)                    # focus the video (single click does nothing else)
time.sleep(0.5)
key("f")
time.sleep(1.5)
wid, x, y, w, h = win()
record("F key: fullscreen", w >= 1200 and y == 0, f"{w}x{h}+{x}+{y}")
move(x + w // 2, y + h // 3)
time.sleep(4.5)                                   # controls hide after 3 s without activity
im = grab("fs-hidden")
bottom = (0, h - 160, w, h)
hidden, dark_before = bar_shown(im, bottom)
move(x + w // 2 + 80, y + h // 3 + 40)           # a real pointer move over the video
time.sleep(0.25)
move(x + w // 2 + 160, y + h // 3 + 60)
time.sleep(0.8)
im = grab("fs-after-move")
shown, dark_after = bar_shown(im, bottom)
record("Pointer move in fullscreen brings the controls back", not hidden and shown,
       f"control bar before: {hidden} (dark {dark_before:.0%}), after: {shown} (dark {dark_after:.0%})")
centre = accent_centre(im, bottom)
if centre:
    cx, cy = centre
    before = mpris("status")
    click(x + cx, y + cy)                        # Play/Pause button in the fullscreen bar
    time.sleep(1)
    record("Click Play/Pause in the fullscreen bar", mpris("status") != before, f"{before} -> {mpris('status')}")
    click(x + cx, y + cy)
    time.sleep(1)
else:
    record("Click Play/Pause in the fullscreen bar", False, "bar not found")
vol0 = float(mpris("volume") or 0)
move(x + w // 2, y + h // 3)
time.sleep(0.3)
for _ in range(3):                               # 3 notches: on X11 Qt (XInput2) uses the first
    wheel_up()                                   # scroll event after the pointer arrives only as a start point
    time.sleep(0.3)
time.sleep(0.8)
vol1 = float(mpris("volume") or 0)
record("Mouse wheel over the video raises the volume", vol1 > vol0, f"{vol0:.2f} -> {vol1:.2f}")
windows_before = visible_windows()
click(x + w // 2, y + h // 3, button=3)          # right-click: the video menu
time.sleep(1)
windows_after = visible_windows()
grab("right-click-menu")
record("Right-click on the video opens the menu", windows_after > windows_before,
       f"visible X windows {windows_before} -> {windows_after}")
key("Escape")
time.sleep(0.5)
click(x + w // 2, y + h // 3, repeat=2)           # double-click: leave fullscreen
time.sleep(1.5)
_, x2, y2, w2, h2 = win()
record("Double-click on the video leaves fullscreen", (w2, h2) != (w, h), f"{w}x{h} -> {w2}x{h2}")
click(x2 + w2 // 2, y2 + h2 // 3, repeat=2)        # and enters it again
time.sleep(1.5)
_, x3, y3, w3, h3 = win()
record("Double-click on the video enters fullscreen", (w3, h3) == (w, h), f"{w2}x{h2} -> {w3}x{h3}")
key("Escape")
time.sleep(1.5)

# ---------- 2. windowed: seek bar drag, Next button
wid, x, y, w, h = win()
im = grab("windowed")
bar_area = (0, h - 140, w, h)
centre = accent_centre(im, bar_area)
if centre:
    seek_y = play_button(im, bar_area)[1] - 38      # the seek bar is 38 px above the buttons
    left, right = 12, w - 12                       # playlist hidden: the bar spans the window
    for _ in range(10):                            # paused, so the position does not run on before it is read
        mpris("pause")
        time.sleep(0.3)
        if mpris("status") == "Paused":
            break
    before_drag = float(mpris("position") or 0)
    goal = 0.25 if before_drag > 15 else 0.75      # drag to the far side, so the position must change
    move(x + left + 20, y + seek_y)
    time.sleep(0.1)
    press_button(1, True)
    time.sleep(0.2)
    for k in range(1, 6):
        move(x + left + 20 + (int(goal * (right - left)) - 20) * k // 5, y + seek_y)
        time.sleep(0.08)
    press_button(1, False)
    time.sleep(0.6)
    length = 30.0
    pos = float(mpris("position") or 0)
    record(f"Drag the seek bar to {goal:.0%}", abs(pos - goal * length) <= 3 and abs(pos - before_drag) > 1,
           f"position {before_drag:.1f} -> {pos:.1f} s of {length:.0f} s ({mpris('status')})")
else:
    record("Drag the seek bar", False, "control bar not found")
record("Close (video)", close(p))

# ---------- 3. music: Next / Previous buttons in the window
p = start(MUSIC)
time.sleep(1)
wid, x, y, w, h = win()
im = grab("music-window")
centre = accent_centre(im, (0, h - 140, w, h))
if centre:
    bl, bt, br, bb = play_button(im, (0, h - 140, w, h))
    cy = (bt + bb) // 2
    t1 = mpris("metadata", "xesam:title")
    click(x + br + 8 + 20, y + cy)               # Next starts 8 px right of Play/Pause
    time.sleep(1.5)
    t2 = mpris("metadata", "xesam:title")
    record("Click Next", t2 != t1, f"{t1} -> {t2}")
    click(x + bl - 8 - 20, y + cy)               # Prev (restarts or goes back)
    time.sleep(1.5)
    record("Click Prev", mpris("metadata", "xesam:title") in (t1, t2), mpris("metadata", "xesam:title"))
else:
    record("Click Next", False, "control bar not found")
record("Close (music)", close(p))
print(f"{sum(results)}/{len(results)} PASS")
