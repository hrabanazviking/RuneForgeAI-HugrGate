"""Distributed provenance. Slice 221.

Every node keeps its own decision history (:class:`ProvenanceStore`
on its gate). :class:`ProvenanceExchange` lets nodes share it:

- **Attribution** — records carry their origin in
  ``metadata["node_id"]``, stamped by the serving node at pull time
  (``setdefault``: a record merged from elsewhere keeps its true
  origin, never overwritten).
- **Pull** — ``PROVENANCE_PULL`` / ``PROVENANCE_RESPONSE`` with
  ``since`` / ``limit``; the RPC client validates every record shape
  on arrival.
- **Merge** — remote records are appended to the local store, which
  re-chains them into local history (``verify_chain`` still passes);
  records already present — same ``(request_hash, node_id)`` — are
  skipped, so repeated pulls are idempotent.

Records never carry raw states (only ``state_keys``), so sharing them
is privacy-safe by construction.
"""

from __future__ import annotations

from typing import Any, Protocol

from hugrgate.cluster.discovery import PeerRecord
from hugrgate.cluster.protocol import new_trace_id
from hugrgate.cluster.rpc import RPCClient
from hugrgate.core import HugrGate
from hugrgate.errors import SpecError
from hugrgate.provenance import DecisionRecord

__all__ = [
    "DEFAULT_PROVENANCE_PULL_LIMIT",
    "MAX_PROVENANCE_PULL_LIMIT",
    "ProvenanceExchange",
    "attribute_record",
]

#: Default / maximum records per pull.
DEFAULT_PROVENANCE_PULL_LIMIT = 100
MAX_PROVENANCE_PULL_LIMIT = 1000


class _ExchangeNode(Protocol):
    """The slice of :class:`ClusterNode` the exchange needs.

    A Protocol (not a ``TYPE_CHECKING`` import of node.py) because the
    import graph must stay acyclic even counting ``TYPE_CHECKING``
    edges — and node.py eagerly imports this module.
    """

    @property
    def node_id(self) -> str: ...
    @property
    def gate(self) -> HugrGate: ...
    @property
    def rpc(self) -> RPCClient: ...


def attribute_record(record: DecisionRecord, node_id: str) -> DecisionRecord:
    """Stamp origin; never overwrite an existing attribution."""
    record.metadata.setdefault("node_id", node_id)
    return record


class ProvenanceExchange:
    """Pull and merge decision history across the cluster."""

    def __init__(self, node: _ExchangeNode) -> None:
        self._node = node

    # -- serving side ----------------------------------------------------

    def serve_pull(self, since: float | None,
                   limit: int) -> list[dict[str, Any]]:
        """Records for a ``PROVENANCE_PULL`` (dicts, attributed)."""
        if not isinstance(limit, int) or limit < 1:
            raise SpecError("provenance pull needs a positive int limit")
        limit = min(limit, MAX_PROVENANCE_PULL_LIMIT)
        if since is not None and (
                not isinstance(since, (int, float)) or since < 0):
            raise SpecError("provenance 'since' must be a non-negative "
                            "timestamp")
        store = self._node.gate.provenance
        records = store.recent(limit)
        if since is not None:
            records = [r for r in records if r.timestamp >= since]
        return [attribute_record(r, self._node.node_id).to_dict()
                for r in records]

    # -- client side -----------------------------------------------------

    def pull(self, peer: PeerRecord, since: float | None = None,
             limit: int = DEFAULT_PROVENANCE_PULL_LIMIT,
             trace_id: str | None = None) -> list[DecisionRecord]:
        """Fetch a peer's decision history. Validates every record."""
        if not isinstance(limit, int) or limit < 1:
            raise SpecError("provenance pull needs a positive int limit")
        raw = self._node.rpc.pull_provenance(
            peer, since=since,
            limit=min(limit, MAX_PROVENANCE_PULL_LIMIT),
            trace_id=trace_id or new_trace_id())
        records = []
        for item in raw:
            record = DecisionRecord.from_dict(item)  # validates shape
            attribute_record(record, peer.node_id)
            records.append(record)
        return records

    def merge(self, records: list[DecisionRecord]) -> int:
        """Merge records into the local store. Returns the count added.

        Idempotent: records already present (same request hash from
        the same node) are skipped. The store re-chains merged records
        into local history.
        """
        store = self._node.gate.provenance
        known = {(r.request_hash, r.metadata.get("node_id"))
                 for r in store.recent(10 ** 6)}
        added = 0
        for record in records:
            if not isinstance(record, DecisionRecord):
                raise SpecError(
                    f"can only merge DecisionRecord, got {record!r}")
            attribute_record(record, "unknown")
            key = (record.request_hash, record.metadata.get("node_id"))
            if key in known:
                continue
            known.add(key)
            store.append(record)
            added += 1
        return added

    def pull_and_merge(self, peer: PeerRecord,
                       since: float | None = None,
                       limit: int = DEFAULT_PROVENANCE_PULL_LIMIT) -> int:
        """Pull a peer's history and merge it. Returns the count added."""
        return self.merge(self.pull(peer, since=since, limit=limit))
