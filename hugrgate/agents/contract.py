"""Agent Nervous System (Campaign XVI) — the agent integration contract.

Slice 376.  No agent joins the nervous system without a declared
contract: who it is, what it can do (capabilities), what it
understands (intents), what tools it may touch, the shape of its
inputs/outputs, its SLOs, and its privacy clearance.  The contract
is the trust anchor every later slice builds on — routers check
capabilities (378/379/387), gates check clearance (380/381/390),
and the release gate (400) refuses to ship agents with invalid
contracts.

:class:`AgentContract` is a frozen dataclass so a validated
contract is tamper-evident in memory; :func:`assert_contract`
raises :class:`AgentContractViolation` naming every violation.
Input/output checking is structural (field presence + declared
scalar types) — deep schema validation belongs to
:mod:`hugrgate.validation`, which callers can layer on top.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from hugrgate.errors import AgentContractViolation
from hugrgate.privacy import PRIVACY_CLASS_ORDER

__all__ = [
    "SCHEMA_TYPES",
    "AgentContract",
    "assert_contract",
    "check_input",
    "check_output",
    "check_payload",
    "validate_contract",
]

#: Scalar type names accepted in input/output schemas.
SCHEMA_TYPES: tuple[str, ...] = ("str", "int", "float", "bool", "list", "dict")

_TYPE_CHECKS = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
}


@dataclass(frozen=True)
class AgentContract:
    """The integration contract one agent declares to the nervous system."""

    #: Stable agent id, e.g. ``"planner-01"``.
    agent_id: str
    #: Contract version, ``MAJOR.MINOR.PATCH``.
    version: str = "1.0.0"
    #: Capability tags the agent claims, e.g. ``("summarize", "classify")``.
    capabilities: tuple[str, ...] = ()
    #: Intent names the agent handles, e.g. ``("summarize.text",)``.
    intents: tuple[str, ...] = ()
    #: Tool names the agent may invoke, e.g. ``("web_search",)``.
    tools: tuple[str, ...] = ()
    #: Required input fields: name -> one of SCHEMA_TYPES.
    input_schema: Mapping[str, str] = field(default_factory=dict)
    #: Promised output fields: name -> one of SCHEMA_TYPES.
    output_schema: Mapping[str, str] = field(default_factory=dict)
    #: Latency SLO in milliseconds (must be > 0).
    max_latency_ms: float = 5000.0
    #: Cost SLO per decision in abstract cost units (must be >= 0).
    max_cost: float = 1.0
    #: Minimum acceptable confidence in [0, 1].
    min_confidence: float = 0.0
    #: Highest privacy class the agent may touch (privacy ladder name).
    privacy_clearance: str = "standard"
    #: How deep this agent may escalate (0 = never escalates).
    max_escalation_depth: int = 3

    def has_capability(self, capability: str) -> bool:
        """True when the agent declares ``capability``."""
        return capability in self.capabilities

    def handles_intent(self, intent: str) -> bool:
        """True when the agent declares ``intent``."""
        return intent in self.intents

    def may_use_tool(self, tool: str) -> bool:
        """True when the agent's contract allows ``tool``."""
        return tool in self.tools


def _check_version(version: str, violations: list[str]) -> None:
    parts = version.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        violations.append(
            f"version {version!r} must be MAJOR.MINOR.PATCH numeric"
        )


def validate_contract(contract: AgentContract) -> tuple[str, ...]:
    """Return every contract violation; empty tuple means valid.

    Pure (no raises) so registries and release gates can aggregate
    violations across many agents before deciding.
    """
    violations: list[str] = []
    if not contract.agent_id or not contract.agent_id.strip():
        violations.append("agent_id must be non-empty")
    _check_version(contract.version, violations)
    for name, values in (
        ("capabilities", contract.capabilities),
        ("intents", contract.intents),
        ("tools", contract.tools),
    ):
        if any(not v or not v.strip() for v in values):
            violations.append(f"{name} must not contain empty entries")
        if len(set(values)) != len(values):
            violations.append(f"{name} must not contain duplicates")
    for name, schema in (
        ("input_schema", contract.input_schema),
        ("output_schema", contract.output_schema),
    ):
        for fname, ftype in schema.items():
            if not fname or not fname.strip():
                violations.append(f"{name} must not contain empty field names")
            if ftype not in SCHEMA_TYPES:
                violations.append(
                    f"{name}[{fname!r}] type {ftype!r} not in {SCHEMA_TYPES}"
                )
    if not (contract.max_latency_ms > 0):
        violations.append("max_latency_ms must be > 0")
    if not (contract.max_cost >= 0):
        violations.append("max_cost must be >= 0")
    if not (0.0 <= contract.min_confidence <= 1.0):
        violations.append("min_confidence must be in [0, 1]")
    if contract.privacy_clearance not in PRIVACY_CLASS_ORDER:
        violations.append(
            f"privacy_clearance {contract.privacy_clearance!r} not on the "
            f"privacy ladder {PRIVACY_CLASS_ORDER}"
        )
    if contract.max_escalation_depth < 0:
        violations.append("max_escalation_depth must be >= 0")
    return tuple(violations)


def assert_contract(contract: AgentContract) -> None:
    """Validate ``contract``; raise :class:`AgentContractViolation` on failure."""
    violations = validate_contract(contract)
    if violations:
        raise AgentContractViolation(
            f"agent {contract.agent_id!r} contract invalid: "
            + "; ".join(violations),
            agent_id=contract.agent_id,
            violations=list(violations),
        )


def check_payload(
    schema: Mapping[str, str], payload: Mapping[str, Any], *, what: str
) -> tuple[str, ...]:
    """Structural check of ``payload`` against ``schema``.

    Returns missing-field and wrong-type violations; extra fields
    are allowed (contracts are permissive on input, strict on shape).
    ``int`` also accepts ``bool``-free ints only — ``bool`` is a
    subclass of ``int`` in Python, so it is explicitly excluded.
    """
    violations: list[str] = []
    for fname, ftype in schema.items():
        if fname not in payload:
            violations.append(f"{what}: missing field {fname!r}")
            continue
        value = payload[fname]
        expected = _TYPE_CHECKS[ftype]
        if ftype == "int" and isinstance(value, bool):
            violations.append(f"{what}: field {fname!r} must be int, got bool")
        elif ftype == "float" and isinstance(value, bool):
            violations.append(f"{what}: field {fname!r} must be float, got bool")
        elif not isinstance(value, expected):
            violations.append(
                f"{what}: field {fname!r} must be {ftype}, "
                f"got {type(value).__name__}"
            )
    return tuple(violations)


def check_input(
    contract: AgentContract, payload: Mapping[str, Any]
) -> tuple[str, ...]:
    """Check a caller payload against the contract's input schema."""
    return check_payload(contract.input_schema, payload, what="input")


def check_output(
    contract: AgentContract, payload: Mapping[str, Any]
) -> tuple[str, ...]:
    """Check an agent result against the contract's output schema."""
    return check_payload(contract.output_schema, payload, what="output")
