"""Slice 315 — Memory privacy controls, incl. adversarial negatives."""

from __future__ import annotations

import pytest

from hugrgate.errors import MemoryAccessDenied
from hugrgate.memory import (
    DecisionHistory,
    GuardedHistory,
    MemoryAccessPolicy,
    MemoryQuery,
    Outcome,
    RolePermission,
)
from hugrgate.provenance import DecisionRecord


def _record(**kw) -> DecisionRecord:
    base = dict(request_hash="h" * 16, spec={"type": "binary"},
                backend="local", model="m1", value=True, probability=0.8,
                metadata={"state_keys": ["secret_q"]})
    base.update(kw)
    return DecisionRecord(**base)


def _history() -> DecisionHistory:
    hist = DecisionHistory()
    hist.record(_record(), privacy_class="public", tags=["t"])
    hist.record(_record(), privacy_class="sensitive", tags=["t"])
    hist.record(_record(), privacy_class="strict", tags=["t"])
    hist.record(_record(), privacy_class="forbidden", tags=["t"])
    return hist


def test_owner_sees_everything():
    hist = _history()
    guarded = GuardedHistory(hist, "owner")
    assert guarded.count() == 4
    episode = guarded.recent(1)[0]
    assert episode.privacy_class == "forbidden"
    assert episode.record.metadata == {"state_keys": ["secret_q"]}
    assert episode.tags == ("t",)


def test_analyst_scope_and_redaction():
    hist = _history()
    guarded = GuardedHistory(hist, "analyst")
    assert guarded.count() == 2  # public + sensitive
    sensitive = guarded.find(MemoryQuery(privacy_classes={"sensitive"}))[0]
    assert sensitive.record.metadata == {}
    assert sensitive.tags == ()
    public = guarded.find(MemoryQuery(privacy_classes={"public"}))[0]
    assert public.record.metadata == {"state_keys": ["secret_q"]}


def test_auditor_scope_and_redaction():
    hist = _history()
    guarded = GuardedHistory(hist, "auditor")
    assert guarded.count() == 1  # public only
    public = guarded.get(guarded.recent(1)[0].episode_id)
    # public is below the auditor's redact_at="standard": fully visible
    assert public.record.metadata == {"state_keys": ["secret_q"]}
    assert public.record.backend == "local"  # aggregates survive
    assert public.tags == ("t",)


def test_auditor_sees_redacted_standard():
    hist = DecisionHistory()
    episode = hist.record(_record(), privacy_class="standard")
    guarded = GuardedHistory(hist, "auditor")
    view = guarded.get(episode.episode_id)
    assert view.record.metadata == {}
    assert view.tags == ()
    assert view.record.backend == "local"


def test_denied_read_raises_never_silent():
    hist = _history()
    analyst = GuardedHistory(hist, "analyst")
    strict_id = hist.find(MemoryQuery(privacy_classes={"strict"}))[
        0].episode_id
    with pytest.raises(MemoryAccessDenied):
        analyst.get(strict_id)
    auditor = GuardedHistory(hist, "auditor")
    sensitive_id = hist.find(MemoryQuery(privacy_classes={"sensitive"}))[
        0].episode_id
    with pytest.raises(MemoryAccessDenied):
        auditor.get(sensitive_id)


def test_writes_denied_for_non_owners():
    hist = _history()
    episode_id = hist.recent(1)[0].episode_id
    for role in ("analyst", "auditor"):
        guarded = GuardedHistory(hist, role)
        with pytest.raises(MemoryAccessDenied):
            guarded.record(_record())
        with pytest.raises(MemoryAccessDenied):
            guarded.attach_outcome(episode_id, Outcome(kind="success"))
        with pytest.raises(MemoryAccessDenied):
            guarded.clear()
    assert hist.count() == 4  # nothing was written through


def test_owner_writes_allowed():
    hist = DecisionHistory()
    guarded = GuardedHistory(hist, "owner")
    episode = guarded.record(_record())
    assert episode is not None
    guarded.attach_outcome(episode.episode_id, Outcome(kind="success"))
    assert guarded.get(episode.episode_id).outcome is not None


def test_unknown_role_rejected():
    hist = _history()
    with pytest.raises(ValueError):
        GuardedHistory(hist, "superuser")
    policy = MemoryAccessPolicy()
    with pytest.raises(ValueError):
        policy.may_read("superuser", "public")


def test_redacted_view_cannot_leak_or_mutate_store():
    hist = _history()
    analyst = GuardedHistory(hist, "analyst")
    view = analyst.find(MemoryQuery(privacy_classes={"sensitive"}))[0]
    view.record.metadata["injected"] = True  # mutate the view
    fresh = hist.find(MemoryQuery(privacy_classes={"sensitive"}))[0]
    assert fresh.record.metadata == {"state_keys": ["secret_q"]}


def test_custom_policy():
    policy = MemoryAccessPolicy({
        "owner": RolePermission(max_class="forbidden", redact_at=None,
                               write=True),
        "analyst": RolePermission(max_class="public", redact_at=None,
                                  write=False),
        "auditor": RolePermission(max_class="public", redact_at=None,
                                  write=False),
    })
    hist = _history()
    guarded = GuardedHistory(hist, "analyst", policy=policy)
    assert guarded.count() == 1
    assert policy.may_read("analyst", "public")
    assert not policy.may_read("analyst", "standard")


def test_custom_policy_rejects_bad_roles_and_classes():
    with pytest.raises(ValueError):
        MemoryAccessPolicy({"superuser": RolePermission(
            max_class="public", redact_at=None, write=False)})
    with pytest.raises(ValueError):
        MemoryAccessPolicy({"analyst": RolePermission(
            max_class="cosmic", redact_at=None, write=False)})
    with pytest.raises(ValueError):
        MemoryAccessPolicy({"analyst": RolePermission(
            max_class="public", redact_at="cosmic", write=False)})


def test_adversarial_role_escalation_attempt():
    # An analyst must not widen their own role by swapping the guard.
    hist = _history()
    analyst = GuardedHistory(hist, "analyst")
    assert analyst.role == "analyst"
    with pytest.raises(MemoryAccessDenied):
        analyst.attach_outcome(hist.recent(1)[0].episode_id,
                               Outcome(kind="success"))
    # ...nor by reaching through to the wrapped history object.
    assert not hasattr(analyst, "history")
    assert analyst._history is hist  # the guard holds it privately


def test_adversarial_cross_class_query():
    # Querying for a forbidden class as analyst yields nothing and
    # raises nothing — the filter applies before redaction.
    hist = _history()
    analyst = GuardedHistory(hist, "analyst")
    assert analyst.find(MemoryQuery(
        privacy_classes={"forbidden"})) == []
    # by_request_hash respects the class filter too
    got = analyst.by_request_hash("h" * 16)
    assert all(e.privacy_class in ("public", "sensitive") for e in got)
