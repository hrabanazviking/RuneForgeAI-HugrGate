"""Privacy dry-run mode. Slice 245.

:func:`PrivacyDryRun.evaluate` simulates the entire outbound
privacy pipeline for a decision — attempt gate, local-only
stripping, the remote payload compiler (flow policy,
minimization, clearance, secret scan, PII scrub, redaction) —
without executing it: nothing is sent, nothing is cached, the
input state is not mutated. The returned :class:`DryRunReport`
says exactly what *would* happen, stage by stage, so operators
can preview the effect of policy changes before they bite.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from hugrgate.errors import HugrGateError
from hugrgate.privacy import PrivacyGuard

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Mapping

    from hugrgate.backend import Backend
    from hugrgate.policy import DecisionPolicy
    from hugrgate.privacy_labels import FieldLabels

__all__ = ["DryRunReport", "DryRunStage", "PrivacyDryRun"]


@dataclass
class DryRunStage:
    """One simulated pipeline stage."""

    stage: str
    action: str  # "allow" | "deny" | "strip" | "passthrough"
    reason: str
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"stage": self.stage, "action": self.action,
                "reason": self.reason, "detail": dict(self.detail)}


@dataclass
class DryRunReport:
    """What the privacy pipeline *would* do for one decision."""

    backend: str
    allowed: bool
    stages: list[DryRunStage] = field(default_factory=list)
    stripped_fields: list[str] = field(default_factory=list)
    denied_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"backend": self.backend, "allowed": self.allowed,
                "stages": [s.to_dict() for s in self.stages],
                "stripped_fields": list(self.stripped_fields),
                "denied_reason": self.denied_reason}

    def summary(self) -> str:
        lines = [f"dry-run: backend={self.backend} "
                 f"allowed={self.allowed}"]
        for stage in self.stages:
            lines.append(f"  [{stage.stage}] {stage.action}: "
                         f"{stage.reason}")
        if self.stripped_fields:
            lines.append("  stripped: " + ", ".join(self.stripped_fields))
        if self.denied_reason:
            lines.append("  denied: " + self.denied_reason)
        return "\n".join(lines)


class PrivacyDryRun:
    """Simulates the outbound privacy pipeline for a decision.

    Parameters
    ----------
    guard:
        The :class:`~hugrgate.privacy.PrivacyGuard` whose pipeline
        is simulated. Its configured payload compiler (if any) is
        used; nothing is executed or sent.
    """

    def __init__(self, guard: PrivacyGuard):
        self.guard = guard

    def evaluate(self, state: Mapping[str, Any], *,
                 backend: Backend, policy: DecisionPolicy,
                 labels: FieldLabels | None = None) -> DryRunReport:
        """Simulate the pipeline; never raises for policy denials."""
        snapshot = copy.deepcopy(dict(state))
        report = DryRunReport(backend=backend.name, allowed=False)

        # Stage 1 — attempt gate.
        try:
            self.guard.check_backend(backend, policy)
        except HugrGateError as e:
            report.stages.append(DryRunStage(
                "attempt_gate", "deny",
                f"{e.code}: {e.message}", {"code": e.code}))
            report.denied_reason = f"{e.code}: {e.message}"
            return report
        report.stages.append(DryRunStage("attempt_gate", "allow",
                                         "backend passed attempt gate"))

        # Stage 2 — local-only enforcement (mirror compiler strictness).
        compiler = self.guard.payload_compiler
        if labels is not None and backend.is_remote:
            strict = bool(compiler and getattr(compiler,
                                               "local_only_strict", False))
            try:
                result = self.guard.enforce_local_only(
                    state, labels, backend, strict=strict)
            except HugrGateError as e:
                report.stages.append(DryRunStage(
                    "local_only", "deny",
                    f"{e.code}: {e.message}", {"code": e.code}))
                report.denied_reason = f"{e.code}: {e.message}"
                return report
            if result.stripped:
                report.stripped_fields.extend(result.stripped)
                report.stages.append(DryRunStage(
                    "local_only", "strip",
                    f"{len(result.stripped)} local-only field(s) would "
                    f"be stripped",
                    {"stripped": list(result.stripped)}))
            else:
                report.stages.append(DryRunStage(
                    "local_only", "allow", "no local-only fields present"))

        # Stage 3 — full payload compile (or secret scan alone).
        if compiler is not None:
            try:
                payload = compiler.compile(state, backend=backend,
                                           policy=policy)
            except HugrGateError as e:
                report.stages.append(DryRunStage(
                    "payload_compile", "deny",
                    f"{e.code}: {e.message}", {"code": e.code}))
                report.denied_reason = f"{e.code}: {e.message}"
                return report
            detail = {"stages": list(
                payload.manifest.get("stages", [])),
                      "payload_bytes": len(
                          repr(payload.payload).encode("utf-8"))}
            report.stages.append(DryRunStage(
                "payload_compile", "allow",
                "payload would compile cleanly", detail))
        else:
            try:
                self.guard.check_no_secrets(state)
            except HugrGateError as e:
                report.stages.append(DryRunStage(
                    "secret_scan", "deny",
                    f"{e.code}: {e.message}", {"code": e.code}))
                report.denied_reason = f"{e.code}: {e.message}"
                return report
            report.stages.append(DryRunStage("secret_scan", "allow",
                                             "no secrets detected"))

        if dict(state) != snapshot:
            # Defensive: simulation must be side-effect free.
            report.stages.append(DryRunStage(
                "integrity", "deny",
                "simulation mutated the input state (bug)"))
            report.denied_reason = "dry-run mutated input state"
            return report

        report.allowed = True
        return report
