"""Decision provenance — why did the program take this branch? Slice 9."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
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
    """Append-only store of decision records."""

    def __init__(self):
        self._records: List[DecisionRecord] = []

    def append(self, record: DecisionRecord) -> None:
        self._records.append(record)

    def by_hash(self, request_hash: str) -> Optional[DecisionRecord]:
        for r in reversed(self._records):
            if r.request_hash == request_hash:
                return r
        return None

    def recent(self, n: int = 10) -> List[DecisionRecord]:
        return self._records[-n:]

    def count(self) -> int:
        return len(self._records)
