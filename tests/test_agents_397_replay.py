"""Slice 397 — agent replay."""

from __future__ import annotations

import pytest

from hugrgate.agents.replay import AgentReplay


def _recorder():
    r = AgentReplay()
    r.record_step("t1", "route", {"text": "hi"}, {"agent": "a"})
    r.record_step("t1", "tool", {"tool": "search"}, {"hits": 3})
    return r


def test_record_and_replay_fidelity():
    r = _recorder()
    assert len(r.steps("t1")) == 2
    assert r.steps("ghost") == ()

    def agent_fn(step_input, seed):
        return {"agent": "a"} if "text" in step_input else {"hits": 3}

    rep = r.replay("t1", agent_fn, seed=42)
    assert rep.steps == 2 and rep.matched == 2
    assert rep.mismatches == ()
    assert rep.fidelity == 1.0
    assert rep.deterministic is True
    assert rep.seed == 42


def test_mismatch_detection():
    r = _recorder()

    def changed(step_input, seed):
        return {"agent": "b"} if "text" in step_input else {"hits": 3}

    rep = r.replay("t1", changed)
    assert rep.matched == 1
    assert rep.mismatches == (0,)
    assert rep.fidelity == pytest.approx(0.5)
    assert "recorded {'agent': 'a'}" in rep.notes[0]


def test_raising_fn_is_a_mismatch():
    r = _recorder()

    def bad(step_input, seed):
        raise RuntimeError("down")

    rep = r.replay("t1", bad)
    assert rep.mismatches == (0, 1)
    assert rep.fidelity == 0.0


def test_nondeterminism_detected():
    r = _recorder()
    calls = {"n": 0}

    def flippy(step_input, seed):
        calls["n"] += 1
        return {"n": calls["n"]}  # monotonic: every run differs

    assert r.check_determinism("t1", flippy) is False
    rep = r.replay("t1", flippy, seed=1)
    assert rep.deterministic is False


def test_bulk_record_and_json_safety():
    r = AgentReplay()
    n = r.record("t2", [
        {"kind": "a", "input": {"x": 1}, "output": {"y": 2}},
        {"kind": "b", "input": [1, 2], "output": "ok"},
    ])
    assert n == 2
    assert r.steps("t2")[1].kind == "b"
    with pytest.raises(ValueError):
        r.record_step("t2", "c", {"x": object()}, {"y": 1})
    with pytest.raises(ValueError):
        r.record_step("t2", "c", {"x": 1}, {"y": object()})


def test_unknown_ticket_and_forget():
    r = AgentReplay()
    with pytest.raises(ValueError):
        r.replay("ghost", lambda i, s: i)
    with pytest.raises(ValueError):
        r.check_determinism("ghost", lambda i, s: i)
    with pytest.raises(ValueError):
        r.record_step("", "k", {}, {})
    with pytest.raises(ValueError):
        r.record_step("t", "", {}, {})
    r.record_step("t", "k", {}, {})
    assert r.forget("t") is True
    assert r.forget("t") is False
