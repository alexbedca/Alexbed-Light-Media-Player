"""Linux only: start ALMP's MPRIS object alone (no window) for checks with playerctl/gdbus.
Runs for N seconds and prints every command it gets.  python tools/mpris_probe.py 20"""
import sys

from PyQt6.QtCore import QCoreApplication, QTimer

sys.path.insert(0, ".")
from almp.mpris import LinuxMediaControls  # noqa: E402

app = QCoreApplication(sys.argv)
vol = [0.8]
mc = LinuxMediaControls(volume_get=lambda: vol[0], volume_set=lambda v: (vol.__setitem__(0, v), print("volume", v)),
                        position_get=lambda: 12.5)
mc.command.connect(lambda c: print("command", c, flush=True))
mc.raise_requested.connect(lambda: print("raise", flush=True))
print("start", mc.start(), mc.bus_name, flush=True)
mc.set_track("Song ｜ full-width name", length_s=200)
mc.set_status("playing")
QTimer.singleShot(int(float(sys.argv[1] if len(sys.argv) > 1 else 15) * 1000), app.quit)
app.exec()
mc.stop()
print("stopped", flush=True)
