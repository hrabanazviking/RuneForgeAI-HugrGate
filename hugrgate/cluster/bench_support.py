"""Loopback cluster harness for benchmarks (and chaos rehearsals).

Slice 224 support module: builds N :class:`ClusterNode`\\ s whose RPC
transports dispatch directly to each other (no sockets), with
per-node call counting and hot-swappable transports (for
:class:`ChaosProxy` scenarios).
"""

from __future__ import annotations

import httpx

from hugrgate.cluster.backpressure import AdmissionController
from hugrgate.cluster.discovery import Discovery, PeerRecord
from hugrgate.cluster.identity import NodeIdentity
from hugrgate.cluster.node import ClusterNode
from hugrgate.cluster.protocol import decode_message
from hugrgate.cluster.rpc import RPCClient
from hugrgate.errors import SpecError

__all__ = [
    "LoopbackCluster",
    "percent_str",
]

#: First port number assigned to cluster peers (loopback-only).
BASE_PORT = 20000


def percent_str(part: float, whole: float) -> str:
    """``"12.3%"``-style ratio; ``"n/a"`` when the whole is zero."""
    if whole <= 0:
        return "n/a"
    return f"{100.0 * part / whole:.1f}%"


class _CountingLoopback(httpx.BaseTransport):
    """Dispatch to a node; count every request."""

    def __init__(self, node: ClusterNode) -> None:
        self.node = node
        self.calls = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        reply = self.node.dispatch(decode_message(request.content))
        return httpx.Response(200, json={"envelope": reply.to_dict()})


class _PortRouter(httpx.BaseTransport):
    """Route by destination port to the matching node transport.

    Holds the live transports dict, so :meth:`LoopbackCluster.set_transport`
    takes effect without rewiring clients.
    """

    def __init__(self, cluster: LoopbackCluster) -> None:
        self._cluster = cluster

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        port = request.url.port
        if port is None:
            raise SpecError("loopback cluster needs an explicit port")
        name = self._cluster.name_for_port(port)
        return self._cluster.transport_for(name).handle_request(request)


class _Static(Discovery):
    name = "bench"

    def __init__(self, peers: list[PeerRecord]) -> None:
        self._peers = peers

    def peers(self) -> list[PeerRecord]:
        return list(self._peers)


class LoopbackCluster:
    """Named nodes wired loopback-to-loopback.

    ``admission_capacity`` sizes the nodes' token buckets: benchmarks
    are load generators, so the default is effectively unlimited;
    pass a small value to rehearse backpressure (slice 218).
    """

    def __init__(self, names: list[str],
                 admission_capacity: int = 100_000) -> None:
        # Lazy: only service modules may eagerly import the service layer.
        from hugrgate.server import build_gate

        self._nodes: dict[str, ClusterNode] = {}
        self._transports: dict[str, httpx.BaseTransport] = {}
        self._ports: dict[int, str] = {}
        for i, name in enumerate(names):
            node = ClusterNode(NodeIdentity.generate(name), build_gate())
            node.admission = AdmissionController(
                capacity=admission_capacity,
                refill_per_second=float(admission_capacity))
            self._nodes[name] = node
            self._transports[name] = _CountingLoopback(node)
            self._ports[BASE_PORT + i] = name
        router = _PortRouter(self)
        for node in self._nodes.values():
            node.rpc = RPCClient(node_id=node.node_id,
                                 http_client=httpx.Client(transport=router))

    def node(self, name: str) -> ClusterNode:
        return self._nodes[name]

    def names(self) -> list[str]:
        return list(self._nodes)

    def port_for(self, name: str) -> int:
        for port, peer_name in self._ports.items():
            if peer_name == name:
                return port
        raise KeyError(name)

    def name_for_port(self, port: int) -> str:
        return self._ports[port]

    def transport_for(self, name: str) -> httpx.BaseTransport:
        return self._transports[name]

    def calls_for(self, name: str) -> int:
        """Requests served by a node's transport (0 if not counting)."""
        return getattr(self._transports[name], "calls", 0)

    def set_transport(self, name: str,
                      transport: httpx.BaseTransport) -> None:
        """Hot-swap a node's transport (e.g. wrap in a ChaosProxy)."""
        self._transports[name] = transport

    def peer_record(self, name: str) -> PeerRecord:
        node = self._nodes[name]
        return PeerRecord(node_id=node.node_id, host="bench",
                          port=self.port_for(name),
                          capabilities=node.capabilities())

    def static_adapter(self, names: list[str]) -> Discovery:
        """Discovery adapter over the named peers."""
        return _Static([self.peer_record(n) for n in names])
