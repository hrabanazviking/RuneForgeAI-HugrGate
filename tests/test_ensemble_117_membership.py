"""Slice 117 — Dynamic ensemble membership.

Members earn their seats: sustained poor reliability retires them,
strong standby performance promotes them, and every transition is
logged for provenance.
"""

from __future__ import annotations

import pytest

from hugrgate.ensemble import (
    STATUS_ACTIVE,
    STATUS_RETIRED,
    STATUS_STANDBY,
    Ensemble,
    MembershipManager,
)
from hugrgate.errors import PolicyError
from ensemble_fakes import CAT_SPEC, ConstantBackend

ALPHA = {"alpha": 0.7, "beta": 0.2, "gamma": 0.1}


def _members():
    return [ConstantBackend("a", "alpha", ALPHA),
            ConstantBackend("b", "alpha", ALPHA),
            ConstantBackend("c", "alpha", ALPHA)]


# --- success -----------------------------------------------------------------

def test_all_members_start_active():
    mgr = MembershipManager(_members())
    assert mgr.active_members() == ["a", "b", "c"]
    assert mgr.status("a") == STATUS_ACTIVE


def test_sustained_failure_retires_member():
    mgr = MembershipManager(_members(), retire_below=0.4,
                            min_observations=10)
    for _ in range(10):
        mgr.observe("c", False)   # reliability -> 1/12 ≈ 0.083
        mgr.observe("a", True)
    assert mgr.status("c") == STATUS_RETIRED
    assert mgr.active_members() == ["a", "b"]
    kinds = [e["kind"] for e in mgr.events()]
    assert "retired" in kinds
    event = next(e for e in mgr.events() if e["kind"] == "retired")
    assert event["member"] == "c"
    assert event["seq"] >= 1


def test_no_retirement_before_enough_evidence():
    mgr = MembershipManager(_members(), min_observations=10)
    for _ in range(9):
        mgr.observe("c", False)
    assert mgr.status("c") == STATUS_ACTIVE  # only 9 observations


def test_min_active_is_never_breached():
    mgr = MembershipManager(_members(), min_observations=5,
                            min_active=1)
    for _ in range(5):
        for m in ("a", "b", "c"):
            mgr.observe(m, False)
    # all terrible, but one must stay
    assert len(mgr.active_members()) == 1
    assert any(e["kind"] == "retire_blocked" for e in mgr.events())


def test_standby_promotion_on_evidence():
    mgr = MembershipManager(_members(), initial_standby=["c"],
                            promote_above=0.65, min_observations=10)
    assert mgr.status("c") == STATUS_STANDBY
    for _ in range(10):
        mgr.observe("c", True)   # reliability -> 11/12 ≈ 0.917
    assert mgr.status("c") == STATUS_ACTIVE
    assert any(e["kind"] == "promoted" for e in mgr.events())


def test_standby_not_promoted_without_evidence():
    mgr = MembershipManager(_members(), initial_standby=["c"],
                            min_observations=10)
    for _ in range(9):
        mgr.observe("c", True)
    assert mgr.status("c") == STATUS_STANDBY


def test_manual_transitions_and_event_log():
    mgr = MembershipManager(_members())
    mgr.to_standby("b", reason="maintenance")
    assert mgr.status("b") == STATUS_STANDBY
    mgr.activate("b")
    assert mgr.status("b") == STATUS_ACTIVE
    mgr.retire("c", reason="decommissioned")
    assert mgr.status("c") == STATUS_RETIRED
    events = mgr.events()
    assert [e["kind"] for e in events] == ["standby", "activated",
                                          "retired"]
    assert events[0]["detail"] == "maintenance"
    assert [e["seq"] for e in events] == [1, 2, 3]


def test_build_ensemble_uses_active_members_only():
    mgr = MembershipManager(_members())
    mgr.retire("c")
    ens = mgr.build_ensemble(strategy="hard")
    assert isinstance(ens, Ensemble)
    assert [m.name for m in ens.members] == ["a", "b"]
    result = ens.evaluate({"x": 1}, CAT_SPEC())
    assert result.value == "alpha"


def test_to_dict():
    mgr = MembershipManager(_members())
    mgr.observe("a", True)
    d = mgr.to_dict()
    assert d["statuses"] == {"a": "active", "b": "active",
                             "c": "active"}
    assert d["reliabilities"]["a"] == pytest.approx(2 / 3)


# --- failure -----------------------------------------------------------------

def test_validation():
    with pytest.raises(PolicyError, match="needs members"):
        MembershipManager([])
    with pytest.raises(PolicyError, match="unique"):
        MembershipManager([ConstantBackend("a", "alpha", ALPHA),
                           ConstantBackend("a", "alpha", ALPHA)])
    with pytest.raises(PolicyError, match="in \\(0, 1\\)"):
        MembershipManager(_members(), retire_below=0.0)
    with pytest.raises(PolicyError, match="retire_below must be <"):
        MembershipManager(_members(), retire_below=0.7,
                          promote_above=0.6)
    with pytest.raises(PolicyError, match="min_observations"):
        MembershipManager(_members(), min_observations=0)
    with pytest.raises(PolicyError, match="min_active"):
        MembershipManager(_members(), min_active=0)
    with pytest.raises(PolicyError, match="unknown member"):
        MembershipManager(_members()).observe("zzz", True)
    with pytest.raises(PolicyError, match="unknown member"):
        MembershipManager(_members()).status("zzz")


def test_build_ensemble_with_no_actives_rejected():
    mgr = MembershipManager(_members())
    for m in ("a", "b", "c"):
        mgr.retire(m)
    with pytest.raises(PolicyError, match="no active members"):
        mgr.build_ensemble()


# --- boundary -----------------------------------------------------------------

def test_retirement_boundary_exact():
    # reliability exactly at retire_below does NOT retire (strict <)
    mgr = MembershipManager(_members(), retire_below=0.5,
                            min_observations=2, smoothing=1.0)
    # 1 correct of 2 -> (1+1)/(2+2) = 0.5 == bar -> stays
    mgr.observe("c", True)
    mgr.observe("c", False)
    assert mgr.status("c") == STATUS_ACTIVE
    mgr.observe("c", False)  # (1+1)/(3+2) = 0.4 < 0.5 -> retired
    assert mgr.status("c") == STATUS_RETIRED
