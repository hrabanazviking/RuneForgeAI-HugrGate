"""Tests for slice 8 — bus dead letters.

The ``"drop-oldest"`` backpressure policy used to only count shed
signals.  It now keeps a bounded dead-letter queue (default 100) of
the dropped signal payloads, exposed via ``EventBus.dead_letters()``.
"""

from __future__ import annotations

import pytest

from hugrgate.agents.bus import DeadLetter, EventBus
from hugrgate.agents.types import AgentSignal


def _saturate(bus: EventBus, *, n: int = 1, topic: str = "inner") -> None:
    """Publish ``outer`` whose handler re-enters the bus ``n`` times.

    With ``max_pending=1`` each re-entrant publish hits backpressure and,
    under the ``"drop-oldest"`` policy, is shed into the dead letters.
    """

    def reenter(signal):
        for i in range(n):
            bus.publish(
                AgentSignal(topic=topic, payload={"seq": i, "outer": True})
            )

    bus.subscribe("outer", reenter)
    bus.publish(AgentSignal(topic="outer"))


def test_dead_letters_record_dropped_payload():
    bus = EventBus(max_pending=1, backpressure="drop-oldest")
    _saturate(bus, n=1)
    assert bus.stats()["dropped_backpressure"] == 1
    letters = bus.dead_letters()
    assert len(letters) == 1
    letter = letters[0]
    assert isinstance(letter, DeadLetter)
    assert letter.topic == "inner"
    assert letter.payload == {"seq": 0, "outer": True}
    assert letter.reason == "backpressure"
    assert letter.dropped_at > 0


def test_dead_letters_bound_enforced():
    bus = EventBus(
        max_pending=1, backpressure="drop-oldest", dead_letter_capacity=3
    )
    _saturate(bus, n=5)
    assert bus.stats()["dropped_backpressure"] == 5
    letters = bus.dead_letters()
    assert len(letters) == 3
    # Oldest evicted: only the three most recent seqs remain, in order.
    assert [dl.payload["seq"] for dl in letters] == [2, 3, 4]


def test_dead_letters_default_capacity():
    bus = EventBus(max_pending=1, backpressure="drop-oldest")
    _saturate(bus, n=105)
    letters = bus.dead_letters()
    assert len(letters) == 100
    assert [dl.payload["seq"] for dl in letters] == list(range(5, 105))


def test_dead_letters_empty_by_default():
    bus = EventBus()
    assert bus.dead_letters() == []
    bus.publish(AgentSignal(topic="evt"))
    assert bus.dead_letters() == []


def test_dead_letters_return_copy():
    bus = EventBus(max_pending=1, backpressure="drop-oldest")
    _saturate(bus, n=1)
    letters = bus.dead_letters()
    letters.clear()
    assert len(bus.dead_letters()) == 1


def test_dead_letter_capacity_validation():
    with pytest.raises(ValueError):
        EventBus(dead_letter_capacity=0)
    with pytest.raises(ValueError):
        EventBus(dead_letter_capacity=-5)


def test_raise_policy_has_no_dead_letters():
    bus = EventBus(max_pending=1, backpressure="raise")
    bus.subscribe("outer", lambda s: bus.publish(AgentSignal(topic="inner")))
    d = bus.publish(AgentSignal(topic="outer"))
    assert any("saturated" in e for e in d.errors)
    assert bus.dead_letters() == []
    assert bus.stats()["dropped_backpressure"] == 0


def test_payload_snapshot_not_live_reference():
    bus = EventBus(max_pending=1, backpressure="drop-oldest")
    payload: dict = {"seq": 0}
    bus.subscribe("outer", lambda s: bus.publish(AgentSignal(topic="inner", payload=payload)))
    bus.publish(AgentSignal(topic="outer"))
    payload["seq"] = 999  # mutate after the drop
    assert bus.dead_letters()[0].payload == {"seq": 0}
