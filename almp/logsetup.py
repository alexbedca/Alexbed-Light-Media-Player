# Alexbed Light Media Player (ALMP)
# Copyright (C) 2026 Alexander Bediako
# SPDX-License-Identifier: GPL-3.0-or-later
"""A small local log file and the "never crash on an error" hooks.

Nothing is ever sent anywhere. The log (almp.log) is in ALMP's Data folder, at most 256 KB plus one
older copy. What happens to it is a setting (Settings > Privacy):
  * "clear" (default): the log is deleted when ALMP closes normally, unless an error was written
    during this run (then it is kept, so the problem can be looked at);
  * "keep": the log of the last run is kept (the run before it becomes almp.log.1);
  * "off": no log file at all.
The log can contain file names of media you played, so it is only shared if you attach it yourself.
"""
import contextlib
import logging
import logging.handlers
import os
import sys
import time
import traceback

from . import __version__
from .paths import get_log_dir

log = logging.getLogger("almp")
STARTED_AT = time.perf_counter()     # for the start-up times written to almp.log
log.addHandler(logging.NullHandler())

LOG_NAME = "almp.log"
LOG_MAX_BYTES = 256 * 1024
LOG_MODES = ("clear", "keep", "off")

_notify = None          # callable(str) set once the window exists
_file_handler = None
_error_flag = None


class _ErrorFlag(logging.Handler):
    """Remembers whether this run wrote an error (then the log is kept on close)."""

    def __init__(self):
        super().__init__(level=logging.ERROR)
        self.seen = False

    def emit(self, record):
        self.seen = True


def seconds_since_start():
    return time.perf_counter() - STARTED_AT


def set_exception_notify(func):
    global _notify
    _notify = func


def errors_this_run():
    return bool(_error_flag is not None and _error_flag.seen)


def setup_logging(mode="clear", log_dir=None):
    """The file is only created when there is something to write. Returns its path, or None."""
    global _file_handler, _error_flag
    mode = mode if mode in LOG_MODES else "clear"
    if _error_flag is None:
        _error_flag = _ErrorFlag()
        log.addHandler(_error_flag)
    log.setLevel(logging.INFO)
    if mode == "off":
        return None
    try:
        log_dir = get_log_dir() if log_dir is None else log_dir
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            log_dir / LOG_NAME, maxBytes=LOG_MAX_BYTES, backupCount=1, encoding="utf-8", delay=True)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(handler)
        _file_handler = handler
        return log_dir / LOG_NAME
    except Exception:          # noqa: BLE001 - no log file is not a reason to stop
        return None


def start_new_run_log():
    """"Keep the last run": the previous run's log becomes almp.log.1 and this run starts empty.
    Called only by the ALMP that got the single-instance lock (never by a second copy handing over files)."""
    h = _file_handler
    if h is None:
        return False
    try:
        if os.path.getsize(h.baseFilename) > 0:
            h.doRollover()
            return True
    except OSError:
        pass
    return False


def finish_logging(mode="clear", log_dir=None):
    """Called after a NORMAL close. In "clear" mode the log files are deleted unless this run wrote
    an error. Returns True if they were deleted. (After a crash this never runs, so the log stays.)"""
    global _file_handler
    if _file_handler is not None:
        with contextlib.suppress(Exception):
            log.removeHandler(_file_handler)
            _file_handler.close()
        _file_handler = None
    if mode not in ("clear", "off") or errors_this_run():
        return False
    log_dir = get_log_dir() if log_dir is None else log_dir
    removed = False
    for name in (LOG_NAME, LOG_NAME + ".1"):
        p = log_dir / name
        with contextlib.suppress(OSError):
            if p.is_file() and not p.is_symlink():
                p.unlink()
                removed = True
    return removed


def reset_for_tests():
    global _file_handler, _error_flag
    for h in (_file_handler, _error_flag):
        if h is not None:
            with contextlib.suppress(Exception):
                log.removeHandler(h)
                h.close()
    _file_handler = None
    _error_flag = None


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
