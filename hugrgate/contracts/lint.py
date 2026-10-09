"""Contract linting — static checks with severities.

Gjallarbrú slice 048.

Validation proves a contract is *well-formed*; linting judges whether it
is *well-built*. Degenerate configs slip past construction — a zero cost
matrix, an ordinal whose anchors all sit at one position, a
single-field composite, anchors that never span the scale — and then
silently do nothing in production. :func:`lint_contract` runs every
registered check and returns a :class:`LintReport` of :class:`LintFinding`\\ s
graded info / warning / error.

Checks are plain functions appended to :data:`LINT_CHECKS`, so teams can
add their own house rules:

>>> from hugrgate.contracts.lint import LINT_CHECKS, lint_contract
>>> LINT_CHECKS.append(lambda c: [])  # a no-op house rule

:func:`lint_template` applies the same discipline to contract templates
(unused parameters, undocumented parameters); :func:`lint_all` lints a
whole fleet of contracts at once.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from hugrgate.contracts.composite import CompositeContract
from hugrgate.contracts.cost import CostSensitiveContract
from hugrgate.contracts.deadlines import TimedContract
from hugrgate.contracts.distributions import DistributionContract
from hugrgate.contracts.explanations import ExplanationContract
from hugrgate.contracts.features import FeatureContract
from hugrgate.contracts.multilabel import MultilabelContract
from hugrgate.contracts.nested import NestedCategoricalContract
from hugrgate.contracts.ordinal import OrdinalContract
from hugrgate.contracts.schema import DecisionContract
from hugrgate.contracts.templates import ContractTemplate, find_placeholders
from hugrgate.contracts.uncertainty import NumericIntervalContract
from hugrgate.errors import ContractError

__all__ = [
    "ERROR",
    "INFO",
    "LINT_CHECKS",
    "WARNING",
    "LintFinding",
    "LintReport",
    "lint_all",
    "lint_contract",
    "lint_template",
    "register_check",
]

INFO = "info"
WARNING = "warning"
ERROR = "error"
_SEVERITIES = (INFO, WARNING, ERROR)

LintCheck = Callable[[DecisionContract], list["LintFinding"]]

#: Registered lint checks; append your own house rules.
LINT_CHECKS: list[LintCheck] = []


def register_check(func: LintCheck) -> LintCheck:
    """Register a custom lint check (also usable as a decorator)."""
    if not callable(func):
        raise ContractError("lint check must be callable",
                            code="bad_lint_check")
    LINT_CHECKS.append(func)
    return func


@dataclass(frozen=True)
class LintFinding:
    """One lint observation about a contract."""

    severity: str
    code: str
    message: str
    contract_id: str = ""

    def __post_init__(self) -> None:
        if self.severity not in _SEVERITIES:
            raise ContractError(
                f"bad lint severity: {self.severity!r}; use "
                f"{'/'.join(_SEVERITIES)}", code="bad_lint_severity")
        if not self.code:
            raise ContractError("lint finding needs a code",
                                code="bad_lint_finding")


@dataclass
class LintReport:
    """The findings of linting one contract (or many)."""

    findings: list[LintFinding] = field(default_factory=list)

    @property
    def errors(self) -> list[LintFinding]:
        return [f for f in self.findings if f.severity == ERROR]

    @property
    def warnings(self) -> list[LintFinding]:
        return [f for f in self.findings if f.severity == WARNING]

    @property
    def infos(self) -> list[LintFinding]:
        return [f for f in self.findings if f.severity == INFO]

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    @property
    def clean(self) -> bool:
        return not self.findings

    def by_severity(self) -> dict[str, list[LintFinding]]:
        return {INFO: self.infos, WARNING: self.warnings,
                ERROR: self.errors}

    def describe(self) -> str:
        if self.clean:
            return "lint: clean"
        lines = [f"lint: {len(self.errors)} error(s), "
                 f"{len(self.warnings)} warning(s), "
                 f"{len(self.infos)} info"]
        for f in self.findings:
            lines.append(f"  [{f.severity}] {f.code}: {f.message}")
        return "\n".join(lines)


def _find(cid: str, severity: str, code: str, message: str) -> LintFinding:
    return LintFinding(severity=severity, code=code, message=message,
                       contract_id=cid)


# --- generic checks ------------------------------------------------------------

def _check_documented(c: DecisionContract) -> list[LintFinding]:
    if not c.name and not c.description:
        return [_find(c.contract_id, WARNING, "undocumented",
                      "contract has neither name nor description")]
    return []


def _check_metadata(c: DecisionContract) -> list[LintFinding]:
    if not c.metadata:
        return [_find(c.contract_id, INFO, "no_metadata",
                      "contract carries no metadata (owner, version, "
                      "rationale)")]
    return []


def _check_nested(c: DecisionContract) -> list[LintFinding]:
    if not isinstance(c, NestedCategoricalContract):
        return []
    out: list[LintFinding] = []
    if len(c.options or []) == 1:
        out.append(_find(c.contract_id, WARNING, "single_option",
                         "categorical contract has a single option — "
                         "the decision is constant"))
    return out


def _check_ordinal(c: DecisionContract) -> list[LintFinding]:
    if not isinstance(c, OrdinalContract):
        return []
    out: list[LintFinding] = []
    anchors = c.anchors or {}
    if anchors:
        vals = sorted(anchors.values())
        if vals[0] > 0.25:
            out.append(_find(c.contract_id, WARNING, "anchors_not_grounded",
                             "lowest anchor is far above 0 — the scale "
                             "never reaches its floor"))
        if vals[-1] < 0.75:
            out.append(_find(c.contract_id, WARNING, "anchors_not_capped",
                             "highest anchor is far below 1 — the scale "
                             "never reaches its ceiling"))
    else:
        out.append(_find(c.contract_id, INFO, "default_anchors",
                         "no explicit anchors; ranks are evenly spaced"))
    return out


def _check_numeric(c: DecisionContract) -> list[LintFinding]:
    if not isinstance(c, NumericIntervalContract):
        return []
    out: list[LintFinding] = []
    width = c.maximum - c.minimum
    if c.max_width is not None and c.max_width >= width:
        out.append(_find(c.contract_id, WARNING, "vacuous_width_guard",
                         "max_width covers the whole range — the guard "
                         "can never fire"))
    return out


def _check_cost(c: DecisionContract) -> list[LintFinding]:
    if not isinstance(c, CostSensitiveContract):
        return []
    out: list[LintFinding] = []
    costs = [c.matrix.cost(a, b)
             for a in c.outcomes for b in c.outcomes]
    if all(v == 0 for v in costs):
        out.append(_find(c.contract_id, ERROR, "zero_cost_matrix",
                         "every cost is zero — the matrix cannot "
                         "distinguish any decision"))
    elif any(c.matrix.cost(o, o) != 0 for o in c.outcomes):
        out.append(_find(c.contract_id, WARNING, "nonzero_correct_cost",
                         "correct decisions carry cost — usually a "
                         "modelling slip"))
    return out


def _check_multilabel(c: DecisionContract) -> list[LintFinding]:
    if not isinstance(c, MultilabelContract):
        return []
    d = c.to_dict()
    rules = ("min_count", "max_count", "exact_count", "required",
             "forbidden", "implies", "excludes")
    if not any(k in d for k in rules):
        return [_find(c.contract_id, INFO, "no_cardinality_rules",
                      "multilabel contract has no cardinality rules — "
                      "any subset of labels is accepted")]
    return []


def _check_composite(c: DecisionContract) -> list[LintFinding]:
    if not isinstance(c, CompositeContract):
        return []
    if len(c.fields) < 2:
        return [_find(c.contract_id, WARNING, "single_branch",
                      "composite has fewer than two fields — "
                      "composition adds nothing")]
    return []


def _check_features(c: DecisionContract) -> list[LintFinding]:
    if not isinstance(c, FeatureContract):
        return []
    feats = c.features or []
    if feats and all(f.get("required", True) is False for f in feats):
        return [_find(c.contract_id, INFO, "all_features_optional",
                      "every feature is optional — the contract accepts "
                      "an empty input")]
    return []


def _check_distribution(c: DecisionContract) -> list[LintFinding]:
    if not isinstance(c, DistributionContract):
        return []
    if not c.constraints:
        return [_find(c.contract_id, WARNING, "no_constraints",
                      "distribution contract has no health constraints — "
                      "any distribution passes")]
    return []


def _check_explanation(c: DecisionContract) -> list[LintFinding]:
    if not isinstance(c, ExplanationContract):
        return []
    if (not c.required_fields and c.min_length == 0
            and c.min_reasons == 0):
        return [_find(c.contract_id, WARNING, "no_required_sections",
                      "explanation contract requires no fields, no "
                      "minimum length and no reasons — any text passes")]
    return []


def _check_timed(c: DecisionContract) -> list[LintFinding]:
    if not isinstance(c, TimedContract):
        return []
    out: list[LintFinding] = []
    now = time.time()
    if c.not_after is not None and c.not_after < now:
        out.append(_find(c.contract_id, WARNING, "window_in_past",
                         "the time window ends in the past — the deadline "
                         "can never be met going forward"))
    if c.not_before is not None and c.not_before < now and (
            c.not_after is None or c.not_after > now):
        out.append(_find(c.contract_id, INFO, "window_already_open",
                         "the time window opened in the past"))
    return out


LINT_CHECKS.extend([
    _check_documented,
    _check_metadata,
    _check_nested,
    _check_ordinal,
    _check_numeric,
    _check_cost,
    _check_multilabel,
    _check_composite,
    _check_features,
    _check_distribution,
    _check_explanation,
    _check_timed,
])


# --- entry points ------------------------------------------------------------

def lint_contract(contract: DecisionContract) -> LintReport:
    """Run every registered check against one contract."""
    if not isinstance(contract, DecisionContract):
        raise ContractError("lint_contract needs a DecisionContract",
                            code="bad_lint_target")
    findings: list[LintFinding] = []
    for check in LINT_CHECKS:
        findings.extend(check(contract))
    return LintReport(findings=findings)


def lint_template(template: ContractTemplate) -> LintReport:
    """Lint a contract template (parameter hygiene)."""
    if not isinstance(template, ContractTemplate):
        raise ContractError("lint_template needs a ContractTemplate",
                            code="bad_lint_target")
    findings: list[LintFinding] = []
    used = set(find_placeholders(template.body))
    for name, param in template.parameters.items():
        if name not in used:
            findings.append(LintFinding(
                INFO, "unused_parameter",
                f"parameter {name!r} is declared but never referenced",
                template.template_id))
        if not param.description:
            findings.append(LintFinding(
                WARNING, "undocumented_parameter",
                f"parameter {name!r} has no description",
                template.template_id))
    return LintReport(findings=findings)


def lint_all(contracts: Iterable[DecisionContract]) -> LintReport:
    """Lint a fleet of contracts into one report."""
    findings: list[LintFinding] = []
    for contract in contracts:
        findings.extend(lint_contract(contract).findings)
    return LintReport(findings=findings)
