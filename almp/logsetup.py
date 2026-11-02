# Alexbed Light Media Player (ALMP)
# Copyright (C) 2026 Alexander Bediako
# SPDX-License-Identifier: GPL-3.0-or-later
"""A small local log file and the "never crash on an error" hooks.

Nothing is ever sent anywhere: the log stays in %LOCALAPPDATA%\\ALMP\\almp.log (about 1 MB at most).
The log can contain file names of media you played, so it is only shared if you attach it yourself.
"""
import contextlib
import logging
import logging.handlers
import sys
import traceback

from . import __version__
from .paths import get_log_dir

log = logging.getLogger("almp")
log.addHandler(logging.NullHandler())

_notify = None          # callable(str) set once the window exists


def set_exception_notify(func):
    global _notify
    _notify = func


def setup_logging():
    """The file is only created when there is something to write."""
    try:
        log_dir = get_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            log_dir / "almp.log", maxBytes=512 * 1024, backupCount=1, encoding="utf-8", delay=True)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(handler)
        log.setLevel(logging.INFO)
        return log_dir / "almp.log"
    except Exception:          # noqa: BLE001 - no log file is not a reason to stop
        return None


def almp_excepthook(exc_type, exc, tb):
    """Log any uncaught error instead of letting PyQt abort the whole program."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, tb)
        return
    with contextlib.suppress(Exception):          # the hook itself must never raise
        log.error("Uncaught error (ALMP %s):\n%s", __version__,
                  "".join(traceback.format_exception(exc_type, exc, tb)))
    with contextlib.suppress(Exception):
        if _notify is not None:
            _notify("Something went wrong - ALMP kept running. Details were saved in almp.log.")


def almp_thread_excepthook(args):
    with contextlib.suppress(Exception):
        log.error("Uncaught error in a background thread:\n%s",
                  "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))


def install_hooks():
    import threading
    sys.excepthook = almp_excepthook
    threading.excepthook = almp_thread_excepthook
