"""Press a key on a virtual keyboard (Linux uinput), so the desktop sees a real key press on both
Xorg and Wayland. Test helper for the VM only; needs root:  sudo ~/venv/bin/python presskey.py KEY_PLAYPAUSE
Keys used: KEY_PLAYPAUSE, KEY_NEXTSONG, KEY_PREVIOUSSONG, KEY_STOPCD."""
import sys
import time

from evdev import UInput
from evdev import ecodes as e

names = sys.argv[1:] or ["KEY_PLAYPAUSE"]
codes = [getattr(e, n) for n in names]
with UInput({e.EV_KEY: codes}, name="almp-test-keys") as ui:
    time.sleep(1.0)                 # let the desktop notice the new keyboard
    for c in codes:
        ui.write(e.EV_KEY, c, 1)
        ui.syn()
        time.sleep(0.05)
        ui.write(e.EV_KEY, c, 0)
        ui.syn()
        time.sleep(0.3)
