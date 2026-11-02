"""Test setup: import main.py without a screen.

The tests only check plain logic (playlists, versions, retries, timers, delete decisions).
If PyQt6 or python-mpv are not installed (for example on a CI box without Qt), small
stand-in modules are used so that `import main` still works. Nothing here opens a window.
"""
import os
import sys
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _Anything:
    """Stand-in for any Qt class or enum: can be subclassed, called and dotted into."""

    def __init__(self, *args, **kwargs):
        pass

    def __call__(self, *args, **kwargs):
        return _Anything()

    def __getattr__(self, name):
        return _Anything()

    def __or__(self, other):
        return self


def _stub_module(name):
    mod = types.ModuleType(name)

    def __getattr__(attr):
        if attr == "pyqtSignal":
            return lambda *a, **k: _Anything()
        cls = type(attr, (_Anything,), {})
        setattr(mod, attr, cls)
        return cls

    mod.__getattr__ = __getattr__
    return mod


def _install_stubs():
    try:
        import PyQt6.QtCore  # noqa: F401
        import PyQt6.QtGui  # noqa: F401
        import PyQt6.QtNetwork  # noqa: F401
        import PyQt6.QtWidgets  # noqa: F401
        have_qt = True
    except Exception:
        have_qt = False
    if not have_qt:
        pkg = types.ModuleType("PyQt6")
        pkg.__path__ = []
        sys.modules["PyQt6"] = pkg
        for sub in ("QtCore", "QtGui", "QtNetwork", "QtWidgets"):
            m = _stub_module(f"PyQt6.{sub}")
            sys.modules[f"PyQt6.{sub}"] = m
            setattr(pkg, sub, m)
    try:
        import mpv  # noqa: F401
    except Exception:
        sys.modules["mpv"] = types.ModuleType("mpv")
    return have_qt


HAVE_QT = _install_stubs()
