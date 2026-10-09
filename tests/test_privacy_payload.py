"""Slice 237 — Remote payload compiler.

Tests the full eight-stage compilation, each stage in isolation,
denial paths (guard, flow policy, secrets, local-only strict),
manifest auditability, determinism, and ladder integration (the
chokepoint actually gates remote backends; denials are audited as
privacy skips).
"""

from __future__ import annotations

import pytest

from hugrgate.backend import Backend
from hugrgate.errors import (
    DataFlowDenied,
    LocalOnlyViolation,
    PrivacyViolation,
    SecretDetected,
)
from hugrgate.policy import DecisionPolicy
from hugrgate.privacy import PrivacyGuard
from hugrgate.privacy_flow import DataFlowPolicy
from hugrgate.privacy_labels import FieldLabels
from hugrgate.privacy_minimize import MinimizationPolicy
from hugrgate.privacy_payload import RemotePayload, RemotePayloadCompiler
from hugrgate.privacy_redact import MaskRedactor, RedactionPipeline
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec


class FakeBackend(Backend):
    def __init__(self, name: str, remote: bool = False):
        self.name = name
        self.is_remote = remote
        self.seen: list[dict] = []

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        self.seen.append(dict(state))
        return DecisionResult(value="a", probability=0.9,
                              distribution={"a": 0.9, "b": 0.1})


def make_spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


@pytest.fixture
def remote():
    return FakeBackend("remote-llm", remote=True)


@pytest.fixture
def local():
    return FakeBackend("local-ml")


@pytest.fixture
def compiler():
    guard = PrivacyGuard()
    labels = FieldLabels(
        {"ssn": "secret", "api_key": "secret", "email": "confidential",
         "debug": "internal"},
        default="public",
        local_only={"api_key"})
    return RemotePayloadCompiler(
        guard=guard,
        flow_policy=DataFlowPolicy(redact_instead_of_deny=True),
        labels=labels,
        minimization=MinimizationPolicy({"remote-llm": ["q", "email"]}),
        local_only_strict=False)


def test_local_passthrough(compiler, local):
    compiled = compiler.compile({"ssn": "1", "api_key": "k"},
                                backend=local,
                                policy=DecisionPolicy())
    assert compiled.remote is False
    assert compiled.payload == {"ssn": "1", "api_key": "k"}
    assert compiled.manifest["stages"] == ["local-passthrough"]


def test_full_pipeline(compiler, remote):
    state = {"q": "2+2?", "email": "a@b.io", "ssn": "123-45-6789",
             "api_key": "k", "debug": "d", "extra": "e"}
    compiled = compiler.compile(state, backend=remote,
                                policy=DecisionPolicy(remote_inference=True))
    payload = compiled.payload
    # Minimization kept only q + email; secret/local-only gone;
    # email PII masked by the scrub stage.
    assert set(payload) == {"q", "email"}
    assert payload["email"] == "[PII:email]"
    assert payload["q"] == "2+2?"
    manifest = compiled.manifest
    assert manifest["backend"] == "remote-llm"
    assert manifest["trust_level"] == "basic"
    assert manifest["jurisdiction"] == "unknown"  # undeclared remote
    assert "api_key" in manifest["local_only_stripped"]
    assert manifest["flow"]["action"] in ("allow", "redact")
    assert len(manifest["stages"]) == 8
    assert isinstance(compiled, RemotePayload)


def test_deterministic(compiler, remote):
    state = {"q": "x", "email": "a@b.io", "ssn": "1"}
    policy = DecisionPolicy(remote_inference=True)
    first = compiler.compile(state, backend=remote, policy=policy)
    second = compiler.compile(state, backend=remote, policy=policy)
    assert first.payload == second.payload
    assert first.manifest == second.manifest


def test_input_not_mutated(compiler, remote):
    state = {"q": "x", "api_key": "k", "nested": {"a": 1}}
    snapshot = {"q": "x", "api_key": "k", "nested": {"a": 1}}
    compiler.compile(state, backend=remote,
                     policy=DecisionPolicy(remote_inference=True))
    assert state == snapshot


def test_guard_denial_propagates(compiler, remote):
    # forbidden-class data: stage 1 raises PrivacyViolation.
    with pytest.raises(PrivacyViolation):
        compiler.compile({"q": "x"}, backend=remote,
                         policy=DecisionPolicy(remote_inference=True,
                                               privacy_class="forbidden"))


def test_flow_denial_propagates(remote):
    guard = PrivacyGuard()
    compiler = RemotePayloadCompiler(
        guard=guard,
        flow_policy=DataFlowPolicy(redact_instead_of_deny=False),
        labels=FieldLabels({"ssn": "secret"}))
    with pytest.raises(DataFlowDenied):
        compiler.compile({"ssn": "1"}, backend=remote,
                         policy=DecisionPolicy(remote_inference=True))


def test_secret_scan_raises(remote):
    guard = PrivacyGuard()
    compiler = RemotePayloadCompiler(guard=guard, pii_scrub=False)
    with pytest.raises(SecretDetected):
        compiler.compile({"note": "key AKIAIOSFODNN7EXAMPLE"},
                         backend=remote,
                         policy=DecisionPolicy(remote_inference=True))


def test_local_only_strict_raises(remote):
    guard = PrivacyGuard()
    compiler = RemotePayloadCompiler(
        guard=guard,
        # "internal" is below the remote clearance, so the flow policy
        # passes and strict local-only enforcement fires at stage 4.
        labels=FieldLabels({"api_key": "internal"},
                           local_only={"api_key"}),
        local_only_strict=True, pii_scrub=False)
    with pytest.raises(LocalOnlyViolation):
        compiler.compile({"api_key": "k", "q": "x"}, backend=remote,
                         policy=DecisionPolicy(remote_inference=True))


def test_redaction_pipeline_stage(remote):
    guard = PrivacyGuard()
    pipeline = RedactionPipeline(
        field_redactors={"debug": MaskRedactor()})
    compiler = RemotePayloadCompiler(
        guard=guard, redaction_pipeline=pipeline, pii_scrub=False)
    compiled = compiler.compile({"debug": "d", "q": "x"},
                                backend=remote,
                                policy=DecisionPolicy(remote_inference=True))
    assert compiled.payload["debug"] == "[REDACTED]"
    assert ("debug", "mask") in compiled.manifest["redactions_applied"]


def test_pii_drop_action(remote):
    guard = PrivacyGuard()
    compiler = RemotePayloadCompiler(guard=guard, pii_action="drop")
    compiled = compiler.compile({"email": "a@b.io", "q": "x"},
                                backend=remote,
                                policy=DecisionPolicy(remote_inference=True))
    assert "email" not in compiled.payload
    assert compiled.payload["q"] == "x"


def test_payload_to_dict_round_trip(compiler, remote):
    compiled = compiler.compile(
        {"q": "x"}, backend=remote,
        policy=DecisionPolicy(remote_inference=True))
    d = compiled.to_dict()
    assert d["payload"] == compiled.payload
    assert d["manifest"] == compiled.manifest
    assert d["backend"] == "remote-llm" and d["remote"] is True


def test_guard_compile_outbound_no_compiler():
    guard = PrivacyGuard()
    with pytest.raises(AttributeError):
        guard.compile_outbound({"a": 1}, FakeBackend("r", True),
                               DecisionPolicy())


# -- ladder integration -----------------------------------------------------

def test_ladder_compiles_remote_payload(remote):
    from hugrgate.ladder import LadderRouter, LadderRung

    guard = PrivacyGuard()
    labels = FieldLabels({"ssn": "secret"}, local_only=set())
    compiler = RemotePayloadCompiler(
        guard=guard,
        flow_policy=DataFlowPolicy(redact_instead_of_deny=True),
        labels=labels, pii_scrub=False)
    guard.payload_compiler = compiler

    router = LadderRouter(
        rungs=[LadderRung("remote-llm", 0.0)],
        registry=_registry(remote),
        privacy_guard=guard)
    result = router.decide({"q": "x", "ssn": "123-45-6789"},
                           make_spec(),
                           DecisionPolicy(remote_inference=True))
    # The backend saw the compiled payload, not the raw state.
    assert remote.seen and "ssn" not in remote.seen[0]
    assert remote.seen[0]["q"] == "x"
    manifest = result.metadata.get("privacy_manifest")
    assert manifest and manifest["backend"] == "remote-llm"


def test_ladder_denial_audited_as_privacy_skip(remote):
    from hugrgate.errors import Abstention
    from hugrgate.ladder import LadderRouter, LadderRung

    guard = PrivacyGuard()
    compiler = RemotePayloadCompiler(guard=guard, pii_scrub=False)
    guard.payload_compiler = compiler
    router = LadderRouter(
        rungs=[LadderRung("remote-llm", 0.0)],
        registry=_registry(remote),
        privacy_guard=guard)
    # forbidden-class: blocked at selection (RUNG_SKIPPED_PRIVACY) —
    # the ladder exhausts and abstains; nothing reached the backend.
    with pytest.raises(Abstention) as exc:
        router.decide({"q": "x"}, make_spec(),
                      DecisionPolicy(remote_inference=True,
                                     privacy_class="forbidden"))
    assert exc.value.reason == "ladder_exhausted"
    assert remote.seen == []
    skips = [e for e in router.last_audit
             if e.outcome == "skipped_privacy_blocked"]
    assert len(skips) == 1


def test_ladder_no_compiler_unchanged_behavior(remote):
    from hugrgate.ladder import LadderRouter, LadderRung

    router = LadderRouter(
        rungs=[LadderRung("remote-llm", 0.0)],
        registry=_registry(remote),
        privacy_guard=PrivacyGuard())
    result = router.decide({"q": "x"}, make_spec(),
                           DecisionPolicy(remote_inference=True))
    assert remote.seen[0] == {"q": "x"}
    assert "privacy_manifest" not in result.metadata
    assert result.value == "a"


def _registry(*backends):
    from hugrgate.backend import BackendRegistry
    reg = BackendRegistry()
    for backend in backends:
        reg.register(backend)
    return reg


def test_adversarial_secret_after_minimization(remote):
    # A secret in a keep-listed field is still caught: the secret
    # scan runs on the *minimized* payload, not the raw state.
    guard = PrivacyGuard()
    compiler = RemotePayloadCompiler(
        guard=guard,
        minimization=MinimizationPolicy({"remote-llm": ["note"]}),
        pii_scrub=False)
    with pytest.raises(SecretDetected):
        compiler.compile({"note": "AKIAIOSFODNN7EXAMPLE"},
                         backend=remote,
                         policy=DecisionPolicy(remote_inference=True))
