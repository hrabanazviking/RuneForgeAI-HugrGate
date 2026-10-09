"""Slice 070 — route replay."""

from __future__ import annotations

import json

import pytest

from hugrgate import (
    Abstention,
    Backend,
    BackendRegistry,
    DecisionPolicy,
    DecisionResult,
    DecisionSpec,
    SpecError,
)
from hugrgate.ladder import LadderRung
from hugrgate.routing import (
    LadderRouterV2,
    RecordingExecutor,
    ReplayExecutor,
    RouteRecording,
    SerialPlanExecutor,
    replay,
)


class RecBackend(Backend):
    def __init__(self, name, prob=0.95):
        self.name = name
        self._prob = prob
        self.calls = 0

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        self.calls += 1
        n = len(spec.options)
        rest = (1.0 - self._prob) / max(n - 1, 1)
        return DecisionResult(
            value="a", probability=self._prob,
            distribution={o: (self._prob if o == "a" else rest)
                          for o in spec.options},
            backend=self.name)


def reg_of(*bs):
    r = BackendRegistry()
    for b in bs:
        r.register(b)
    return r


def spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


def record_climb():
    weak = RecBackend("weak", prob=0.5)
    strong = RecBackend("strong", prob=0.99)
    reg = reg_of(weak, strong)
    rec = RecordingExecutor(SerialPlanExecutor())
    router = LadderRouterV2(
        reg, rungs=[LadderRung("ghost", 0.9),   # unknown -> skip
                    LadderRung("weak", 0.9),    # below gate
                    LadderRung("strong", 0.9)],  # wins
        executor=rec)
    won = router.decide({}, spec(), DecisionPolicy(minimum_probability=0.9))
    assert won.backend == "strong"
    return rec.last_recording, (weak, strong)


def test_record_and_replay_reproduces_winner():
    recording, (weak, strong) = record_climb()
    assert recording.winner_result["backend"] == "strong"
    assert len(recording.rung_outcomes) == 3

    # replay with an EMPTY registry: no backend is ever touched
    decision = replay(recording)
    assert decision.result.backend == "strong"
    assert decision.result.probability == pytest.approx(0.99)
    assert decision.result.value == "a"
    assert decision.result.metadata["replayed"] is True
    assert decision.accepted_rung == 2
    outcomes = [e["outcome"] for e in decision.audit]
    assert outcomes == ["skipped_unknown_backend", "below_confidence",
                        "accepted"]
    assert weak.calls == 1 and strong.calls == 1  # record-time only


def test_replay_via_executor():
    recording, _ = record_climb()
    reg = BackendRegistry()  # empty on purpose
    router = LadderRouterV2(
        reg, rungs=[LadderRung("x", 0.9)],
        executor=ReplayExecutor(recording))
    won = router.decide({}, spec(), DecisionPolicy(minimum_probability=0.9))
    assert won.backend == "strong"
    assert won.metadata["replayed"] is True


def test_json_round_trip():
    recording, _ = record_climb()
    data = json.loads(json.dumps(recording.to_json()))
    restored = RouteRecording.from_json(data)
    assert restored.plan_fingerprint == recording.plan_fingerprint
    decision = replay(restored)
    assert decision.result.backend == "strong"


def test_tampered_plan_rejected():
    recording, _ = record_climb()
    recording.plan["nodes"][0]["backend_name"] = "mallory"
    with pytest.raises(SpecError) as exc:
        replay(recording)
    assert "fingerprint mismatch" in str(exc.value)


def test_recording_without_winner_rejected():
    rec = RouteRecording(plan={"nodes": [], "strategy": "serial"},
                         plan_fingerprint="x", spec_type="categorical",
                         spec_options=["a", "b"], minimum_probability=0.9)
    with pytest.raises(SpecError):
        replay(rec)


def test_abstention_not_recordable():
    weak = RecBackend("weak", prob=0.1)
    reg = reg_of(weak)
    rec = RecordingExecutor(SerialPlanExecutor())
    router = LadderRouterV2(reg, rungs=[LadderRung("weak", 0.9)],
                            executor=rec)
    with pytest.raises(Abstention):
        router.decide({}, spec(), DecisionPolicy(minimum_probability=0.9))
    assert rec.last_recording is None
