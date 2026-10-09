"""Decision provenance — why did the program take this branch? Slice 9."""

from __future__ import annotations

import copy
import hashlib
import json
import threading
import time
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "DecisionRecord",
    "ProvenanceStore",
]


def _hash_request(state: Mapping[str, Any], spec: DecisionSpec) -> str:
    payload = json.dumps({"state": dict(state), "spec": spec.to_dict()},
                         sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class DecisionRecord:
    request_hash: str
    spec: dict[str, Any]
    backend: str
    model: str
    model_version: str = "unknown"
    calibration_profile: str = "none"
    value: Any = None
    probability: float = 0.0
    policy_threshold: float = 0.0
    accepted: bool = True
    fallback_used: bool = False
    fallback_trace: list[str] = field(default_factory=list)
    latency_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)
    # Integrity chain (slice 015): each appended record commits to the
    # previous record's hash, so silent edits break verify_chain().
    prev_hash: str = ""
    record_hash: str = ""

    @classmethod
    def from_decision(cls, state: Mapping[str, Any], spec: DecisionSpec,
                      result: DecisionResult,
                      policy_threshold: float = 0.0,
                      redact_input: bool = False) -> DecisionRecord:
        return cls(
            request_hash=_hash_request(state, spec),
            spec=spec.to_dict(),
            backend=result.backend,
            model=result.model,
            calibration_profile=result.calibration_profile,
            value=result.value,
            probability=result.probability,
            policy_threshold=policy_threshold,
            accepted=result.accepted,
            fallback_used=result.fallback_used,
            latency_ms=result.latency_ms,
            metadata={} if redact_input else {"state_keys": list(state.keys())},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_hash": self.request_hash,
            "spec": dict(self.spec),
            "backend": self.backend,
            "model": self.model,
            "model_version": self.model_version,
            "calibration_profile": self.calibration_profile,
            "value": self.value,
            "probability": self.probability,
            "policy_threshold": self.policy_threshold,
            "accepted": self.accepted,
            "fallback_used": self.fallback_used,
            "fallback_trace": list(self.fallback_trace),
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp,
            "metadata": dict(self.metadata),
            "prev_hash": self.prev_hash,
            "record_hash": self.record_hash,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> DecisionRecord:
        """Rebuild a record from :meth:`to_dict` output.

        Raises ``SpecError`` when required keys are missing.
        """
        from hugrgate.errors import SpecError
        required = {"request_hash", "spec", "backend", "model", "value",
                    "probability"}
        missing = required - set(d)
        if missing:
            raise SpecError(
                f"DecisionRecord.from_dict missing key(s): "
                f"{sorted(missing)}")
        return cls(
            request_hash=d["request_hash"],
            spec=dict(d["spec"]),
            backend=d["backend"],
            model=d["model"],
            model_version=d.get("model_version", "unknown"),
            calibration_profile=d.get("calibration_profile", "none"),
            value=d["value"],
            probability=d["probability"],
            policy_threshold=d.get("policy_threshold", 0.0),
            accepted=d.get("accepted", True),
            fallback_used=d.get("fallback_used", False),
            fallback_trace=list(d.get("fallback_trace") or []),
            latency_ms=d.get("latency_ms", 0.0),
            timestamp=d.get("timestamp", time.time()),
            metadata=dict(d.get("metadata") or {}),
            prev_hash=d.get("prev_hash", ""),
            record_hash=d.get("record_hash", ""),
        )


class ProvenanceStore:
    """Append-only store of decision records.

    Integrity model: records are deep-copied on the way in and on the
    way out, so no caller can mutate history through a held reference.
    Each stored record carries ``prev_hash`` / ``record_hash`` forming
    a hash chain over the canonical record content; ``verify_chain``
    detects any tampering with the stored list itself.

    ``max_records`` bounds memory: when exceeded, the oldest records
    are evicted, but the chain stays verifiable — ``_floor_hash``
    checkpoints the hash of the last evicted record, and
    ``verify_chain`` treats it as the valid starting link.
    """

    def __init__(self, max_records: int | None = None):
        if max_records is not None and max_records < 1:
            raise ValueError("max_records must be >= 1")
        self._max_records = max_records
        self._records: list[DecisionRecord] = []
        self._floor_hash = ""  # record_hash of the last evicted record
        self._evicted = 0
        self._lock = threading.RLock()

    @staticmethod
    def _canonical(record: DecisionRecord) -> str:
        body = asdict(record)
        body.pop("record_hash", None)
        return json.dumps(body, sort_keys=True, default=str)

    def append(self, record: DecisionRecord) -> None:
        if not isinstance(record, DecisionRecord):
            raise TypeError(
                f"ProvenanceStore only stores DecisionRecord, got "
                f"{type(record).__name__}")
        stored = copy.deepcopy(record)
        with self._lock:
            stored.prev_hash = (self._records[-1].record_hash
                                if self._records else self._floor_hash)
            stored.record_hash = hashlib.sha256(
                (stored.prev_hash + self._canonical(stored)).encode()
            ).hexdigest()
            self._records.append(stored)
            while (self._max_records is not None
                   and len(self._records) > self._max_records):
                dropped = self._records.pop(0)
                self._floor_hash = dropped.record_hash
                self._evicted += 1

    def evicted_count(self) -> int:
        """How many oldest records were evicted by ``max_records``."""
        with self._lock:
            return self._evicted

    def purge(self, predicate) -> int:
        """Remove records matching ``predicate``; return the count removed.

        Slice 239: retention purges. Surviving records are re-chained
        from ``_floor_hash`` so :meth:`verify_chain` still passes —
        a purge re-anchors history (documented; the removed records
        are gone, not hidden). Thread-safe.
        """
        with self._lock:
            kept = [r for r in self._records if not predicate(r)]
            removed = len(self._records) - len(kept)
            if removed:
                prev = self._floor_hash
                for r in kept:
                    r.prev_hash = prev
                    r.record_hash = hashlib.sha256(
                        (prev + self._canonical(r)).encode()).hexdigest()
                    prev = r.record_hash
                self._records = kept
            return removed

    def by_hash(self, request_hash: str) -> DecisionRecord | None:
        with self._lock:
            records = list(self._records)
        for r in reversed(records):
            if r.request_hash == request_hash:
                return copy.deepcopy(r)
        return None

    def recent(self, n: int = 10) -> list[DecisionRecord]:
        if n < 0:
            raise ValueError(f"recent(n) needs n >= 0, got {n}")
        if n == 0:
            return []
        with self._lock:
            return copy.deepcopy(self._records[-n:])

    def count(self) -> int:
        with self._lock:
            return len(self._records)

    def verify_chain(self) -> bool:
        """Recompute every link. True iff the stored history is intact.

        After ``max_records`` evictions the chain starts at the
        checkpoint ``_floor_hash`` instead of the empty string.
        """
        with self._lock:
            records = list(self._records)
            prev = self._floor_hash
        for r in records:
            if r.prev_hash != prev:
                return False
            body = self._canonical(r)
            if r.record_hash != hashlib.sha256(
                    (prev + body).encode()).hexdigest():
                return False
            prev = r.record_hash
        return True
