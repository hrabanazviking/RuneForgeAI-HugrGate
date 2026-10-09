"""Slice 248 — Exfiltration simulation."""

from __future__ import annotations

from hugrgate.privacy import PrivacyGuard
from hugrgate.privacy_exfil import ExfilAttempt, ExfilSimulator, default_attacks
from hugrgate.privacy_labels import FieldLabels


def test_default_suite_holds_against_fortress():
    report = ExfilSimulator().run_suite()
    print(report.summary())
    assert report.passed, \
        f"holes: {[o.name for o in report.failures]}"


def test_suite_has_expected_mix():
    attacks = default_attacks()
    expects = {a.expect for a in attacks}
    assert expects == {"blocked", "neutralized", "allowed"}
    assert len(attacks) >= 7


def test_outcome_details_are_actionable():
    report = ExfilSimulator().run_suite()
    for outcome in report.outcomes:
        assert outcome.mechanism
        data = outcome.to_dict()
        assert data["passed"] is True


def test_misconfigured_guard_fails_suite():
    # A guard with no compiler and no jurisdiction control lets
    # exfiltration through — the simulator must catch it.
    weak = PrivacyGuard()  # no compiler, no attestations
    simulator = ExfilSimulator(guard=weak)
    report = simulator.run_suite()
    assert not report.passed
    failed = {o.name for o in report.failures}
    # Secret smuggling sails through with no compiler.
    assert "secret-smuggling" in failed


def test_single_attempt_never_raises():
    simulator = ExfilSimulator()
    outcome = simulator.attempt(ExfilAttempt(
        name="custom", state={"x": 1}, privacy_class="public",
        backend_name="b", trust="verified", jurisdiction="EU",
        expect="allowed"))
    assert outcome.passed


def test_custom_attacker_scenario():
    # Attacker tries to launder a secret through a *local-only*
    # field on a trusted backend: must be neutralized, not leak.
    secret = "sk-" + "b" * 32
    simulator = ExfilSimulator()
    outcome = simulator.attempt(ExfilAttempt(
        name="launder-via-local-only",
        state={"api_key": secret, "q": "hi"},
        backend_name="trusted-cloud", trust="verified",
        jurisdiction="EU", privacy_class="standard",
        labels=FieldLabels(local_only=["api_key"]),
        markers=[secret], expect="neutralized"))
    assert outcome.passed, outcome.detail


def test_report_serializes():
    report = ExfilSimulator().run_suite()
    data = report.to_dict()
    assert data["passed"] is True
    assert len(data["outcomes"]) == len(default_attacks())


def test_adversarial_empty_state_attack():
    simulator = ExfilSimulator()
    outcome = simulator.attempt(ExfilAttempt(
        name="empty", state={}, privacy_class="forbidden",
        backend_name="trusted-cloud", trust="verified",
        jurisdiction="EU", expect="blocked"))
    assert outcome.passed
