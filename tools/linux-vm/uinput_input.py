"""Real mouse/keyboard input through the kernel (uinput) for test VMs: works on Xorg AND Wayland, where
xdotool's XTEST events do not reach the desktop. Needs root. Reads one command per line on stdin:
    move X Y | down BUTTON | up BUTTON | click BUTTON [COUNT] | wheel up|down | key NAME (evdev name, e.g. KEY_F)
    sudo ~/venv/bin/python uinput_input.py SCREEN_WIDTH SCREEN_HEIGHT
The pointer is an absolute device (like a VM's tablet), so X Y are screen pixels."""
import sys
import time

from evdev import AbsInfo, UInput
from evdev import ecodes as e

W, H = int(sys.argv[1]), int(sys.argv[2])
RANGE = 32767
BUTTONS = {"1": e.BTN_LEFT, "2": e.BTN_MIDDLE, "3": e.BTN_RIGHT}
KEYS = [e.KEY_F, e.KEY_ESC, e.KEY_SPACE, e.KEY_PLAYPAUSE, e.KEY_NEXTSONG, e.KEY_PREVIOUSSONG]

pointer = UInput({e.EV_KEY: list(BUTTONS.values()), e.EV_REL: [e.REL_WHEEL],
                  e.EV_ABS: [(e.ABS_X, AbsInfo(0, 0, RANGE, 0, 0, 0)), (e.ABS_Y, AbsInfo(0, 0, RANGE, 0, 0, 0))]},
                 name="almp-test-tablet")
keyboard = UInput({e.EV_KEY: KEYS}, name="almp-test-keyboard")
# The wheel comes from an ordinary (relative) mouse: libinput ignored the wheel of the absolute tablet.
wheel_mouse = UInput({e.EV_KEY: [e.BTN_LEFT, e.BTN_RIGHT], e.EV_REL: [e.REL_X, e.REL_Y, e.REL_WHEEL,
                                                                      e.REL_WHEEL_HI_RES]},
                     name="almp-test-wheel")
time.sleep(1.0)                      # let the desktop pick up the new devices
print("ready", flush=True)


def button(code, value):
    pointer.write(e.EV_KEY, code, value)
    pointer.syn()


for line in sys.stdin:
    cmd = line.split()
    if not cmd:
        continue
    if cmd[0] == "move":
        pointer.write(e.EV_ABS, e.ABS_X, int(int(cmd[1]) * RANGE / (W - 1)))
        pointer.write(e.EV_ABS, e.ABS_Y, int(int(cmd[2]) * RANGE / (H - 1)))
        pointer.syn()
    elif cmd[0] in ("down", "up"):
        button(BUTTONS[cmd[1]], 1 if cmd[0] == "down" else 0)
    elif cmd[0] == "click":
        for _ in range(int(cmd[2]) if len(cmd) > 2 else 1):
            button(BUTTONS[cmd[1]], 1)
            time.sleep(0.04)
            button(BUTTONS[cmd[1]], 0)
            time.sleep(0.12)
    elif cmd[0] == "wheel":
        step = 1 if cmd[1] == "up" else -1
        wheel_mouse.write(e.EV_REL, e.REL_WHEEL, step)
        wheel_mouse.write(e.EV_REL, e.REL_WHEEL_HI_RES, 120 * step)
        wheel_mouse.syn()
    elif cmd[0] == "key":
        code = getattr(e, cmd[1])
        keyboard.write(e.EV_KEY, code, 1)
        keyboard.syn()
        time.sleep(0.05)
        keyboard.write(e.EV_KEY, code, 0)
        keyboard.syn()
    print("ok", flush=True)
pointer.close()
keyboard.close()
wheel_mouse.close()
