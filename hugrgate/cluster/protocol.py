"""Gjallarbrú node wire protocol. Slice 201.

Every inter-node exchange in a HugrGate cluster is a
:class:`ClusterMessage`: a small versioned JSON envelope carried over
HTTP ``POST /cluster/rpc`` (slice 207) or UDP multicast for discovery
(slice 206). The envelope is deliberately boring — JSON, UTF-8, length
checked — so any future transport can carry it unchanged.

Wire format (all keys required unless noted)::

    {
      "protocol_version": 1,
      "msg_type": "decide_request",
      "sender": "<64-hex node id>",
      "seq": 41,                 # per-sender monotonic sequence
      "trace_id": "<32-hex>",    # slice 222 correlation
      "timestamp": 1728470000.5, # sender clock, informational only
      "payload": {...}           # message-type-specific body
    }

Receivers MUST reject (with :class:`SpecError`) any envelope whose
``protocol_version`` is newer than :data:`PROTOCOL_VERSION` — a node
must never silently misread a future protocol — and any envelope
over :data:`MAX_MESSAGE_BYTES`.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from hugrgate.errors import SpecError

__all__ = [
    "CLUSTER_RPC_PATH",
    "MAX_MESSAGE_BYTES",
    "PROTOCOL_VERSION",
    "ClusterMessage",
    "MessageType",
    "decode_message",
    "encode_message",
    "new_trace_id",
]

#: Current wire protocol version. Bump only with a migration note; receivers
#: reject anything newer (fail-closed on forward incompatibility).
PROTOCOL_VERSION = 1

#: Largest accepted envelope on the wire (1 MiB state limit in
#: ``validate_state`` x4 headroom for result + provenance metadata).
MAX_MESSAGE_BYTES = 4 * 1024 * 1024

#: HTTP path serving the cluster RPC endpoint (slice 207).
CLUSTER_RPC_PATH = "/cluster/rpc"


class MessageType(str, Enum):
    """Every message kind a node may send or expect.

    The enum is a string enum so the wire value is human-readable and
    new kinds stay backward compatible (unknown kinds are rejected,
    never guessed at).
    """

    HELLO = "hello"                    # discovery announcement (206)
    HEARTBEAT = "heartbeat"            # liveness + load signal (213)
    GOODBYE = "goodbye"                # graceful leave
    DECIDE_REQUEST = "decide_request"  # remote decision RPC (207)
    DECIDE_RESPONSE = "decide_response"
    BATCH_REQUEST = "batch_request"    # distributed batching (217)
    BATCH_RESPONSE = "batch_response"
    POLICY_PUSH = "policy_push"        # policy propagation (210)
    POLICY_PULL = "policy_pull"
    POLICY_RESPONSE = "policy_response"
    PROVENANCE_PULL = "provenance_pull"      # distributed provenance (221)
    PROVENANCE_RESPONSE = "provenance_response"
    STEAL_REQUEST = "steal_request"    # work stealing (216)
    STEAL_RESPONSE = "steal_response"
    TRACE_SPAN = "trace_span"          # trace correlation (222)
    AUTH_CHALLENGE = "auth_challenge"  # mutual authentication (208)
    AUTH_RESPONSE = "auth_response"
    ERROR = "error"                    # typed error envelope


def new_trace_id() -> str:
    """Generate a fresh 128-bit trace id (hex). Slice 222 owns semantics."""
    return uuid.uuid4().hex


@dataclass
class ClusterMessage:
    """One versioned envelope on the cluster wire."""

    msg_type: MessageType
    sender: str                      # node id, 64 lowercase hex chars
    seq: int                         # per-sender monotonic sequence number
    trace_id: str = field(default_factory=new_trace_id)
    protocol_version: int = PROTOCOL_VERSION
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not isinstance(self.msg_type, MessageType):
            raise SpecError(
                f"msg_type must be a MessageType, got {self.msg_type!r}")
        if (not isinstance(self.sender, str) or len(self.sender) != 64
                or any(c not in "0123456789abcdef" for c in self.sender)):
            raise SpecError(
                "sender must be a 64-char lowercase hex node id")
        if not isinstance(self.seq, int) or self.seq < 0:
            raise SpecError(f"seq must be a non-negative int, got {self.seq!r}")
        if (not isinstance(self.trace_id, str) or len(self.trace_id) != 32
                or any(c not in "0123456789abcdef"
                       for c in self.trace_id)):
            raise SpecError("trace_id must be a 32-char lowercase hex string")
        if not isinstance(self.payload, dict):
            raise SpecError("payload must be a dict")
        if not isinstance(self.timestamp, (int, float)):
            raise SpecError("timestamp must be numeric")

    @property
    def message_id(self) -> str:
        """Stable id for dedup: ``sender:seq``."""
        return f"{self.sender}:{self.seq}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "msg_type": self.msg_type.value,
            "sender": self.sender,
            "seq": self.seq,
            "trace_id": self.trace_id,
            "timestamp": self.timestamp,
            "payload": dict(self.payload),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ClusterMessage:
        """Rebuild and validate; raises :class:`SpecError` on any defect."""
        if not isinstance(data, dict):
            raise SpecError(
                f"cluster message must be a dict, got {type(data).__name__}")
        version = data.get("protocol_version", PROTOCOL_VERSION)
        if not isinstance(version, int):
            raise SpecError("protocol_version must be an int")
        if version > PROTOCOL_VERSION:
            raise SpecError(
                f"protocol version {version} newer than supported "
                f"{PROTOCOL_VERSION}: refusing to misread the future")
        if version < 1:
            raise SpecError(f"protocol version {version} is not valid")
        raw_type = data.get("msg_type")
        try:
            msg_type = MessageType(raw_type)
        except ValueError:
            raise SpecError(
                f"unknown message type {raw_type!r}") from None
        return cls(
            msg_type=msg_type,
            sender=data.get("sender", ""),
            seq=data.get("seq", -1),
            trace_id=data.get("trace_id", ""),
            protocol_version=version,
            payload=data.get("payload", {}),
            timestamp=data.get("timestamp", -1.0),
        )


def encode_message(message: ClusterMessage) -> bytes:
    """Serialize to wire bytes; rejects oversized envelopes."""
    raw = json.dumps(message.to_dict(), separators=(",", ":"),
                     sort_keys=True).encode("utf-8")
    if len(raw) > MAX_MESSAGE_BYTES:
        raise SpecError(
            f"cluster message is {len(raw)} bytes, over the "
            f"{MAX_MESSAGE_BYTES}-byte limit")
    return raw


def decode_message(data: bytes | str) -> ClusterMessage:
    """Parse wire bytes back into a validated :class:`ClusterMessage`."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    if len(data) > MAX_MESSAGE_BYTES:
        raise SpecError(
            f"cluster message is {len(data)} bytes, over the "
            f"{MAX_MESSAGE_BYTES}-byte limit")
    try:
        parsed = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise SpecError(f"cluster message is not valid JSON: {e}") from e
    return ClusterMessage.from_dict(parsed)
