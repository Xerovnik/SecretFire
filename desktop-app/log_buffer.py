# SecretFire
# Copyright (C) 2026 J. Zerovnik
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""
In-memory log buffer — captures all log records so the UI console tab
can display them without any disk I/O.
"""

import logging
import collections
import threading
import sys
import time

_MAXLEN = 500
_buffer: collections.deque = collections.deque(maxlen=_MAXLEN)
_lock = threading.Lock()

_LEVEL_COLOURS = {
    "DEBUG":    "dim",
    "INFO":     "info",
    "WARNING":  "warn",
    "ERROR":    "error",
    "CRITICAL": "error",
}


class BufferingHandler(logging.Handler):
    """Appends formatted log records to the shared in-memory buffer."""

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            with _lock:
                _buffer.append({
                    "ts":    record.created,
                    "level": record.levelname,
                    "name":  record.name,
                    "msg":   msg,
                    "cls":   _LEVEL_COLOURS.get(record.levelname, "info"),
                })
        except Exception:
            pass


class _StdoutCapture:
    """
    Wraps sys.stdout so that print() calls are captured into the log buffer
    (appearing in the Console tab) AND forwarded to the real stdout if it exists.
    """

    def __init__(self, real_stdout):
        self._real = real_stdout
        self._pending = ""

    def write(self, text: str):
        # Forward to real stdout if it's writable (console window / terminal)
        try:
            if self._real and not getattr(self._real, "closed", False):
                self._real.write(text)
        except Exception:
            pass

        # Accumulate and flush complete lines into the buffer
        self._pending += text
        while "\n" in self._pending:
            line, self._pending = self._pending.split("\n", 1)
            line = line.rstrip("\r")
            if line:
                with _lock:
                    _buffer.append({
                        "ts":    time.time(),
                        "level": "INFO",
                        "name":  "stdout",
                        "msg":   line,
                        "cls":   "info",
                    })

    def flush(self):
        try:
            if self._real and not getattr(self._real, "closed", False):
                self._real.flush()
        except Exception:
            pass

    def __getattr__(self, name):
        return getattr(self._real, name)


def install(fmt: str = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"):
    """
    Attach the buffer handler to the root logger.
    Call this AFTER logging.basicConfig() so basicConfig's StreamHandler
    is already in place and this just adds the buffer as a second handler.
    Also wraps sys.stdout so print() calls appear in the Console tab.
    """
    # Attach buffer handler to root logger
    h = BufferingHandler()
    h.setFormatter(logging.Formatter(fmt))
    logging.getLogger().addHandler(h)

    # Redirect stdout so print() output also appears in the console tab
    sys.stdout = _StdoutCapture(sys.stdout)


def get_lines(since_ts: float = 0.0, limit: int = 200) -> list[dict]:
    """Return buffered log lines newer than since_ts, up to limit."""
    with _lock:
        lines = [l for l in _buffer if l["ts"] > since_ts]
    return lines[-limit:]
