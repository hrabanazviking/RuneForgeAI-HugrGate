"""Slice 125 — Ensemble release gate.

The checklist with teeth: benchmark thresholds, diversity floor,
no correlated cliques, adversarial cleanliness, and caller evidence
combine into one PASS/FAIL verdict.
"""

from __future__ import annotations

import pytest

from hugrgate.ensemble import (
    AdversarialCase,
    DropoutBackend,
    AbstainBackend,
    Ensemble,
    ReleaseGate,
    adversarial_clean,
    benchmark_thresholds,
    diversity_floor,
    evidence_check,
    no_correlated_cliques,
)
from hugrgate.errors import PolicyError
from ensemble_fakes import CAT_SPEC, ConstantBackend

ALPHA = {"alpha": 0.7, "beta": 0.2, "gamma": 0.1}
BETA = {"alpha": 0.2, "beta": 0.6, "gamma": 0.2}


def _healthy_factory():
    return [ConstantBackend("a", "alpha", ALPHA),
            ConstantBackend("b", "alpha", ALPHA),
            ConstantBackend("c", "beta", BETA)]


def _labeled(n=8, label="alpha"):
    return [{"x": i} for i in range(n)], [label] * n


def _dropout_case():
    members = [DropoutBackend(ConstantBackend("a", "alpha", ALPHA),
                              every=2),
               ConstantBackend("b", "alpha", ALPHA),
               ConstantBackend("c", "alpha", ALPHA)]
    states, _ = _labeled(4)
    return AdversarialCase("dropout",
                           Ensemble(members, strategy="hard"),
                           states, CAT_SPEC())


def _full_gate(factory=_healthy_factory, label="alpha"):
    states, labels = _labeled(8, label)
    gate = ReleaseGate("council-1.0")
    gate.add("benchmarks", benchmark_thresholds(
        factory, states, CAT_SPEC(), labels, strategy="soft",
        min_accuracy=0.5, max_ece=0.5))
    gate.add("diversity", diversity_floor(
        factory, states, CAT_SPEC(), min_disagreement_rate=0.1))
    gate.add("cliques", no_correlated_cliques(
        factory, states, CAT_SPEC(), labels))
    gate.add("adversarial", adversarial_clean([_dropout_case()]))
    name, check = evidence_check("tests", True, "278 green")
    gate.add(name, check)
    return gate


# --- success -----------------------------------------------------------------

def test_full_gate_passes_for_healthy_council():
    verdict = _full_gate().run()
    assert verdict.passed is True
    assert verdict.failures == []
    assert len(verdict.checks) == 5
    text = verdict.summary()
    assert "PASS" in text and "5/5 checks" in text
    assert "[PASS] benchmarks" in text
    d = verdict.to_dict()
    assert d["passed"] is True and d["gate"] == "council-1.0"


def test_may_refuse_allows_honest_refusal():
    members = [AbstainBackend(ConstantBackend("a", "alpha", ALPHA),
                              every=1),
               AbstainBackend(ConstantBackend("b", "alpha", ALPHA),
                              every=1)]
    states, _ = _labeled(2)
    wave = AdversarialCase("abstention-wave",
                           Ensemble(members, strategy="hard",
                                    min_members=1),
                           states, CAT_SPEC())
    gate = ReleaseGate("g")
    gate.add("adversarial",
             adversarial_clean([wave], may_refuse=("abstention-wave",)))
    assert gate.run().passed is True


# --- failure -----------------------------------------------------------------

def test_benchmark_failure_blocks_release():
    verdict = _full_gate(label="beta").run()  # majority is wrong
    assert verdict.passed is False
    names = [c.name for c in verdict.failures]
    assert "benchmarks" in names
    detail = next(c.detail for c in verdict.failures
                  if c.name == "benchmarks")
    assert "accuracy 0.000 < 0.5" in detail
    assert "FAIL" in verdict.summary()


def test_diversity_failure_blocks_release():
    def identical():
        return [ConstantBackend("a", "alpha", ALPHA),
                ConstantBackend("b", "alpha", ALPHA)]
    verdict = _full_gate(factory=identical).run()
    assert verdict.passed is False
    assert [c.name for c in verdict.failures] == ["diversity"]


def test_clique_failure_blocks_release():
    from hugrgate.result import DecisionResult
    from ensemble_fakes import ScriptedBackend

    def _res(value, dist):
        return DecisionResult(value=value, probability=dist[value],
                              distribution=dict(dist))

    # a and b err together on states 0-3, right together on 4-7
    wrong_then_right = ([_res("beta", BETA)] * 4
                        + [_res("alpha", ALPHA)] * 4)

    def cloned():
        return [ScriptedBackend("a", list(wrong_then_right)),
                ScriptedBackend("b", list(wrong_then_right)),
                ScriptedBackend("c", [_res("alpha", ALPHA)] * 8)]
    verdict = _full_gate(factory=cloned).run()
    assert verdict.passed is False
    assert "cliques" in [c.name for c in verdict.failures]
    detail = next(c.detail for c in verdict.failures
                  if c.name == "cliques")
    assert "a" in detail and "b" in detail


def test_adversarial_failure_blocks_release():
    members = [DropoutBackend(ConstantBackend("a", "alpha", ALPHA),
                              every=1)]
    states, _ = _labeled(2)
    case = AdversarialCase("total-dropout",
                           Ensemble(members, strategy="hard",
                                    min_members=1),
                           states, CAT_SPEC())
    gate = ReleaseGate("g")
    gate.add("adversarial", adversarial_clean([case]))
    verdict = gate.run()
    assert verdict.passed is False
    assert "decided 0/2" in verdict.failures[0].detail


def test_missing_evidence_blocks_release():
    gate = ReleaseGate("g")
    name, check = evidence_check("docs", False, "notes missing")
    gate.add(name, check)
    verdict = gate.run()
    assert verdict.passed is False
    assert verdict.failures[0].detail == "notes missing"


def test_raising_check_fails_gracefully():
    gate = ReleaseGate("g")
    gate.add("boom", lambda: 1 / 0)  # noqa: B018
    name, check = evidence_check("ok", True)
    gate.add(name, check)
    verdict = gate.run()
    assert verdict.passed is False
    assert len(verdict.checks) == 2  # gate ran everything
    assert "ZeroDivisionError" in verdict.failures[0].detail


def test_empty_gate_does_not_pass():
    assert ReleaseGate("g").run().passed is False


# --- failure: construction ----------------------------------------------------

def test_gate_validation():
    with pytest.raises(PolicyError, match="needs a name"):
        ReleaseGate("")
    gate = ReleaseGate("g")
    with pytest.raises(PolicyError, match="must be callable"):
        gate.add("x", "not-a-check")
    gate.add("x", lambda: (True, ""))
    with pytest.raises(PolicyError, match="duplicate check name"):
        gate.add("x", lambda: (True, ""))


def test_check_factory_validation():
    states, labels = _labeled(4)
    with pytest.raises(PolicyError, match="min_accuracy"):
        benchmark_thresholds(_healthy_factory, states, CAT_SPEC(),
                             labels, min_accuracy=2.0)
    with pytest.raises(PolicyError, match="max_brier"):
        benchmark_thresholds(_healthy_factory, states, CAT_SPEC(),
                             labels, max_brier=3.0)
    with pytest.raises(PolicyError, match="min_disagreement_rate"):
        diversity_floor(_healthy_factory, states, CAT_SPEC(),
                        min_disagreement_rate=-0.1)


# --- boundary -----------------------------------------------------------------

def test_thresholds_at_exact_boundary_pass():
    states, labels = _labeled(4)
    gate = ReleaseGate("g")
    # accuracy exactly 1.0 meets a 1.0 floor
    gate.add("benchmarks", benchmark_thresholds(
        _healthy_factory, states, CAT_SPEC(), labels,
        strategy="hard", min_accuracy=1.0, max_ece=1.0))
    assert gate.run().passed is True
