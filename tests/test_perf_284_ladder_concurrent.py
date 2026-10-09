"""Slice 284 — concurrent ladder execution.

Covers: ordered-race semantics (lowest sufficient rung wins even when a
higher rung finishes first), latency overlap (concurrent faster than
sequential sum), pruning parity with sequential decide, cancellation
audit for post-win rungs, exhaustion abstention, max_workers
validation, and metadata marking.
"""

from __future__ import annotations

import time

import pytest

from hugrgate import DecisionPolicy, DecisionSpec
from hugrgate.backend import Backend, BackendRegistry
from hugrgate.errors import Abstention, SpecError
from hugrgate.ladder import (
    RUNG_ABSTAINED,
    RUNG_ACCEPTED,
    RUNG_BELOW_CONFIDENCE,
    RUNG_CANCELLED,
    RUNG_SKIPPED_LATENCY,
    LadderRouter,
    LadderRung,
)
from hugrgate.result import DecisionResult

SPEC = DecisionSpec(type="categorical", options=["a", "b"])


class SlowBackend(Backend):
    """Configurable latency + confidence; thread-safe by construction."""

    def __init__(self, name, delay, prob):
        self._name = name
        self.delay = delay
        self.prob = prob

    @property
    def name(self):
        return self._name

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        time.sleep(self.delay)
        return DecisionResult(value="a", probability=self.prob,
                              distribution={"a": self.prob,
                                            "b": 1.0 - self.prob})


def _router(backends, rungs, **kw) -> LadderRouter:
    registry = BackendRegistry()
    for b in backends:
        registry.register(b)
    return LadderRouter(registry, rungs=rungs, **kw)


POLICY = DecisionPolicy(minimum_probability=0.0)


def test_ordered_race_lowest_sufficient_wins():
    # rung 1 is fast and sufficient; rung 0 is slow but also sufficient
    # and must still win because it is lower in the ladder.
    backends = [SlowBackend("slow-sufficient", 0.15, 0.95),
                SlowBackend("fast-sufficient", 0.01, 0.95)]
    rungs = [LadderRung("slow-sufficient", min_confidence=0.9),
             LadderRung("fast-sufficient", min_confidence=0.9)]
    router = _router(backends, rungs)
    result = router.decide_concurrent({"x": 1}, SPEC, POLICY)
    assert result.backend == "slow-sufficient"
    assert result.metadata["ladder_rung"] == 0
    assert result.metadata["ladder_concurrent"] is True
    outcomes = [e.outcome for e in router.last_audit]
    assert outcomes[0] == RUNG_ACCEPTED
    assert RUNG_CANCELLED in outcomes  # rung 1 dropped after the win


def test_below_confidence_climbs_to_next_rung():
    backends = [SlowBackend("weak", 0.02, 0.3),
                SlowBackend("strong", 0.02, 0.95)]
    rungs = [LadderRung("weak", min_confidence=0.9),
             LadderRung("strong", min_confidence=0.9)]
    router = _router(backends, rungs)
    result = router.decide_concurrent({"x": 1}, SPEC, POLICY)
    assert result.backend == "strong"
    assert [e.outcome for e in router.last_audit] == [
        RUNG_BELOW_CONFIDENCE, RUNG_ACCEPTED]


def test_concurrent_overlaps_latency():
    # sequential would pay 0.05 + 0.05 for the climb; concurrent pays ~0.05
    backends = [SlowBackend("weak", 0.05, 0.3),
                SlowBackend("strong", 0.05, 0.95)]
    rungs = [LadderRung("weak", min_confidence=0.9),
             LadderRung("strong", min_confidence=0.9)]
    router = _router(backends, rungs)
    start = time.perf_counter()
    result = router.decide_concurrent({"x": 1}, SPEC, POLICY, max_workers=2)
    elapsed = time.perf_counter() - start
    assert result.backend == "strong"
    assert elapsed < 0.09, f"no overlap: took {elapsed:.3f}s"


def test_exhaustion_abstains_with_trace():
    backends = [SlowBackend("weak1", 0.01, 0.2),
                SlowBackend("weak2", 0.01, 0.3)]
    rungs = [LadderRung("weak1", min_confidence=0.9),
             LadderRung("weak2", min_confidence=0.9)]
    router = _router(backends, rungs)
    with pytest.raises(Abstention) as exc:
        router.decide_concurrent({"x": 1}, SPEC, POLICY)
    assert exc.value.details["reason"] == "ladder_exhausted"
    assert len(router.last_audit) == 2


def test_pruning_parity_with_sequential():
    backends = [SlowBackend("slow", 0.5, 0.99),
                SlowBackend("fast", 0.01, 0.95)]
    rungs = [LadderRung("slow", min_confidence=0.9, latency_budget_ms=10.0),
             LadderRung("fast", min_confidence=0.9)]
    seq = _router(backends, rungs)
    conc = _router(backends, rungs)
    seq_result = seq.decide({"x": 1}, SPEC, POLICY)
    conc_result = conc.decide_concurrent({"x": 1}, SPEC, POLICY)
    assert seq_result.backend == conc_result.backend == "fast"
    seq_outcomes = [e.outcome for e in seq.last_audit]
    conc_outcomes = [e.outcome for e in conc.last_audit]
    assert seq_outcomes == conc_outcomes
    assert RUNG_SKIPPED_LATENCY in conc_outcomes


def test_failed_rung_climbs_on():
    class FailBackend(Backend):
        name = "fail-284"

        def capabilities(self):
            return {"spec_types": ["categorical"]}

        def supports(self, spec):
            return spec.type == "categorical"

        def evaluate(self, state, spec, context=None):
            raise RuntimeError("boom")

    backends = [FailBackend(), SlowBackend("strong", 0.01, 0.95)]
    rungs = [LadderRung("fail-284", min_confidence=0.9),
             LadderRung("strong", min_confidence=0.9)]
    router = _router(backends, rungs)
    result = router.decide_concurrent({"x": 1}, SPEC, POLICY)
    assert result.backend == "strong"


def test_abstaining_rung_climbs_on():
    class AbstainBackend(Backend):
        name = "abstain-284"

        def capabilities(self):
            return {"spec_types": ["categorical"]}

        def supports(self, spec):
            return spec.type == "categorical"

        def evaluate(self, state, spec, context=None):
            from hugrgate.errors import Abstention as A
            raise A("nope", reason="test")

    backends = [AbstainBackend(), SlowBackend("strong", 0.01, 0.95)]
    rungs = [LadderRung("abstain-284", min_confidence=0.0),
             LadderRung("strong", min_confidence=0.9)]
    router = _router(backends, rungs)
    result = router.decide_concurrent({"x": 1}, SPEC, POLICY)
    assert result.backend == "strong"
    assert router.last_audit[0].outcome == RUNG_ABSTAINED


def test_max_workers_validation():
    router = _router([SlowBackend("s", 0.01, 0.95)],
                     [LadderRung("s", min_confidence=0.9)])
    with pytest.raises(SpecError):
        router.decide_concurrent({"x": 1}, SPEC, POLICY, max_workers=0)


def test_single_worker_matches_sequential_winner():
    backends = [SlowBackend("weak", 0.01, 0.3),
                SlowBackend("strong", 0.01, 0.95)]
    rungs = [LadderRung("weak", min_confidence=0.9),
             LadderRung("strong", min_confidence=0.9)]
    router = _router(backends, rungs)
    result = router.decide_concurrent({"x": 1}, SPEC, POLICY, max_workers=1)
    assert result.backend == "strong"
    assert RUNG_CANCELLED not in [e.outcome for e in router.last_audit]
