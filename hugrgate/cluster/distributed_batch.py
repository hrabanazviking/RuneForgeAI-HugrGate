"""Distributed batching. Slice 217.

One BATCH_REQUEST envelope per peer instead of one DECIDE_REQUEST per
decision: :class:`DistributedBatcher` buffers jobs keyed by
destination node id and ``flush()`` sends each peer's jobs in a
single envelope (the wire shape from slice 207). Batches are split at
``max_batch_size``; a failed peer poisons only its own jobs — every
buffered job gets an explicit outcome, never a silent drop.

Typical use: route each job with the distributed router (slice 212),
``submit()`` it to the chosen peer, then ``flush()`` once per tick.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Protocol

from hugrgate.cluster.discovery import PeerRecord
from hugrgate.cluster.privacy_boundary import PrivacyBoundary
from hugrgate.cluster.protocol import new_trace_id
from hugrgate.cluster.rpc import RPCClient
from hugrgate.errors import BackendError, PrivacyViolation, SpecError
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult
from hugrgate.serde import result_from_dict
from hugrgate.spec import DecisionSpec

__all__ = [
    "DEFAULT_MAX_BATCH_SIZE",
    "BatchJob",
    "BatchOutcome",
    "DistributedBatcher",
]


class _BatcherNode(Protocol):
    """The slice of :class:`ClusterNode` the batcher needs.

    A Protocol (not a ``TYPE_CHECKING`` import of node.py) because the
    import graph must stay acyclic even counting ``TYPE_CHECKING``
    edges — and node.py eagerly imports this module.
    """

    @property
    def rpc(self) -> RPCClient: ...
    def peers(self) -> list[PeerRecord]: ...

#: Jobs per envelope per peer per flush.
DEFAULT_MAX_BATCH_SIZE = 32


@dataclass
class BatchJob:
    """One decision to be sent to a peer."""

    spec: DecisionSpec
    state: dict[str, Any]
    policy: DecisionPolicy | None = None
    backend_name: str | None = None
    context: dict[str, Any] | None = None


@dataclass
class BatchOutcome:
    """Per-job result of a flush."""

    ok: bool
    result: DecisionResult | None = None
    error: str | None = None
    abstained: bool = False
    trace_id: str = field(default_factory=new_trace_id)


class DistributedBatcher:
    """Group pending decisions by destination node; flush as batches."""

    def __init__(self, node: _BatcherNode,
                 max_batch_size: int = DEFAULT_MAX_BATCH_SIZE) -> None:
        if not isinstance(max_batch_size, int) or max_batch_size < 1:
            raise SpecError("max_batch_size must be a positive int")
        self._node = node
        self._max_batch_size = max_batch_size
        self._buffer: dict[str, list[BatchJob]] = {}
        self._lock = threading.RLock()

    @property
    def max_batch_size(self) -> int:
        return self._max_batch_size

    def pending(self, node_id: str | None = None) -> int:
        """Jobs buffered (for one peer, or all)."""
        with self._lock:
            if node_id is not None:
                return len(self._buffer.get(node_id, []))
            return sum(len(jobs) for jobs in self._buffer.values())

    def submit(self, node_id: str, job: BatchJob) -> None:
        """Buffer a job for a peer (by node id)."""
        if not isinstance(job, BatchJob):
            raise SpecError(f"can only submit BatchJob, got {job!r}")
        if not isinstance(job.spec, DecisionSpec):
            raise SpecError("BatchJob.spec must be a DecisionSpec")
        with self._lock:
            self._buffer.setdefault(node_id, []).append(job)

    def flush(self) -> dict[str, list[BatchOutcome]]:
        """Send every buffered job, grouped by peer.

        Returns ``{node_id: [BatchOutcome, ...]}`` in submit order.
        Buffers are cleared even when a peer fails — a failed peer's
        jobs come back as error outcomes, never vanish.
        """
        with self._lock:
            buffered = self._buffer
            self._buffer = {}
        outcomes: dict[str, list[BatchOutcome]] = {}
        for node_id, jobs in buffered.items():
            outcomes[node_id] = self._flush_peer(node_id, jobs)
        return outcomes

    def _flush_peer(self, node_id: str,
                    jobs: list[BatchJob]) -> list[BatchOutcome]:
        outcomes: list[BatchOutcome] = []
        peer = self._find_peer(node_id)
        if peer is None:
            for _ in jobs:
                outcomes.append(BatchOutcome(
                    ok=False, error=f"unknown peer {node_id[:12]}…"))
            return outcomes
        for chunk in self._chunks(jobs):
            outcomes.extend(self._send_chunk(peer, node_id, chunk))
        return outcomes

    def _find_peer(self, node_id: str):  # PeerRecord | None
        for peer in self._node.peers():
            if peer.node_id == node_id:
                return peer
        return None

    def _chunks(self, jobs: list[BatchJob]) -> list[list[BatchJob]]:
        return [jobs[i:i + self._max_batch_size]
                for i in range(0, len(jobs), self._max_batch_size)]

    def _send_chunk(self, peer, node_id: str,
                    chunk: list[BatchJob]) -> list[BatchOutcome]:
        # Jobs whose own policy forbids remote inference never leave
        # the node: they get error outcomes right here.
        boundary = PrivacyBoundary()
        blocked: dict[int, BatchOutcome] = {}
        sendable: list[BatchJob] = []
        for i, job in enumerate(chunk):
            try:
                boundary.check_outbound_allowed(
                    job.policy or DecisionPolicy())
            except PrivacyViolation as e:
                blocked[i] = BatchOutcome(ok=False, error=e.message)
            else:
                sendable.append(job)
        requests = [{
            "spec": job.spec,
            "state": job.state,
            "policy": job.policy,
            "backend_name": job.backend_name,
            "context": job.context,
        } for job in sendable]
        sent: list[BatchOutcome] = []
        if requests:
            try:
                raw_results = self._node.rpc.batch(
                    peer, requests,
                    policy=DecisionPolicy(remote_inference=True))
            except BackendError as e:
                sent = [BatchOutcome(ok=False, error=e.message)
                        for _ in sendable]
            else:
                for _raw in raw_results:
                    sent.append(self._outcome_from(_raw))
                # A short reply is a protocol violation: pad with
                # errors so no job loses its outcome.
                while len(sent) < len(sendable):
                    sent.append(BatchOutcome(
                        ok=False, error="peer returned a short batch"))
        sent_iter = iter(sent)
        outcomes: list[BatchOutcome] = []
        for i in range(len(chunk)):
            if i in blocked:
                outcomes.append(blocked[i])
            else:
                outcomes.append(next(sent_iter))
        return outcomes

    @staticmethod
    def _outcome_from(raw: Any) -> BatchOutcome:
        if not isinstance(raw, dict):
            return BatchOutcome(ok=False, error=f"bad batch item {raw!r}")
        if raw.get("abstained"):
            return BatchOutcome(ok=False, abstained=True,
                                error=raw.get("message")
                                or "peer abstained")
        if "error" in raw:
            err = raw["error"]
            message = (err.get("message") if isinstance(err, dict)
                       else str(err))
            return BatchOutcome(ok=False, error=message)
        result = raw.get("result")
        if isinstance(result, dict) and "value" in result:
            return BatchOutcome(
                ok=True, result=result_from_dict(result))
        return BatchOutcome(ok=False, error="peer returned no result")
