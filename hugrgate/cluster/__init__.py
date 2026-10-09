"""Cluster package for distributed HugrGate. Campaign IX (slices 201-225).

The subpackage is intentionally import-light at the top level: importing
``hugrgate.cluster`` must not drag in FastAPI/uvicorn, so service-heavy
modules (routes, transport servers) stay behind their own imports.
"""

from __future__ import annotations

from hugrgate.cluster.protocol import (
    CLUSTER_RPC_PATH,
    MAX_MESSAGE_BYTES,
    PROTOCOL_VERSION,
    ClusterMessage,
    MessageType,
    decode_message,
    encode_message,
    new_trace_id,
)

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
