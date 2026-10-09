"""Optimization provenance. Slice 470.

Every tuning decision must answer "who changed what, when, why, and
from what data". This module records each tuning *run* and each
proposal *disposition* as a hash-chained :class:`OptimizationRecord`
— mirroring :mod:`hugrgate.provenance`'s integrity chain so silent
edits break :meth:`OptimizationProvenance.verify_chain`.

A record captures: the tuner, the proposal id and its changes, the
mode and disposition, the config hash before/after, the seed, a
fingerprint of the input data (dataset hash supplied by the caller —
the tuner knows its data, this module does not), and a compact
evidence summary. :class:`ProvenanceTracker.track_run` consumes a
controller :class:`TuningRun` directly, so wiring provenance into an
existing controller is one call per cycle.

Privacy: changes and evidence summaries are config values, not user
payload — but track_run *redacts* any key whose name looks secret
(``token``, ``secret``, ``password``, ``key``) before recording.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from hugrgate.autotune.controller import Disposition, TuningRun
from hugrgate.errors import ReproducibilityError

__all__ = [
    "OptimizationProvenance",
    "OptimizationRecord",
    "ProvenanceTracker",
    "hash_mapping",
]

_SECRET_HINTS = ("token", "secret", "password", "passwd", "api_key",
                 "apikey", "private_key")


def hash_mapping(mapping: Mapping[str, Any]) -> str:
    """Stable sha256 fingerprint of a string-keyed mapping."""
    payload = json.dumps(dict(mapping), sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _redact(mapping: Mapping[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in mapping.items():
        if any(h in k.lower() for h in _SECRET_HINTS):
            out[k] = "<redacted>"
        else:
            out[k] = v
    return out


@dataclass
class OptimizationRecord:
    """One tuning event with a hash-chain integrity link."""

    record_id: str
    timestamp: float
    tuner: str
    proposal_id: str
    mode: str
    disposition: str
    changes: dict[str, Any]
    config_before_hash: str
    config_after_hash: str
    data_fingerprint: str
    seed: int
    evidence_summary: dict[str, Any] = field(default_factory=dict)
    prev_hash: str = ""
    record_hash: str = ""

    def canonical(self) -> str:
        return json.dumps({
            "record_id": self.record_id,
            "timestamp": self.timestamp,
            "tuner": self.tuner,
            "proposal_id": self.proposal_id,
            "mode": self.mode,
            "disposition": self.disposition,
            "changes": _redact(self.changes),
            "config_before_hash": self.config_before_hash,
            "config_after_hash": self.config_after_hash,
            "data_fingerprint": self.data_fingerprint,
            "seed": self.seed,
            "evidence_summary": self.evidence_summary,
            "prev_hash": self.prev_hash,
        }, sort_keys=True, default=str)

    def seal(self, prev_hash: str) -> None:
        self.prev_hash = prev_hash
        self.record_hash = hashlib.sha256(
            self.canonical().encode()).hexdigest()[:16]

    def verify(self, prev_hash: str) -> bool:
        if self.prev_hash != prev_hash:
            return False
        return (hashlib.sha256(self.canonical().encode()).hexdigest()[:16]
                == self.record_hash)

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "timestamp": self.timestamp,
            "tuner": self.tuner,
            "proposal_id": self.proposal_id,
            "mode": self.mode,
            "disposition": self.disposition,
            "changes": _redact(self.changes),
            "config_before_hash": self.config_before_hash,
            "config_after_hash": self.config_after_hash,
            "data_fingerprint": self.data_fingerprint,
            "seed": self.seed,
            "evidence_summary": dict(self.evidence_summary),
            "prev_hash": self.prev_hash,
            "record_hash": self.record_hash,
        }


class OptimizationProvenance:
    """Append-only, hash-chained store of tuning events."""

    def __init__(self, max_records: int | None = None) -> None:
        self._records: list[OptimizationRecord] = []
        self._max = max_records

    def append(self, record: OptimizationRecord) -> OptimizationRecord:
        prev = self._records[-1].record_hash if self._records else ""
        record.seal(prev)
        self._records.append(record)
        if self._max is not None:
            del self._records[:-self._max]
        return record

    def verify_chain(self) -> bool:
        prev = ""
        for record in self._records:
            if not record.verify(prev):
                return False
            prev = record.record_hash
        return True

    def by_proposal(self, proposal_id: str) -> list[OptimizationRecord]:
        return [r for r in self._records if r.proposal_id == proposal_id]

    def by_tuner(self, tuner: str) -> list[OptimizationRecord]:
        return [r for r in self._records if r.tuner == tuner]

    def recent(self, n: int = 10) -> list[OptimizationRecord]:
        return self._records[-n:]

    def __len__(self) -> int:
        return len(self._records)

    def export(self) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self._records]


class ProvenanceTracker:
    """Turn controller runs into provenance records."""

    def __init__(self, store: OptimizationProvenance | None = None,
                 clock: Any = time.time) -> None:
        self.provenance = store or OptimizationProvenance()
        self._clock = clock

    def track_run(self, run: TuningRun,
                  config_before: Mapping[str, Any],
                  config_after: Mapping[str, Any],
                  data_fingerprint: str = "",
                  tuner_of: Mapping[str, str] | None = None) -> int:
        """Record every proposal disposition in a tuning run.

        ``tuner_of`` maps proposal_id -> tuner name (from the run's
        driver details when available); unknown when the driver did
        not report it. Returns the number of records appended.
        """
        tuner_of = tuner_of or {}
        before_hash = hash_mapping(config_before)
        after_hash = hash_mapping(config_after)
        n = 0
        for result in run.results:
            tuner = tuner_of.get(result.proposal_id, "")
            if not tuner and result.detail.get("tuner"):
                tuner = str(result.detail["tuner"])
            record = OptimizationRecord(
                record_id=f"opt-{uuid4().hex[:10]}",
                timestamp=self._clock(),
                tuner=tuner,
                proposal_id=result.proposal_id,
                mode=run.mode.value,
                disposition=result.disposition.value,
                changes=dict(result.detail.get("applied",
                                              result.detail.get("changes",
                                                                {}))),
                config_before_hash=before_hash,
                config_after_hash=after_hash,
                data_fingerprint=data_fingerprint,
                seed=run.seed,
                evidence_summary={"run_id": run.run_id,
                                  "detail": {k: v for k, v in
                                             result.detail.items()
                                             if k != "applied"}},
            )
            self.provenance.append(record)
            n += 1
        if not run.results:
            # The cycle itself is still an event (e.g. all tuners
            # silent): record the heartbeat.
            self.provenance.append(OptimizationRecord(
                record_id=f"opt-{uuid4().hex[:10]}",
                timestamp=self._clock(),
                tuner="", proposal_id="", mode=run.mode.value,
                disposition=Disposition.SKIPPED.value,
                changes={}, config_before_hash=before_hash,
                config_after_hash=after_hash,
                data_fingerprint=data_fingerprint, seed=run.seed,
                evidence_summary={"run_id": run.run_id,
                                  "note": "no proposals this cycle"}))
            n = 1
        return n

    def verify(self) -> bool:
        """Verify the whole chain; raise on tampering."""
        if not self.provenance.verify_chain():
            raise ReproducibilityError(
                "optimization provenance chain is broken: records were "
                "modified or reordered")
        return True
