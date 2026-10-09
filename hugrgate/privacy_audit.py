"""Policy violation audit log. Slice 244.

Every privacy denial should leave a trace. :class:`PrivacyAuditLog`
is an append-only, hash-chained log of privacy-relevant events
(backend blocks, flow denials, secret detections, jurisdiction and
local-only violations, key rotations, purges). Each event commits
to the previous event's hash, so silent edits or deletions break
:meth:`PrivacyAuditLog.verify`.

The log is in-memory by default; attach a sink (e.g.
:class:`FileAuditSink`) for durability. Sinks receive the event
dict and must not raise — a failing sink would otherwise turn an
audit trail into a denial of service; sink errors are logged and
swallowed deliberately (documented).
"""

from __future__ import annotations

import copy
import hashlib
import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hugrgate.log import get_logger

logger = get_logger(__name__)

__all__ = [
    "FileAuditSink",
    "PrivacyAuditEvent",
    "PrivacyAuditLog",
]

#: Well-known event names (operators may record custom ones too).
EVENT_BACKEND_BLOCKED = "backend_blocked"
EVENT_FLOW_DENIED = "flow_denied"
EVENT_SECRET_DETECTED = "secret_detected"
EVENT_JURISDICTION_VIOLATION = "jurisdiction_violation"
EVENT_LOCAL_ONLY_VIOLATION = "local_only_violation"
EVENT_KEY_ROTATED = "key_rotated"
EVENT_RECORD_PURGED = "record_purged"


@dataclass
class PrivacyAuditEvent:
    """One audited privacy event."""

    event: str
    timestamp: float = field(default_factory=time.time)
    details: dict[str, Any] = field(default_factory=dict)
    prev_hash: str = ""
    event_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"event": self.event, "timestamp": self.timestamp,
                "details": dict(self.details), "prev_hash": self.prev_hash,
                "event_hash": self.event_hash}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PrivacyAuditEvent:
        return cls(event=data["event"],
                   timestamp=data.get("timestamp", time.time()),
                   details=dict(data.get("details", {})),
                   prev_hash=data.get("prev_hash", ""),
                   event_hash=data.get("event_hash", ""))


class FileAuditSink:
    """Append-only JSON-lines sink."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def __call__(self, event: dict[str, Any]) -> None:
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, sort_keys=True, default=str)
                     + "\n")


class PrivacyAuditLog:
    """Append-only, hash-chained privacy audit log.

    Parameters
    ----------
    sink:
        Optional callable receiving each event dict (e.g.
        :class:`FileAuditSink`). Sink errors are logged and
        swallowed — auditing must never break the guarded
        operation.
    """

    def __init__(self, sink: Callable[[dict[str, Any]], None] | None = None):
        self._events: list[PrivacyAuditEvent] = []
        self._sink = sink

    @staticmethod
    def _canonical(event: PrivacyAuditEvent) -> str:
        body = event.to_dict()
        body.pop("event_hash", None)
        return json.dumps(body, sort_keys=True, default=str)

    def record(self, event: str, **details: Any) -> PrivacyAuditEvent:
        """Append an event; returns it (a copy)."""
        entry = PrivacyAuditEvent(
            event=str(event), details=dict(details),
            prev_hash=self._events[-1].event_hash if self._events else "")
        entry.event_hash = hashlib.sha256(
            (entry.prev_hash + self._canonical(entry)).encode()).hexdigest()
        self._events.append(entry)
        if self._sink is not None:
            try:
                self._sink(entry.to_dict())
            except Exception as e:  # noqa: BLE001 - auditing never breaks ops
                logger.error("privacy audit sink failed: %s", e)
        return copy.deepcopy(entry)

    def verify(self) -> bool:
        """Recompute every link; False on any tampering."""
        prev = ""
        for entry in self._events:
            if entry.prev_hash != prev:
                return False
            if entry.event_hash != hashlib.sha256(
                    (entry.prev_hash +
                     self._canonical(entry)).encode()).hexdigest():
                return False
            prev = entry.event_hash
        return True

    def events(self, event: str | None = None) -> list[PrivacyAuditEvent]:
        """All events, optionally filtered by name (deep copies)."""
        selected = [e for e in self._events
                    if event is None or e.event == event]
        return copy.deepcopy(selected)

    def count(self) -> int:
        return len(self._events)

    def to_dict(self) -> dict[str, Any]:
        return {"events": [e.to_dict() for e in self._events]}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PrivacyAuditLog:
        log = cls()
        log._events = [PrivacyAuditEvent.from_dict(e)
                       for e in data.get("events", [])]
        return log
