"""Which signals ALMP's seek bar sends for press -> drag -> release (Qt events, no screen needed).
    python tools/slider_probe.py [style]      e.g. fusion (Linux default) or windows11"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF, Qt  # noqa: E402
from PyQt6.QtGui import QMouseEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])
if len(sys.argv) > 1:
    app.setStyle(sys.argv[1])
from almp.widgets import ClickSeekSlider  # noqa: E402

s = ClickSeekSlider(Qt.Orientation.Horizontal)
s.setRange(0, 30)
s.resize(1000, 24)
s.show()
app.processEvents()
log = []
s.sliderPressed.connect(lambda: log.append(("pressed", s.value())))
s.sliderMoved.connect(lambda v: log.append(("moved", v)))
s.sliderReleased.connect(lambda: log.append(("released", s.value())))


def send(kind, x, buttons):
    btn = Qt.MouseButton.LeftButton if kind != QMouseEvent.Type.MouseMove else Qt.MouseButton.NoButton
    ev = QMouseEvent(kind, QPointF(x, 12), s.mapToGlobal(QPointF(x, 12)), btn, buttons,
                     Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(s, ev)
    app.processEvents()


held = Qt.MouseButton.LeftButton
send(QMouseEvent.Type.MouseButtonPress, 300, held)
for k in range(1, 9):
    send(QMouseEvent.Type.MouseMove, 300 + 450 * k // 8, held)
send(QMouseEvent.Type.MouseButtonRelease, 750, Qt.MouseButton.NoButton)
print("style", app.style().name(), "| signals:", log, "| final value", s.value())
