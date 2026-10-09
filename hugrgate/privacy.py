"""Privacy enforcement — system-level guardrails. Slice 40.

The per-decision ``DecisionPolicy`` already gates remote backends, but policy
is application-supplied and can be loosened by mistake. ``PrivacyGuard`` is
the operator-level backstop: when remote inference is *forbidden* at this
level, remote backends are excluded at **selection time** — before any state
ever flows to them — and any direct attempt raises ``PrivacyViolation``.

It also owns provenance redaction: records must never carry raw state when
the privacy class forbids it.

Slice 226 (privacy classification v2) promotes the old binary
``standard``/``strict`` classes to a five-rung ordered ladder —
``public`` < ``standard`` < ``sensitive`` < ``strict`` < ``forbidden`` —
each with machine-enforceable semantics (minimum backend trust, cache
retention, remote eligibility, provenance mode). The ladder is defined
here; :class:`DecisionPolicy` accepts exactly these classes.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace
from typing import Any

from hugrgate.backend import Backend
from hugrgate.errors import BackendUnavailable, PrivacyViolation
from hugrgate.log import get_logger
from hugrgate.policy import DecisionPolicy
from hugrgate.privacy_jurisdiction import (
    JurisdictionRegistry,
    JurisdictionViolation,
)
from hugrgate.privacy_labels import FieldLabels
from hugrgate.privacy_localonly import LocalOnlyPolicy, LocalOnlyResult
from hugrgate.privacy_redact import redact_metadata
from hugrgate.privacy_trust import (
    TRUST_ORDER,
    BackendTrustRegistry,
    default_trust_level,
    trust_rank,
)
from hugrgate.provenance import DecisionRecord

logger = get_logger(__name__)

__all__ = [
    "CLASS_SEMANTICS",
    "NON_CACHEABLE_PRIVACY_CLASSES",
    "PRIVACY_CLASS_ORDER",
    "REMOTE_MODES",
    "TRUST_ORDER",
    "PrivacyGuard",
    "at_least",
    "class_rank",
    "default_trust_level",
    "provenance_mode_for",
    "semantics_for",
    "trust_rank",
]

REMOTE_MODES = ("allow", "forbidden")

#: Slice 226 — the privacy classification ladder, lowest to highest
#: sensitivity. Must equal ``DecisionPolicy.PRIVACY_CLASSES`` (enforced
#: by test); the ordering is load-bearing for ``at_least()``.
PRIVACY_CLASS_ORDER = ("public", "standard", "sensitive", "strict",
                       "forbidden")

#: Machine-enforceable semantics per privacy class.
#:
#: - ``min_trust``: minimum backend trust rank for the class's data.
#: - ``cacheable``: whether decision caching may retain the data.
#: - ``remote_eligible``: whether remote backends may ever see it.
#: - ``provenance``: ``"full"`` (state keys + values metadata),
#:   ``"keys"`` (state keys only), ``"redacted"`` (scrubbed),
#:   ``"none"`` (no state-derived metadata at all).
CLASS_SEMANTICS: dict[str, dict[str, Any]] = {
    "public": {
        "min_trust": "untrusted",
        "cacheable": True,
        "remote_eligible": True,
        "provenance": "full",
    },
    "standard": {
        "min_trust": "untrusted",
        "cacheable": True,
        "remote_eligible": True,
        "provenance": "keys",
    },
    "sensitive": {
        "min_trust": "basic",
        "cacheable": True,
        "remote_eligible": True,
        "provenance": "keys",
    },
    "strict": {
        # Hardened in slice 226: "strict" data now requires a *verified*
        # remote backend (attested, slice 229). Previously any remote
        # backend the policy allowed would receive strict data — an
        # unverified third party could be handed the most sensitive
        # payloads the policy still permitted remotely.
        "min_trust": "verified",
        "cacheable": False,
        "remote_eligible": True,
        "provenance": "redacted",
    },
    "forbidden": {
        # Never leaves the process: no remote backend, no cache, and no
        # state-derived provenance metadata, regardless of policy or
        # guard mode. Local-only by construction.
        "min_trust": "enclave",
        "cacheable": False,
        "remote_eligible": False,
        "provenance": "none",
    },
}

#: Privacy classes whose data must never touch the decision cache or
#: leave the process in provenance records.
NON_CACHEABLE_PRIVACY_CLASSES = frozenset({"strict", "forbidden"})


def class_rank(privacy_class: str) -> int:
    """Ordinal of a privacy class on the ladder (higher = more sensitive)."""
    try:
        return PRIVACY_CLASS_ORDER.index(privacy_class)
    except ValueError:
        raise ValueError(
            f"unknown privacy_class: {privacy_class!r}; expected one of "
            f"{list(PRIVACY_CLASS_ORDER)}") from None


def at_least(privacy_class: str, minimum: str) -> bool:
    """True when ``privacy_class`` is at least as sensitive as ``minimum``."""
    return class_rank(privacy_class) >= class_rank(minimum)


def semantics_for(privacy_class: str) -> dict[str, Any]:
    """The enforceable semantics for a privacy class (copy)."""
    try:
        return dict(CLASS_SEMANTICS[privacy_class])
    except KeyError:
        raise ValueError(
            f"unknown privacy_class: {privacy_class!r}; expected one of "
            f"{list(CLASS_SEMANTICS)}") from None


def provenance_mode_for(privacy_class: str) -> str:
    """Provenance mode (``"full"|"keys"|"redacted"|"none"``) for a class."""
    return semantics_for(privacy_class)["provenance"]


class PrivacyGuard:
    """Operator-level privacy enforcement.

    Parameters
    ----------
    remote_inference:
        ``"allow"`` — defer to each decision's ``DecisionPolicy``.
        ``"forbidden"`` — remote backends are blocked at selection time
        even if the policy would permit them; direct attempts raise
        ``PrivacyViolation``.
    redact_provenance:
        When True, provenance records produced under this guard have raw
        state material scrubbed.
    trust_registry:
        Optional :class:`~hugrgate.privacy_trust.BackendTrustRegistry`
        of attested backend trust levels (slice 229). When absent, the
        slice-226 defaults apply (in-process = ``"enclave"``,
        remote = ``"basic"``).
    jurisdiction_registry:
        Optional :class:`~hugrgate.privacy_jurisdiction.JurisdictionRegistry`
        of backend jurisdiction declarations (slice 230).
    jurisdictions_allowed:
        Optional set of jurisdiction codes remote data may flow to.
        ``None`` (default) means no restriction. Local backends are
        always allowed.
    """

    def __init__(self, remote_inference: str = "allow",
                 redact_provenance: bool = True,
                 trust_registry: BackendTrustRegistry | None = None,
                 jurisdiction_registry: JurisdictionRegistry | None = None,
                 jurisdictions_allowed: set[str] | frozenset[str] | None = None):
        if remote_inference not in REMOTE_MODES:
            raise ValueError(f"remote_inference must be one of {REMOTE_MODES}, "
                             f"got {remote_inference!r}")
        self.remote_inference = remote_inference
        self.redact_provenance = redact_provenance
        self.trust_registry = trust_registry
        self.jurisdiction_registry = jurisdiction_registry or \
            JurisdictionRegistry()
        self.jurisdictions_allowed = \
            frozenset(jurisdictions_allowed) \
            if jurisdictions_allowed is not None else None

    def _trust_level(self, backend: Backend) -> str:
        """Effective trust level, attested when a registry is present."""
        if self.trust_registry is not None:
            return self.trust_registry.level_for(backend)
        return default_trust_level(backend)

    def _jurisdiction(self, backend: Backend) -> str:
        """Jurisdiction code for a backend (declared or default)."""
        return self.jurisdiction_registry.jurisdiction_for(backend)

    def _jurisdiction_blocked(self, backend: Backend) -> str | None:
        """Return a denial reason when jurisdiction blocks the backend."""
        if not backend.is_remote or self.jurisdictions_allowed is None:
            return None
        jurisdiction = self._jurisdiction(backend)
        if jurisdiction not in self.jurisdictions_allowed:
            return (f"jurisdiction {jurisdiction!r} not in allowed "
                    f"{sorted(self.jurisdictions_allowed)}")
        return None

    # -- selection-time enforcement -------------------------------------

    def _class_remote_blocked(self, backend: Backend,
                              policy: DecisionPolicy) -> str | None:
        """Return a denial reason when the privacy *class* blocks remote.

        Returns None when the class permits this backend. Slice 226:
        the class ladder is now enforceable, not advisory.
        """
        sem = semantics_for(policy.privacy_class)
        if backend.is_remote and not sem["remote_eligible"]:
            return (f"privacy_class {policy.privacy_class!r} forbids "
                    f"remote inference entirely")
        need = trust_rank(sem["min_trust"])
        level = self._trust_level(backend)
        have = trust_rank(level)
        if have < need:
            return (f"privacy_class {policy.privacy_class!r} requires "
                    f"trust >= {sem['min_trust']!r}; backend "
                    f"{backend.name!r} is {level!r}")
        return None

    def remote_allowed(self, backend: Backend, policy: DecisionPolicy) -> bool:
        """True only if guard, class, jurisdiction, and policy all permit."""
        if self._class_remote_blocked(backend, policy) is not None:
            return False
        if self._jurisdiction_blocked(backend) is not None:
            return False
        if backend.is_remote and self.remote_inference == "forbidden":
            return False
        return policy.backend_allowed(backend.name, backend.is_remote)

    def check_backend(self, backend: Backend, policy: DecisionPolicy) -> None:
        """Attempt gate: raise before any state flows to a blocked backend.

        Raises
        ------
        PrivacyViolation
            When remote inference is forbidden at guard level, or the
            privacy class's trust/eligibility rules block the backend.
        BackendUnavailable
            When the decision policy itself disallows the backend.
        """
        if backend.is_remote and self.remote_inference == "forbidden":
            logger.warning("privacy: remote backend %r blocked (guard=forbidden)",
                           backend.name)
            raise PrivacyViolation(
                f"remote backend {backend.name!r} blocked: remote_inference "
                f"is forbidden by the privacy guard",
                backend=backend.name)
        denial = self._class_remote_blocked(backend, policy)
        if denial is not None:
            logger.warning("privacy: backend %r blocked (%s)",
                           backend.name, denial)
            raise PrivacyViolation(f"backend {backend.name!r} blocked: {denial}",
                                   backend=backend.name,
                                   privacy_class=policy.privacy_class)
        jdenial = self._jurisdiction_blocked(backend)
        if jdenial is not None:
            logger.warning("privacy: backend %r blocked (%s)",
                           backend.name, jdenial)
            raise JurisdictionViolation(
                f"backend {backend.name!r} blocked: {jdenial}",
                backend=backend.name,
                jurisdiction=self._jurisdiction(backend))
        if not policy.backend_allowed(backend.name, backend.is_remote):
            logger.debug("privacy: backend %r excluded by decision policy",
                         backend.name)
            raise BackendUnavailable(
                f"backend {backend.name!r} blocked by decision policy",
                backend=backend.name)

    def filter_backends(self, backends: Iterable[Backend],
                        policy: DecisionPolicy) -> list[Backend]:
        """Selection-time filter: blocked backends never become candidates."""
        return [b for b in backends if self.remote_allowed(b, policy)]

    # -- local-only field enforcement (slice 231) ------------------------

    def enforce_local_only(self, state: Mapping[str, Any],
                           labels: FieldLabels, backend: Backend,
                           *, strict: bool = False) -> LocalOnlyResult:
        """Strip (or in strict mode, reject) local-only fields.

        Local backends pass through untouched. For remote backends,
        any present local-only field is removed from the returned
        copy and reported in ``result.stripped``; strict mode raises
        :class:`~hugrgate.errors.LocalOnlyViolation` instead.
        """
        return LocalOnlyPolicy(strict=strict).enforce_for_backend(
            state, labels, backend)

    # -- cache policy ----------------------------------------------------

    @staticmethod
    def cache_allowed(policy: DecisionPolicy) -> bool:
        """Never cache when the privacy class forbids retention."""
        return semantics_for(policy.privacy_class)["cacheable"]

    # -- redaction -------------------------------------------------------

    @staticmethod
    def redact_state(state: Mapping[str, Any]) -> dict:
        """Return a state-shaped mapping with every value masked."""
        return {k: "<redacted>" for k in state.keys()}

    def redact_record(self, record: DecisionRecord) -> DecisionRecord:
        """Return a copy of ``record`` with raw state material scrubbed.

        Slice 232 hardening: the scrub is now *deep* — ``state`` /
        ``state_keys`` / ``raw_state`` keys are dropped at any nesting
        depth inside metadata, and remaining string values are
        pattern-scrubbed. Idempotent.
        """
        return replace(record,
                       metadata=redact_metadata(record.metadata))

    def provenance_redaction_needed(self,
                                    policy: DecisionPolicy | None) -> bool:
        """Whether records for this policy must be redacted."""
        if self.redact_provenance:
            return True
        return policy is not None and \
            policy.privacy_class in NON_CACHEABLE_PRIVACY_CLASSES
