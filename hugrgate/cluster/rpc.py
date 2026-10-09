"""Remote decision RPC. Slice 207.

:mod:`hugrgate.client` already speaks HTTP to ``/decide``; the cluster
RPC is a different animal: versioned :class:`ClusterMessage` envelopes
over ``POST /cluster/rpc`` carrying a ``trace_id`` for cross-node
correlation (slice 222), typed error envelopes, and batch calls.

- :class:`RPCClient` — sends envelopes to a peer, maps the reply.
- :class:`RemoteBackend` — a :class:`Backend` (``is_remote=True``) that
  routes ``evaluate()`` to a peer, so the existing core, ladder, and
  policy machinery treat remote nodes as ordinary backends. The core's
  ``policy.backend_allowed`` gate already keeps remote backends out
  unless ``policy.remote_inference=True``; this module enforces the
  same rule on both ends of the wire (defense in depth).

Privacy is fail-closed: a remote call without ``remote_inference``
raises :class:`PrivacyViolation`, never silently downgrades to local.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from typing import Any

import httpx

from hugrgate.backend import Backend
from hugrgate.cluster.discovery import PeerRecord
from hugrgate.cluster.privacy_boundary import PrivacyBoundary
from hugrgate.cluster.protocol import (
    CLUSTER_RPC_PATH,
    ClusterMessage,
    MessageType,
    decode_message,
    encode_message,
    new_trace_id,
)
from hugrgate.errors import (
    Abstention,
    BackendError,
    BackendUnavailable,
    HugrGateError,
    PrivacyViolation,
    QueueFull,
    SpecError,
    TimeoutError,
)
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult
from hugrgate.serde import (
    policy_from_dict,
    policy_to_dict,
    result_from_dict,
)
from hugrgate.spec import SPEC_TYPES, DecisionSpec

__all__ = [
    "RPCClient",
    "RemoteBackend",
    "error_envelope",
]

#: Hook applied to outbound messages (slice 208 plugs signing in here).
OutboundHook = Callable[[ClusterMessage], ClusterMessage]


def error_envelope(error: HugrGateError, sender: str, seq: int,
                   trace_id: str) -> ClusterMessage:
    """Wrap an error in a ``MessageType.ERROR`` envelope."""
    return ClusterMessage(
        msg_type=MessageType.ERROR,
        sender=sender,
        seq=seq,
        trace_id=trace_id,
        payload={"error": error.to_dict()},
    )


class RPCClient:
    """Cluster RPC client: envelopes to ``POST /cluster/rpc``.

    ``http_client`` is injectable for tests (pass an
    ``httpx.Client`` with a custom transport); production use builds its
    own with ``trust_env=False`` so proxy env vars can never reroute
    cluster traffic (same rationale as :class:`HugrGateClient`).

    ``mac_provider`` seals the exact wire bytes of every outbound
    envelope; the tag travels in the ``X-Cluster-MAC`` header (slice
    208). Use :func:`enable_mutual_auth
    <hugrgate.cluster.auth.enable_mutual_auth>` to wire it.
    """

    def __init__(self, node_id: str, timeout: float = 10.0,
                 outbound_hook: OutboundHook | None = None,
                 mac_provider: Callable[[bytes], str] | None = None,
                 http_client: httpx.Client | None = None) -> None:
        if not node_id:
            raise SpecError("RPCClient needs a node_id")
        if timeout <= 0:
            raise SpecError("RPCClient timeout must be > 0")
        self.node_id = node_id
        self.timeout = timeout
        self._outbound_hook = outbound_hook
        self._mac_provider = mac_provider
        self._http = http_client or httpx.Client(timeout=timeout,
                                                 trust_env=False)
        self._owns_http = http_client is None
        self._seq = 0
        self._lock = threading.Lock()

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def next_seq(self) -> int:
        with self._lock:
            self._seq += 1
            return self._seq

    def _prepare(self, msg_type: MessageType,
                 payload: dict[str, Any],
                 trace_id: str | None = None) -> ClusterMessage:
        return ClusterMessage(
            msg_type=msg_type,
            sender=self.node_id,
            seq=self.next_seq(),
            trace_id=trace_id or new_trace_id(),
            payload=payload,
        )

    def _apply_hook(self, message: ClusterMessage) -> ClusterMessage:
        if self._outbound_hook is not None:
            message = self._outbound_hook(message)
            if not isinstance(message, ClusterMessage):
                raise SpecError(
                    "outbound_hook must return a ClusterMessage")
        return message

    def send(self, peer: PeerRecord,
             message: ClusterMessage) -> ClusterMessage:
        """Send a raw envelope; return the decoded reply envelope.

        The outbound hook (slice 208 signing) is applied here so every
        outbound envelope — decide, batch, policy, … — is sealed.
        """
        message = self._apply_hook(message)
        data = encode_message(message)
        headers = {"content-type": "application/json"}
        if self._mac_provider is not None:
            headers["x-cluster-mac"] = self._mac_provider(data)
        url = peer.address + CLUSTER_RPC_PATH
        try:
            response = self._http.post(url, content=data, headers=headers)
        except httpx.ConnectError as e:
            raise BackendUnavailable(
                f"peer {peer.node_id[:12]}… unreachable: {e}") from e
        except httpx.TimeoutException as e:
            raise TimeoutError(
                f"peer {peer.node_id[:12]}… timed out: {e}") from e
        except httpx.TransportError as e:
            raise BackendError(
                f"peer {peer.node_id[:12]}… transport failure: {e}") from e
        if response.status_code == 400:
            # Undecodable envelope — our bug or a version mismatch.
            raise SpecError(
                f"peer {peer.node_id[:12]}… rejected the envelope: "
                f"{response.text[:200]}")
        if response.status_code == 429:
            # Backpressure (slice 218): the peer is shedding load.
            # Recoverable — the caller should back off and retry.
            try:
                body = response.json()
            except ValueError:
                body = {}
            raw: Any = {}
            if isinstance(body, dict):
                envelope = body.get("envelope", {})
                if isinstance(envelope, dict):
                    raw = envelope.get("error", {})
            if isinstance(raw, dict) and raw.get("code") == "queue_full":
                raise HugrGateError.from_dict(raw)
            raise QueueFull(f"peer {peer.node_id[:12]}… is shedding load")
        if response.status_code != 200:
            raise BackendError(
                f"peer {peer.node_id[:12]}… HTTP {response.status_code}")
        try:
            body = response.json()
        except ValueError as e:
            raise BackendError(
                f"peer {peer.node_id[:12]}… returned non-JSON: {e}") from e
        # The cluster endpoint wraps the envelope as {"envelope": {...}};
        # accept a bare envelope too for forward compatibility.
        envelope = body.get("envelope", body)
        try:
            if isinstance(envelope, dict):
                reply = ClusterMessage.from_dict(envelope)
            else:
                reply = decode_message(response.content)
        except SpecError as e:
            raise BackendError(
                f"peer {peer.node_id[:12]}… returned garbage: {e}") from e
        if reply.msg_type is MessageType.ERROR:
            raw = reply.payload.get("error", {})
            if isinstance(raw, dict):
                raise HugrGateError.from_dict(raw)
            raise BackendError(f"peer error: {raw!r}")
        return reply

    def _check_remote_allowed(self, policy: DecisionPolicy,
                              peer: PeerRecord) -> None:
        try:
            PrivacyBoundary().check_outbound_allowed(policy)
        except PrivacyViolation as e:
            raise PrivacyViolation(
                f"peer {peer.node_id[:12]}…: {e.message}") from e

    def decide(self, peer: PeerRecord, spec: DecisionSpec,
               state: Mapping[str, Any],
               policy: DecisionPolicy | None = None,
               backend_name: str | None = None,
               context: Mapping[str, Any] | None = None,
               trace_id: str | None = None) -> DecisionResult:
        """Ask a peer to decide. Returns the peer's :class:`DecisionResult`.

        Raises :class:`PrivacyViolation` when the policy forbids remote
        inference, :class:`Abstention` when the peer abstains, and the
        peer's typed error otherwise.
        """
        effective = policy or DecisionPolicy()
        self._check_remote_allowed(effective, peer)
        clean_state, redacted = PrivacyBoundary().prepare_outbound(
            effective, state)
        payload: dict[str, Any] = {
            "spec": spec.to_dict(),
            "state": clean_state,
            "redacted_fields": redacted,
            "policy": policy_to_dict(effective),
            "backend_name": backend_name,
            "context": dict(context) if context else None,
        }
        message = self._prepare(MessageType.DECIDE_REQUEST, payload,
                                trace_id)
        reply = self.send(peer, message)
        if reply.msg_type is not MessageType.DECIDE_RESPONSE:
            raise BackendError(
                f"peer {peer.node_id[:12]}… sent unexpected "
                f"{reply.msg_type.value}")
        body = reply.payload
        if body.get("abstained"):
            raise Abstention(body.get("message") or "peer abstained",
                             reason=body.get("reason")
                             or "below_threshold")
        raw = body.get("result")
        if not isinstance(raw, dict) or "value" not in raw:
            raise BackendError(
                f"peer {peer.node_id[:12]}… returned no decision")
        result = result_from_dict(raw)
        result.metadata["remote_node"] = peer.node_id
        result.metadata["remote_trace_id"] = reply.trace_id
        return result

    def batch(self, peer: PeerRecord,
              requests: list[dict[str, Any]],
              policy: DecisionPolicy | None = None,
              trace_id: str | None = None) -> list[dict[str, Any]]:
        """Send several decide requests in one envelope (slice 217's
        wire shape, usable now). Each request dict carries ``spec``,
        ``state``, and optional ``policy``/``backend_name``/``context``.

        Returns per-index ``{"result": {...}}`` / ``{"abstained": ...}``
        / ``{"error": {...}}`` dicts in request order.
        """
        effective = policy or DecisionPolicy()
        self._check_remote_allowed(effective, peer)
        items = []
        boundary = PrivacyBoundary()
        for req in requests:
            spec = req["spec"]
            req_policy = req.get("policy", effective)
            if isinstance(req_policy, DecisionPolicy):
                self._check_remote_allowed(req_policy, peer)
                policy_dict: Any = policy_to_dict(req_policy)
            elif isinstance(req_policy, dict):
                # Raw dicts are validated + checked, never trusted blind.
                self._check_remote_allowed(
                    policy_from_dict(req_policy), peer)
                policy_dict = req_policy
            elif req_policy is not None:
                raise SpecError(
                    "batch item 'policy' must be a DecisionPolicy, "
                    "a dict, or omitted")
            else:
                policy_dict = policy_to_dict(effective)
            clean_state, redacted = boundary.redact_state(req["state"])
            item: dict[str, Any] = {
                "spec": spec.to_dict() if isinstance(spec, DecisionSpec)
                else spec,
                "state": clean_state,
                "redacted_fields": redacted,
                "policy": policy_dict,
                "backend_name": req.get("backend_name"),
                "context": (dict(req["context"])
                            if req.get("context") else None),
            }
            items.append(item)
        message = self._prepare(MessageType.BATCH_REQUEST,
                                {"requests": items}, trace_id)
        reply = self.send(peer, message)
        if reply.msg_type is not MessageType.BATCH_RESPONSE:
            raise BackendError(
                f"peer {peer.node_id[:12]}… sent unexpected "
                f"{reply.msg_type.value}")
        results = reply.payload.get("results")
        if not isinstance(results, list):
            raise BackendError(
                f"peer {peer.node_id[:12]}… returned no batch results")
        return results

    def steal(self, peer: PeerRecord, max_jobs: int = 8,
              trace_id: str | None = None) -> list[dict]:
        """Steal queued jobs from a peer (work stealing, slice 216).

        Returns the stolen job dicts (already privacy-redacted by the
        victim). Raises the peer's typed error on refusal.
        """
        from hugrgate.cluster.work_stealing import StealJob

        if not isinstance(max_jobs, int) or max_jobs < 1:
            raise SpecError("max_jobs must be a positive int")
        message = self._prepare(MessageType.STEAL_REQUEST,
                                {"max_jobs": max_jobs}, trace_id)
        reply = self.send(peer, message)
        if reply.msg_type is not MessageType.STEAL_RESPONSE:
            raise BackendError(
                f"peer {peer.node_id[:12]}… sent unexpected "
                f"{reply.msg_type.value}")
        jobs = reply.payload.get("jobs")
        if not isinstance(jobs, list):
            raise BackendError(
                f"peer {peer.node_id[:12]}… returned no stolen jobs")
        # Validate shape early: a lying peer's garbage dies here, not
        # in the local queue.
        for raw in jobs:
            StealJob.from_dict(raw)
        return jobs

    def heartbeat(self, peer: PeerRecord,
                  trace_id: str | None = None) -> dict[str, Any]:
        """Ping a peer's liveness (partition detection, slice 219).

        Returns the peer's heartbeat payload. Control-plane: never
        shed, never privacy-gated.
        """
        message = self._prepare(MessageType.HEARTBEAT,
                                {"node_id": self.node_id}, trace_id)
        reply = self.send(peer, message)
        if reply.msg_type is not MessageType.HEARTBEAT:
            raise BackendError(
                f"peer {peer.node_id[:12]}… sent unexpected "
                f"{reply.msg_type.value}")
        return reply.payload

    def pull_provenance(self, peer: PeerRecord,
                        since: float | None = None,
                        limit: int = 100,
                        trace_id: str | None = None) -> list[dict]:
        """Fetch a peer's decision history (slice 221).

        Returns raw record dicts; the caller validates them (the
        exchange does). The serving node clamps ``limit``. Control-
        plane read: never shed, never gated.
        """
        if not isinstance(limit, int) or limit < 1:
            raise SpecError("provenance pull needs a positive int limit")
        message = self._prepare(MessageType.PROVENANCE_PULL,
                                {"since": since, "limit": limit}, trace_id)
        reply = self.send(peer, message)
        if reply.msg_type is not MessageType.PROVENANCE_RESPONSE:
            raise BackendError(
                f"peer {peer.node_id[:12]}… sent unexpected "
                f"{reply.msg_type.value}")
        records = reply.payload.get("records")
        if not isinstance(records, list):
            raise BackendError(
                f"peer {peer.node_id[:12]}… returned no provenance records")
        return records


class RemoteBackend(Backend):
    """A peer node exposed as an ordinary backend.

    ``is_remote=True`` so the core's policy gate and the ladder's
    privacy pruning treat it as remote automatically. Carries its own
    :class:`DecisionPolicy` (default: remote allowed, no threshold)
    which is sent to the peer so thresholds apply there too — the
    peer re-validates ``remote_inference`` on its side as well.
    """

    def __init__(self, peer: PeerRecord, rpc: RPCClient,
                 policy: DecisionPolicy | None = None,
                 name: str | None = None) -> None:
        self.peer = peer
        self.rpc = rpc
        self.policy = policy or DecisionPolicy(remote_inference=True)
        self.name = name or f"remote@{peer.node_id[:12]}"
        self.is_remote = True
        self._capabilities: dict[str, Any] | None = None
        if peer.capabilities is not None:
            self._capabilities = {
                "spec_types": peer.capabilities.spec_types(),
                "description": (
                    f"Remote node {peer.node_id[:12]}… "
                    f"({peer.capabilities.display_name or 'unnamed'})"),
                "deterministic": False,
                "peer_node_id": peer.node_id,
            }

    def capabilities(self) -> dict[str, Any]:
        if self._capabilities is not None:
            return dict(self._capabilities)
        # Operator-configured without advertised caps: trust the
        # operator, claim every spec type (documented, explicit).
        return {
            "spec_types": list(SPEC_TYPES),
            "description": f"Remote node {self.peer.node_id[:12]}… "
                           f"(unadvertised capabilities)",
            "deterministic": False,
            "peer_node_id": self.peer.node_id,
        }

    def supports(self, spec: DecisionSpec) -> bool:
        if self._capabilities is not None:
            return spec.type in self._capabilities["spec_types"]
        return True

    def evaluate(self, state: Mapping[str, Any], spec: DecisionSpec,
                 context: Mapping[str, Any] | None = None
                 ) -> DecisionResult:
        try:
            return self.rpc.decide(self.peer, spec, state,
                                   policy=self.policy, context=context)
        except HugrGateError:
            raise
        except Exception as e:
            raise BackendError(
                f"remote backend {self.name} failed: {e}") from e

    def estimated_latency(self) -> float:
        # Remote calls pay network cost; conservative default until
        # slice 214's latency scoring refines it per peer.
        return 500.0
