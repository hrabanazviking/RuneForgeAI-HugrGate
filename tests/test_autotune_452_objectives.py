"""Slice 452 — objective specification. Unit tests."""

from __future__ import annotations

import math

import pytest

from hugrgate.autotune.objectives import (
    Direction,
    GuardedObjective,
    LexicographicObjective,
    ObjectiveSpec,
    WeightedObjective,
    metric_from_samples,
)
from hugrgate.errors import ObjectiveError


def _spec(oid="o", fn=None, direction=Direction.MAXIMIZE,
          bounds=(0.0, 1.0), target=None):
    return ObjectiveSpec(objective_id=oid,
                         evaluate=fn or (lambda v: v.get("x", 0.0)),
                         direction=direction, bounds=bounds, target=target)


def test_empty_id_rejected():
    with pytest.raises(ObjectiveError):
        _spec(oid="")


def test_bad_bounds_rejected():
    with pytest.raises(ObjectiveError):
        _spec(bounds=(1.0, 0.0))
    with pytest.raises(ObjectiveError):
        _spec(bounds=(0.0, math.inf))


def test_non_callable_evaluate_rejected():
    with pytest.raises(ObjectiveError):
        ObjectiveSpec(objective_id="o", evaluate="nope")  # type: ignore[arg-type]


def test_evaluator_exception_wrapped():
    def _boom(values):
        raise RuntimeError("bad")

    with pytest.raises(ObjectiveError):
        _spec(fn=_boom).raw({})


def test_non_finite_result_rejected():
    with pytest.raises(ObjectiveError):
        _spec(fn=lambda v: math.nan).raw({})


def test_normalized_maximize_and_minimize():
    mx = _spec(fn=lambda v: 75.0, bounds=(50.0, 100.0))
    assert mx.normalized({}) == pytest.approx(0.5)
    mn = _spec(fn=lambda v: 75.0, bounds=(50.0, 100.0),
               direction=Direction.MINIMIZE)
    assert mn.normalized({}) == pytest.approx(0.5)
    lo = _spec(fn=lambda v: 50.0, bounds=(50.0, 100.0))
    assert lo.normalized({}) == pytest.approx(0.0)
    hi = _spec(fn=lambda v: 100.0, bounds=(50.0, 100.0),
               direction=Direction.MINIMIZE)
    assert hi.normalized({}) == pytest.approx(0.0)  # worst for minimize


def test_normalized_clamps_outside_bounds():
    s = _spec(fn=lambda v: 1000.0, bounds=(0.0, 1.0))
    assert s.normalized({}) == pytest.approx(1.0)


def test_meets_target():
    s = _spec(fn=lambda v: 0.8, target=0.7)
    assert s.meets_target({})
    assert not _spec(fn=lambda v: 0.6, target=0.7).meets_target({})
    assert _spec(fn=lambda v: 0.5).meets_target({})  # no target: vacuously true
    mn = _spec(fn=lambda v: 0.2, target=0.3, direction=Direction.MINIMIZE)
    assert mn.meets_target({})


def test_weighted_requires_parts_and_positive_weights():
    with pytest.raises(ObjectiveError):
        WeightedObjective(objective_id="w", parts=())
    with pytest.raises(ObjectiveError):
        WeightedObjective(objective_id="w",
                          parts=((_spec("a"), 0.0), (_spec("b"), 0.0)))
    with pytest.raises(ObjectiveError):
        WeightedObjective(objective_id="w",
                          parts=((_spec("a"), -1.0),))
    with pytest.raises(ObjectiveError):
        WeightedObjective(objective_id="w",
                          parts=((_spec("a"), 1.0), (_spec("a"), 1.0)))


def test_weighted_normalizes_scale():
    # raw scales differ wildly; normalization keeps the mix scale-free
    big = _spec("big", fn=lambda v: 9000.0, bounds=(0.0, 10000.0))
    small = _spec("small", fn=lambda v: 0.9, bounds=(0.0, 1.0))
    w = WeightedObjective(objective_id="w",
                          parts=((big, 1.0), (small, 1.0)))
    assert w.normalized({}) == pytest.approx(0.9)
    assert w.as_callable()({}) == pytest.approx(0.9)


def test_lexicographic_priority_order():
    a = _spec("a", fn=lambda v: v["a"])
    b = _spec("b", fn=lambda v: v["b"])
    lex = LexicographicObjective(objective_id="lex", specs=(a, b))
    # b is much better but a is slightly worse -> a decides
    assert lex.better({"a": 0.4, "b": 0.1}, {"a": 0.39, "b": 0.99})
    assert not lex.better({"a": 0.39, "b": 0.99}, {"a": 0.4, "b": 0.1})
    # tie on a within tolerance -> b decides
    assert lex.better({"a": 0.5, "b": 0.9}, {"a": 0.5, "b": 0.1})
    # exact tie -> not better
    assert not lex.better({"a": 0.5, "b": 0.5}, {"a": 0.5, "b": 0.5})


def test_lexicographic_rank_monotone():
    a = _spec("a", fn=lambda v: v["a"])
    b = _spec("b", fn=lambda v: v["b"])
    lex = LexicographicObjective(objective_id="lex", specs=(a, b))
    assert lex.rank({"a": 1.0, "b": 0.0}) > lex.rank({"a": 0.0, "b": 1.0})


def test_lexicographic_requires_specs():
    with pytest.raises(ObjectiveError):
        LexicographicObjective(objective_id="lex", specs=())


def test_guarded_infeasible_is_minus_inf():
    primary = _spec("p", fn=lambda v: 1.0)
    guard = _spec("g", fn=lambda v: v["g"])
    g = GuardedObjective(objective_id="guarded", primary=primary,
                         guards=((guard, 0.5),))
    assert g.normalized({"g": 0.9}) == pytest.approx(1.0)
    assert g.normalized({"g": 0.1}) == float("-inf")
    assert g.violations({"g": 0.1}) == ["g"]
    assert g.violations({"g": 0.9}) == []
    assert g.feasible({"g": 0.9}) and not g.feasible({"g": 0.1})


def test_metric_from_samples():
    s = metric_from_samples("acc", bounds=(0.0, 1.0))
    assert s.normalized({"metrics": {"acc": 0.8}}) == pytest.approx(0.8)
    with pytest.raises(ObjectiveError):
        s.raw({})
    with pytest.raises(ObjectiveError):
        s.raw({"metrics": {"other": 1.0}})


def test_to_dict():
    d = _spec("o", target=0.5, bounds=(0.0, 2.0)).to_dict()
    assert d == {"objective_id": "o", "direction": "maximize",
                 "bounds": [0.0, 2.0], "target": 0.5, "description": ""}
