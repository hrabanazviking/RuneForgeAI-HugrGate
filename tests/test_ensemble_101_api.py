"""Slice 101 — Ensemble API.

The Ensemble backend: member fan-out with fault isolation, a strategy
registry, and the shared metadata contract. Covers success, failure,
and boundary behavior.
"""

from __future__ import annotations

import pytest
from ensemble_fakes import (
    CAT_SPEC,
    AbstainingBackend,
    ConstantBackend,
    FailingBackend,
    ScriptedBackend,
    make_result,
)

from hugrgate import DecisionPolicy, DecisionResult, DecisionSpec, HugrGate
from hugrgate.ensemble import (
    STRATEGIES,
    Ensemble,
    EnsembleConfig,
    get_strategy,
    normalize_weights,
    register_strategy,
    soft_voting,
)
from hugrgate.ensemble.base import MemberVote, break_tie
from hugrgate.errors import BackendError, PolicyError

ALPHA = {"alpha": 0.7, "beta": 0.2, "gamma": 0.1}
BETA = {"alpha": 0.2, "beta": 0.6, "gamma": 0.2}
GAMMA = {"alpha": 0.1, "beta": 0.3, "gamma": 0.6}


def _trio():
    return [
        ConstantBackend("a", "alpha", ALPHA),
        ConstantBackend("b", "beta", BETA),
        ConstantBackend("c", "gamma", GAMMA),
    ]


# --- success -----------------------------------------------------------------

def test_soft_voting_averages_distributions():
    ens = Ensemble(_trio(), strategy="soft")
    result = ens.evaluate({"x": 1}, CAT_SPEC())
    # mean: alpha=(0.7+0.2+0.1)/3=1/3, beta=(0.2+0.6+0.3)/3=0.3667
    assert result.value == "beta"
    assert result.probability == pytest.approx(0.3666667)
    assert abs(sum(result.distribution.values()) - 1.0) < 1e-9
    assert result.distribution["beta"] == pytest.approx(result.probability)
    assert result.backend == ens.name
    assert result.latency_ms >= 0


def test_ensemble_metadata_contract():
    ens = Ensemble(_trio(), strategy="soft", name="trio")
    result = ens.evaluate({"x": 1}, CAT_SPEC())
    meta = result.metadata["ensemble"]
    assert meta["strategy"] == "soft"
    assert meta["members"] == ["a", "b", "c"]
    assert meta["usable_votes"] == 3
    assert meta["skipped_votes"] == 0
    assert len(meta["member_votes"]) == 3
    assert abs(sum(meta["weights"].values()) - 1.0) < 1e-9
    # a voted alpha and c voted gamma while the winner is beta:
    # the minority report names both dissenters, never dropping them.
    dissenters = {r["backend"]: r["value"]
                  for r in meta["minority_report"]}
    assert dissenters == {"a": "alpha", "c": "gamma"}


def test_tie_break_is_deterministic():
    m1 = ConstantBackend("m1", "alpha", {"alpha": 0.5, "beta": 0.5})
    m2 = ConstantBackend("m2", "beta", {"alpha": 0.5, "beta": 0.5})
    spec = DecisionSpec(type="categorical", options=["alpha", "beta"])
    winners = {Ensemble([m1, m2], strategy="soft").evaluate({"x": 1}, spec).value
               for _ in range(5)}
    assert winners == {"alpha"}  # earliest ballot wins the tie


def test_custom_strategy_registration():
    def always_gamma(votes, ctx):
        from hugrgate.ensemble.base import finalize_result
        usable = [v for v in votes if not v.skipped]
        dist = {"alpha": 0.0, "beta": 0.0, "gamma": 1.0}
        return finalize_result(strategy="gamma cult", spec=ctx.spec,
                               votes=votes,
                               weights={v.backend: 1.0 for v in usable},
                               value="gamma", probability=1.0,
                               distribution=dist, uncertainty=0.0,
                               winner_share=1.0)

    register_strategy("gamma-cult", always_gamma)
    try:
        ens = Ensemble(_trio(), strategy="gamma-cult")
        result = ens.evaluate({"x": 1}, CAT_SPEC())
        assert result.value == "gamma"
        assert result.metadata["ensemble"]["strategy"] == "gamma cult"
    finally:
        del STRATEGIES["gamma-cult"]


def test_integrates_with_hugrgate_decide_and_provenance():
    gate = HugrGate()
    ens = Ensemble(_trio(), strategy="soft", name="trio")
    gate.register(ens)
    result = gate.decide({"x": 1}, CAT_SPEC(), DecisionPolicy())
    assert result.accepted
    assert gate.provenance.count() == 1
    record = gate.provenance.recent(1)[0]
    assert record.backend == "trio"
    assert record.value == "beta"


def test_member_votes_introspection():
    ens = Ensemble(_trio(), strategy="soft")
    votes = ens.member_votes({"x": 1}, CAT_SPEC())
    assert [v.backend for v in votes] == ["a", "b", "c"]
    assert all(isinstance(v, MemberVote) for v in votes)
    assert not any(v.skipped for v in votes)


def test_supports_requires_one_member():
    ens = Ensemble(_trio(), strategy="soft")
    assert ens.supports(CAT_SPEC())
    numeric = DecisionSpec(type="numeric", minimum=0.0, maximum=1.0)
    assert not ens.supports(numeric)


# --- failure -----------------------------------------------------------------

def test_failing_member_is_skipped_not_fatal():
    members = [ConstantBackend("a", "alpha", ALPHA),
               FailingBackend("bad"),
               ConstantBackend("c", "gamma", GAMMA)]
    ens = Ensemble(members, strategy="soft")
    result = ens.evaluate({"x": 1}, CAT_SPEC())
    meta = result.metadata["ensemble"]
    assert meta["usable_votes"] == 2
    assert meta["skipped_votes"] == 1
    skipped = [v for v in meta["member_votes"] if v["skipped"]]
    assert len(skipped) == 1 and skipped[0]["backend"] == "bad"
    assert "backend_error" in skipped[0]["skip_reason"]


def test_all_members_failing_raises():
    ens = Ensemble([FailingBackend("x"), FailingBackend("y")],
                   strategy="soft")
    with pytest.raises(BackendError, match="only 0 of 2 members"):
        ens.evaluate({"x": 1}, CAT_SPEC())


def test_min_members_enforced():
    members = [ConstantBackend("a", "alpha", ALPHA),
               FailingBackend("bad"),
               ConstantBackend("c", "gamma", GAMMA)]
    ens = Ensemble(members, strategy="soft", min_members=3)
    with pytest.raises(BackendError, match="need >= 3"):
        ens.evaluate({"x": 1}, CAT_SPEC())


def test_abstaining_member_skipped():
    members = [ConstantBackend("a", "alpha", ALPHA),
               AbstainingBackend("shy")]
    ens = Ensemble(members, strategy="soft")
    result = ens.evaluate({"x": 1}, CAT_SPEC())
    meta = result.metadata["ensemble"]
    assert meta["usable_votes"] == 1
    assert "abstained" in meta["member_votes"][1]["skip_reason"]


def test_unsupported_spec_member_skipped():
    cat_only = ConstantBackend("cat", "alpha", ALPHA,
                               spec_types=("categorical",))
    spec = DecisionSpec(type="binary", statement="s")
    # cat_only does not support binary; ScriptedBackend supports all
    members = [cat_only,
               ScriptedBackend("flex", [make_result(
                   "true", {"true": 0.8, "false": 0.2}, "flex")])]
    ens = Ensemble(members, strategy="soft")
    result = ens.evaluate({"x": 1}, spec)
    meta = result.metadata["ensemble"]
    assert meta["usable_votes"] == 1
    assert meta["member_votes"][0]["skip_reason"] == "unsupported_spec"
    assert result.value == "true"


def test_unknown_strategy_fails_fast():
    with pytest.raises(BackendError, match="unknown ensemble strategy"):
        Ensemble(_trio(), strategy="nope")


def test_get_strategy_unknown():
    with pytest.raises(BackendError, match="unknown ensemble strategy"):
        get_strategy("nope")


# --- boundary ----------------------------------------------------------------

def test_empty_members_rejected():
    with pytest.raises(PolicyError, match="at least one member"):
        Ensemble([])


def test_duplicate_member_names_rejected():
    with pytest.raises(PolicyError, match="must be unique"):
        Ensemble([ConstantBackend("a", "alpha", ALPHA),
                  ConstantBackend("a", "beta", BETA)])


def test_non_backend_member_rejected():
    with pytest.raises(PolicyError, match="must be Backend instances"):
        Ensemble([object()])  # type: ignore[list-item]


def test_bad_weights_rejected():
    with pytest.raises(PolicyError, match="unknown member"):
        Ensemble(_trio(), strategy="soft", weights={"zzz": 1.0})
    with pytest.raises(PolicyError, match=">= 0"):
        Ensemble(_trio(), strategy="soft", weights={"a": -1.0})
    with pytest.raises(PolicyError, match="positive"):
        Ensemble(_trio(), strategy="soft",
                 weights={"a": 0.0, "b": 0.0, "c": 0.0})


def test_min_members_boundary():
    with pytest.raises(PolicyError, match="min_members must be >= 1"):
        Ensemble(_trio(), strategy="soft", min_members=0)
    with pytest.raises(PolicyError, match="min_members must be >= 1"):
        EnsembleConfig(min_members=0)


def test_register_strategy_validation():
    with pytest.raises(PolicyError, match="non-empty string"):
        register_strategy("  ", soft_voting)
    with pytest.raises(PolicyError, match="must be callable"):
        register_strategy("junk", "not-a-function")  # type: ignore[arg-type]


def test_normalize_weights_unit():
    w = normalize_weights({"a": 2.0, "b": 1.0}, ["a", "b", "c"])
    assert w == pytest.approx({"a": 2 / 3, "b": 1 / 3, "c": 0.0})
    with pytest.raises(PolicyError, match="finite"):
        normalize_weights({"a": float("nan")}, ["a"])


def test_break_tie_total_order():
    assert break_tie(["b", "a"], {"a": 1.0, "b": 1.0},
                     {"a": 1, "b": 0}) == "b"  # earliest ballot
    assert break_tie(["b", "a"], {"a": 2.0, "b": 1.0},
                     {"a": 1, "b": 0}) == "a"  # score wins
    assert break_tie(["b", "a"], {"a": 1.0, "b": 1.0},
                     {}) == "a"  # lexicographic fallback


def test_numeric_spec_rejected_by_soft():
    numeric = DecisionSpec(type="numeric", minimum=0.0, maximum=1.0)
    flex = ScriptedBackend("flex", [DecisionResult(
        value=0.5, probability=1.0, backend="flex")])
    ens = Ensemble([flex], strategy="soft")
    with pytest.raises(BackendError, match="discrete spec"):
        ens.evaluate({"x": 1}, numeric)


def test_ensemble_config_defaults():
    cfg = EnsembleConfig()
    assert cfg.weights is None and cfg.min_members == 1
    assert cfg.strategy_options == {}


def test_decide_batch_passthrough():
    ens = Ensemble(_trio(), strategy="soft")
    results = ens.decide_batch([{"x": 1}, {"x": 2}], CAT_SPEC())
    assert [r.value for r in results] == ["beta", "beta"]
