"""Structured logging for HugrGate (slice 009).

Library policy:

- Every module logs through ``get_logger(__name__)`` (a child of the
  ``hugrgate`` logger). The ``hugrgate`` logger carries a
  :class:`logging.NullHandler` and configures **no** handlers itself, so
  importing the library never emits output and never hijacks the host
  application's logging.
- :func:`configure_logging` is the one explicit opt-in: it sets the
  level on the ``hugrgate`` logger and attaches a single stream handler
  (plain or JSON). It is idempotent — repeated calls do not duplicate
  handlers.
- **Privacy rule:** log metadata, never payload. Decision ``state``
  dicts, raw inputs, and result ``value``\\ s may contain PII; log only
  backend names, spec types, latencies, probabilities, and error codes.

Levels used across the package:

- ``DEBUG`` — per-decision internals (backend selection, cache hit/miss,
  abstention verdicts);
- ``INFO`` — lifecycle (daemon start/stop, backend registration,
  circuit-breaker transitions, fallback engagement);
- ``WARNING`` — recoverable failures (backend error, privacy-blocked
  backend, queue back-pressure);
- ``ERROR`` — unrecoverable internal faults.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any, TextIO

__all__ = [
    "PRIVACY_RULE",
    "JsonFormatter",
    "configure_logging",
    "get_logger",
]

PRIVACY_RULE = (
    "Log metadata, never payload: decision state dicts and result values "
    "must never appear in log records."
)

_ROOT_NAME = "hugrgate"


def _root() -> logging.Logger:
    logger = logging.getLogger(_ROOT_NAME)
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
    return logger


def get_logger(name: str) -> logging.Logger:
    """Return the ``hugrgate.<name>`` logger (child of the package root)."""
    short = name.split(".")[-1]
    return _root().getChild(short)


class JsonFormatter(logging.Formatter):
    """One JSON object per record: timestamp, level, logger, message."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "WARNING",
                      stream: TextIO | None = None,
                      json_format: bool = False) -> logging.Logger:
    """Opt-in logging setup for HugrGate. Idempotent.

    Sets *level* on the ``hugrgate`` logger and attaches one stream
    handler (plain text or JSON). Calling again replaces the previous
    HugrGate handler instead of stacking duplicates.
    """
    root = _root()
    root.setLevel(level.upper())
    for handler in list(root.handlers):
        if getattr(handler, "_hugrgate_managed", False):
            root.removeHandler(handler)
    handler = logging.StreamHandler(stream or sys.stderr)
    handler._hugrgate_managed = True  # type: ignore[attr-defined]
    if json_format:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    root.addHandler(handler)
    return root
