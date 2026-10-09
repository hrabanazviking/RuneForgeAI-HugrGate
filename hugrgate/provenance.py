"""Decision provenance — why did the program take this branch? Slice 9."""

from __future__ import annotations

import copy
import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional

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
    spec: Dict[str, Any]
    backend: str
    model: str
    model_version: str = "unknown"
    calibration_profile: str = "none"
    value: Any = None
    probability: float = 0.0
    policy_threshold: float = 0.0
    accepted: bool = True
    fallback_used: bool = False
    fallback_trace: List[str] = field(default_factory=list)
    latency_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Integrity chain (slice 015): each appended record commits to the
    # previous record's hash, so silent edits break verify_chain().
    prev_hash: str = ""
    record_hash: str = ""

    @classmethod
    def from_decision(cls, state: Mapping[str, Any], spec: DecisionSpec,
                      result: DecisionResult,
                      policy_threshold: float = 0.0,
                      redact_input: bool = False) -> "DecisionRecord":
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


class ProvenanceStore:
    """Append-only store of decision records.

    Integrity model: records are deep-copied on the way in and on the
    way out, so no caller can mutate history through a held reference.
    Each stored record carries ``prev_hash`` / ``record_hash`` forming
    a hash chain over the canonical record content; ``verify_chain``
    detects any tampering with the stored list itself.
    """

    def __init__(self):
        self._records: List[DecisionRecord] = []

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
        stored.prev_hash = (self._records[-1].record_hash
                            if self._records else "")
        stored.record_hash = hashlib.sha256(
            (stored.prev_hash + self._canonical(stored)).encode()
        ).hexdigest()
        self._records.append(stored)

    def by_hash(self, request_hash: str) -> Optional[DecisionRecord]:
        for r in reversed(self._records):
            if r.request_hash == request_hash:
                return copy.deepcopy(r)
        return None

    def recent(self, n: int = 10) -> List[DecisionRecord]:
        if n < 0:
            raise ValueError(f"recent(n) needs n >= 0, got {n}")
        if n == 0:
            return []
        return copy.deepcopy(self._records[-n:])

    def count(self) -> int:
        return len(self._records)

    def verify_chain(self) -> bool:
        """Recompute every link. True iff the stored history is intact."""
        prev = ""
        for r in self._records:
            if r.prev_hash != prev:
                return False
            body = self._canonical(r)
            if r.record_hash != hashlib.sha256(
                    (prev + body).encode()).hexdigest():
                return False
            prev = r.record_hash
        return True
