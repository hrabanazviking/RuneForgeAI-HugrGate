"""Tests for slice 204 — node discovery framework."""

from __future__ import annotations

import time

import pytest

from hugrgate.cluster.discovery import (
    DEFAULT_STALE_AFTER_S,
    Discovery,
    DiscoveryRegistry,
    PeerRecord,
)
from hugrgate.errors import SpecError


class _Static(Discovery):
    name = "static-test"

    def __init__(self, peers):
        self._peers = peers

    def peers(self):
        return list(self._peers)


class _Boom(Discovery):
    name = "boom"

    def peers(self):
        raise RuntimeError("adapter exploded")


def _peer(node_id="n1", host="127.0.0.1", port=8377, age=0.0, source="s"):
    return PeerRecord(node_id=node_id, host=host, port=port,
                      last_seen=time.time() - age, source=source)


# --- PeerRecord ------------------------------------------------------------

def test_address_scheme_follows_tls():
    assert _peer().address == "http://127.0.0.1:8377"
    assert _peer(node_id="n2", port=9999).address == "http://127.0.0.1:9999"
    tls_peer = PeerRecord(node_id="n3", host="h", port=1, tls=True)
    assert tls_peer.address.startswith("https://")


def test_peer_rejects_bad_fields():
    with pytest.raises(SpecError):
        PeerRecord(node_id="", host="h", port=1)
    with pytest.raises(SpecError):
        PeerRecord(node_id="n", host="", port=1)
    with pytest.raises(SpecError):
        PeerRecord(node_id="n", host="h", port=0)
    with pytest.raises(SpecError):
        PeerRecord(node_id="n", host="h", port=70000)


def test_staleness():
    fresh = _peer(age=1.0)
    old = _peer(age=DEFAULT_STALE_AFTER_S + 1.0)
    assert not fresh.is_stale()
    assert old.is_stale()
    assert old.is_stale(stale_after_s=10**9) is False


def test_peer_to_dict_round_trip_shape():
    d = _peer().to_dict()
    assert d["node_id"] == "n1" and d["capabilities"] is None


# --- DiscoveryRegistry -----------------------------------------------------

def test_merges_adapters_and_dedups_by_node_id():
    reg = DiscoveryRegistry()
    old = _peer(node_id="n1", age=10.0, source="a")
    new = _peer(node_id="n1", age=1.0, source="b")
    reg.add_adapter(_Static([old, _peer(node_id="n2")]))
    reg.add_adapter(_Static([new]))
    peers = reg.peers()
    assert [p.node_id for p in peers] == ["n2", "n1"]  # freshest first
    winner = next(p for p in peers if p.node_id == "n1")
    assert winner.source == "b"  # newest last_seen wins


def test_prunes_stale_peers():
    reg = DiscoveryRegistry(stale_after_s=5.0)
    reg.add_adapter(_Static([_peer(node_id="old", age=60.0),
                             _peer(node_id="new", age=1.0)]))
    assert [p.node_id for p in reg.peers()] == ["new"]


def test_never_lists_self():
    reg = DiscoveryRegistry(local_node_id="me")
    reg.add_adapter(_Static([_peer(node_id="me"), _peer(node_id="you")]))
    assert [p.node_id for p in reg.peers()] == ["you"]


def test_failing_adapter_does_not_blind_registry():
    reg = DiscoveryRegistry()
    reg.add_adapter(_Boom())
    reg.add_adapter(_Static([_peer()]))
    assert [p.node_id for p in reg.peers()] == ["n1"]


def test_find_and_len():
    reg = DiscoveryRegistry()
    assert reg.find("n1") is None and len(reg) == 0
    reg.add_adapter(_Static([_peer()]))
    assert reg.find("n1").host == "127.0.0.1"
    assert len(reg) == 1


def test_rejects_non_adapter():
    with pytest.raises(SpecError):
        DiscoveryRegistry().add_adapter(object())


def test_rejects_bad_stale_after():
    with pytest.raises(SpecError):
        DiscoveryRegistry(stale_after_s=0)


def test_start_stop_all_and_context_manager():
    started, stopped = [], []

    class Life(_Static):
        def start(self):
            started.append(1)

        def stop(self):
            stopped.append(1)

    reg = DiscoveryRegistry()
    adapter = Life([])
    reg.add_adapter(adapter)
    reg.start_all()
    reg.stop_all()
    assert started == [1] and stopped == [1]
    with adapter:
        pass
    assert stopped == [1, 1]


def test_peers_freshest_first():
    reg = DiscoveryRegistry()
    reg.add_adapter(_Static([_peer(node_id="a", age=5.0),
                             _peer(node_id="b", age=1.0),
                             _peer(node_id="c", age=3.0)]))
    assert [p.node_id for p in reg.peers()] == ["b", "c", "a"]
