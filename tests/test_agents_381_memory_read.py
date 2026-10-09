"""Slice 381 — memory-read gating."""

from __future__ import annotations

import pytest

from hugrgate.agents.memory_read import (
    MemoryReadGate,
    ReadGateConfig,
    ReadPermit,
)


def _gate(**kw) -> MemoryReadGate:
    clock = [1000.0]
    kw.setdefault("clock", lambda: clock[0])
    gate = MemoryReadGate(**kw)
    gate.bind_agent("owner1", role="owner", clearance="forbidden")
    gate.bind_agent("analyst1", role="analyst", clearance="sensitive")
    gate.bind_agent("auditor1", role="auditor", clearance="standard")
    return gate


def test_grant_and_redaction_lines():
    g = _gate()
    p = g.attempt_read("owner1", "sensitive")
    assert isinstance(p, ReadPermit)
    assert p.granted and p.reason == "ok" and not p.redacted
    # Analyst reading sensitive: granted but redacted (redact_at=sensitive).
    p = g.attempt_read("analyst1", "sensitive")
    assert p.granted and p.redacted
    # Analyst reading standard: below redact line, not redacted.
    p = g.attempt_read("analyst1", "standard")
    assert p.granted and not p.redacted
    # Auditor reading standard: granted but redacted (redact_at=standard).
    p = g.attempt_read("auditor1", "standard")
    assert p.granted and p.redacted


def test_role_max_class_enforced():
    g = _gate()
    # Auditor clearance is standard; analyst clearance is sensitive.
    p = g.attempt_read("auditor1", "sensitive")
    assert not p.granted and p.reason == "clearance"
    g.bind_agent("auditor2", role="auditor", clearance="forbidden")
    p = g.attempt_read("auditor2", "sensitive")
    assert not p.granted and p.reason == "role_class"  # max_class=standard


def test_fail_closed_and_bad_class():
    g = _gate()
    assert g.attempt_read("ghost", "public").reason == "unbound_agent"
    assert g.attempt_read("owner1", "ultra").reason == "bad_class"


def test_rate_limit():
    clock = [0.0]
    g = MemoryReadGate(ReadGateConfig(max_reads_per_minute=1),
                       clock=lambda: clock[0])
    g.bind_agent("r", role="owner", clearance="forbidden")
    assert g.attempt_read("r", "public").granted
    assert g.attempt_read("r", "public").reason == "rate_limited"
    clock[0] += 61.0
    assert g.attempt_read("r", "public").granted


def test_audit_trail_bounded_and_copied():
    clock = [0.0]
    g = MemoryReadGate(ReadGateConfig(audit_trail_size=3),
                       clock=lambda: clock[0])
    g.bind_agent("r", role="owner", clearance="forbidden")
    for i in range(5):
        clock[0] += 1.0
        g.attempt_read("r", "public", purpose=f"q{i}")
    trail = g.audit_trail()
    assert len(trail) == 3  # bounded
    assert [e["purpose"] for e in trail] == ["q2", "q3", "q4"]  # oldest kept order
    trail[0]["purpose"] = "mutated"
    assert g.audit_trail()[0]["purpose"] == "q2"  # copies
    s = g.stats()
    assert s["requests"] == 5 and s["granted"] == 5 and s["redacted"] == 0


def test_denied_reads_audited():
    g = _gate()
    g.attempt_read("ghost", "public", purpose="sneak")
    trail = g.audit_trail()
    assert len(trail) == 1
    assert trail[0]["granted"] is False
    assert trail[0]["reason"] == "unbound_agent"
    assert trail[0]["purpose"] == "sneak"


def test_binding_validation():
    g = MemoryReadGate()
    with pytest.raises(ValueError):
        g.bind_agent("x", role="nobody", clearance="public")
    with pytest.raises(ValueError):
        g.bind_agent("x", role="owner", clearance="nobody")
    with pytest.raises(ValueError):
        MemoryReadGate(ReadGateConfig(default_role="nobody"))
