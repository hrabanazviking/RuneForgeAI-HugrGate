"""Cluster package for distributed HugrGate. Campaign IX (slices 201-225).

The subpackage is intentionally import-light at the top level: importing
``hugrgate.cluster`` must not drag in FastAPI/uvicorn, so service-heavy
modules (routes, transport servers) stay behind their own imports.
"""

from __future__ import annotations

from hugrgate.cluster.auth import (
    AUTH_HEADER,
    Authenticator,
    ClusterKey,
    enable_mutual_auth,
)
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
from hugrgate.cluster.node import (
    ClusterNode,
    InboundHook,
    NodeAuthenticator,
)
from hugrgate.cluster.node_cost import CostModel
from hugrgate.cluster.node_health import (
    DEFAULT_QUARANTINE_THRESHOLD,
    NodeHealthMonitor,
    PeerHealth,
)
from hugrgate.cluster.node_latency import (
    DEFAULT_LATENCY_TARGET_MS,
    LatencyTracker,
    PeerLatency,
)
from hugrgate.cluster.policy_sync import (
    PolicyPropagator,
    PolicyVersion,
    merge_policies,
)
from hugrgate.cluster.privacy_boundary import (
    SENSITIVE_PREFIX,
    PrivacyBoundary,
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
from hugrgate.cluster.routing import (
    DistributedRouter,
    PeerScores,
    RouteCandidate,
)
from hugrgate.cluster.rpc import (
    OutboundHook,
    RemoteBackend,
    RPCClient,
    error_envelope,
)
from hugrgate.cluster.static_config import (
    StaticDiscovery,
    StaticPeerConfig,
    example_config,
    load_static_config,
)
from hugrgate.cluster.transport import (
    TLSServer,
    cert_fingerprint,
    fetch_server_fingerprint,
    make_self_signed_cert,
    trusted_context_for,
    verify_cert_fingerprint,
)
from hugrgate.cluster.work_stealing import (
    MAX_STEAL_BATCH,
    StealableQueue,
    StealJob,
)

__all__ = [
    "AUTH_HEADER",
    "CLUSTER_RPC_PATH",
    "DEFAULT_LAN_GROUP",
    "DEFAULT_LAN_PORT",
    "DEFAULT_LATENCY_TARGET_MS",
    "DEFAULT_QUARANTINE_THRESHOLD",
    "DEFAULT_STALE_AFTER_S",
    "KEY_BYTES",
    "MAX_MESSAGE_BYTES",
    "MAX_STEAL_BATCH",
    "PROTOCOL_VERSION",
    "SENSITIVE_PREFIX",
    "Authenticator",
    "ClusterKey",
    "ClusterMessage",
    "ClusterNode",
    "CostModel",
    "Discovery",
    "DiscoveryRegistry",
    "DistributedRouter",
    "InboundHook",
    "LANDiscoveryAdapter",
    "LatencyTracker",
    "MessageType",
    "MulticastConfig",
    "NodeAuthenticator",
    "NodeCapabilities",
    "NodeHealthMonitor",
    "NodeIdentity",
    "OutboundHook",
    "PeerHealth",
    "PeerLatency",
    "PeerRecord",
    "PeerScores",
    "PolicyPropagator",
    "PolicyVersion",
    "PrivacyBoundary",
    "RPCClient",
    "RemoteBackend",
    "RouteCandidate",
    "StaticDiscovery",
    "StaticPeerConfig",
    "StealJob",
    "StealableQueue",
    "TLSServer",
    "cert_fingerprint",
    "decode_message",
    "enable_mutual_auth",
    "encode_message",
    "error_envelope",
    "example_config",
    "fetch_server_fingerprint",
    "load_static_config",
    "make_self_signed_cert",
    "merge_policies",
    "new_trace_id",
    "trusted_context_for",
    "verify_cert_fingerprint",
]
