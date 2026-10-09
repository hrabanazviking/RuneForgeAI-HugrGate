"""Slice 143 — router shadow mode tests."""

from __future__ import annotations

import pytest

from hugrgate.adaptive.shadow import RouterShadowMode, ShadowDivergence
from hugrgate.adaptive.telemetry import TelemetryStore
from hugrgate.errors import SpecError

CANDS = ["a", "b"]
PROPS = {"a": 0.6, "b": 0.4}
FEATS = {"x0": 1.0}


def shadow_mode(**kw):
    return RouterShadowMode(TelemetryStore(), **kw)


# --- success ---------------------------------------------------------------

def test_shadow_records_do_not_affect_served_traffic():
    sm = shadow_mode()
    rid = sm.record_shadow(features=FEATS, candidates=CANDS,
                           propensities=PROPS, shadow_choice="b",
                           served_choice="a")
    assert rid is not None
    event = sm.store.get(rid)
    assert event.shadow is True
    assert event.chosen == "b"  # shadow's choice, logged...
    assert event.metadata["served_choice"] == "a"  # ...served kept separate
    assert event.metadata["diverged"] is True

def test_shadow_events_excluded_from_training_sets():
    from hugrgate.adaptive.offline import OfflinePolicyLearning
    sm = shadow_mode()
    sm.record_shadow(features=FEATS, candidates=CANDS, propensities=PROPS,
                     shadow_choice="a", served_choice="a")
    learner = OfflinePolicyLearning(["x0"])
    with pytest.raises(SpecError):  # zero usable events: shadow skipped
        learner.fit(sm.store.events())
    # And a labeled shadow event is still skipped (shadow check first).
    sm.store.attach_outcome(next(iter(sm.store.events())).request_id,
                            {"quality": 0.9})
    with pytest.raises(SpecError):
        learner.fit(sm.store.events())

def test_divergence_report_counts_disagreement():
    sm = shadow_mode()
    sm.record_shadow(features=FEATS, candidates=CANDS, propensities=PROPS,
                     shadow_choice="a", served_choice="a")
    sm.record_shadow(features=FEATS, candidates=CANDS, propensities=PROPS,
                     shadow_choice="b", served_choice="a")
    sm.record_shadow(features=FEATS, candidates=CANDS, propensities=PROPS,
                     shadow_choice="b", served_choice="b")
    report = sm.divergence_report()
    assert isinstance(report, ShadowDivergence)
    assert report.n_shadow == 3
    assert report.n_diverged == 1
    assert report.divergence_rate == pytest.approx(1 / 3)
    assert report.per_arm_agreement["a"] == {"a": 1, "b": 1}
    assert report.to_dict()["divergence_rate"] == pytest.approx(1 / 3)

def test_empty_divergence_report():
    report = shadow_mode().divergence_report()
    assert report.n_shadow == 0 and report.divergence_rate == 0.0

def test_disabled_shadow_mode_logs_nothing():
    sm = shadow_mode(enabled=False)
    assert sm.record_shadow(features=FEATS, candidates=CANDS,
                            propensities=PROPS, shadow_choice="b",
                            served_choice="a") is None
    assert len(sm.store) == 0

def test_shadow_choices_for_filters_by_served():
    sm = shadow_mode()
    sm.record_shadow(features=FEATS, candidates=CANDS, propensities=PROPS,
                     shadow_choice="b", served_choice="a")
    sm.record_shadow(features=FEATS, candidates=CANDS, propensities=PROPS,
                     shadow_choice="a", served_choice="b")
    assert sm.shadow_choices_for("a") == ["b"]
    assert sm.shadow_choices_for("b") == ["a"]

def test_custom_policy_version_tag():
    sm = shadow_mode(policy_version="candidate-v2")
    rid = sm.record_shadow(features=FEATS, candidates=CANDS,
                           propensities=PROPS, shadow_choice="a",
                           served_choice="a")
    assert sm.store.get(rid).policy_version == "candidate-v2"

# --- failure ---------------------------------------------------------------

def test_shadow_choice_must_be_a_candidate():
    sm = shadow_mode()
    with pytest.raises(SpecError):
        sm.record_shadow(features=FEATS, candidates=CANDS,
                         propensities=PROPS, shadow_choice="zzz",
                         served_choice="a")
    with pytest.raises(SpecError):
        sm.record_shadow(features=FEATS, candidates=CANDS,
                         propensities=PROPS, shadow_choice="a",
                         served_choice="zzz")

def test_bad_propensity_sum_rejected():
    sm = shadow_mode()
    with pytest.raises(SpecError):
        sm.record_shadow(features=FEATS, candidates=CANDS,
                         propensities={"a": 0.5, "b": 0.2},
                         shadow_choice="a", served_choice="a")

def test_constructor_validates_store():
    with pytest.raises(SpecError):
        RouterShadowMode("not-a-store")
