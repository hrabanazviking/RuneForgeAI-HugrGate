"""Slice 382 — notification gating."""

from __future__ import annotations

import pytest

from hugrgate.agents.bus import EventBus
from hugrgate.agents.notify import (
    ChannelConfig,
    Notification,
    NotificationGate,
    NotifyDecision,
)
from hugrgate.agents.types import AgentSignal


def _gate(**kw):
    sent: list[Notification] = []
    kw.setdefault("sender", sent.append)
    clock = [1000.0]
    kw.setdefault("clock", lambda: clock[0])
    gate = NotificationGate(**kw)
    gate.configure("ops", ChannelConfig(rate_per_minute=2,
                                        min_severity="warning"))
    gate.configure("debug", ChannelConfig(min_severity="info"))
    return gate, sent, clock


def test_sent_path_and_bus_signal():
    bus = EventBus()
    seen: list[AgentSignal] = []
    bus.subscribe("notify.sent", seen.append)
    gate, sent, _ = _gate(bus=bus)
    d = gate.notify(Notification(channel="ops", title="disk hot",
                                  severity="critical",
                                  trace_id="hg-trace-00000001"))
    assert isinstance(d, NotifyDecision)
    assert d.sent and d.reason == "sent"
    assert len(sent) == 1 and sent[0].title == "disk hot"
    assert len(seen) == 1
    assert seen[0].trace_id == "hg-trace-00000001"


def test_severity_filter_and_unknown_channel():
    gate, sent, _ = _gate()
    d = gate.notify(Notification(channel="ops", title="meh", severity="info"))
    assert not d.sent and d.reason == "severity_filtered"
    d = gate.notify(Notification(channel="n/a", title="x"))
    assert d.reason == "channel_unknown"
    assert sent == []


def test_disabled_channel():
    gate, sent, _ = _gate()
    gate.configure("ops", ChannelConfig(enabled=False))
    d = gate.notify(Notification(channel="ops", title="x",
                                  severity="critical"))
    assert d.reason == "channel_disabled"
    assert sent == []


def test_dedup_suppresses_repeats():
    clock = [0.0]
    gate = NotificationGate(clock=lambda: clock[0])
    gate.configure("ops", ChannelConfig(dedup_window_s=60.0))
    n = Notification(channel="ops", title="flap", severity="critical",
                     dedup_key="k")
    assert gate.notify(n).sent
    assert gate.notify(n).reason == "duplicate"
    clock[0] += 61.0
    assert gate.notify(n).sent


def test_rate_limit():
    clock = [0.0]
    gate = NotificationGate(clock=lambda: clock[0])
    gate.configure("ops", ChannelConfig(rate_per_minute=1))
    assert gate.notify(Notification(channel="ops", title="a",
                                     severity="critical")).sent
    d = gate.notify(Notification(channel="ops", title="b",
                                  severity="critical"))
    assert d.reason == "rate_limited"
    clock[0] += 61.0
    assert gate.notify(Notification(channel="ops", title="c",
                                     severity="critical")).sent


def test_sender_failure_is_a_decision():
    def bad(n):
        raise RuntimeError("smtp down")
    gate = NotificationGate(sender=bad)
    gate.configure("ops", ChannelConfig())
    d = gate.notify(Notification(channel="ops", title="x"))
    assert not d.sent and d.reason == "sender_failed"


def test_validation():
    with pytest.raises(ValueError):
        Notification(channel="", title="x")
    with pytest.raises(ValueError):
        Notification(channel="c", title="x", severity="nope")
    with pytest.raises(ValueError):
        ChannelConfig(rate_per_minute=0)
    with pytest.raises(ValueError):
        ChannelConfig(min_severity="nope")
    gate = NotificationGate()
    with pytest.raises(ValueError):
        gate.configure("", ChannelConfig())


def test_stats():
    gate, _, _ = _gate()
    gate.notify(Notification(channel="ops", title="a", severity="critical"))
    gate.notify(Notification(channel="ops", title="b", severity="info"))
    gate.notify(Notification(channel="debug", title="c", severity="info"))
    s = gate.stats()
    assert s["requests"] == 3 and s["sent"] == 2 and s["suppressed"] == 1
    assert s["by_reason"]["sent"] == 2
    assert s["by_reason"]["severity_filtered"] == 1
    assert s["by_channel"]["ops"] == {"sent": 1, "suppressed": 1}
