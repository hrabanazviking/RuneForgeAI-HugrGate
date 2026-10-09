"""ClusterNode — one HugrGate node in a cluster. Slice 207 (grows).

A node binds the campaign's pieces: identity (202), capabilities
(203), discovery (204-206), RPC (207), and the local :class:`HugrGate`.
Later slices register more message handlers and subsystems on the same
object (policy sync in 210, work stealing in 216, …) instead of
building parallel node types.

Inbound dispatch is a handler table keyed by :class:`MessageType`;
unknown types get a typed ERROR envelope, never a guess.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any, Protocol

from hugrgate.cluster.capabilities import NodeCapabilities
from hugrgate.cluster.discovery import DiscoveryRegistry, PeerRecord
from hugrgate.cluster.identity import NodeIdentity
from hugrgate.cluster.node_cost import CostModel
from hugrgate.cluster.node_health import NodeHealthMonitor
from hugrgate.cluster.node_latency import LatencyTracker
from hugrgate.cluster.policy_sync import PolicyPropagator
from hugrgate.cluster.protocol import (
    ClusterMessage,
    MessageType,
    new_trace_id,
)
from hugrgate.cluster.routing import DistributedRouter, PeerScores
from hugrgate.cluster.rpc import RPCClient, error_envelope
from hugrgate.cluster.work_stealing import (
    DEFAULT_STEAL_BATCH,
    MAX_STEAL_BATCH,
    StealableQueue,
    StealJob,
)
from hugrgate.core import HugrGate
from hugrgate.errors import (
    Abstention,
    BackendError,
    BackendUnavailable,
    ClusterAuthError,
    HugrGateError,
    PolicyError,
    PrivacyViolation,
    SpecError,
)
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult
from hugrgate.serde import policy_from_dict
from hugrgate.spec import DecisionSpec

if TYPE_CHECKING:
    from hugrgate.cluster.rpc import OutboundHook

__all__ = [
    "ClusterNode",
    "InboundHook",
    "NodeAuthenticator",
]

#: Structural type for slice-208 authenticators. Declared here (rather
#: than importing ``hugrgate.cluster.auth``) because the import graph —
#: including ``TYPE_CHECKING`` edges — must stay acyclic: auth.py
#: already references ClusterNode.
class NodeAuthenticator(Protocol):
    def seal(self, data: bytes) -> str: ...
    def verify(self, data: bytes, tag: str | None) -> bool: ...

#: Server-side hook applied to inbound envelopes (slice 208 plugs
#: authentication verification in here). May raise to reject.
InboundHook = Callable[[ClusterMessage], None]


class ClusterNode:
    """One node: identity + gate + discovery + RPC.

    ``gate`` is required (built by the caller with
    :func:`hugrgate.server.build_gate` or by hand) so this module never
    imports the service layer — the dependency rule
    "only service modules import service modules" holds.
    """

    def __init__(self, identity: NodeIdentity, gate: HugrGate,
                 discovery: DiscoveryRegistry | None = None,
                 rpc_timeout: float = 10.0,
                 outbound_hook: OutboundHook | None = None,
                 serve_remote: bool = True) -> None:
        self.identity = identity
        self.gate = gate
        self.discovery = discovery or DiscoveryRegistry(
            local_node_id=identity.node_id)
        self.rpc = RPCClient(node_id=identity.node_id,
                             timeout=rpc_timeout,
                             outbound_hook=outbound_hook)
        #: Operator kill-switch: refuse to serve remote decisions.
        self.serve_remote = serve_remote
        #: Server-side inbound hook (authentication, slice 208).
        self.inbound_hook: InboundHook | None = None
        #: Mutual authentication (slice 208). When ``require_auth`` is
        #: true, every inbound envelope must carry a valid HMAC tag.
        self.authenticator: NodeAuthenticator | None = None
        self.require_auth = False
        self._seq = 0
        self._last_seq: dict[str, int] = {}  # sender -> highest seq seen
        # RLock: _check_auth holds the lock while fail() -> next_seq()
        # re-enters it.
        self._lock = threading.RLock()
        self._handlers: dict[MessageType,
                             Callable[[ClusterMessage], ClusterMessage]] = {
            MessageType.DECIDE_REQUEST: self.handle_decide,
            MessageType.BATCH_REQUEST: self.handle_batch,
            MessageType.STEAL_REQUEST: self.handle_steal_request,
            MessageType.POLICY_PUSH: self.handle_policy_push,
            MessageType.POLICY_PULL: self.handle_policy_pull,
        }
        #: Work stealing (slice 216): pending decision jobs thieves may
        #: steal from the tail.
        self.steal_queue = StealableQueue()
        #: Cluster policy propagation (slice 210).
        self.policy_sync = PolicyPropagator(node_id=identity.node_id)
        #: Node health scoring (slice 213).
        self.health = NodeHealthMonitor()
        #: Node latency scoring (slice 214).
        self.latency = LatencyTracker()
        #: Node cost scoring (slice 215).
        self.costs = CostModel()
        #: Distributed routing (slice 212).
        self.router = DistributedRouter(self)

    # -- local facts --------------------------------------------------------

    @property
    def node_id(self) -> str:
        return self.identity.node_id

    def capabilities(self) -> NodeCapabilities:
        return NodeCapabilities.from_gate(self.gate, self.identity)

    def peers(self) -> list[PeerRecord]:
        return self.discovery.peers()

    def next_seq(self) -> int:
        with self._lock:
            self._seq += 1
            return self._seq

    def register_handler(
            self, msg_type: MessageType,
            handler: Callable[[ClusterMessage], ClusterMessage]) -> None:
        """Register (or replace) an inbound message handler."""
        self._handlers[msg_type] = handler

    def close(self) -> None:
        self.rpc.close()
        self.discovery.stop_all()

    # -- outbound -----------------------------------------------------------

    def decide_remote(self, peer: PeerRecord, spec: DecisionSpec,
                      state: Mapping[str, Any],
                      policy: DecisionPolicy | None = None,
                      backend_name: str | None = None,
                      context: Mapping[str, Any] | None = None,
                      trace_id: str | None = None) -> DecisionResult:
        """Ask a peer to decide (trace-correlated, slice 222).

        Every outcome feeds the health monitor (slice 213): transport
        and backend failures count against the peer, successes heal it.
        Round-trip time feeds the latency tracker (slice 214).
        """
        import time

        start = time.perf_counter()
        try:
            result = self.rpc.decide(peer, spec, state, policy=policy,
                                     backend_name=backend_name,
                                     context=context,
                                     trace_id=trace_id or new_trace_id())
        except BackendError:
            self.health.record_failure(peer.node_id)
            raise
        rtt_ms = (time.perf_counter() - start) * 1000.0
        self.health.record_success(peer.node_id)
        self.latency.record(peer.node_id, rtt_ms)
        return result

    def refresh_scores(self) -> None:
        """Push monitor readings into the router (slices 213-215).

        Called opportunistically — after RPCs, on heartbeat ticks —
        never on the hot path's critical section.
        """
        for peer in self.peers():
            node_id = peer.node_id
            self.router.set_scores(node_id, PeerScores(
                health=self.health.score(node_id),
                latency=self.latency.score(node_id),
                cost=self.costs.score(node_id),
            ))

    # -- inbound ------------------------------------------------------------

    def _check_auth(self, message: ClusterMessage,
                    auth_tag: str | None,
                    raw: bytes | None) -> ClusterMessage | None:
        """Verify authentication; return an ERROR envelope or None."""
        def fail(reason: str) -> ClusterMessage:
            return error_envelope(
                ClusterAuthError(reason),
                self.node_id, self.next_seq(), message.trace_id)

        if self.authenticator is None:
            return fail("node requires authentication but has no "
                        "authenticator configured")
        if not auth_tag or raw is None:
            return fail("missing authentication tag")
        if not self.authenticator.verify(raw, auth_tag):
            return fail("authentication failed: bad tag")
        with self._lock:
            last = self._last_seq.get(message.sender, -1)
            if message.seq <= last:
                return fail("replayed or stale message: seq not monotonic")
            self._last_seq[message.sender] = message.seq
        return None

    def _respond(self, request: ClusterMessage,
                 msg_type: MessageType,
                 payload: dict[str, Any]) -> ClusterMessage:
        return ClusterMessage(
            msg_type=msg_type,
            sender=self.node_id,
            seq=self.next_seq(),
            trace_id=request.trace_id,  # correlate with the request
            payload=payload,
        )

    def dispatch(self, message: ClusterMessage,
                 auth_tag: str | None = None,
                 raw: bytes | None = None) -> ClusterMessage:
        """Route one inbound envelope to its handler.

        When ``require_auth`` is set, ``auth_tag`` (the
        ``X-Cluster-MAC`` header) is verified against ``raw`` (the
        exact wire bytes) before anything else, and per-sender ``seq``
        monotonicity rejects replays. All auth failures return a typed
        ``cluster_auth_error`` envelope — never a guess, never a leak.
        """
        if self.require_auth:
            failure = self._check_auth(message, auth_tag, raw)
            if failure is not None:
                return failure
        if self.inbound_hook is not None:
            try:
                self.inbound_hook(message)
            except HugrGateError as e:
                return error_envelope(e, self.node_id, self.next_seq(),
                                      message.trace_id)
            except Exception as e:  # noqa: BLE001 - hook bugs must not
                # kill the connection; report them as backend errors
                return error_envelope(
                    BackendError(f"inbound hook failed: {e}"),
                    self.node_id, self.next_seq(), message.trace_id)
        handler = self._handlers.get(message.msg_type)
        if handler is None:
            return error_envelope(
                SpecError(f"unsupported message type "
                          f"{message.msg_type.value}"),
                self.node_id, self.next_seq(), message.trace_id)
        try:
            return handler(message)
        except HugrGateError as e:
            return error_envelope(e, self.node_id, self.next_seq(),
                                  message.trace_id)
        except Exception as e:  # noqa: BLE001 - never leak a traceback
            # across the wire; normalize to BackendError
            return error_envelope(
                BackendError(f"handler failed: {e}"),
                self.node_id, self.next_seq(), message.trace_id)

    # -- policy propagation (slice 210) -------------------------------------

    def handle_policy_push(self, message: ClusterMessage) -> ClusterMessage:
        """Merge an inbound cluster policy; report what changed."""
        payload = message.payload
        changed = self.policy_sync.receive(
            payload.get("policy", {}), payload.get("version", {}))
        snapshot = self.policy_sync.snapshot()
        snapshot["changed"] = changed
        return self._respond(message, MessageType.POLICY_RESPONSE,
                             snapshot)

    def handle_policy_pull(self, message: ClusterMessage) -> ClusterMessage:
        """Serve the current cluster policy snapshot."""
        snapshot = self.policy_sync.snapshot()
        snapshot["changed"] = False
        return self._respond(message, MessageType.POLICY_RESPONSE,
                             snapshot)

    def propagate_policy(self) -> dict[str, str]:
        """Push the cluster policy to every known peer.

        Returns ``{node_id: "ok" | error}`` — best effort per peer;
        one unreachable peer never blocks the rest.
        """
        snapshot = self.policy_sync.snapshot()
        outcomes: dict[str, str] = {}
        for peer in self.peers():
            message = ClusterMessage(
                msg_type=MessageType.POLICY_PUSH,
                sender=self.node_id,
                seq=self.rpc.next_seq(),
                trace_id=new_trace_id(),
                payload=dict(snapshot),
            )
            try:
                reply = self.rpc.send(peer, message)
            except HugrGateError as e:
                outcomes[peer.node_id] = f"{e.code}: {e.message}"
                continue
            if reply.msg_type is MessageType.ERROR:
                raw = reply.payload.get("error", {})
                code = raw.get("code", "unknown") if isinstance(
                    raw, dict) else "unknown"
                outcomes[peer.node_id] = f"peer error: {code}"
            else:
                outcomes[peer.node_id] = "ok"
        return outcomes

    # -- decide ---------------------------------------------------------------

    def _request_policy(self, payload: dict[str, Any]) -> DecisionPolicy:
        raw = payload.get("policy")
        if raw is None:
            return DecisionPolicy()
        if isinstance(raw, dict):
            return policy_from_dict(raw)
        raise SpecError("decide request 'policy' must be an object")

    def handle_decide(self, message: ClusterMessage) -> ClusterMessage:
        """Serve one remote decision against the local gate."""
        if not self.serve_remote:
            return error_envelope(
                BackendUnavailable("this node does not serve remote "
                                   "decisions"),
                self.node_id, self.next_seq(), message.trace_id)
        payload = message.payload
        try:
            spec = DecisionSpec.from_dict(payload["spec"])
        except (KeyError, SpecError, TypeError, ValueError) as e:
            return error_envelope(
                SpecError(f"bad spec in decide request: {e}"),
                self.node_id, self.next_seq(), message.trace_id)
        state = payload.get("state")
        if not isinstance(state, dict):
            return error_envelope(
                SpecError("decide request needs a 'state' object"),
                self.node_id, self.next_seq(), message.trace_id)
        try:
            policy = self._request_policy(payload)
        except (PolicyError, SpecError) as e:
            return error_envelope(e, self.node_id, self.next_seq(),
                                  message.trace_id)
        # Defense in depth: the client already checked, but a hostile
        # or buggy peer must not get remote inference for free.
        # privacy_class="strict" is local-only (slice 211).
        if not policy.remote_inference:
            return error_envelope(
                PrivacyViolation(
                    "remote inference blocked: policy.remote_inference "
                    "is false"),
                self.node_id, self.next_seq(), message.trace_id)
        if policy.privacy_class == "strict":
            return error_envelope(
                PrivacyViolation(
                    "privacy_class='strict' is local-only: refusing "
                    "remote decision"),
                self.node_id, self.next_seq(), message.trace_id)
        try:
            result = self.gate.decide(
                state, spec, policy,
                backend_name=payload.get("backend_name"),
                context=payload.get("context"))
        except Abstention as e:
            return self._respond(
                message, MessageType.DECIDE_RESPONSE,
                {"abstained": True, "reason": e.reason,
                 "message": e.message})
        result.metadata["served_by"] = self.node_id
        redacted = payload.get("redacted_fields")
        if redacted:
            result.metadata["redacted_fields"] = list(redacted)
        return self._respond(message, MessageType.DECIDE_RESPONSE,
                             {"result": result.to_dict()})

    def handle_batch(self, message: ClusterMessage) -> ClusterMessage:
        """Serve several decide requests in one envelope."""
        if not self.serve_remote:
            return error_envelope(
                BackendUnavailable("this node does not serve remote "
                                   "decisions"),
                self.node_id, self.next_seq(), message.trace_id)
        requests = message.payload.get("requests")
        if not isinstance(requests, list):
            return error_envelope(
                SpecError("batch request needs a 'requests' list"),
                self.node_id, self.next_seq(), message.trace_id)
        results: list[dict[str, Any]] = []
        for req in requests:
            results.append(self._serve_one(req))
        return self._respond(message, MessageType.BATCH_RESPONSE,
                             {"results": results})

    def handle_steal_request(self, message: ClusterMessage) -> ClusterMessage:
        """Victim side of work stealing: hand over tail jobs, redacted."""
        if not self.serve_remote:
            return error_envelope(
                BackendUnavailable("this node does not serve remote "
                                   "decisions"),
                self.node_id, self.next_seq(), message.trace_id)
        raw_max = message.payload.get("max_jobs", DEFAULT_STEAL_BATCH)
        if not isinstance(raw_max, int) or raw_max < 1:
            return error_envelope(
                SpecError("steal request needs a positive int 'max_jobs'"),
                self.node_id, self.next_seq(), message.trace_id)
        stolen = self.steal_queue.steal(min(raw_max, MAX_STEAL_BATCH))
        jobs = [job.redacted().to_dict() for job in stolen]
        return self._respond(message, MessageType.STEAL_RESPONSE,
                             {"jobs": jobs,
                              "remaining": len(self.steal_queue)})

    def request_steal(self, peer: PeerRecord,
                      max_jobs: int = DEFAULT_STEAL_BATCH,
                      trace_id: str | None = None) -> int:
        """Steal up to ``max_jobs`` from a peer; enqueue locally.

        Returns the number stolen. Feeds health/latency like any
        remote call.
        """
        import time

        start = time.perf_counter()
        try:
            jobs = self.rpc.steal(peer, max_jobs,
                                  trace_id=trace_id or new_trace_id())
        except BackendError:
            self.health.record_failure(peer.node_id)
            raise
        rtt_ms = (time.perf_counter() - start) * 1000.0
        self.health.record_success(peer.node_id)
        self.latency.record(peer.node_id, rtt_ms)
        for raw in jobs:
            self.steal_queue.offer(StealJob.from_dict(raw))
        return len(jobs)

    def _serve_one(self, req: Any) -> dict[str, Any]:
        if not isinstance(req, dict):
            return {"error": SpecError(
                "batch item must be an object").to_dict()}
        try:
            spec = DecisionSpec.from_dict(req["spec"])
        except (KeyError, SpecError, TypeError, ValueError) as e:
            return {"error": SpecError(f"bad spec: {e}").to_dict()}
        state = req.get("state")
        if not isinstance(state, dict):
            return {"error": SpecError(
                "batch item needs a 'state' object").to_dict()}
        try:
            policy = self._request_policy(req)
        except (PolicyError, SpecError) as e:
            return {"error": e.to_dict()}
        if not policy.remote_inference:
            return {"error": PrivacyViolation(
                "remote inference blocked").to_dict()}
        if policy.privacy_class == "strict":
            return {"error": PrivacyViolation(
                "privacy_class='strict' is local-only").to_dict()}
        try:
            result = self.gate.decide(
                state, spec, policy,
                backend_name=req.get("backend_name"),
                context=req.get("context"))
        except Abstention as e:
            return {"abstained": True, "reason": e.reason,
                    "message": e.message}
        except HugrGateError as e:
            return {"error": e.to_dict()}
        result.metadata["served_by"] = self.node_id
        redacted = req.get("redacted_fields")
        if redacted:
            result.metadata["redacted_fields"] = list(redacted)
        return {"result": result.to_dict()}
