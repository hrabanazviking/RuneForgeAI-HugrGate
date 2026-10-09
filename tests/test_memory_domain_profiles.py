"""Slice 314 — Domain history profiles: per-domain aggregates."""

from __future__ import annotations

import time

import pytest

from hugrgate.memory import (
    DecisionHistory,
    DomainProfile,
    Outcome,
    domain_for,
    domain_profiles,
)
from hugrgate.provenance import DecisionRecord


def _record(**kw) -> DecisionRecord:
    base = dict(request_hash="h" * 16, spec={"type": "binary"},
                backend="local", model="m1", value=True, probability=0.8)
    base.update(kw)
    return DecisionRecord(**base)


def _spec_with_domain(domain: str) -> dict:
    return {"type": "binary", "metadata": {"domain": domain}}


def test_domain_for_prefers_spec_metadata():
    hist = DecisionHistory()
    episode = hist.record(_record(spec=_spec_with_domain("trading")))
    assert domain_for(hist.get(episode.episode_id)) == "trading"


def test_domain_for_falls_back_to_record_metadata():
    hist = DecisionHistory()
    record = _record()
    record.metadata["domain"] = "ops"
    episode = hist.record(record)
    assert domain_for(hist.get(episode.episode_id)) == "ops"


def test_domain_for_defaults():
    hist = DecisionHistory()
    episode = hist.record(_record())
    assert domain_for(hist.get(episode.episode_id)) == "default"


def test_domain_profiles():
    hist = DecisionHistory()
    for kind in ("success", "failure"):
        episode = hist.record(_record(spec=_spec_with_domain("trading"),
                                      backend="local", probability=0.9))
        hist.attach_outcome(episode.episode_id, Outcome(kind=kind))
    hist.record(_record(spec=_spec_with_domain("trading"), backend="remote",
                        probability=0.5))
    hist.record(_record(backend="local"))  # default domain
    profiles = domain_profiles(hist, now=time.time())
    assert set(profiles) == {"trading", "default"}
    trading = profiles["trading"]
    assert isinstance(trading, DomainProfile)
    assert trading.decision_count == 3
    assert trading.accepted_rate == 1.0
    assert trading.outcome_counts == {"success": 1, "failure": 1}
    assert trading.success_rate == pytest.approx(0.5)
    assert trading.top_backends[0] == ("local", 2)
    assert trading.spec_types == ("binary",)
    assert trading.mean_probability == pytest.approx((0.9 + 0.9 + 0.5) / 3)
    assert trading.activity == pytest.approx(3.0, abs=0.05)
    assert trading.first_seen <= trading.last_seen
    default = profiles["default"]
    assert default.decision_count == 1
    assert default.success_rate is None


def test_activity_decays():
    hist = DecisionHistory()
    old = hist.record(_record(spec=_spec_with_domain("trading")))
    hist._by_id[old.episode_id].recorded_at -= 10 * 86400
    profiles = domain_profiles(hist, half_life_seconds=86400.0,
                               now=time.time())
    assert profiles["trading"].activity == pytest.approx(2 ** -10,
                                                         abs=1e-6)


def test_top_backends_capped_at_three():
    hist = DecisionHistory()
    for i in range(5):
        hist.record(_record(spec=_spec_with_domain("d"),
                            backend=f"b{i}"))
    profiles = domain_profiles(hist, now=time.time())
    assert len(profiles["d"].top_backends) == 3


def test_empty_history():
    assert domain_profiles(DecisionHistory(), now=1.0) == {}


def test_limit_validation():
    hist = DecisionHistory()
    hist.record(_record())
    with pytest.raises(ValueError):
        domain_profiles(hist, limit=0, now=time.time())


def test_to_dict():
    hist = DecisionHistory()
    hist.record(_record(spec=_spec_with_domain("trading")))
    d = domain_profiles(hist, now=time.time())["trading"].to_dict()
    assert d["domain"] == "trading"
    assert d["decision_count"] == 1
    assert d["top_backends"] == [["local", 1]]
