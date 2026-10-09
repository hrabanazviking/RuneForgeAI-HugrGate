"""Slice 307 — Contextual memory policies: record/drop/redact rules."""

from __future__ import annotations

import pytest

from hugrgate.memory import (
    DecisionHistory,
    MemoryPolicy,
    MemoryRule,
    drop_backend,
    drop_forbidden,
    drop_unaccepted,
    record_only_backend,
    redact_above,
)
from hugrgate.provenance import DecisionRecord


def _record(**kw) -> DecisionRecord:
    base = dict(request_hash="h" * 16, spec={"type": "binary"},
                backend="local", model="m1", value=True, probability=0.8,
                metadata={"state_keys": ["q"]})
    base.update(kw)
    return DecisionRecord(**base)


def test_default_policy_records():
    hist = DecisionHistory()
    episode = hist.record(_record(), policy=MemoryPolicy())
    assert episode is not None
    assert hist.count() == 1


def test_no_policy_records():
    hist = DecisionHistory()
    assert hist.record(_record()) is not None


def test_drop_forbidden():
    hist = DecisionHistory()
    policy = MemoryPolicy([drop_forbidden()])
    assert hist.record(_record(), privacy_class="forbidden",
                       policy=policy) is None
    assert hist.count() == 0
    kept = hist.record(_record(), privacy_class="standard", policy=policy)
    assert kept is not None
    assert hist.count() == 1


def test_redact_above_strips_metadata():
    hist = DecisionHistory()
    policy = MemoryPolicy([redact_above("sensitive")])
    episode = hist.record(_record(), privacy_class="strict", policy=policy)
    assert episode is not None
    assert episode.record.metadata == {}
    assert episode.annotations["redacted"] is True
    assert episode.annotations["redact_rule"] == "redact-above-sensitive"
    # below the threshold: untouched
    plain = hist.record(_record(), privacy_class="standard", policy=policy)
    assert plain is not None
    assert plain.record.metadata == {"state_keys": ["q"]}
    assert "redacted" not in plain.annotations


def test_redact_does_not_mutate_caller_record():
    hist = DecisionHistory()
    policy = MemoryPolicy([redact_above("standard")])
    rec = _record()
    hist.record(rec, policy=policy)
    assert rec.metadata == {"state_keys": ["q"]}


def test_drop_backend():
    hist = DecisionHistory()
    policy = MemoryPolicy([drop_backend("remote")])
    assert hist.record(_record(backend="remote"), policy=policy) is None
    assert hist.record(_record(backend="local"), policy=policy) is not None


def test_record_only_backend():
    hist = DecisionHistory()
    policy = MemoryPolicy([record_only_backend("local")])
    assert hist.record(_record(backend="remote"), policy=policy) is None
    assert hist.record(_record(backend="local"), policy=policy) is not None


def test_drop_unaccepted():
    hist = DecisionHistory()
    policy = MemoryPolicy([drop_unaccepted()])
    assert hist.record(_record(accepted=False), policy=policy) is None
    assert hist.record(_record(accepted=True), policy=policy) is not None


def test_first_match_wins():
    hist = DecisionHistory()
    policy = MemoryPolicy([
        drop_backend("local"),
        redact_above("public"),  # would also fire for standard
    ])
    # drop fires first even though redact would also match
    assert hist.record(_record(backend="local"), privacy_class="standard",
                       policy=policy) is None


def test_decide_reports_rule_and_reason():
    policy = MemoryPolicy([drop_forbidden()])
    verdict = policy.decide(_record(), "forbidden")
    assert verdict.action == "drop"
    assert verdict.rule == "drop-forbidden"
    assert verdict.reason
    default = policy.decide(_record(), "public")
    assert default.action == "record"
    assert default.rule == "default"


def test_rule_validation():
    with pytest.raises(ValueError):
        MemoryRule(name="x", predicate=lambda r, c, t: True, action="burn")
    with pytest.raises(ValueError):
        MemoryRule(name="", predicate=lambda r, c, t: True, action="drop")
    with pytest.raises(ValueError):
        MemoryPolicy([
            MemoryRule(name="dup", predicate=lambda r, c, t: True,
                       action="drop"),
            MemoryRule(name="dup", predicate=lambda r, c, t: False,
                       action="record"),
        ])


def test_custom_rule():
    hist = DecisionHistory()
    slow = MemoryRule(
        name="drop-slow",
        predicate=lambda record, cls, tags: record.latency_ms > 1000,
        action="drop",
        reason="too slow to matter",
    )
    policy = MemoryPolicy([slow])
    assert hist.record(_record(latency_ms=5000.0), policy=policy) is None
    assert hist.record(_record(latency_ms=5.0), policy=policy) is not None


def test_explain():
    policy = MemoryPolicy([drop_forbidden(), drop_unaccepted()])
    text = policy.explain()
    assert "drop-forbidden" in text and "drop-unaccepted" in text
    assert "default: [record]" in text
    assert MemoryPolicy().explain() == "MemoryPolicy(default=record)"


def test_policy_applies_to_import():
    # import_from_provenance does not take a policy: documents that bulk
    # import is intentionally unfiltered (operator's explicit choice).
    from hugrgate.provenance import ProvenanceStore
    store = ProvenanceStore()
    store.append(_record())
    hist = DecisionHistory()
    assert hist.import_from_provenance(store) == 1
