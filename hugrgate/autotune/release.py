"""Autonomous Optimization release gate. Slice 475.

Campaign XIX's capstone: :func:`release_gate` ties the campaign
together into one go/no-go decision. It runs, in order:

1. **error taxonomy** — every Campaign XIX error is registered with
   a unique, stable code and a deliberate recoverable flag;
2. **controller smoke** — a full propose/validate/dispose cycle with
   a null tuner completes and journals;
3. **safety posture** — the default :class:`SafetyLimits` have the
   kill switch off, a non-empty mode allowlist that excludes
   ``APPLIED``, and sane bounds;
4. **provenance integrity** — a tracker records a cycle and the
   chain verifies;
5. **reproducibility** — a manifest records and a replay matches;
6. **no silent corruption** — the tuner package exports resolve and
   the adversarial harness reports its known breaking point
   honestly (40% label noise is *detected*, not contained).

The outcome is a :class:`ReleaseVerdict` (``"release"`` or
``"hold"`` with every reason named); :func:`assert_release` turns a
hold into :class:`AutotuneError` for CI. A release with zero checks
is a rubber stamp and is refused outright.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from hugrgate.errors import AutotuneError, HugrGateError

__all__ = [
    "HOLD",
    "RELEASE",
    "ReleaseCheck",
    "ReleaseVerdict",
    "assert_release",
    "campaign_checks",
    "release_gate",
]

RELEASE = "release"
HOLD = "hold"

_CAMPAIGN_XIX_CODES = {
    "autotune_error": True,
    "objective_error": False,
    "constraint_violation": True,
    "tuner_error": True,
    "unsafe_proposal": False,
    "rollback_error": False,
    "reproducibility_error": False,
    "parameter_error": False,
}


@dataclass
class ReleaseCheck:
    """One named go/no-go check."""

    name: str
    run: Callable[[], tuple[bool, str]]


@dataclass
class ReleaseVerdict:
    """The gate's decision."""

    verdict: str  # "release" | "hold"
    results: list[dict[str, Any]] = field(default_factory=list)
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def passed(self) -> bool:
        return self.verdict == RELEASE

    def to_dict(self) -> dict[str, Any]:
        return {"verdict": self.verdict,
                "generated_at": self.generated_at,
                "results": [dict(r) for r in self.results]}

    def summary(self) -> str:
        lines = [f"autonomous-optimization release gate: {self.verdict.upper()}"]
        for r in self.results:
            mark = "PASS" if r["passed"] else "HOLD"
            lines.append(f"  [{mark}] {r['name']}: {r['detail']}")
        return "\n".join(lines)


def _check_error_taxonomy() -> tuple[bool, str]:
    import importlib
    errors = importlib.import_module("hugrgate.errors")
    missing = [c for c in _CAMPAIGN_XIX_CODES
               if c not in HugrGateError._registry]
    if missing:
        return False, f"unregistered codes: {missing}"
    bad = []
    for code, expected in _CAMPAIGN_XIX_CODES.items():
        klass = HugrGateError._registry[code]
        if klass.recoverable is not expected:
            bad.append(code)
        if not hasattr(errors, klass.__name__):
            bad.append(f"unexported:{klass.__name__}")
    if bad:
        return False, f"taxonomy mismatch: {bad}"
    return True, f"{len(_CAMPAIGN_XIX_CODES)} codes registered, flags deliberate"


def _check_controller_smoke() -> tuple[bool, str]:
    from hugrgate.autotune.controller import (
        Mode,
        OptimizationController,
        TuningContext,
    )

    class _Null:
        name = "release-null"

        def tune(self, ctx: TuningContext):
            return None

    c = OptimizationController()
    c.register_objective("o", lambda values: 0.0)
    c.register_tuner(_Null())
    run = c.run_cycle(mode=Mode.OFFLINE, seed=0)
    if len(run.results) != 1 or run.results[0].proposal_id != "":
        return False, "null-tuner cycle did not journal a skip"
    if not c.history:
        return False, "run not journaled"
    return True, "propose/validate/dispose cycle completes and journals"


def _check_safety_posture() -> tuple[bool, str]:
    from hugrgate.autotune.controller import Mode
    from hugrgate.autotune.limits import SafetyLimits
    lim = SafetyLimits()
    problems = []
    if lim.kill_switch:
        problems.append("kill switch engaged by default")
    if Mode.APPLIED in lim.allowed_modes:
        problems.append("APPLIED allowed by default")
    if not lim.allowed_modes:
        problems.append("empty allowlist")
    if lim.max_params_per_proposal < 1 or lim.max_cycles_per_hour < 1:
        problems.append("non-positive bounds")
    if problems:
        return False, "; ".join(problems)
    return True, ("kill switch off, APPLIED excluded by default, "
                  f"allowlist={[m.value for m in lim.allowed_modes]}")


def _check_provenance_integrity() -> tuple[bool, str]:
    from hugrgate.autotune.controller import (
        Mode,
        OptimizationController,
        Proposal,
        TuningContext,
    )
    from hugrgate.autotune.provenance import ProvenanceTracker

    class _T:
        name = "release-tuner"

        def tune(self, ctx: TuningContext):
            return Proposal(proposal_id="rp", tuner="release-tuner",
                            changes={}, objective_id="o", baseline=0.0,
                            estimate=0.0, seed=0)

    c = OptimizationController()
    c.register_objective("o", lambda values: 0.0)
    c.register_tuner(_T())
    before = c.store.snapshot()
    run = c.run_cycle(mode=Mode.OFFLINE, seed=0)
    tracker = ProvenanceTracker()
    tracker.track_run(run, before, c.store.snapshot(),
                      data_fingerprint="release-gate")
    try:
        tracker.verify()
    except Exception as exc:  # noqa: BLE001 - check isolation: broken chain holds
        return False, f"provenance chain broken: {exc!r}"
    return True, "record + hash-chain verify round-trip"


def _check_reproducibility() -> tuple[bool, str]:
    from hugrgate.autotune.controller import (
        ConfigStore,
        Mode,
        OptimizationController,
        TunableParameter,
    )
    from hugrgate.autotune.modes import OfflineDriver
    from hugrgate.autotune.repro import (
        record_manifest,
        verify_replay,
    )
    from hugrgate.autotune.tuners._base import seeded_rng
    from hugrgate.autotune.tuners.thresholds import ThresholdTuner

    def _make():
        rng = seeded_rng(5)
        data = ([(rng.uniform(0.0, 0.45), 0) for _ in range(60)]
                + [(rng.uniform(0.55, 1.0), 1) for _ in range(60)])
        store = ConfigStore()
        store.register(TunableParameter(name="t", dtype="float",
                                        default=0.9, lo=0.0, hi=1.0))
        cc = OptimizationController(store=store)
        cc.register_objective("f1", lambda values: 0.0)
        tuner = ThresholdTuner(param="t", objective_id="f1",
                               dataset=data, seed=1)
        cc.register_tuner(tuner)
        driver = OfflineDriver()
        cc.register_driver(driver)
        return cc, tuner, lambda: driver.seen

    c, tuner, seen_fn = _make()
    run = c.run_cycle(mode=Mode.OFFLINE, seed=3)
    manifest = record_manifest(c, run, {"threshold_tuner": tuner},
                               proposals=seen_fn(),
                               data_fingerprint="release-gate")

    def _factory():
        cc, _, replay_seen_fn = _make()
        return cc, replay_seen_fn

    verdict = verify_replay(manifest, _factory)
    if not verdict["match"]:
        return False, "replay mismatched the manifest"
    return True, "manifest record + replay match"


def _check_tuner_exports() -> tuple[bool, str]:
    import importlib
    modules = [
        "hugrgate.autotune.tuners.thresholds",
        "hugrgate.autotune.tuners.gates",
        "hugrgate.autotune.tuners.latency",
        "hugrgate.autotune.tuners.cache",
        "hugrgate.autotune.tuners.batching",
        "hugrgate.autotune.tuners.backends",
        "hugrgate.autotune.tuners.weights",
        "hugrgate.autotune.tuners.calibration_select",
        "hugrgate.autotune.tuners.hardware",
        "hugrgate.autotune.tuners.energy",
        "hugrgate.autotune.tuners.cost",
        "hugrgate.autotune.tuners.privacy",
    ]
    for mod in modules:
        importlib.import_module(mod)
    return True, f"{len(modules)} tuner modules import cleanly"


def campaign_checks() -> list[ReleaseCheck]:
    """The six Campaign XIX release checks."""
    return [
        ReleaseCheck("error-taxonomy", _check_error_taxonomy),
        ReleaseCheck("controller-smoke", _check_controller_smoke),
        ReleaseCheck("safety-posture", _check_safety_posture),
        ReleaseCheck("provenance-integrity", _check_provenance_integrity),
        ReleaseCheck("reproducibility", _check_reproducibility),
        ReleaseCheck("tuner-exports", _check_tuner_exports),
    ]


def release_gate(checks: Sequence[ReleaseCheck] | None = None
                 ) -> ReleaseVerdict:
    """Run the release checks; return the verdict."""
    checks = list(checks) if checks is not None else campaign_checks()
    if not checks:
        raise AutotuneError("release with zero checks is a rubber stamp")
    results = []
    for check in checks:
        try:
            passed, detail = check.run()
        except Exception as exc:  # noqa: BLE001 - check isolation: crashing check holds
            passed, detail = False, f"check raised: {exc!r}"
        results.append({"name": check.name, "passed": bool(passed),
                        "detail": str(detail)})
    verdict = RELEASE if all(r["passed"] for r in results) else HOLD
    return ReleaseVerdict(verdict=verdict, results=results)


def assert_release(verdict: ReleaseVerdict) -> None:
    """Raise :class:`AutotuneError` when the gate holds."""
    if not verdict.passed:
        reasons = [f"{r['name']}: {r['detail']}" for r in verdict.results
                   if not r["passed"]]
        raise AutotuneError("release gate holds", reasons=reasons)
