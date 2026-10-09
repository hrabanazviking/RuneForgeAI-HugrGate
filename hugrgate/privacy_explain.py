"""Privacy explanation reports. Slice 246.

Privacy denials are cryptic by default — a bare error code tells
an operator nothing actionable. :class:`PrivacyExplainer` turns
any privacy error (or dry-run report, or redacted provenance
record) into a plain-language explanation: what happened, why
the policy requires it, and what the operator can do about it.

Remediation advice is advisory only — it never bypasses the
policy; every suggested action goes *through* the policy
(change the flow, the classification, or the configuration, not
around it).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hugrgate.errors import HugrGateError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from hugrgate.privacy_dryrun import DryRunReport
    from hugrgate.provenance import DecisionRecord

__all__ = ["PrivacyExplainer", "explain_denial"]

#: Remediation templates per error code. ``{d}`` placeholders are
#: filled from ``error.details`` when present.
_REMEDIATIONS: dict[str, str] = {
    "privacy_violation": (
        "The privacy guard blocked this backend. If the message "
        "mentions remote_inference='forbidden', remote inference is "
        "disabled at guard level — enable it explicitly or route the "
        "decision to a local backend. If it mentions a trust level, "
        "the backend's attested trust ({d[trust_level]}) is below "
        "what the privacy class requires — attest the backend or "
        "lower the classification."),
    "data_flow_denied": (
        "The data-flow policy denied this exact flow. Change one "
        "axis of the flow: a different backend, a lower privacy "
        "class, a permitted jurisdiction, or add a flow rule that "
        "covers it. Do not copy the data around the policy."),
    "jurisdiction_violation": (
        "The backend's jurisdiction ({d[jurisdiction]}) is not in "
        "the allowed set. Declare the backend's jurisdiction "
        "accurately in the registry, or extend jurisdictions_allowed "
        "deliberately — never leave remotes as 'unknown' to slip "
        "through."),
    "local_only_violation": (
        "A field marked local-only was present in strict mode. "
        "Either remove the field from the outbound state, mark it "
        "with a lower sensitivity, or run enforcement in strip "
        "(non-strict) mode so it is removed automatically."),
    "secret_detected": (
        "A secret-shaped value was found in the outbound data. "
        "Rotate the exposed secret, redact the field, or mark the "
        "field local_only so it never leaves the process."),
    "backend_unavailable": (
        "The decision policy disallows this backend (remote "
        "inference not enabled in the policy, or the backend is not "
        "in allowed_backends). Adjust the policy deliberately, or "
        "pick an allowed backend."),
    "seal_error": (
        "Authenticated decryption failed: wrong key, truncated blob, "
        "or a failed authentication tag. Supply the correct key "
        "(check key rotation state) or treat the blob as tampered "
        "and discard it."),
    "key_provider_error": (
        "Key material could not be supplied. Check that the "
        "environment variable is set, the key file exists with mode "
        "0o600, or that the ephemeral provider was not forgotten."),
}

_WHY: dict[str, str] = {
    "privacy_violation": "data sovereignty: the guard's job is to "
    "stop state from reaching backends it must not reach.",
    "data_flow_denied": "information-flow control: every flow must "
    "match an explicit policy rule.",
    "jurisdiction_violation": "data residency: flows must stay "
    "inside permitted jurisdictions.",
    "local_only_violation": "data minimization: local-only fields "
    "must never leave the process.",
    "secret_detected": "secret hygiene: secrets must never travel "
    "in decision state.",
    "backend_unavailable": "policy routing: the decision policy "
    "decides which backends may serve it.",
    "seal_error": "integrity: sealed data that fails "
    "authentication must not be trusted.",
    "key_provider_error": "key custody: without key material, "
    "encrypted stores cannot open.",
}


class PrivacyExplainer:
    """Turns privacy denials into actionable plain-language reports."""

    def explain_denial(self, error: HugrGateError,
                       *, context: dict[str, Any] | None = None) -> str:
        """Explain *what happened, why, and what to do* for an error."""
        code = error.code
        details = dict(error.details)
        if context:
            details.update(context)
        why = _WHY.get(code, "privacy enforcement: the operation was "
                             "stopped before data could leak.")
        template = _REMEDIATIONS.get(
            code, "No specific remediation is known for this error. "
                  "Review the policy configuration and the error "
                  "details, and change the flow — not the guard.")
        remediation = self._fill(template, details)
        lines = [
            f"Privacy denial ({code})",
            "",
            f"What happened: {error.message or '(no message)'}",
            "",
            f"Why this exists: {why}",
            "",
            f"What you can do: {remediation}",
        ]
        if details:
            rendered = ", ".join(f"{k}={v!r}"
                                 for k, v in sorted(details.items()))
            lines += ["", f"Details: {rendered}"]
        return "\n".join(lines)

    @staticmethod
    def _fill(template: str, details: dict[str, Any]) -> str:
        """Fill {d[key]} placeholders; leave unknown ones literal."""
        out: list[str] = []
        i = 0
        while i < len(template):
            start = template.find("{d[", i)
            if start == -1:
                out.append(template[i:])
                break
            out.append(template[i:start])
            end = template.find("]}", start)
            if end == -1:
                out.append(template[start:])
                break
            key = template[start + 3:end]
            value = details.get(key)
            out.append("(unknown)" if value is None else repr(value))
            i = end + 2
        return "".join(out)

    def explain_dry_run(self, report: DryRunReport) -> str:
        """Turn a :class:`DryRunReport` into a readable walkthrough."""
        verdict = ("would be ALLOWED" if report.allowed
                   else "would be DENIED")
        lines = [f"Dry-run for backend {report.backend!r}: {verdict}", ""]
        for stage in report.stages:
            lines.append(f"- {stage.stage}: {stage.action} — "
                         f"{stage.reason}")
        if report.stripped_fields:
            lines += ["",
                      "Fields that would be stripped: "
                      + ", ".join(report.stripped_fields)]
        if report.denied_reason:
            lines += ["", "Denial reason: " + report.denied_reason,
                      "",
                      "To proceed, change the flow, the privacy class, "
                      "or the backend — not the guard."]
        return "\n".join(lines)

    def explain_record(self, record: DecisionRecord) -> str:
        """Explain why a provenance record looks the way it does."""
        privacy_class = record.metadata.get("privacy_class", "unknown")
        redacted = bool(record.metadata.get("redacted", False))
        has_keys = "state_keys" in record.metadata
        has_fingerprints = "value_fingerprints" in record.metadata
        if redacted and not has_keys:
            mode = "redacted"
        elif has_fingerprints:
            mode = "fingerprint"
        elif has_keys:
            mode = "keys"
        elif privacy_class == "forbidden":
            mode = "none"
        else:
            mode = "full"
        lines = [
            f"Provenance record {record.request_hash[:12]}…:",
            f"- privacy class: {privacy_class}",
            f"- provenance mode: {mode}",
        ]
        if mode == "redacted":
            lines.append("- State values were scrubbed before retention: "
                         "the privacy class forbids keeping them. Only "
                         "structure is auditable.")
        elif mode == "fingerprint":
            lines.append("- The state is stored as fingerprints: you "
                         "can verify a state matches this record, but "
                         "the record cannot reveal the state.")
        elif mode == "none":
            lines.append("- No state-derived metadata was recorded: this "
                         "class forbids any retention.")
        else:
            lines.append("- Field names were retained: this class permits "
                         "it.")
        return "\n".join(lines)


def explain_denial(error: HugrGateError,
                   **context: Any) -> str:
    """One-shot explanation for a privacy error."""
    return PrivacyExplainer().explain_denial(error, context=context or None)
