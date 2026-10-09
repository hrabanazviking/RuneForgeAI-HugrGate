"""Slice 236 — Prompt / data minimization."""

from __future__ import annotations

import pytest

from hugrgate.privacy_minimize import (
    MinimizationPolicy,
    MinimizationReport,
    PromptMinimizer,
    minimize_state,
)


def test_minimize_state_top_level():
    state = {"a": 1, "b": 2, "c": 3}
    out, report = minimize_state(state, ["a", "c"])
    assert out == {"a": 1, "c": 3}
    assert report.kept == ["a", "c"]
    assert report.dropped == ["b"]


def test_minimize_state_dotted_paths():
    state = {"user": {"name": "n", "ssn": "1"}, "x": 1}
    out, report = minimize_state(state, ["user.name"])
    assert out == {"user": {"name": "n"}}
    assert report.kept == ["user.name"]
    assert "user.ssn" in report.dropped and "x" in report.dropped


def test_minimize_state_absent_keep_ignored():
    out, report = minimize_state({"a": 1}, ["a", "missing"])
    assert out == {"a": 1}
    assert report.kept == ["a"]


def test_minimize_state_empty_keep():
    out, report = minimize_state({"a": 1}, [])
    assert out == {}
    assert report.dropped == ["a"]


def test_minimize_state_no_mutation():
    state = {"user": {"name": "n", "ssn": "1"}}
    snapshot = {"user": {"name": "n", "ssn": "1"}}
    out, _ = minimize_state(state, ["user.name"])
    out["user"]["name"] = "MUT"
    assert state == snapshot


def test_minimization_report_type():
    _, report = minimize_state({"a": 1}, ["a"], backend="llm")
    assert isinstance(report, MinimizationReport)
    assert report.backend == "llm"


def test_policy_per_backend():
    policy = MinimizationPolicy({"llm": ["question", "user.name"]})
    out, report = policy.minimize(
        {"question": "q", "user": {"name": "n", "ssn": "1"},
         "debug": True}, "llm")
    assert out == {"question": "q", "user": {"name": "n"}}
    assert report.backend == "llm"


def test_policy_undeclared_passes_through():
    policy = MinimizationPolicy({"llm": ["a"]})
    state = {"a": 1, "b": 2}
    out, report = policy.minimize(state, "unknown-backend")
    assert out == state  # documented pass-through
    assert report.kept == [] and report.dropped == []


def test_policy_default_keep():
    policy = MinimizationPolicy(default_keep=["a"])
    out, _ = policy.minimize({"a": 1, "b": 2}, "anything")
    assert out == {"a": 1}


def test_policy_declare_and_round_trip():
    policy = MinimizationPolicy()
    policy.declare("llm", ["q"])
    assert policy.keep_for("llm") == ["q"]
    rebuilt = MinimizationPolicy.from_dict(policy.to_dict())
    assert rebuilt.keep_for("llm") == ["q"]


def test_prompt_minimizer_renders_compact():
    minimizer = PromptMinimizer(max_chars=4000)
    prompt, _report = minimizer.render(
        {"q": "what?", "user": {"name": "n", "ssn": "1"},
         "secret": "x"}, ["q", "user.name"])
    assert "ssn" not in prompt and "secret" not in prompt
    assert '"q": "what?"' in prompt


def test_prompt_minimizer_budget_skips_not_truncates():
    minimizer = PromptMinimizer(max_chars=20)
    prompt, report = minimizer.render(
        {"aaa": "x" * 100, "b": "y"}, ["aaa", "b"])
    # "aaa" alone overflows -> skipped whole, "b" still emitted.
    assert "xxx" not in prompt
    assert '"b": "y"' in prompt
    assert any(d.startswith("prompt-budget:") for d in report.dropped)


def test_prompt_minimizer_invalid_budget():
    with pytest.raises(ValueError):
        PromptMinimizer(max_chars=0)


def test_adversarial_extra_fields_never_leak():
    # Fuzz-ish: 100 extra fields, keep-list of 2 -> only 2 survive.
    state = {f"f{i}": i for i in range(100)}
    state["keep1"] = "a"
    state["keep2"] = "b"
    out, report = minimize_state(state, ["keep1", "keep2"])
    assert set(out) == {"keep1", "keep2"}
    assert len(report.dropped) == 100


def test_adversarial_nested_smuggle():
    # A keep-listed parent keeps the whole subtree (documented);
    # a dotted keep-list keeps only the leaf.
    state = {"user": {"name": "n", "ssn": "1"}}
    out, _ = minimize_state(state, ["user.name"])
    assert out == {"user": {"name": "n"}}
    out, _ = minimize_state(state, ["user"])
    assert out == state  # whole subtree: declare carefully
