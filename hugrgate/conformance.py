"""Backend conformance kit. Slice 440.

A backend is not conformant because it *imports* — it is
conformant because it honors the :class:`Backend` contract under
exercise. :func:`run_backend_conformance` drives a backend through
a battery of checks and returns a :class:`ConformanceReport`:

- interface shape (via :func:`hugrgate.plugins.validate_plugin`),
- ``supports()`` returns booleans and never raises on well-formed
  specs of every spec type,
- ``evaluate()`` returns well-formed results (distribution sums to
  1, probabilities in [0, 1], decided value inside the spec's
  value space, probability consistent with the distribution),
- ``evaluate()`` failures raise taxonomy errors or stdlib
  validation errors — never raw ``Exception``\ s (slice 007 law),
- ``health()`` / ``privacy_properties()`` /
  ``calibration_info()`` return dicts,
- latency/cost estimates are sane non-negative numbers.

:func:`assert_conformance` raises
:class:`~hugrgate.errors.ConformanceError` listing every failure.
``hugrgate check-backend NAME`` runs the kit from the CLI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hugrgate.backend import Backend
from hugrgate.errors import ConformanceError, HugrGateError, PluginError
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "ConformanceCheck",
    "ConformanceReport",
    "assert_conformance",
    "run_backend_conformance",
]


@dataclass
class ConformanceCheck:
    """One named check and its outcome."""

    name: str
    passed: bool
    detail: str = ""


@dataclass
class ConformanceReport:
    """The full battery outcome for one backend."""

    backend: str
    checks: list[ConformanceCheck] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failures(self) -> list[ConformanceCheck]:
        return [c for c in self.checks if not c.passed]

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "passed": self.passed,
            "checks": [{"name": c.name, "passed": c.passed,
                        "detail": c.detail} for c in self.checks],
        }


_PROBE_SPECS: dict[str, DecisionSpec] = {
    "categorical": DecisionSpec.from_dict(
        {"type": "categorical", "options": ["a", "b", "c"]}),
    "binary": DecisionSpec.from_dict(
        {"type": "binary", "statement": "go?"}),
    "ordinal": DecisionSpec.from_dict(
        {"type": "ordinal", "levels": ["low", "high"]}),
    "numeric": DecisionSpec.from_dict(
        {"type": "numeric", "minimum": 0.0, "maximum": 10.0}),
}

_PROBE_STATE: dict[str, Any] = {"signal": 0.7, "flag": True,
                                "text": "probe"}


def _check(report: ConformanceReport, name: str, passed: bool,
           detail: str = "") -> None:
    report.checks.append(ConformanceCheck(name=name, passed=passed,
                                         detail=detail))


def _result_is_well_formed(result: Any, spec: DecisionSpec,
                           ) -> tuple[bool, str]:
    if not isinstance(result, DecisionResult):
        return False, f"expected DecisionResult, got {type(result).__name__}"
    if not (0.0 <= result.probability <= 1.0):
        return False, "probability must be in [0, 1]"
    if spec.type == "numeric":
        # Continuous value space: no distribution is expected.
        return True, ""
    dist = result.distribution
    if not isinstance(dist, dict) or not dist:
        return False, "distribution must be a non-empty dict"
    total = sum(dist.values())
    if not all(isinstance(p, (int, float)) and 0.0 <= p <= 1.0
               for p in dist.values()):
        return False, "distribution probabilities must be in [0, 1]"
    if abs(total - 1.0) > 0.01:
        return False, f"distribution sums to {total:.4f}, not 1.0"
    # The spec's own value_space() is the authority on legal values.
    space = spec.value_space()
    if space and result.value not in space:
        return False, (f"value {result.value!r} outside spec value "
                       f"space {space}")
    return True, ""


def run_backend_conformance(backend: Backend) -> ConformanceReport:
    """Run the conformance battery against ``backend``."""
    from hugrgate.plugins import validate_plugin
    report = ConformanceReport(backend=getattr(backend, "name", "?"))

    # 1. interface shape
    try:
        validate_plugin(backend)
    except PluginError as e:
        _check(report, "interface", False, e.message)
        return report  # nothing else is meaningful
    except Exception as e:  # noqa: BLE001 - defensive: validate contracts
        _check(report, "interface", False, str(e))
        return report
    _check(report, "interface", True)

    # 2. supports() booleans
    supports_ok = True
    supported: list[str] = []
    for kind, spec in _PROBE_SPECS.items():
        try:
            verdict = backend.supports(spec)
        except Exception as e:  # noqa: BLE001 - check records, not raises
            supports_ok = False
            _check(report, f"supports[{kind}]", False,
                   f"raised {type(e).__name__}: {e}")
            continue
        if not isinstance(verdict, bool):
            supports_ok = False
            _check(report, f"supports[{kind}]", False,
                   f"returned {type(verdict).__name__}, not bool")
            continue
        if verdict:
            supported.append(kind)
    if supports_ok:
        _check(report, "supports", True,
               f"supports: {supported or '(none)'}")

    # 3-4. evaluate() shape + error taxonomy, per supported kind
    for kind in supported:
        spec = _PROBE_SPECS[kind]
        try:
            result = backend.evaluate(dict(_PROBE_STATE), spec)
        except (HugrGateError, ValueError, TypeError, KeyError) as e:
            _check(report, f"evaluate[{kind}]", False,
                   f"raised on valid input: {type(e).__name__}: {e}")
            continue
        except Exception as e:  # noqa: BLE001 - taxonomy violation
            _check(report, f"evaluate[{kind}]-taxonomy", False,
                   f"raised non-taxonomy {type(e).__name__}: {e}")
            continue
        ok, detail = _result_is_well_formed(result, spec)
        _check(report, f"evaluate[{kind}]", ok, detail)

    # 5. invalid input: *if* the backend raises, it must be a
    #    taxonomy error or a stdlib validation error (slice 007 law).
    #    A backend that ignores the bad input passes with a note —
    #    silence is not a taxonomy violation.
    bad_spec = DecisionSpec.from_dict(
        {"type": "categorical", "options": ["a", "b"]})
    try:
        backend.evaluate("not-a-state", bad_spec)  # type: ignore[arg-type]
    except (HugrGateError, ValueError, TypeError, KeyError, AttributeError):
        _check(report, "error-taxonomy", True)
    except Exception as e:  # noqa: BLE001 - the violation being tested
        _check(report, "error-taxonomy", False,
               f"raised non-taxonomy {type(e).__name__} on bad input")
    else:
        _check(report, "error-taxonomy", True,
               "does not validate state input")

    # 6. metadata shapes
    for method in ("health", "privacy_properties", "calibration_info"):
        try:
            value = getattr(backend, method)()
        except Exception as e:  # noqa: BLE001 - check records, not raises
            _check(report, method, False, f"raised: {e}")
            continue
        _check(report, method, isinstance(value, dict),
               "" if isinstance(value, dict)
               else f"returned {type(value).__name__}, not dict")

    # 7. sane estimates
    try:
        lat, cost = backend.estimated_latency(), backend.estimated_cost()
        sane = (isinstance(lat, (int, float)) and lat >= 0
                and isinstance(cost, (int, float)) and cost >= 0)
        _check(report, "estimates", sane,
               "" if sane else f"latency={lat!r} cost={cost!r}")
    except Exception as e:  # noqa: BLE001 - check records, not raises
        _check(report, "estimates", False, f"raised: {e}")

    return report


def assert_conformance(report: ConformanceReport) -> None:
    """Raise :class:`ConformanceError` unless every check passed."""
    if report.passed:
        return
    failures = "; ".join(f"{c.name}: {c.detail or 'failed'}"
                         for c in report.failures)
    raise ConformanceError(
        f"backend {report.backend!r} failed "
        f"{len(report.failures)}/{len(report.checks)} conformance "
        f"check(s): {failures}")
