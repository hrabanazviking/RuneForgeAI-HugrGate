"""Exfiltration simulation. Slice 248.

The fortress claims to stop data exfiltration; this module
attacks that claim. :class:`ExfilSimulator` runs a suite of
attacker scenarios against a configured :class:`PrivacyGuard`
— direct remote calls, secret smuggling, local-only exfil,
PII in free text, jurisdiction hops, untrusted backends —
and reports, per scenario, whether the attempt was
**blocked** (refused outright), **neutralized** (the data was
sanitized before leaving), or **allowed** (it got out).

Each scenario declares what it *expects*; the report fails
when reality disagrees. A red-team operator runs the default
suite against their production guard configuration: any
``allowed`` where ``blocked`` was expected is a live hole.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from hugrgate.backend import Backend
from hugrgate.errors import HugrGateError
from hugrgate.policy import DecisionPolicy
from hugrgate.privacy import PrivacyGuard
from hugrgate.privacy_labels import FieldLabels
from hugrgate.privacy_payload import RemotePayloadCompiler
from hugrgate.privacy_trust import BackendTrustRegistry

__all__ = [
    "ExfilAttempt",
    "ExfilOutcome",
    "ExfilReport",
    "ExfilSimulator",
    "default_attacks",
]


@dataclass
class _FakeBackend(Backend):
    """Minimal backend surface the guard needs."""

    name: str = "fake"
    is_remote: bool = True

    def capabilities(self) -> dict[str, Any]:
        return {}

    def supports(self, spec: Any) -> bool:
        return True

    def evaluate(self, state: Any, spec: Any,
                 context: Any = None) -> Any:
        raise NotImplementedError("exfil simulation never evaluates")


@dataclass
class ExfilAttempt:
    """One attacker scenario."""

    name: str
    state: dict[str, Any]
    backend_name: str = "attacker-controlled"
    trust: str = "basic"
    jurisdiction: str = "unknown"
    privacy_class: str = "strict"
    labels: FieldLabels | None = None
    #: Secret-shaped strings planted in the state.
    markers: list[str] = field(default_factory=list)
    #: What the fortress *should* do: "blocked" | "neutralized" |
    #: "allowed".
    expect: str = "blocked"


@dataclass
class ExfilOutcome:
    """What actually happened for one attempt."""

    name: str
    verdict: str  # "blocked" | "neutralized" | "allowed"
    mechanism: str
    detail: str
    expected: str

    @property
    def passed(self) -> bool:
        return self.verdict == self.expected

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "verdict": self.verdict,
                "mechanism": self.mechanism, "detail": self.detail,
                "expected": self.expected, "passed": self.passed}


@dataclass
class ExfilReport:
    """Outcome of a full red-team run."""

    outcomes: list[ExfilOutcome] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return bool(self.outcomes) and all(o.passed
                                           for o in self.outcomes)

    @property
    def failures(self) -> list[ExfilOutcome]:
        return [o for o in self.outcomes if not o.passed]

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed,
                "outcomes": [o.to_dict() for o in self.outcomes]}

    def summary(self) -> str:
        lines = [f"exfil simulation: "
                 f"{sum(o.passed for o in self.outcomes)}/"
                 f"{len(self.outcomes)} scenarios held"]
        for outcome in self.outcomes:
            mark = "OK " if outcome.passed else "FAIL"
            lines.append(f"  [{mark}] {outcome.name}: "
                         f"{outcome.verdict} ({outcome.mechanism})")
        return "\n".join(lines)


def default_attacks() -> list[ExfilAttempt]:
    """The standard red-team suite."""
    ssn = "123-45-6789"
    api_key = "ghp_" + "a" * 36
    return [
        ExfilAttempt(
            name="strict-to-untrusted-remote",
            state={"query": "summarize this"},
            backend_name="shady-cloud", trust="basic",
            jurisdiction="EU", privacy_class="strict",
            expect="blocked"),
        ExfilAttempt(
            name="forbidden-never-remote",
            state={"query": "summarize this"},
            backend_name="trusted-cloud", trust="verified",
            jurisdiction="EU", privacy_class="forbidden",
            expect="blocked"),
        ExfilAttempt(
            name="secret-smuggling",
            state={"notes": "deploy with key " + api_key},
            backend_name="trusted-cloud", trust="verified",
            jurisdiction="EU", privacy_class="standard",
            markers=[api_key], expect="blocked"),
        ExfilAttempt(
            name="local-only-exfil",
            state={"user_ssn": ssn, "query": "hello"},
            backend_name="trusted-cloud", trust="verified",
            jurisdiction="EU", privacy_class="standard",
            labels=FieldLabels(local_only=["user_ssn"]),
            markers=[ssn], expect="neutralized"),
        ExfilAttempt(
            name="pii-in-free-text",
            state={"transcript": f"my ssn is {ssn}, call me"},
            backend_name="trusted-cloud", trust="verified",
            jurisdiction="EU", privacy_class="standard",
            markers=[ssn], expect="neutralized"),
        ExfilAttempt(
            name="jurisdiction-hop",
            state={"query": "hello"},
            backend_name="mystery-cloud", trust="verified",
            jurisdiction="unknown", privacy_class="standard",
            expect="blocked"),
        ExfilAttempt(
            name="sanity-allowed-flow",
            state={"query": "hello"},
            backend_name="trusted-cloud", trust="verified",
            jurisdiction="EU", privacy_class="public",
            expect="allowed"),
    ]


class ExfilSimulator:
    """Red-teams a privacy guard configuration.

    Builds its own guard (trust registry, jurisdiction allow-list,
    payload compiler) unless one is supplied — the point is to
    test a *configuration*, so callers should pass the guard they
    actually deploy.
    """

    def __init__(self, guard: PrivacyGuard | None = None,
                 jurisdictions_allowed: frozenset[str] | None = None):
        if guard is None:
            trust = BackendTrustRegistry()
            guard = PrivacyGuard(
                trust_registry=trust,
                jurisdictions_allowed=(jurisdictions_allowed
                                       or frozenset({"EU"})))
            guard.payload_compiler = RemotePayloadCompiler(guard=guard)
        self.guard = guard
        self._trust = guard.trust_registry

    def _prepare(self, attempt: ExfilAttempt) -> tuple[_FakeBackend,
                                                      DecisionPolicy]:
        backend = _FakeBackend(name=attempt.backend_name)
        if self._trust is not None:
            self._trust.attest(backend.name, attempt.trust)
        jurisdiction_registry = self.guard.jurisdiction_registry
        if attempt.jurisdiction != "unknown":
            jurisdiction_registry.declare(backend.name,
                                          attempt.jurisdiction)
        policy = DecisionPolicy(privacy_class=attempt.privacy_class,
                                remote_inference=True)
        return backend, policy

    def attempt(self, attempt: ExfilAttempt) -> ExfilOutcome:
        """Run one scenario; never raises."""
        backend, policy = self._prepare(attempt)
        state = copy.deepcopy(attempt.state)

        # Layer 1 — attempt gate.
        try:
            self.guard.check_backend(backend, policy)
        except HugrGateError as e:
            return ExfilOutcome(attempt.name, "blocked", e.code,
                                e.message, attempt.expect)

        # Layer 2 — payload compiler (flow, secrets, PII, ...).
        # An attempt may carry its own field labels; they must reach
        # the compiler or local-only stripping would silently not run.
        compiler = self.guard.payload_compiler
        if attempt.labels is not None:
            compiler = RemotePayloadCompiler(guard=self.guard,
                                             labels=attempt.labels)
        if compiler is None:
            return ExfilOutcome(attempt.name, "allowed",
                                "no-compiler",
                                "no payload compiler configured; "
                                "state would leave raw",
                                attempt.expect)
        try:
            payload = compiler.compile(state, backend=backend,
                                       policy=policy)
        except HugrGateError as e:
            return ExfilOutcome(attempt.name, "blocked", e.code,
                                e.message, attempt.expect)

        # Layer 3 — did planted markers survive the pipeline?
        body = repr(payload.payload)
        survivors = [m for m in attempt.markers if m in body]
        if survivors:
            return ExfilOutcome(
                attempt.name, "allowed", "pipeline-passthrough",
                f"markers survived: {len(survivors)}", attempt.expect)
        if attempt.markers:
            stages = payload.manifest.get("stages", [])
            return ExfilOutcome(
                attempt.name, "neutralized",
                "sanitized:" + "+".join(stages[:3]),
                f"{len(attempt.markers)} marker(s) removed by pipeline",
                attempt.expect)
        return ExfilOutcome(attempt.name, "allowed", "clean-flow",
                            "no markers planted; flow permitted",
                            attempt.expect)

    def run_suite(self,
                  attempts: list[ExfilAttempt] | None = None
                  ) -> ExfilReport:
        """Run the full suite (default: :func:`default_attacks`)."""
        return ExfilReport(
            outcomes=[self.attempt(a)
                      for a in (attempts or default_attacks())])
