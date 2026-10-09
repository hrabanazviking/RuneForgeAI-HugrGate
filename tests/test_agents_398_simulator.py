"""Slice 398 — agent simulator."""

from __future__ import annotations

import pytest

from hugrgate.agents.bus import EventBus
from hugrgate.agents.runaway import RunawayLimits
from hugrgate.agents.simulator import (
    BEHAVIORS,
    AgentSimulator,
    SimContext,
)
from hugrgate.agents.types import AgentSignal


def _sim(**kw):
    sim = AgentSimulator(**kw)
    sim.add_agent("worker", "honest")
    sim.add_agent("flake", "faulty")
    sim.add_agent("looper", "looping")
    sim.add_agent("climber", "escalating")
    return sim


def _step(ticket, frm, to, intent="do"):
    return {"ticket": ticket, "from": frm, "to": to, "intent": intent}


def test_honest_and_faulty():
    sim = _sim()
    rep = sim.run([_step("t1", "boss", "worker"),
                   _step("t1", "boss", "flake"),
                   _step("t2", "boss", "worker")], seed=7)
    assert rep.steps == 3
    assert rep.successes == 2 and rep.failures == 1
    assert rep.success_rate == pytest.approx(2 / 3)
    assert rep.seed == 7
    assert rep.per_agent["worker"]["successes"] == 2
    assert rep.per_agent["flake"]["failures"] == 1


def test_looping_trips_breaker():
    sim = _sim()
    rep = sim.run([_step("t1", "boss", "looper")], seed=1)
    assert rep.loops_detected == 1
    assert rep.successes == 0


def test_escalating_trips_runaway_guard():
    sim = AgentSimulator(runaway_limits=RunawayLimits(
        max_escalations_per_ticket=2, max_steps_per_ticket=1000,
        max_tokens_per_ticket=100000))
    sim.add_agent("climber", "escalating")
    script = [_step("t1", "boss", "climber") for _ in range(4)]
    rep = sim.run(script, seed=1)
    assert rep.escalations == 2
    assert rep.runaways == 2


def test_fault_hook_trips_kill_switch():
    sim = _sim()
    seen: list[AgentSignal] = []
    sim.bus.subscribe("agent.runaway", seen.append)

    def kill_at_2(s, i):
        if i == 2:
            s.guard.trip_kill_switch("chaos fault")

    rep = sim.run([_step("t1", "boss", "climber"),
                   _step("t1", "boss", "climber"),
                   _step("t1", "boss", "climber"),
                   _step("t1", "boss", "worker")], seed=1,
                  faults=[kill_at_2])
    assert rep.runaways >= 1  # kill switch halts climber's escalations
    assert any(s.payload.get("kill_switch") for s in seen)


def test_custom_behavior_and_unknown_behavior():
    sim = AgentSimulator()
    calls = []

    def custom(ctx: SimContext):
        calls.append((ctx.ticket_id, ctx.agent_id, ctx.step_index))
        assert ctx.rng is not None
        return "complete"

    sim.add_agent("custom", custom)
    rep = sim.run([_step("t9", "boss", "custom")], seed=3)
    assert rep.successes == 1
    assert calls == [("t9", "custom", 0)]
    with pytest.raises(ValueError):
        sim.add_agent("x", "chaotic")


def test_determinism_same_seed():
    sim = _sim()
    script = [_step("t1", "boss", "worker"), _step("t1", "boss", "flake")]
    r1 = sim.run(script, seed=99)
    sim2 = _sim()
    r2 = sim2.run(script, seed=99)
    assert (r1.successes, r1.failures) == (r2.successes, r2.failures)


def test_empty_script():
    sim = _sim()
    rep = sim.run([], seed=1)
    assert rep.steps == 0 and rep.success_rate == 1.0
    assert set(BEHAVIORS) == {"honest", "slow", "faulty", "looping",
                              "escalating"}
    assert isinstance(sim.bus, EventBus)
