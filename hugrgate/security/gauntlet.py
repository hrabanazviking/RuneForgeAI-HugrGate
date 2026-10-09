"""The security gauntlet. Slice 424.

The capstone battery: runs every Security Forge adversarial suite
in one pass and reports per-battery containment. A battery that
raises fails *that battery* — the gauntlet itself never crashes.

Batteries:

- threat_model — the STRIDE model validates and every threat
  names its tests;
- attack_surface — no unlisted routes/commands/env vars (drift);
- injection_corpus — all 30 payloads neutralized/detected;
- malicious_backends — the five hostile backends stay contained;
- provenance_tamper — chain + tip seals detect every attack;
- cache_poison — cross-tenant/stale-model reads contained;
- replay — sealed envelopes reject replays;
- authz — unknown keys and escalation denied;
- rate_limit — bursts rejected with retry-after;
- secret_audit — zero high/medium findings over the package;
- fuzz_smoke — 100-case campaigns on the codec + validator;
- depscan — no advisory findings over the project.

Use :func:`run_security_gauntlet` (named to avoid clashing with
the slice-415 backend :func:`run_gauntlet`).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "BatteryResult",
    "SecurityGauntletReport",
    "run_security_gauntlet",
]

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = _PACKAGE_ROOT.parent


@dataclass
class BatteryResult:
    name: str
    passed: bool
    detail: str = ""
    seconds: float = 0.0


@dataclass
class SecurityGauntletReport:
    batteries: list[BatteryResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return bool(self.batteries) and all(
            b.passed for b in self.batteries)

    @property
    def failed(self) -> list[BatteryResult]:
        return [b for b in self.batteries if not b.passed]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "batteries": [
                {"name": b.name, "passed": b.passed,
                 "detail": b.detail,
                 "seconds": round(b.seconds, 3)}
                for b in self.batteries],
        }

    def summary(self) -> str:
        lines = []
        for b in self.batteries:
            mark = "PASS" if b.passed else "FAIL"
            lines.append(f"[{mark}] {b.name}: {b.detail}")
        lines.append(f"gauntlet {'PASSED' if self.passed else 'FAILED'}: "
                     f"{len(self.batteries) - len(self.failed)}/"
                     f"{len(self.batteries)} batteries held")
        return "\n".join(lines)


def _battery(name: str, fn: Callable[[], str]) -> BatteryResult:
    start = time.monotonic()
    try:
        detail = fn()
    except Exception as e:  # noqa: BLE001 - a raising battery fails
        return BatteryResult(name=name, passed=False,
                             detail=f"{type(e).__name__}: {e}",
                             seconds=time.monotonic() - start)
    return BatteryResult(name=name, passed=True, detail=detail,
                         seconds=time.monotonic() - start)


def _threat_model() -> str:
    from hugrgate.security.threat_model import default_threat_model
    model = default_threat_model()
    model.validate()
    # Every threat names its tests, except accepted residual risks
    # (T-18: cache timing is out of scope for the local-first
    # single-tenant model — documented, not forgotten).
    orphans = [t.id for t in model.threats
               if not t.tests and t.residual != "accepted"]
    if orphans:
        raise AssertionError(f"threats without tests: {orphans}")
    accepted = [t.id for t in model.threats
                if t.residual == "accepted"]
    return (f"{len(model.threats)} threats validated, all name tests "
            f"(accepted residual: {accepted})")


def _attack_surface() -> str:
    from hugrgate.security.attack_surface import (
        curated_surface,
        find_unlisted,
    )
    drift = find_unlisted(curated_surface())
    total = sum(len(v) for v in drift.values())
    if total:
        raise AssertionError(f"surface drift: {drift}")
    return "no unlisted routes, commands, or env vars"


def _injection_corpus() -> str:
    from hugrgate.security.injection_corpus import run_corpus
    results = run_corpus()
    failed = [r for r in results if not r.passed]
    if failed:
        raise AssertionError(
            f"{len(failed)} payloads escaped: "
            f"{[r.payload.text[:40] for r in failed][:5]}")
    return f"{len(results)} payloads neutralized/detected"


def _malicious_backends() -> str:
    from hugrgate.security.malicious_backend import run_gauntlet
    report = run_gauntlet()
    if not report.passed:
        raise AssertionError(f"escapes: {report.escaped}")
    return f"{len(report.contained)} hostile backends contained"


def _cache_poison() -> str:
    from hugrgate.security.cache_poisoning import run_poison_suite
    reports = run_poison_suite()
    failed = [r for r in reports if not r.contained]
    if failed:
        raise AssertionError(
            f"uncontained: {[r.attack for r in failed]}")
    return f"{len(reports)} poison attacks contained"


def _replay() -> str:
    from hugrgate.errors import ReplayDetected
    from hugrgate.security.replay import (
        ReplayGuard,
        open_request,
        seal_request,
    )
    key = b"k" * 32
    guard = ReplayGuard()
    env = seal_request({"op": "decide"}, key, "n1")
    assert open_request(env, {"n1": key}, guard) == {"op": "decide"}
    try:
        open_request(env, {"n1": key}, guard)
    except ReplayDetected:
        return "replay rejected, fresh envelope accepted"
    raise AssertionError("replay was accepted")


def _authz() -> str:
    from hugrgate.errors import AuthzDenied
    from hugrgate.security.authz import AuthzPolicy
    policy = AuthzPolicy()
    policy.register_key("c1", b"c" * 32, ("caller",))
    for key_id, secret, cap in (("ghost", b"x" * 32, "decide"),
                                ("c1", b"c" * 32, "configure")):
        try:
            policy.check(key_id, secret, cap)
        except AuthzDenied:
            continue
        raise AssertionError(f"{key_id}/{cap} was granted")
    return "unknown keys and escalation denied"


def _rate_limit() -> str:
    from hugrgate.errors import RateLimitExceeded
    from hugrgate.security.ratelimit import RateLimiter
    limiter = RateLimiter(capacity=2, refill_per_second=0.01)
    limiter.throttle("flood")
    limiter.throttle("flood")
    try:
        limiter.throttle("flood")
    except RateLimitExceeded as e:
        assert e.details["retry_after_ms"] >= 0
        return "burst rejected with retry-after hint"
    raise AssertionError("burst was not limited")


def _secret_audit() -> str:
    from hugrgate.security.secret_audit import run_secret_audit
    report = run_secret_audit(_PACKAGE_ROOT)
    bad = [f for f in report["findings"]
           if f.severity in ("high", "medium")]
    if bad:
        raise AssertionError(
            f"{len(bad)} findings: "
            f"{[(f.path, f.line, f.rule) for f in bad][:5]}")
    return "no high/medium secret-handling findings"


def _fuzz_smoke() -> str:
    from hugrgate.security.fuzzing import (
        FuzzTarget,
        hostile_states,
        hostile_values,
        run_campaign,
    )
    from hugrgate.spec import DecisionSpec
    from hugrgate.validation import validate_state

    def dict_cases(rng):
        value = hostile_values(rng)
        return value if isinstance(value, dict) else {"k": value}

    total = 0
    for target, gen in (
            (FuzzTarget("spec", DecisionSpec.from_dict), dict_cases),
            (FuzzTarget("validate_state", validate_state),
             hostile_states)):
        report = run_campaign(target, gen, n_cases=100)
        if report.unique_crashes or report.hangs:
            raise AssertionError(
                f"{target.name}: "
                f"{[c.signature for c in report.unique_crashes]}")
        total += report.cases
    return f"{total} fuzz cases, zero crashes/hangs"


def _depscan() -> str:
    from hugrgate.security.depscan import scan_project
    findings = scan_project(REPO_ROOT)
    high = [f for f in findings
            if f.severity in ("high", "critical")]
    if high:
        raise AssertionError(
            f"{len(high)} advisory findings: "
            f"{[(f.package, f.cve) for f in high][:5]}")
    return f"{len(findings)} low/info findings, no advisories"


def _provenance_tamper() -> str:
    from hugrgate.provenance import DecisionRecord, ProvenanceStore
    from hugrgate.security.model_signing import ModelSigner
    from hugrgate.security.provenance_guards import (
        run_tamper_suite,
        seal_tip,
    )
    store = ProvenanceStore()
    for i in range(4):
        store.append(DecisionRecord(
            request_hash=f"req{i}", spec={}, backend="b", model="m",
            value=f"v{i}"))
    key = b"s" * 32
    signer = ModelSigner(key, "tip")
    checkpoint = seal_tip(store, signer)
    reports = run_tamper_suite(store.recent(4), key)
    # The "no_attack" control must NOT be flagged; every real
    # attack must be caught by the chain or the tip seal.
    controls = [r for r in reports if r.attack == "no_attack"]
    if not controls:
        raise AssertionError("tamper suite lost its control case")
    missed = [r for r in reports
              if r.attack != "no_attack"
              and not (r.detected_by_chain or r.detected_by_tip)]
    if missed:
        raise AssertionError(
            f"undetected: {[r.attack for r in missed]}")
    return (f"{len(reports)} tamper attacks detected "
            f"(tip checkpoint {checkpoint.key_id!r})")


_BATTERIES: list[tuple[str, Callable[[], str]]] = [
    ("threat_model", _threat_model),
    ("attack_surface", _attack_surface),
    ("injection_corpus", _injection_corpus),
    ("malicious_backends", _malicious_backends),
    ("provenance_tamper", _provenance_tamper),
    ("cache_poison", _cache_poison),
    ("replay", _replay),
    ("authz", _authz),
    ("rate_limit", _rate_limit),
    ("secret_audit", _secret_audit),
    ("fuzz_smoke", _fuzz_smoke),
    ("depscan", _depscan),
]


def run_security_gauntlet() -> SecurityGauntletReport:
    """Run every Security Forge battery; return the combined report."""
    report = SecurityGauntletReport()
    for name, fn in _BATTERIES:
        result = _battery(name, fn)
        report.batteries.append(result)
    return report
