"""Screenshots of every ALMP window on a Linux desktop (Xorg test VM), with title bars, for a side-by-side
look with the Windows screenshots (ALMP-GitHub/images). Real clicks (xdotool), fresh settings, media copies.
    ~/x.sh python3 look_shots.py <ALMP program> <music folder copy> <video file> <shots folder>
The delete question is answered with Escape (Cancel): nothing is deleted."""
import os
import sys
import time

sys.argv = [sys.argv[0], sys.argv[1], sys.argv[3], sys.argv[2], sys.argv[4]]
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mouse_check_lib as m  # noqa: E402  (mouse_check.py without its test run)

SHOTS = sys.argv[4]


def screen(name):
    m.run("import", "-window", "root", os.path.join(SHOTS, name + ".png"))
    print("shot", name, flush=True)


def window_of(title_part):
    for line in m.run("wmctrl", "-l").splitlines():
        if title_part in line:
            wid = line.split()[0]
            info = m.run("xwininfo", "-id", wid)
            import re
            v = {k: int(x) for k, x in re.findall(r"(Absolute upper-left [XY]|Width|Height):\s+(-?\d+)", info)}
            return v["Absolute upper-left X"], v["Absolute upper-left Y"], v["Width"], v["Height"]
    return None


p = m.start(sys.argv[3])                       # the music folder
time.sleep(1.5)
wid, x, y, w, h = m.win()
m.run("wmctrl", "-i", "-r", wid, "-b", "remove,maximized_vert,maximized_horz")
m.run("wmctrl", "-i", "-r", wid, "-e", "0,60,60,1100,650")
time.sleep(1.5)
wid, x, y, w, h = m.win()
screen("01-main-window")
im = m.grab("tmp")
bl, bt, br, bb = m.play_button(im, (0, h - 140, w, h))
pc = ((bl + br) // 2, (bt + bb) // 2)
row2 = pc[1] + 46                                # the second row of buttons (narrow bar) or the same row
icons = {"sleep": 16, "contrast": 68, "settings": 120}
# sleep timer menu
m.click(x + pc[0] + icons["sleep"], y + row2)
time.sleep(1)
screen("02-sleep-timer-menu")
m.key("Escape")
time.sleep(0.5)
# high contrast on, shot, off
m.click(x + pc[0] + icons["contrast"], y + row2)
time.sleep(1.2)
screen("03-high-contrast")
m.click(x + pc[0] + icons["contrast"], y + row2)
time.sleep(1.2)
# Settings, then About from Settings
m.click(x + pc[0] + icons["settings"], y + row2)
time.sleep(1.5)
screen("04-settings")
s = window_of("ALMP settings")
if s:
    sx, sy, sw, sh = s
    m.click(sx + 122, sy + sh - 27)              # "About ALMP" at the bottom left of Settings
    time.sleep(1.5)
    screen("05-about")
    m.key("Escape")                          # closes About
    time.sleep(0.8)
m.run("wmctrl", "-c", "ALMP settings")
time.sleep(0.8)
# delete question: first playlist row, Delete key, then Escape = Cancel
m.click(x + w - 200, y + 140)
time.sleep(0.5)
m.run("xdotool", "key", "shift+Delete")          # "Delete file..." asks first
time.sleep(1.2)
screen("06-delete-question")
m.key("Escape")
time.sleep(0.8)
# fullscreen with the controls showing
m.close(p)
p = m.start(sys.argv[2])                       # the video
time.sleep(1)
m.key("f")
time.sleep(4)
wid, x, y, w, h = m.win()
m.move(x + w // 2, y + h // 3)
time.sleep(0.3)
m.move(x + w // 2 + 100, y + h // 3 + 50)
time.sleep(0.8)
screen("07-fullscreen-controls")
m.key("Escape")
time.sleep(1)
m.close(p)
print("done")
