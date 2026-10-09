"""Tests for slice 206 — LAN discovery adapter."""

from __future__ import annotations

import time

import pytest

from hugrgate.cluster.capabilities import NodeCapabilities
from hugrgate.cluster.identity import NodeIdentity
from hugrgate.cluster.lan import (
    DEFAULT_LAN_GROUP,
    DEFAULT_LAN_PORT,
    LANDiscoveryAdapter,
    MulticastConfig,
)
from hugrgate.cluster.protocol import (
    MessageType,
    decode_message,
)
from hugrgate.errors import SpecError
from hugrgate.server import build_gate

pytestmark = pytest.mark.slow


class FakeSocket:
    """In-memory UDP stand-in; the adapter never knows."""

    def __init__(self):
        self.sent: list = []
        self.inbox: list = []
        self.closed = False

    def sendto(self, data, addr):
        self.sent.append((data, addr))
        return len(data)

    def recvfrom(self, n):
        if self.inbox:
            return self.inbox.pop(0)
        time.sleep(0.01)
        raise TimeoutError()

    def close(self):
        self.closed = True

    def settimeout(self, t):
        pass


def _adapter(**kw):
    kw.setdefault("identity", NodeIdentity.generate("lan-test"))
    kw.setdefault("http_port", 8377)
    factory_holder: dict = {}

    def factory():
        sock = FakeSocket()
        factory_holder["sock"] = sock
        return sock

    kw.setdefault("socket_factory", factory)
    adapter = LANDiscoveryAdapter(**kw)
    return adapter, factory_holder


def _hello_bytes(node_id, http_port=9999, tls=False, caps=None):
    from hugrgate.cluster.protocol import ClusterMessage, encode_message
    payload = {"node_id": node_id, "display_name": "peer",
               "http_port": http_port, "tls": tls}
    if caps is not None:
        payload["capabilities"] = caps
    return encode_message(ClusterMessage(
        msg_type=MessageType.HELLO, sender=node_id, seq=1,
        payload=payload))


# --- config validation -----------------------------------------------------

def test_config_rejects_non_multicast_group():
    with pytest.raises(SpecError, match=r"not in 224\.0\.0\.0/4"):
        MulticastConfig(group="10.0.0.1")


def test_config_rejects_garbage_group():
    with pytest.raises(SpecError, match="not an IPv4 address"):
        MulticastConfig(group="not-an-ip")


def test_config_rejects_bad_port_and_ttl():
    with pytest.raises(SpecError, match="port"):
        MulticastConfig(port=0)
    with pytest.raises(SpecError, match="ttl"):
        MulticastConfig(ttl=256)
    with pytest.raises(SpecError, match="announce_interval"):
        MulticastConfig(announce_interval_s=0)


def test_adapter_rejects_bad_http_port():
    with pytest.raises(SpecError, match="http_port"):
        LANDiscoveryAdapter(identity=NodeIdentity.generate(), http_port=0)


# --- announce ---------------------------------------------------------------

def test_announce_sends_hello_to_group():
    adapter, holder = _adapter()
    adapter.start()
    try:
        adapter.announce()
        data, addr = holder["sock"].sent[-1]
        assert addr == (DEFAULT_LAN_GROUP, DEFAULT_LAN_PORT)
        msg = decode_message(data)
        assert msg.msg_type is MessageType.HELLO
        assert msg.payload["node_id"] == adapter._identity.node_id
        assert msg.payload["http_port"] == 8377
        assert msg.payload["tls"] is False
    finally:
        adapter.stop()


def test_announce_before_start_raises():
    adapter, _ = _adapter()
    with pytest.raises(SpecError, match="not started"):
        adapter.announce()


# --- receive -----------------------------------------------------------------

def test_valid_hello_registers_peer():
    adapter, holder = _adapter()
    other = NodeIdentity.generate("other")
    adapter.start()
    try:
        holder["sock"].inbox.append(
            (_hello_bytes(other.node_id, http_port=1234, tls=True),
             ("192.168.1.5", 18377)))
        deadline = time.time() + 2.0
        while not adapter.peers() and time.time() < deadline:
            time.sleep(0.05)
        peers = adapter.peers()
        assert len(peers) == 1
        peer = peers[0]
        assert peer.node_id == other.node_id
        assert peer.host == "192.168.1.5"  # from datagram source
        assert peer.port == 1234           # from payload
        assert peer.tls is True
        assert peer.source == "lan"
    finally:
        adapter.stop()


def test_ignores_own_hello():
    adapter, holder = _adapter()
    adapter.start()
    try:
        holder["sock"].inbox.append(
            (_hello_bytes(adapter._identity.node_id), ("127.0.0.1", 1)))
        time.sleep(0.3)
        assert adapter.peers() == []
    finally:
        adapter.stop()


def test_ignores_malformed_and_non_hello():
    adapter, holder = _adapter()
    import json

    from hugrgate.cluster.protocol import (
        PROTOCOL_VERSION,
        ClusterMessage,
        encode_message,
    )
    other = NodeIdentity.generate()
    # A HELLO whose sender fails envelope validation: built as raw JSON
    # so it fails at decode time (inside the adapter), not at test
    # construction time.
    bad_hello = json.dumps({
        "protocol_version": PROTOCOL_VERSION, "msg_type": "hello",
        "sender": "short-id", "seq": 1, "trace_id": "ab" * 16,
        "timestamp": 1.0,
        "payload": {"node_id": "short-id", "http_port": 9999},
    }).encode()
    non_hello = encode_message(ClusterMessage(
        msg_type=MessageType.HEARTBEAT, sender=other.node_id, seq=1))
    adapter.start()
    try:
        holder["sock"].inbox.extend([
            (b"garbage bytes", ("127.0.0.1", 1)),
            (bad_hello, ("127.0.0.1", 1)),
            (non_hello, ("127.0.0.1", 1)),
        ])
        time.sleep(0.3)
        assert adapter.peers() == []
    finally:
        adapter.stop()


def test_bad_capabilities_keep_peer_drop_caps():
    adapter, holder = _adapter()
    other = NodeIdentity.generate()
    adapter.start()
    try:
        holder["sock"].inbox.append(
            (_hello_bytes(other.node_id, caps={"bogus": True}),
             ("127.0.0.1", 1)))
        deadline = time.time() + 2.0
        while not adapter.peers() and time.time() < deadline:
            time.sleep(0.05)
        assert len(adapter.peers()) == 1
        assert adapter.peers()[0].capabilities is None
    finally:
        adapter.stop()


def test_good_capabilities_parsed():
    adapter, holder = _adapter()
    other = NodeIdentity.generate()
    caps = NodeCapabilities.from_gate(
        build_gate(), other).to_dict()
    adapter.start()
    try:
        holder["sock"].inbox.append(
            (_hello_bytes(other.node_id, caps=caps), ("127.0.0.1", 1)))
        deadline = time.time() + 2.0
        while not adapter.peers() and time.time() < deadline:
            time.sleep(0.05)
        peer = adapter.peers()[0]
        assert peer.capabilities is not None
        assert "keyword" in peer.capabilities.backend_names()
    finally:
        adapter.stop()


# --- lifecycle ---------------------------------------------------------------

def test_start_stop_lifecycle():
    adapter, holder = _adapter()
    assert not adapter.running
    adapter.start()
    assert adapter.running
    adapter.start()  # idempotent
    assert adapter.running
    adapter.stop()
    assert not adapter.running
    assert holder["sock"].closed


def test_socket_open_failure_raises_specerror():
    def boom():
        raise OSError("no multicast for you")

    adapter = LANDiscoveryAdapter(identity=NodeIdentity.generate(),
                                  http_port=8377, socket_factory=boom)
    with pytest.raises(SpecError, match="multicast socket"):
        adapter.start()


# --- real loopback multicast --------------------------------------------------

def _multicast_delivery_works(group, port) -> bool:
    """Probe: can this sandbox actually deliver multicast on loopback?"""
    import socket as _socket

    def _mk():
        s = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM,
                           _socket.IPPROTO_UDP)
        s.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
        if hasattr(_socket, "SO_REUSEPORT"):
            s.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEPORT, 1)
        s.setsockopt(_socket.IPPROTO_IP, _socket.IP_MULTICAST_LOOP, 1)
        s.setsockopt(_socket.IPPROTO_IP, _socket.IP_ADD_MEMBERSHIP,
                     _socket.inet_aton(group)
                     + _socket.inet_aton("127.0.0.1"))
        s.bind(("", port))
        s.settimeout(1.0)
        return s

    try:
        a, b = _mk(), _mk()
    except OSError:
        return False
    try:
        a.sendto(b"probe", (group, port))
        try:
            return b.recvfrom(16)[0] == b"probe"
        except TimeoutError:
            return False
    except OSError:
        return False
    finally:
        a.close()
        b.close()


def test_two_adapters_discover_each_other_on_loopback():
    if not _multicast_delivery_works(DEFAULT_LAN_GROUP, DEFAULT_LAN_PORT):
        pytest.skip("multicast delivery blocked in this sandbox")
    a_id, b_id = NodeIdentity.generate("a"), NodeIdentity.generate("b")
    cfg = MulticastConfig(interface="127.0.0.1", announce_interval_s=0.2)
    adapter_a = LANDiscoveryAdapter(a_id, 18301, config=cfg)
    adapter_b = LANDiscoveryAdapter(b_id, 18302, config=cfg)
    try:
        adapter_a.start()
        adapter_b.start()
        deadline = time.time() + 8.0
        while time.time() < deadline:
            ids_a = {p.node_id for p in adapter_a.peers()}
            ids_b = {p.node_id for p in adapter_b.peers()}
            if b_id.node_id in ids_a and a_id.node_id in ids_b:
                break
            time.sleep(0.2)
        assert b_id.node_id in {p.node_id for p in adapter_a.peers()}
        assert a_id.node_id in {p.node_id for p in adapter_b.peers()}
        peer = next(p for p in adapter_a.peers()
                    if p.node_id == b_id.node_id)
        assert peer.port == 18302
        assert adapter_a.stats()["received"] >= 1
        assert adapter_a.stats()["sent"] >= 1
    finally:
        adapter_a.stop()
        adapter_b.stop()
