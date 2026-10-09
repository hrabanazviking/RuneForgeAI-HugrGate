"""Slice 380 — memory-write gating."""

from __future__ import annotations

import pytest

from hugrgate.agents.memory_write import (
    MemoryWriteGate,
    WriteGateConfig,
    WritePermit,
)


def _gate(**kw) -> MemoryWriteGate:
    clock = [1000.0]
    kw.setdefault("clock", lambda: clock[0])
    gate = MemoryWriteGate(**kw)
    gate.bind_agent("writer", role="owner", clearance="sensitive")
    gate.bind_agent("reader", role="analyst", clearance="sensitive")
    return gate


def test_grant_path():
    g = _gate()
    p = g.attempt_write("writer", {"privacy_class": "standard",
                                   "size_bytes": 100})
    assert isinstance(p, WritePermit)
    assert p.granted and p.reason == "ok"
    assert p.privacy_class == "standard"


def test_bad_class_rejected():
    g = _gate()
    p = g.attempt_write("writer", {"privacy_class": "ultra"})
    assert not p.granted and p.reason == "bad_class"
    p = g.attempt_write("writer", {})
    assert p.reason == "bad_class"


def test_unbound_agent_denied_fail_closed():
    g = _gate()
    p = g.attempt_write("ghost", {"privacy_class": "public"})
    assert not p.granted and p.reason == "unbound_agent"


def test_clearance_enforced():
    g = _gate()
    p = g.attempt_write("writer", {"privacy_class": "strict"})
    assert not p.granted and p.reason == "clearance"  # writer: sensitive
    g.bind_agent("top", role="owner", clearance="forbidden")
    assert g.attempt_write("top", {"privacy_class": "forbidden"}).granted


def test_readonly_roles_cannot_write():
    g = _gate()
    p = g.attempt_write("reader", {"privacy_class": "public"})
    assert not p.granted and p.reason == "role_readonly"


def test_rate_limit_and_size_cap():
    clock = [0.0]
    g = MemoryWriteGate(
        WriteGateConfig(max_writes_per_minute=2, max_payload_bytes=10),
        clock=lambda: clock[0],
    )
    g.bind_agent("w", role="owner", clearance="forbidden")
    assert g.attempt_write("w", {"privacy_class": "public"}).granted
    assert g.attempt_write("w", {"privacy_class": "public"}).granted
    p = g.attempt_write("w", {"privacy_class": "public"})
    assert not p.granted and p.reason == "rate_limited"
    clock[0] += 61.0  # bucket refills
    assert g.attempt_write("w", {"privacy_class": "public"}).granted
    p = g.attempt_write("w", {"privacy_class": "public", "size_bytes": 11})
    assert not p.granted and p.reason == "too_large"


def test_dedup_suppresses_repeats():
    clock = [0.0]
    g = MemoryWriteGate(
        WriteGateConfig(dedup_window_s=60.0), clock=lambda: clock[0])
    g.bind_agent("w", role="owner", clearance="forbidden")
    ep = {"privacy_class": "public", "dedup_key": "k"}
    assert g.attempt_write("w", ep).granted
    p = g.attempt_write("w", ep)
    assert not p.granted and p.reason == "duplicate"
    clock[0] += 61.0
    assert g.attempt_write("w", ep).granted


def test_default_role_and_binding_validation():
    g = MemoryWriteGate(WriteGateConfig(default_role="auditor"))
    p = g.attempt_write("anyone", {"privacy_class": "public"})
    assert not p.granted and p.reason == "role_readonly"  # auditor: no write
    with pytest.raises(ValueError):
        g.bind_agent("x", role="pope", clearance="public")
    with pytest.raises(ValueError):
        g.bind_agent("x", role="owner", clearance="ultra")
    with pytest.raises(ValueError):
        MemoryWriteGate(WriteGateConfig(default_role="pope"))
    assert g.unbind_agent("nobody") is False


def test_stats():
    g = _gate()
    g.attempt_write("writer", {"privacy_class": "public"})
    g.attempt_write("ghost", {"privacy_class": "public"})
    s = g.stats()
    assert s["requests"] == 2 and s["granted"] == 1 and s["denied"] == 1
    assert s["by_reason"]["ok"] == 1
    assert s["by_reason"]["unbound_agent"] == 1
