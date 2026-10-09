"""Work stealing. Slice 216.

An idle node steals queued decision jobs from a busy peer instead of
sitting idle: the classic Chase-Lev pattern across the cluster wire.

- :class:`StealableQueue` — a thread-safe double-ended queue of
  pending :class:`StealJob`\\ s. Local workers take from the **left**
  (newest first); thieves steal from the **right** (oldest, least
  likely to be in flight).
- Victim side — ``STEAL_REQUEST`` handler (``node.handle_steal_request``):
  pops up to ``max_jobs`` from the tail, redacts each job's state
  through the privacy boundary (slice 211 — stolen states never carry
  ``private_*`` fields), and answers ``STEAL_RESPONSE``.
- Thief side — ``RPCClient.steal`` / ``node.request_steal``: fetches
  jobs and enqueues them locally.

A node only serves steals while it serves remote decisions
(``serve_remote``); a busy node with an empty queue simply answers
with no jobs. Steal RPCs feed the health monitor and latency tracker
like any other remote call.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from hugrgate.cluster.privacy_boundary import PrivacyBoundary
from hugrgate.errors import SpecError

__all__ = [
    "MAX_STEAL_BATCH",
    "StealJob",
    "StealableQueue",
]

#: Hard cap on jobs per steal (a thief that asks for more gets this).
MAX_STEAL_BATCH = 64
#: Default batch when the request names none.
DEFAULT_STEAL_BATCH = 8


@dataclass
class StealJob:
    """One queued decision job, stealable by an idle peer."""

    spec: dict[str, Any]
    state: dict[str, Any]
    policy: dict[str, Any] | None = None
    context: dict[str, Any] | None = None
    enqueued_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {"spec": self.spec, "state": self.state,
                "policy": self.policy, "context": self.context,
                "enqueued_at": self.enqueued_at}

    @classmethod
    def from_dict(cls, raw: Any) -> StealJob:
        if not isinstance(raw, dict):
            raise SpecError(f"steal job must be an object, got {raw!r}")
        spec = raw.get("spec")
        state = raw.get("state")
        if not isinstance(spec, dict) or not isinstance(state, dict):
            raise SpecError("steal job needs 'spec' and 'state' objects")
        policy = raw.get("policy")
        context = raw.get("context")
        if policy is not None and not isinstance(policy, dict):
            raise SpecError("steal job 'policy' must be an object")
        if context is not None and not isinstance(context, dict):
            raise SpecError("steal job 'context' must be an object")
        return cls(spec=spec, state=state, policy=policy,
                   context=context,
                   enqueued_at=float(raw.get("enqueued_at", time.time())))

    def redacted(self) -> StealJob:
        """Copy with ``private_*`` state fields stripped (slice 211)."""
        clean, _ = PrivacyBoundary().redact_state(self.state)
        return StealJob(spec=self.spec, state=clean, policy=self.policy,
                        context=self.context,
                        enqueued_at=self.enqueued_at)


class StealableQueue:
    """Thread-safe double-ended job queue.

    Local workers take from the left (``take``); thieves steal from
    the right (``steal``) — the oldest jobs, least likely in flight.
    """

    def __init__(self) -> None:
        self._jobs: deque[StealJob] = deque()
        self._lock = threading.RLock()

    def offer(self, job: StealJob) -> None:
        """Enqueue a job (newest on the left for local workers)."""
        if not isinstance(job, StealJob):
            raise SpecError(f"can only offer StealJob, got {job!r}")
        with self._lock:
            self._jobs.appendleft(job)

    def take(self) -> StealJob | None:
        """Take the newest job for local work."""
        with self._lock:
            return self._jobs.popleft() if self._jobs else None

    def steal(self, max_jobs: int = DEFAULT_STEAL_BATCH) -> list[StealJob]:
        """Steal up to ``max_jobs`` of the oldest jobs (the tail)."""
        if not isinstance(max_jobs, int) or max_jobs < 1:
            raise SpecError("max_jobs must be a positive int")
        n = min(max_jobs, MAX_STEAL_BATCH)
        with self._lock:
            stolen = [self._jobs.pop() for _ in range(min(n, len(self._jobs)))]
        return stolen

    def __len__(self) -> int:
        with self._lock:
            return len(self._jobs)

    def drain(self) -> list[StealJob]:
        with self._lock:
            jobs = list(self._jobs)
            self._jobs.clear()
        return jobs
