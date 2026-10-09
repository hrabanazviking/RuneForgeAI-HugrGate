"""Ensemble provenance — every council ruling on the record. Slice 119.

Ensemble decisions already carry rich metadata (strategy, members,
member votes, weights, minority report), but :class:`DecisionRecord`
drops it: ``from_decision`` only keeps state keys. This module closes
the gap:

- :func:`record_ensemble_decision` builds the record from the state,
  spec, and ensemble result, copies the full ``metadata["ensemble"]``
  block into ``record.metadata["ensemble"]``, optionally attaches a
  :class:`MembershipManager` event log, appends to the store, and
  returns the stored (hash-chained) record;
- :func:`find_ensemble_records` retrieves recent ensemble records,
  optionally filtered by strategy.

Because records travel through ``ProvenanceStore.append``, they get
the slice-015 integrity chain for free: tampering with a recorded
ensemble ruling breaks ``verify_chain()``.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Mapping, Optional, Sequence

from hugrgate.errors import PolicyError
from hugrgate.provenance import DecisionRecord, ProvenanceStore
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "record_ensemble_decision",
    "find_ensemble_records",
]


def record_ensemble_decision(store: ProvenanceStore,
                             state: Mapping[str, Any],
                             spec: DecisionSpec,
                             result: DecisionResult,
                             membership_events: Optional[
                                 Sequence[Dict[str, Any]]] = None,
                             policy_threshold: float = 0.0,
                             redact_input: bool = False
                             ) -> DecisionRecord:
    """Record an ensemble decision with its full council detail.

    Returns the stored record (with ``prev_hash``/``record_hash``
    assigned by the store).
    """
    if not isinstance(store, ProvenanceStore):
        raise PolicyError(
            f"store must be a ProvenanceStore, got "
            f"{type(store).__name__}")
    record = DecisionRecord.from_decision(
        state, spec, result,
        policy_threshold=policy_threshold,
        redact_input=redact_input)
    ensemble_block: Dict[str, Any] = copy.deepcopy(
        result.metadata.get("ensemble", {}))
    ensemble_block["recorded"] = bool(result.metadata.get("ensemble"))
    if membership_events is not None:
        ensemble_block["membership_events"] = copy.deepcopy(
            list(membership_events))
    record.metadata["ensemble"] = ensemble_block
    store.append(record)
    stored = store.recent(1)
    return stored[0]


def find_ensemble_records(store: ProvenanceStore,
                          strategy: Optional[str] = None,
                          n: int = 100) -> List[DecisionRecord]:
    """Recent records that carry ensemble detail, newest last.

    With ``strategy`` set, only records from that strategy match.
    """
    if n < 1:
        raise PolicyError(f"n must be >= 1, got {n}")
    found = []
    for record in store.recent(n):
        block = record.metadata.get("ensemble")
        if not isinstance(block, dict) or not block.get("recorded"):
            continue
        if strategy is not None and block.get("strategy") != strategy:
            continue
        found.append(record)
    return found
