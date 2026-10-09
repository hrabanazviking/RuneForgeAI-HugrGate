"""Contract conformance kit — behavioral checks for templates.

Gjallarbrú slice 441.

:func:`lint_template` judges whether a template is *well-built*;
this kit proves a template *behaves*: it instantiates across its
parameter space, rejects what it must reject, and every instance
it produces is a valid, round-trippable, lint-clean contract.

- :func:`run_template_conformance` — the battery.
- :func:`run_contract_conformance` — the instance-level battery
  (round-trip, lint-clean, value validation sane).
- :func:`assert_conformance` — raise
  :class:`~hugrgate.errors.ConformanceError` on any failure.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from hugrgate.contracts.lint import ERROR, lint_contract, lint_template
from hugrgate.contracts.schema import DecisionContract, contract_from_dict
from hugrgate.contracts.templates import ContractTemplate
from hugrgate.errors import ConformanceError, ContractError

__all__ = [
    "TemplateConformanceCheck",
    "TemplateConformanceReport",
    "assert_conformance",
    "run_contract_conformance",
    "run_template_conformance",
]


@dataclass
class TemplateConformanceCheck:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class TemplateConformanceReport:
    template_id: str
    checks: list[TemplateConformanceCheck] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failures(self) -> list[TemplateConformanceCheck]:
        return [c for c in self.checks if not c.passed]

    def to_dict(self) -> dict[str, Any]:
        return {
            "template_id": self.template_id,
            "passed": self.passed,
            "checks": [{"name": c.name, "passed": c.passed,
                        "detail": c.detail} for c in self.checks],
        }


def _check(report: TemplateConformanceReport, name: str, passed: bool,
           detail: str = "") -> None:
    report.checks.append(TemplateConformanceCheck(
        name=name, passed=passed, detail=detail))


def _boundary_values(param: Any) -> list[Any]:
    """Interesting values for one declared parameter."""
    values: list[Any] = []
    if param.allowed:
        values.extend(param.allowed)
    if param.default is not None:
        values.append(param.default)
    if param.type == "string":
        values += ["", "x" * 256]
    elif param.type == "integer":
        values += [0, -1, 10 ** 9]
    elif param.type == "number":
        values += [0.0, -1.5, 1e9]
    elif param.type == "boolean":
        values += [True, False]
    elif param.type == "array":
        values += [[], ["a", "b"]]
    # dedupe preserving order; unhashable values compared by repr
    seen: list[str] = []
    unique: list[Any] = []
    for v in values:
        key = repr(v)
        if key not in seen:
            seen.append(key)
            unique.append(v)
    return unique


def _wrong_type_value(param: Any) -> Any:
    """A value guaranteed to violate the declared type."""
    return {"string": {"not": "a string"},
            "number": "not-a-number",
            "integer": 1.5,
            "boolean": "not-a-bool",
            "array": "not-an-array",
            "object": [1, 2, 3]}.get(param.type, None)


def _random_value(rng: random.Random, param: Any) -> Any:
    if param.allowed:
        return rng.choice(list(param.allowed))
    if param.type == "string":
        return rng.choice(["alpha", "beta", ""])
    if param.type == "integer":
        return rng.randint(-5, 100)
    if param.type == "number":
        return rng.uniform(-5.0, 100.0)
    if param.type == "boolean":
        return rng.choice([True, False])
    if param.type == "array":
        return [rng.choice(["a", "b", "c"])
                for _ in range(rng.randint(0, 3))]
    if param.type == "object":
        return {"k": rng.randint(0, 9)}
    return rng.randint(0, 9)


def _defaults(template: ContractTemplate) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for name, param in template.parameters.items():
        if param.default is not None:
            params[name] = param.default
        elif param.allowed:
            params[name] = param.allowed[0]
        elif not param.required:
            continue
        else:
            params[name] = _random_value(random.Random(0), param)
    return params


def run_template_conformance(template: ContractTemplate,
                             fuzz_runs: int = 25,
                             seed: int = 441) -> TemplateConformanceReport:
    """Run the conformance battery against one template."""
    report = TemplateConformanceReport(
        template_id=template.template_id or "?")

    # 1. template shape
    if not template.template_id or not isinstance(
            template.template_id, str):
        _check(report, "template-shape", False,
               "template_id must be a non-empty string")
        return report
    _check(report, "template-shape", True,
           f"{len(template.parameters)} parameter(s)")

    # 2. lint must be ERROR-clean
    try:
        lint_report = lint_template(template)
        errors = [f for f in lint_report.findings
                  if f.severity == ERROR]
    except ContractError as e:
        _check(report, "lint-clean", False, str(e))
        return report
    _check(report, "lint-clean", not errors,
           "" if not errors else
           "; ".join(f.message for f in errors))

    # 3. defaults instantiate to a valid contract
    try:
        contract = template.instantiate(**_defaults(template))
    except ContractError as e:
        _check(report, "instantiate-defaults", False, str(e))
        return report  # nothing else is meaningful
    _check(report, "instantiate-defaults", True,
           type(contract).__name__)

    # 4. every allowed value instantiates
    bad_allowed: list[str] = []
    for name, param in template.parameters.items():
        for value in param.allowed:
            probe = _defaults(template)
            probe[name] = value
            try:
                template.instantiate(**probe)
            except ContractError as e:
                bad_allowed.append(f"{name}={value!r}: {e}")
    _check(report, "instantiate-allowed-values", not bad_allowed,
           "" if not bad_allowed else "; ".join(bad_allowed[:5]))

    # 5. boundary values instantiate (or are rejected as ContractError —
    #    both are conformant; a crash or silent garbage is not)
    bad_boundary: list[str] = []
    for name, param in template.parameters.items():
        for value in _boundary_values(param):
            probe = _defaults(template)
            probe[name] = value
            try:
                template.instantiate(**probe)
            except ContractError:
                pass  # rejection is conformant
            except Exception as e:  # noqa: BLE001 - the violation
                bad_boundary.append(
                    f"{name}={value!r} raised {type(e).__name__}")
    _check(report, "instantiate-boundaries", not bad_boundary,
           "" if not bad_boundary else "; ".join(bad_boundary[:5]))

    # 6. unknown parameters are rejected
    try:
        template.instantiate(**{**_defaults(template),
                                 "__nope__": 1})
    except ContractError:
        _check(report, "rejects-unknown-params", True)
    except Exception as e:  # noqa: BLE001 - the violation
        _check(report, "rejects-unknown-params", False,
               f"raised {type(e).__name__} instead of ContractError")
    else:
        _check(report, "rejects-unknown-params", False,
               "silently accepted an unknown parameter")

    # 7. wrong types are rejected per parameter
    bad_types: list[str] = []
    for name, param in template.parameters.items():
        if param.type == "any":
            continue
        probe = _defaults(template)
        probe[name] = _wrong_type_value(param)
        try:
            template.instantiate(**probe)
        except ContractError:
            pass
        except Exception as e:  # noqa: BLE001 - the violation
            bad_types.append(f"{name} raised {type(e).__name__}")
        else:
            bad_types.append(f"{name} accepted a wrong-typed value")
    _check(report, "rejects-wrong-types", not bad_types,
           "" if not bad_types else "; ".join(bad_types[:5]))

    # 8. missing required parameters are rejected
    missing_ok = True
    missing_detail = ""
    for name, param in template.parameters.items():
        if not param.required:
            continue
        probe = {k: v for k, v in _defaults(template).items()
                 if k != name}
        try:
            template.instantiate(**probe)
        except ContractError:
            pass
        except Exception as e:  # noqa: BLE001 - the violation
            missing_ok = False
            missing_detail = f"{name} raised {type(e).__name__}"
            break
        else:
            missing_ok = False
            missing_detail = f"{name} accepted without a value"
            break
    _check(report, "rejects-missing-required", missing_ok,
           missing_detail)

    # 9. seeded fuzz: random instantiations all validate
    rng = random.Random(seed)
    fuzz_bad: list[str] = []
    for i in range(fuzz_runs):
        probe = {name: _random_value(rng, param)
                 for name, param in template.parameters.items()}
        try:
            made = template.instantiate(**probe)
            contract_from_dict(made.to_dict())
        except ContractError:
            pass  # rejection is conformant
        except Exception as e:  # noqa: BLE001 - the violation
            fuzz_bad.append(f"run {i}: {type(e).__name__}: {e}")
            if len(fuzz_bad) >= 5:
                break
    _check(report, "fuzz-instantiations", not fuzz_bad,
           "" if not fuzz_bad else "; ".join(fuzz_bad))

    return report


def run_contract_conformance(
        contract: DecisionContract) -> TemplateConformanceReport:
    """Instance-level battery: round-trip, lint-clean, value checks."""
    report = TemplateConformanceReport(
        template_id=getattr(contract, "contract_id", "?") or "?")

    # round-trip through the validated serde path
    try:
        rebuilt = contract_from_dict(contract.to_dict())
    except ContractError as e:
        _check(report, "round-trip", False, str(e))
        return report
    _check(report, "round-trip", True, type(rebuilt).__name__)

    # lint ERROR-clean
    try:
        findings = [f for f in lint_contract(contract).findings
                    if f.severity == ERROR]
    except ContractError as e:
        _check(report, "lint-clean", False, str(e))
        return report
    _check(report, "lint-clean", not findings,
           "" if not findings else "; ".join(f.message for f in findings))

    # check_value returns a list (possibly empty) and never raises
    # on arbitrary input
    try:
        problems = contract.check_value(object())
    except Exception as e:  # noqa: BLE001 - the violation
        _check(report, "check-value-robust", False,
               f"raised {type(e).__name__}: {e}")
    else:
        _check(report, "check-value-robust",
               isinstance(problems, list),
               "" if isinstance(problems, list)
               else f"returned {type(problems).__name__}")
    return report


def assert_conformance(report: TemplateConformanceReport) -> None:
    """Raise :class:`ConformanceError` unless every check passed."""
    if report.passed:
        return
    failures = "; ".join(f"{c.name}: {c.detail or 'failed'}"
                         for c in report.failures)
    raise ConformanceError(
        f"template {report.template_id!r} failed "
        f"{len(report.failures)}/{len(report.checks)} conformance "
        f"check(s): {failures}")
