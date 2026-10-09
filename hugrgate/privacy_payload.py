"""Remote payload compiler — the outbound chokepoint. Slice 237.

Every byte that leaves the process for a remote backend passes
through :class:`RemotePayloadCompiler.compile`. The compilation is
a fixed, ordered pipeline; each stage is recorded in the
:attr:`RemotePayload.manifest` so any payload is auditable
after the fact:

1. **attempt gate** — ``PrivacyGuard.check_backend`` (guard mode,
   class trust floor, jurisdiction); raises on denial;
2. **local-only enforcement** — strip (or strict-raise) local-only
   fields first, so strict mode fires before any other stage can
   silently drop them;
3. **data-flow policy** — ``DataFlowPolicy.check`` on the planned
   flow; ``redact`` decisions strip the named fields;
4. **minimization** — project to the backend's keep-list;
5. **clearance filter** — drop fields above the remote clearance;
6. **secret scan** — raise ``SecretDetected`` on any hit;
7. **PII scrub** — mask/drop PII findings;
8. **redaction pipeline** — per-field / per-level strategies.

Local backends bypass compilation (the data never leaves the
process) and get a passthrough manifest. Compilation is
deterministic: the same inputs always produce the same payload and
manifest.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from hugrgate.backend import Backend
from hugrgate.policy import DecisionPolicy
from hugrgate.privacy import PrivacyGuard
from hugrgate.privacy_flow import DataFlowPolicy, FlowRequest
from hugrgate.privacy_labels import FieldLabels, filter_by_clearance
from hugrgate.privacy_minimize import MinimizationPolicy
from hugrgate.privacy_pii import PIIDetector, PIIScrubber, RegexPIIDetector
from hugrgate.privacy_redact import RedactionPipeline

__all__ = [
    "RemotePayload",
    "RemotePayloadCompiler",
]


@dataclass
class RemotePayload:
    """Compiled outbound payload plus its audit manifest."""

    payload: dict[str, Any]
    manifest: dict[str, Any]
    backend: str = ""
    remote: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"payload": copy.deepcopy(self.payload),
                "manifest": copy.deepcopy(self.manifest),
                "backend": self.backend, "remote": self.remote}


class RemotePayloadCompiler:
    """Compiles outbound state for remote backends (see module docs).

    Parameters
    ----------
    guard:
        The :class:`~hugrgate.privacy.PrivacyGuard` supplying
        backend gates, trust levels, and jurisdictions. Required.
    flow_policy:
        Data-flow rules; defaults to ``DataFlowPolicy()``.
    labels:
        Field sensitivity labels; defaults to all-``PUBLIC``.
    minimization:
        Optional per-backend keep-lists.
    pii_detector:
        PII detector for the scrub stage; defaults to
        :class:`RegexPIIDetector`. ``None`` selects the default.
    pii_scrub:
        Set False to disable PII scrubbing entirely.
    pii_action:
        ``"mask"`` or ``"drop"`` for the PII scrubber.
    redaction_pipeline:
        Optional final redaction stage.
    local_only_strict:
        Raise on local-only fields instead of stripping them.
    """

    def __init__(self, guard: PrivacyGuard,
                 flow_policy: DataFlowPolicy | None = None,
                 labels: FieldLabels | None = None,
                 minimization: MinimizationPolicy | None = None,
                 pii_detector: PIIDetector | None = None,
                 pii_scrub: bool = True,
                 pii_action: str = "mask",
                 redaction_pipeline: RedactionPipeline | None = None,
                 local_only_strict: bool = False):
        self.guard = guard
        self.flow_policy = flow_policy or DataFlowPolicy()
        self.labels = labels or FieldLabels()
        self.minimization = minimization
        if pii_scrub:
            self.pii_scrubber: PIIScrubber | None = PIIScrubber(
                pii_detector or RegexPIIDetector(), action=pii_action)
        else:
            self.pii_scrubber = None
        self.redaction_pipeline = redaction_pipeline
        self.local_only_strict = local_only_strict

    # -- main entry ----------------------------------------------------

    def compile(self, state: Mapping[str, Any], *,
                backend: Backend, policy: DecisionPolicy) -> RemotePayload:
        """Compile ``state`` into a remote-bound payload.

        Raises
        ------
        PrivacyViolation
            Backend blocked by guard, class, trust, or jurisdiction.
        DataFlowDenied
            The data-flow policy denied the planned flow.
        SecretDetected
            A secret-shaped value was found in the outbound data.
        LocalOnlyViolation
            Strict mode and a local-only field was present.
        """
        manifest: dict[str, Any] = {
            "backend": backend.name,
            "remote": backend.is_remote,
            "privacy_class": policy.privacy_class,
            "stages": [],
        }

        # Local backends: data never leaves the process — passthrough.
        if not backend.is_remote:
            manifest["stages"].append("local-passthrough")
            manifest["trust_level"] = self.guard.trust_level_for(backend)
            return RemotePayload(payload=copy.deepcopy(dict(state)),
                                 manifest=manifest,
                                 backend=backend.name, remote=False)

        manifest["trust_level"] = self.guard.trust_level_for(backend)
        manifest["jurisdiction"] = self.guard.jurisdiction_for(backend)

        # Stage 1 — attempt gate.
        self.guard.check_backend(backend, policy)
        manifest["stages"].append("attempt-gate:pass")

        working = copy.deepcopy(dict(state))

        # Stage 2 — local-only enforcement (before the flow policy, so
        # strict mode raises instead of being silently stripped).
        lo_result = self.guard.enforce_local_only(
            working, self.labels, backend, strict=self.local_only_strict)
        working = lo_result.state
        manifest["local_only_stripped"] = lo_result.stripped
        manifest["stages"].append("local-only:stripped" if lo_result.stripped
                                  else "local-only:clean")

        # Stage 3 — data-flow policy.
        flow_request = FlowRequest(
            privacy_class=policy.privacy_class,
            dst_name=backend.name,
            dst_remote=True,
            dst_trust=manifest["trust_level"],
            dst_jurisdiction=manifest["jurisdiction"],
            field_levels=self.labels.label_state(working),
            local_only_fields=[
                p for p in self.labels.label_state(working)
                if self.labels.is_local_only(p)],
            jurisdictions_allowed=self.guard.jurisdictions_allowed)
        decision = self.flow_policy.check(flow_request)  # raises on deny
        manifest["flow"] = {"action": decision.action,
                            "reasons": decision.reasons,
                            "redactions": decision.redactions}
        manifest["stages"].append(f"data-flow:{decision.action}")
        if decision.action == "redact":
            working = self._strip_paths(working, decision.redactions)

        # Stage 4 — minimization.
        if self.minimization is not None:
            working, min_report = self.minimization.minimize(
                working, backend.name)
            manifest["minimization"] = {
                "kept": min_report.kept, "dropped": min_report.dropped}
            manifest["stages"].append("minimization:applied")
        else:
            manifest["stages"].append("minimization:skipped")

        # Stage 5 — clearance filter.
        clearance = self.flow_policy.max_remote_level
        before = self._leaf_paths(working)
        working = filter_by_clearance(working, self.labels, clearance,
                                      drop_local_only=True)
        manifest["clearance"] = str(clearance)
        manifest["clearance_dropped"] = sorted(set(before)
                                               - set(self._leaf_paths(working)))
        manifest["stages"].append("clearance:applied")

        # Stage 6 — secret scan (raises SecretDetected).
        self.guard.check_no_secrets(working)
        manifest["stages"].append("secret-scan:clean")

        # Stage 7 — PII scrub.
        if self.pii_scrubber is not None:
            working, pii_findings = self.pii_scrubber.scrub_state(working)
            manifest["pii_findings"] = [f.to_dict()
                                        for f in pii_findings]
            manifest["stages"].append(
                f"pii-scrub:{len(pii_findings)}-findings")
        else:
            manifest["stages"].append("pii-scrub:disabled")

        # Stage 8 — redaction pipeline.
        if self.redaction_pipeline is not None:
            working, applied = self.redaction_pipeline.apply_with_labels(
                working, self.labels)
            manifest["redactions_applied"] = applied
            manifest["stages"].append("redaction:applied")
        else:
            manifest["stages"].append("redaction:skipped")

        return RemotePayload(payload=working, manifest=manifest,
                             backend=backend.name, remote=True)

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _leaf_paths(state: Mapping[str, Any]) -> list[str]:
        paths: list[str] = []

        def walk(node: Any, prefix: str) -> None:
            if isinstance(node, Mapping):
                for key, value in node.items():
                    path = f"{prefix}.{key}" if prefix else str(key)
                    if isinstance(value, Mapping):
                        walk(value, path)
                    else:
                        paths.append(path)

        walk(state, "")
        return paths

    @classmethod
    def _strip_paths(cls, state: dict[str, Any],
                     paths: list[str]) -> dict[str, Any]:
        """Remove dotted paths from a nested dict (pruning empties)."""
        out = copy.deepcopy(state)
        for path in paths:
            parts = tuple(path.split("."))
            node = out
            trail: list[tuple[dict, str]] = []
            for part in parts:
                if not isinstance(node, dict) or part not in node:
                    break
                trail.append((node, part))
                node = node[part]
            else:
                parent, key = trail[-1]
                del parent[key]
                for parent, key in reversed(trail[:-1]):
                    child = parent[key]
                    if isinstance(child, dict) and not child:
                        del parent[key]
                    else:
                        break
        return out
