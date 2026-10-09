"""Slice 460 — ensemble-weight tuner. Unit tests."""

from __future__ import annotations

import pytest

from hugrgate.autotune.controller import (
    ConfigStore,
    Mode,
    OptimizationController,
    TunableParameter,
    TuningContext,
)
from hugrgate.autotune.tuners._base import seeded_rng
from hugrgate.autotune.tuners.weights import (
    EnsembleWeightTuner,
    mean_log_likelihood,
)
from hugrgate.errors import TunerError

MEMBERS = ["sharp", "dull", "noise"]


def _ctx(store, seed=5):
    return TuningContext(store=store, objectives={}, constraints=[],
                         seed=seed, mode=Mode.OFFLINE, run_id="r")


def _store(weights=(1 / 3, 1 / 3, 1 / 3)):
    s = ConfigStore()
    for m, w in zip(MEMBERS, weights, strict=True):
        s.register(TunableParameter(name=f"ensemble.weight.{m}",
                                    dtype="float", default=w,
                                    lo=0.0, hi=1.0))
    return s


def _votes_labels(seed=55, n=300):
    """'sharp' is near-perfect, 'dull' is mediocre, 'noise' is random."""
    rng = seeded_rng(seed)
    votes, labels = [], []
    for _ in range(n):
        y = rng.randrange(2)
        labels.append(y)
        sharp = [0.05, 0.05]
        sharp[y] = 0.95
        dull = [0.4, 0.4]
        dull[y] = 0.6
        nz = [rng.random(), rng.random()]
        tot = sum(nz)
        votes.append([sharp, dull, [x / tot for x in nz]])
    return votes, labels


def _tuner(**kw):
    votes, labels = _votes_labels()
    base = dict(objective_id="ll", members=list(MEMBERS), votes=votes,
                labels=labels, seed=1)
    base.update(kw)
    return EnsembleWeightTuner(**base)


def test_mean_log_likelihood():
    votes = [[[0.8, 0.2]], [[0.3, 0.7]]]
    ll = mean_log_likelihood(votes, [0, 1], [1.0])
    import math
    assert ll == pytest.approx((math.log(0.8) + math.log(0.7)) / 2)


def test_tuner_concentrates_on_best_member():
    t = _tuner()
    prop = t.tune(_ctx(_store()))
    assert prop is not None
    w = prop.evidence["tuned"]["weights"]
    assert w["sharp"] > 0.9
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert all(v >= 0 for v in w.values())
    assert prop.evidence["tuned"]["mean_log_likelihood"] > \
        prop.evidence["baseline"]["mean_log_likelihood"]


def test_tuner_beats_uniform_meaningfully():
    t = _tuner()
    prop = t.tune(_ctx(_store()))
    assert prop is not None
    assert prop.delta > 0.1  # uniform is far from optimal here


def test_tuner_deterministic():
    p1 = _tuner().tune(_ctx(_store(), seed=3))
    p2 = _tuner().tune(_ctx(_store(), seed=3))
    assert p1 is not None and p2 is not None
    assert p1.changes == p2.changes


def test_silent_when_already_optimal():
    t = _tuner()
    first = t.tune(_ctx(_store()))
    assert first is not None
    s = _store()
    s.apply(first.changes)
    assert _tuner(min_delta=1e-9).tune(_ctx(s)) is None


def test_bad_specs_rejected():
    votes, labels = _votes_labels()
    with pytest.raises(TunerError):
        EnsembleWeightTuner(objective_id="o", members=["a"],
                            votes=votes, labels=labels)
    with pytest.raises(TunerError):
        EnsembleWeightTuner(objective_id="o", members=["a", "b"],
                            votes=votes, labels=labels)  # 3 members in votes
    with pytest.raises(TunerError):
        EnsembleWeightTuner(objective_id="o", members=list(MEMBERS),
                            votes=votes, labels=labels[:-1])
    with pytest.raises(TunerError):
        EnsembleWeightTuner(objective_id="", members=list(MEMBERS),
                            votes=votes, labels=labels)
    bad = [[[1.0, -0.5]]]
    with pytest.raises(TunerError):
        EnsembleWeightTuner(objective_id="o", members=["a", "b"],
                            votes=bad, labels=[0])


def test_end_to_end_offline():
    store = _store()
    c = OptimizationController(store=store)
    c.register_objective("ll", lambda values: 0.0)
    c.register_tuner(_tuner())
    run = c.run_cycle(mode=Mode.OFFLINE, seed=4)
    assert run.results[0].proposal_id != ""
    assert store.get("ensemble.weight.sharp") == pytest.approx(1 / 3)
