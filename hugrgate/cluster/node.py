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
from typing import TYPE_CHECKING, Any

from hugrgate.cluster.capabilities import NodeCapabilities
from hugrgate.cluster.discovery import DiscoveryRegistry, PeerRecord
from hugrgate.cluster.identity import NodeIdentity
from hugrgate.cluster.protocol import (
    ClusterMessage,
    MessageType,
    new_trace_id,
)
from hugrgate.cluster.rpc import RPCClient, error_envelope
from hugrgate.core import HugrGate
from hugrgate.errors import (
    Abstention,
    BackendError,
    BackendUnavailable,
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
]

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
        self._seq = 0
        self._lock = threading.Lock()
        self._handlers: dict[MessageType,
                             Callable[[ClusterMessage], ClusterMessage]] = {
            MessageType.DECIDE_REQUEST: self.handle_decide,
            MessageType.BATCH_REQUEST: self.handle_batch,
        }

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
        """Ask a peer to decide (trace-correlated, slice 222)."""
        return self.rpc.decide(peer, spec, state, policy=policy,
                               backend_name=backend_name,
                               context=context,
                               trace_id=trace_id or new_trace_id())

    # -- inbound ------------------------------------------------------------

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

    def dispatch(self, message: ClusterMessage) -> ClusterMessage:
        """Route one inbound envelope to its handler."""
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
        if not policy.remote_inference:
            return error_envelope(
                PrivacyViolation(
                    "remote inference blocked: policy.remote_inference "
                    "is false"),
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
        return {"result": result.to_dict()}
