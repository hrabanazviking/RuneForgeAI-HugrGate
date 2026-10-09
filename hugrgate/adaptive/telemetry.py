"""Routing telemetry dataset. Slice 126.

Campaign VI (adaptive routing) learns from experience, and experience is
a dataset: every route decision becomes a :class:`RouteEvent` — the
context features the router saw, the candidates it considered, the arm it
pulled, the propensity it pulled it with, and (once known) the outcome.

:class:`TelemetryStore` is an append-only, JSONL-backed event log with:

- a schema version (``SCHEMA_VERSION``) so offline learners can reject
  foreign logs loudly instead of misreading them;
- bounded memory: ``max_records`` evicts the oldest events first;
- outcome attachment: outcomes arrive later (slices 127/128) as separate
  ``outcome`` lines that are merged on read, so the decision log itself
  is never rewritten;
- JSON-serializable validation at the boundary — malformed events raise
  :class:`~hugrgate.errors.SpecError` instead of corrupting the log.

Nothing here invents outcomes: an event without an attached outcome is
simply unlabeled, and learners must skip it (see slice 131).
"""

from __future__ import annotations

import json
import time
import uuid
from collections import OrderedDict
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from hugrgate.errors import SpecError

__all__ = [
    "SCHEMA_VERSION",
    "RouteEvent",
    "TelemetryStore",
]

#: Version stamp written into every JSONL line. Bump when the line
#: schema changes; readers reject anything else.
SCHEMA_VERSION = "adaptive-telemetry/v1"


def _require_jsonable(value: Any, name: str) -> None:
    try:
        json.dumps(value)
    except (TypeError, ValueError) as exc:
        raise SpecError(
            f"telemetry field {name!r} is not JSON-serializable: {exc}") from exc


@dataclass
class RouteEvent:
    """One logged routing decision.

    ``propensities`` maps every candidate arm to the probability with
    which the logging policy selected it — the fuel for off-policy
    evaluation (slice 144). They must sum to ~1 and include ``chosen``.

    ``outcome`` is attached later by the feedback API (slice 127) and is
    ``None`` until then. ``shadow`` marks records produced by shadow mode
    (slice 143); learners must exclude them from training.
    """

    request_id: str
    timestamp: float
    spec: dict[str, Any]
    features: dict[str, float]
    candidates: list[str]
    propensities: dict[str, float]
    chosen: str
    policy_version: str
    privacy_class: str
    latency_ms: float = 0.0
    cost: float = 0.0
    energy_wh: float = 0.0
    immediate_quality: float = 0.0
    outcome: dict[str, Any] | None = None
    shadow: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.request_id, str) or not self.request_id:
            raise SpecError("RouteEvent.request_id must be a non-empty string")
        if not self.candidates:
            raise SpecError("RouteEvent needs at least one candidate")
        if len(set(self.candidates)) != len(self.candidates):
            raise SpecError("RouteEvent.candidates must be unique")
        if self.chosen not in self.candidates:
            raise SpecError(
                f"chosen {self.chosen!r} is not among candidates "
                f"{self.candidates!r}")
        missing = set(self.candidates) - set(self.propensities)
        if missing:
            raise SpecError(
                f"propensities missing candidates: {sorted(missing)}")
        total = sum(self.propensities[c] for c in self.candidates)
        if abs(total - 1.0) > 1e-6:
            raise SpecError(
                f"propensities must sum to 1, got {total!r}")
        for name, prob in self.propensities.items():
            if not 0.0 <= prob <= 1.0:
                raise SpecError(
                    f"propensity for {name!r} out of [0,1]: {prob!r}")
        if self.propensities[self.chosen] <= 0.0:
            raise SpecError(
                "propensity of the chosen arm must be positive (needed "
                "for inverse-propensity weighting)")
        if not 0.0 <= self.immediate_quality <= 1.0:
            raise SpecError(
                f"immediate_quality out of [0,1]: {self.immediate_quality!r}")
        for fname, fval in self.features.items():
            if not isinstance(fval, (int, float)):
                raise SpecError(
                    f"feature {fname!r} must be numeric, got {fval!r}")
        for num_name in ("latency_ms", "cost", "energy_wh"):
            if getattr(self, num_name) < 0:
                raise SpecError(
                    f"{num_name} must be >= 0, got {getattr(self, num_name)!r}")
        if not isinstance(self.policy_version, str) or not self.policy_version:
            raise SpecError("policy_version must be a non-empty string")
        if not isinstance(self.privacy_class, str) or not self.privacy_class:
            raise SpecError("privacy_class must be a non-empty string")
        _require_jsonable(self.spec, "spec")
        _require_jsonable(self.metadata, "metadata")
        if self.outcome is not None:
            _require_jsonable(self.outcome, "outcome")

    @property
    def labeled(self) -> bool:
        """True once an outcome has been attached to this event."""
        return self.outcome is not None

    @property
    def quality(self) -> float | None:
        """Best known quality: outcome label wins, else immediate."""
        if self.outcome is not None and "quality" in self.outcome:
            return float(self.outcome["quality"])
        return self.immediate_quality

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["schema"] = SCHEMA_VERSION
        data["kind"] = "route_event"
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RouteEvent:
        if data.get("schema") != SCHEMA_VERSION:
            raise SpecError(
                f"unsupported telemetry schema {data.get('schema')!r}; "
                f"expected {SCHEMA_VERSION!r}")
        if data.get("kind") != "route_event":
            raise SpecError(
                f"not a route event line: kind={data.get('kind')!r}")
        payload = {k: v for k, v in data.items()
                   if k not in ("schema", "kind")}
        return cls(**payload)


class TelemetryStore:
    """Append-only JSONL store of :class:`RouteEvent` records.

    The file is the source of truth; an in-memory index (insertion
    ordered) serves reads. Outcomes are appended as separate
    ``outcome`` lines and merged onto their events on read, so decision
    lines are immutable.
    """

    def __init__(self, path: str | None = None,
                 max_records: int = 100_000) -> None:
        if max_records <= 0:
            raise SpecError(
                f"max_records must be positive, got {max_records}")
        self.path = Path(path) if path else None
        self.max_records = max_records
        self._events: OrderedDict[str, RouteEvent] = OrderedDict()
        if self.path is not None and self.path.exists():
            self._load()

    # -- writes ---------------------------------------------------------

    def record(self, event: RouteEvent) -> str:
        """Append a route decision. Returns its ``request_id``."""
        if not isinstance(event, RouteEvent):
            raise SpecError(
                f"TelemetryStore only stores RouteEvent, got "
                f"{type(event).__name__}")
        if event.request_id in self._events:
            raise SpecError(
                f"duplicate request_id {event.request_id!r}: telemetry is "
                f"append-only; attach outcomes instead")
        self._events[event.request_id] = event
        self._append_line(event.to_dict())
        self._enforce_bound()
        return event.request_id

    @staticmethod
    def new_request_id() -> str:
        return uuid.uuid4().hex[:16]

    def attach_outcome(self, request_id: str,
                       outcome: Mapping[str, Any]) -> RouteEvent:
        """Attach an outcome dict to an existing event (append-only)."""
        event = self._events.get(request_id)
        if event is None:
            raise KeyError(f"unknown request_id {request_id!r}")
        if event.outcome is not None:
            raise SpecError(
                f"outcome already attached for {request_id!r}; refusing to "
                f"overwrite history")
        _require_jsonable(dict(outcome), "outcome")
        if "quality" in outcome:
            q = outcome["quality"]
            if not isinstance(q, (int, float)) or not 0.0 <= q <= 1.0:
                raise SpecError(
                    f"outcome quality must be in [0,1], got {q!r}")
        merged = RouteEvent(**{**asdict(event), "outcome": dict(outcome)})
        self._events[request_id] = merged
        self._append_line({
            "schema": SCHEMA_VERSION,
            "kind": "outcome",
            "request_id": request_id,
            "outcome": dict(outcome),
            "attached_at": time.time(),
        })
        return merged

    # -- reads ----------------------------------------------------------

    def get(self, request_id: str) -> RouteEvent | None:
        event = self._events.get(request_id)
        return RouteEvent(**asdict(event)) if event else None

    def __len__(self) -> int:
        return len(self._events)

    def __contains__(self, request_id: object) -> bool:
        return request_id in self._events

    def events(self) -> Iterator[RouteEvent]:
        for event in self._events.values():
            yield RouteEvent(**asdict(event))

    def labeled(self) -> Iterator[RouteEvent]:
        """Events with an attached outcome, oldest first."""
        for event in self.events():
            if event.labeled:
                yield event

    def unlabeled(self) -> Iterator[RouteEvent]:
        for event in self.events():
            if not event.labeled:
                yield event

    def stats(self) -> dict[str, Any]:
        events = list(self._events.values())
        labeled = [e for e in events if e.labeled]
        return {
            "schema": SCHEMA_VERSION,
            "n_events": len(events),
            "n_labeled": len(labeled),
            "n_shadow": sum(1 for e in events if e.shadow),
            "label_rate": len(labeled) / len(events) if events else 0.0,
            "max_records": self.max_records,
            "path": str(self.path) if self.path else None,
        }

    # -- persistence ----------------------------------------------------

    def _append_line(self, line: Mapping[str, Any]) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, sort_keys=True, default=str) + "\n")

    def _load(self) -> None:
        assert self.path is not None
        with self.path.open(encoding="utf-8") as fh:
            for lineno, raw in enumerate(fh, 1):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    line = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise SpecError(
                        f"corrupt telemetry line {lineno} in {self.path}: "
                        f"{exc}") from exc
                if line.get("schema") != SCHEMA_VERSION:
                    raise SpecError(
                        f"telemetry line {lineno} has schema "
                        f"{line.get('schema')!r}; expected "
                        f"{SCHEMA_VERSION!r}")
                kind = line.get("kind")
                if kind == "route_event":
                    event = RouteEvent.from_dict(line)
                    self._events[event.request_id] = event
                elif kind == "outcome":
                    rid = line.get("request_id")
                    prior = self._events.get(rid)
                    if prior is None:
                        raise SpecError(
                            f"outcome line {lineno} references unknown "
                            f"request_id {rid!r}")
                    merged = RouteEvent(
                        **{**asdict(prior), "outcome": line["outcome"]})
                    self._events[rid] = merged
                else:
                    raise SpecError(
                        f"telemetry line {lineno} has unknown kind "
                        f"{kind!r}")
        self._enforce_bound()

    def _enforce_bound(self) -> None:
        while len(self._events) > self.max_records:
            self._events.popitem(last=False)

    def export(self, path: str) -> int:
        """Write every event (with outcomes) as route_event lines."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with out.open("w", encoding="utf-8") as fh:
            for event in self._events.values():
                fh.write(json.dumps(event.to_dict(), sort_keys=True,
                                    default=str) + "\n")
                count += 1
        return count

    @classmethod
    def import_file(cls, path: str,
                    max_records: int = 100_000) -> TelemetryStore:
        """Load a store from an exported file (route_event lines only)."""
        store = cls(path=None, max_records=max_records)
        with open(path, encoding="utf-8") as fh:
            for lineno, raw in enumerate(fh, 1):
                raw = raw.strip()
                if not raw:
                    continue
                event = RouteEvent.from_dict(json.loads(raw))
                if event.request_id in store._events:
                    raise SpecError(
                        f"duplicate request_id {event.request_id!r} at line "
                        f"{lineno} of {path}")
                store._events[event.request_id] = event
        store._enforce_bound()
        return store

    def ingest(self, events: Iterable[RouteEvent]) -> int:
        """Bulk-record events (e.g. from another store). Returns count."""
        count = 0
        for event in events:
            self.record(event)
            count += 1
        return count
