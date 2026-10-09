"""Cluster package for distributed HugrGate. Campaign IX (slices 201-225).

The subpackage is intentionally import-light at the top level: importing
``hugrgate.cluster`` must not drag in FastAPI/uvicorn, so service-heavy
modules (routes, transport servers) stay behind their own imports.
"""

from __future__ import annotations

from hugrgate.cluster.capabilities import NodeCapabilities
from hugrgate.cluster.discovery import (
    DEFAULT_STALE_AFTER_S,
    Discovery,
    DiscoveryRegistry,
    PeerRecord,
)
from hugrgate.cluster.identity import KEY_BYTES, NodeIdentity
from hugrgate.cluster.lan import (
    DEFAULT_LAN_GROUP,
    DEFAULT_LAN_PORT,
    LANDiscoveryAdapter,
    MulticastConfig,
)
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
from hugrgate.cluster.static_config import (
    StaticDiscovery,
    StaticPeerConfig,
    example_config,
    load_static_config,
)

__all__ = [
    "CLUSTER_RPC_PATH",
    "DEFAULT_LAN_GROUP",
    "DEFAULT_LAN_PORT",
    "DEFAULT_STALE_AFTER_S",
    "KEY_BYTES",
    "MAX_MESSAGE_BYTES",
    "PROTOCOL_VERSION",
    "ClusterMessage",
    "Discovery",
    "DiscoveryRegistry",
    "LANDiscoveryAdapter",
    "MessageType",
    "MulticastConfig",
    "NodeCapabilities",
    "NodeIdentity",
    "PeerRecord",
    "StaticDiscovery",
    "StaticPeerConfig",
    "decode_message",
    "encode_message",
    "example_config",
    "load_static_config",
    "new_trace_id",
]
