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


def install(fmt: str = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"):
    """Attach the buffer handler to the root logger."""
    h = BufferingHandler()
    h.setFormatter(logging.Formatter(fmt))
    logging.getLogger().addHandler(h)


def get_lines(since_ts: float = 0.0, limit: int = 200) -> list[dict]:
    """Return buffered log lines newer than since_ts, up to limit."""
    with _lock:
        lines = [l for l in _buffer if l["ts"] > since_ts]
    return lines[-limit:]
