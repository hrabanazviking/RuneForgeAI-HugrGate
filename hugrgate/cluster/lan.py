"""LAN discovery adapter — UDP multicast HELLOs. Slice 206.

Nodes announce themselves on a multicast group; every listener builds
its peer table from the HELLOs it hears. Multicast TTL defaults to 1
(stay on the LAN segment), and the interface defaults to loopback so
the adapter is fully testable without a real network.

The socket layer is injectable (``socket_factory``) so unit tests never
touch the network; one integration test exercises real multicast on
``127.0.0.1`` and skips cleanly where the sandbox forbids it.

HELLO payload::

    {"node_id": "<64-hex>", "display_name": "...", "http_port": 8377,
     "tls": false, "capabilities": {...}}
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from hugrgate.cluster.capabilities import NodeCapabilities
from hugrgate.cluster.discovery import Discovery, PeerRecord
from hugrgate.cluster.identity import NodeIdentity
from hugrgate.cluster.protocol import (
    ClusterMessage,
    MessageType,
    decode_message,
    encode_message,
    new_trace_id,
)
from hugrgate.errors import SpecError

__all__ = [
    "DEFAULT_LAN_GROUP",
    "DEFAULT_LAN_PORT",
    "LANDiscoveryAdapter",
    "MulticastConfig",
]

#: Administratively-scoped multicast group (239.0.0.0/8 is site-local).
DEFAULT_LAN_GROUP = "239.0.9.77"
#: UDP port for HELLO traffic (distinct from the HTTP API port).
DEFAULT_LAN_PORT = 18377


@dataclass
class MulticastConfig:
    """Multicast transport tuning."""

    group: str = DEFAULT_LAN_GROUP
    port: int = DEFAULT_LAN_PORT
    ttl: int = 1                    # 1 = LAN segment only
    interface: str = "127.0.0.1"    # loopback default: no real net needed
    announce_interval_s: float = 2.0
    socket_timeout_s: float = 0.2

    def __post_init__(self) -> None:
        try:
            packed = socket.inet_aton(self.group)
        except OSError:
            raise SpecError(
                f"multicast group {self.group!r} is not an IPv4 address"
            ) from None
        if not 224 <= packed[0] <= 239:
            raise SpecError(
                f"multicast group {self.group!r} is not in 224.0.0.0/4")
        if not 1 <= self.port <= 65535:
            raise SpecError(f"multicast port out of range: {self.port!r}")
        if not 0 <= self.ttl <= 255:
            raise SpecError(f"multicast ttl out of range: {self.ttl!r}")
        if self.announce_interval_s <= 0:
            raise SpecError("announce_interval_s must be > 0")


SocketFactory = Callable[[], socket.socket]


def _default_socket_factory(config: MulticastConfig) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
                         socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, config.ttl)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
                    socket.inet_aton(config.interface))
    # Membership: group + interface as raw 4-byte addresses (no struct).
    membership = (socket.inet_aton(config.group)
                  + socket.inet_aton(config.interface))
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
    sock.bind(("", config.port))
    sock.settimeout(config.socket_timeout_s)
    return sock


class LANDiscoveryAdapter(Discovery):
    """Multicast-based peer discovery.

    ``start()`` opens the multicast socket and begins announcing +
    listening; ``peers()`` returns every distinct node heard from
    recently. Malformed datagrams are ignored, never fatal.
    """

    name = "lan"

    def __init__(self, identity: NodeIdentity,
                 http_port: int,
                 capabilities: NodeCapabilities | None = None,
                 config: MulticastConfig | None = None,
                 tls: bool = False,
                 socket_factory: SocketFactory | None = None) -> None:
        if not 1 <= http_port <= 65535:
            raise SpecError(f"http_port out of range: {http_port!r}")
        self._identity = identity
        self._http_port = http_port
        self._capabilities = capabilities
        self._config = config or MulticastConfig()
        self._tls = tls
        self._socket_factory = socket_factory or (
            lambda: _default_socket_factory(self._config))
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.RLock()
        self._seen: dict[str, PeerRecord] = {}
        self._seq = 0
        self._sent = 0
        self._received = 0
        self._send_errors = 0

    # -- lifecycle --------------------------------------------------------

    def start(self) -> None:
        with self._lock:
            if self._thread is not None:
                return
            try:
                self._sock = self._socket_factory()
            except OSError as e:
                raise SpecError(
                    f"LAN discovery cannot open multicast socket: {e}"
                ) from e
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run, name="lan-discovery", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            thread, sock = self._thread, self._sock
            self._thread, self._sock = None, None
        self._stop_event.set()
        if sock is not None:
            try:
                sock.close()
            except OSError:  # best-effort close during shutdown
                pass
        if thread is not None:
            thread.join(timeout=2.0)

    @property
    def running(self) -> bool:
        with self._lock:
            return self._thread is not None

    # -- Discovery API ----------------------------------------------------

    def peers(self) -> list[PeerRecord]:
        with self._lock:
            return list(self._seen.values())

    # -- internals --------------------------------------------------------

    def _hello_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "node_id": self._identity.node_id,
            "display_name": self._identity.display_name,
            "http_port": self._http_port,
            "tls": self._tls,
        }
        if self._capabilities is not None:
            payload["capabilities"] = self._capabilities.to_dict()
        return payload

    def _make_hello(self) -> ClusterMessage:
        self._seq += 1
        return ClusterMessage(
            msg_type=MessageType.HELLO,
            sender=self._identity.node_id,
            seq=self._seq,
            trace_id=new_trace_id(),
            payload=self._hello_payload(),
        )

    def announce(self) -> None:
        """Send one HELLO immediately (also called periodically)."""
        sock = self._sock
        if sock is None:
            raise SpecError("LAN discovery is not started")
        data = encode_message(self._make_hello())
        try:
            sock.sendto(data, (self._config.group, self._config.port))
        except OSError:
            with self._lock:
                self._send_errors += 1
            raise
        with self._lock:
            self._sent += 1

    def stats(self) -> dict[str, int]:
        """Send/receive counters for health scoring (slice 213)."""
        with self._lock:
            return {
                "sent": self._sent,
                "received": self._received,
                "send_errors": self._send_errors,
                "peers_seen": len(self._seen),
            }

    def _run(self) -> None:
        last_announce = 0.0
        while not self._stop_event.is_set():
            now = time.time()
            if now - last_announce >= self._config.announce_interval_s:
                last_announce = now
                try:
                    self.announce()
                except (OSError, SpecError):
                    # Transient send failure (e.g. sandbox blocks
                    # multicast); the counter records it, we retry next
                    # interval.
                    pass
            sock = self._sock
            if sock is None:
                break
            try:
                data, addr = sock.recvfrom(65535)
            except TimeoutError:
                continue
            except OSError:
                break  # socket closed from stop()
            self._handle_datagram(data, addr[0])

    def _handle_datagram(self, data: bytes, source_host: str) -> None:
        try:
            message = decode_message(data)
        except SpecError:
            return  # malformed: ignore, never fatal
        if message.msg_type is not MessageType.HELLO:
            return
        payload = message.payload
        node_id = payload.get("node_id")
        http_port = payload.get("http_port")
        if (not isinstance(node_id, str) or len(node_id) != 64
                or any(c not in "0123456789abcdef" for c in node_id)):
            return
        if node_id == self._identity.node_id:
            return  # our own announcement reflected back
        if (not isinstance(http_port, int) or isinstance(http_port, bool)
                or not 1 <= http_port <= 65535):
            return
        capabilities = None
        raw_caps = payload.get("capabilities")
        if isinstance(raw_caps, dict):
            try:
                capabilities = NodeCapabilities.from_dict(raw_caps)
            except SpecError:
                capabilities = None  # bad caps: keep the peer, drop caps
        record = PeerRecord(
            node_id=node_id,
            host=source_host,
            port=http_port,
            capabilities=capabilities,
            source=self.name,
            tls=bool(payload.get("tls", False)),
        )
        with self._lock:
            self._seen[node_id] = record
            self._received += 1
