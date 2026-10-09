"""Slice 145 — router rollback tests."""

from __future__ import annotations

import pytest

from hugrgate.adaptive.rollback import RouterRollback
from hugrgate.errors import SpecError


def rollback():
    return RouterRollback(max_checkpoints=3)


# --- success ---------------------------------------------------------------

def test_checkpoint_and_rollback_round_trip():
    rb = rollback()
    rb.checkpoint({"weights": [1.0, 2.0]}, note="gen1")
    rb.checkpoint({"weights": [1.5, 2.5]}, note="gen2")
    restored = rb.rollback(steps=1)
    assert restored == {"weights": [1.5, 2.5]}
    assert rb.rollback(steps=2) == {"weights": [1.0, 2.0]}

def test_checkpoint_ids_are_sequential():
    rb = rollback()
    assert rb.checkpoint({"a": 1}) == "ckpt-1"
    assert rb.checkpoint({"a": 2}) == "ckpt-2"
    assert rb.latest_id() == "ckpt-2"

def test_bounded_stack_evicts_oldest():
    rb = rollback()  # max 3
    for i in range(5):
        rb.checkpoint({"gen": i})
    assert len(rb) == 3
    assert [c["checkpoint_id"] for c in rb.history()] == \
        ["ckpt-3", "ckpt-4", "ckpt-5"]

def test_rollback_returns_deep_copy():
    rb = rollback()
    rb.checkpoint({"nested": {"x": [1]}})
    restored = rb.rollback()
    restored["nested"]["x"].append(999)
    assert rb.rollback()["nested"]["x"] == [1]

def test_audit_log_records_checkpoints_and_rollbacks():
    rb = rollback()
    rb.checkpoint({"a": 1}, note="first")
    rb.rollback()
    log = rb.audit_log()
    assert [e["action"] for e in log] == ["checkpoint", "rollback"]
    assert log[0]["note"] == "first"
    assert log[1]["restored_checkpoint_id"] == "ckpt-1"
    # Rolling back does not erase the audit trail.
    assert len(rb.audit_log()) == 2

def test_history_lists_checkpoints_oldest_first():
    rb = rollback()
    rb.checkpoint({"a": 1}, note="one")
    history = rb.history()
    assert isinstance(history[0], dict)
    assert history[0]["checkpoint_id"] == "ckpt-1"
    assert history[0]["note"] == "one"

def test_empty_rollback_has_no_latest():
    assert rollback().latest_id() is None

# --- failure ---------------------------------------------------------------

def test_rollback_past_genesis_rejected():
    rb = rollback()
    rb.checkpoint({"a": 1})
    with pytest.raises(SpecError):
        rb.rollback(steps=2)
    with pytest.raises(SpecError):
        RouterRollback().rollback()

def test_nonpositive_steps_rejected():
    rb = rollback()
    rb.checkpoint({"a": 1})
    with pytest.raises(SpecError):
        rb.rollback(steps=0)
    with pytest.raises(SpecError):
        rb.rollback(steps=-1)

def test_non_serializable_state_rejected():
    rb = rollback()
    with pytest.raises(SpecError):
        rb.checkpoint({"fn": lambda: 1})
    with pytest.raises(SpecError):
        rb.checkpoint("not-a-mapping")

def test_bad_max_checkpoints_rejected():
    with pytest.raises(SpecError):
        RouterRollback(max_checkpoints=0)
