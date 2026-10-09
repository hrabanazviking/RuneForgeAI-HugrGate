"""Privacy-aware routing v2. Slice 060.

The v1 ladder gates only on *where* a backend runs (remote vs local).
v2 gates on *what the data is*: every request's state keys are classified
into a :class:`PrivacyTier`, every backend is graded to a clearance from
its privacy properties, and rungs where the data outranks the clearance
are pruned at plan time — before any bytes move.

- :class:`DataClassifier` — key-name heuristics → tier (PUBLIC <
  INTERNAL < CONFIDENTIAL < RESTRICTED); explicit override via
  ``spec.metadata["data_tier"]``; ``policy.privacy_class == "strict"``
  floors every request at CONFIDENTIAL.
- :class:`BackendClearance` — local + no retention → RESTRICTED; remote
  → at most INTERNAL; ``data_retained`` → at most INTERNAL; remote *and*
  retaining → PUBLIC only.
- :class:`PrivacyAwarePlanner` — prunes rungs whose clearance < data
  tier, recording the verdict per node.

This is defense in depth *over* the existing guards: the executor's
``skip_reason`` (policy + ``PrivacyGuard``) still re-checks at run time.
Adversarial behavior — exfiltration-shaped routing — is pruned, audited,
and tested below.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Dict, List, Optional

from hugrgate.backend import Backend
from hugrgate.routing.architecture import (RouterContext, RungNode,
                                            RungPlanner, RoutingPlan)

__all__ = [
    "PrivacyTier",
    "DataClassifier",
    "BackendClearance",
    "PrivacyAwarePlanner",
]


class PrivacyTier(IntEnum):
    PUBLIC = 0
    INTERNAL = 1
    CONFIDENTIAL = 2
    RESTRICTED = 3

    def __str__(self) -> str:
        return self.name.lower()


#: Key-name fragments mapping to tiers. Order matters: first hit wins.
_KEY_TIERS = (
    (PrivacyTier.RESTRICTED,
     ("ssn", "social_security", "password", "passwd", "secret", "private_key",
      "credit_card", "bank_account", "biometric")),
    (PrivacyTier.CONFIDENTIAL,
     ("token", "api_key", "email", "phone", "address", "dob",
      "date_of_birth", "health", "medical", "diagnosis", "salary",
      "employee_id")),
    (PrivacyTier.INTERNAL,
     ("internal", "employee", "team", "project")),
)


class DataClassifier:
    """Classify request state into a privacy tier."""

    def __init__(self, extra_rules: Optional[Dict[str, PrivacyTier]] = None):
        self.extra_rules = dict(extra_rules or {})

    def classify_key(self, key: str) -> PrivacyTier:
        lowered = key.lower()
        for fragment, tier in self.extra_rules.items():
            if fragment.lower() in lowered:
                return tier
        for tier, fragments in _KEY_TIERS:
            if any(f in lowered for f in fragments):
                return tier
        return PrivacyTier.PUBLIC

    def classify(self, ctx: RouterContext) -> PrivacyTier:
        override = (ctx.spec.metadata or {}).get("data_tier")
        if override is not None:
            try:
                tier = PrivacyTier[str(override).upper()]
            except KeyError:
                raise ValueError(f"unknown data_tier: {override!r}")
            return self._apply_policy_floor(ctx, tier)
        tier = PrivacyTier.PUBLIC
        for key in ctx.state_keys:
            tier = max(tier, self.classify_key(key))
        return self._apply_policy_floor(ctx, tier)

    @staticmethod
    def _apply_policy_floor(ctx: RouterContext,
                            tier: PrivacyTier) -> PrivacyTier:
        if ctx.policy.privacy_class == "strict":
            return max(tier, PrivacyTier.CONFIDENTIAL)
        return tier


class BackendClearance:
    """Grade a backend's clearance from its privacy properties."""

    @staticmethod
    def clearance(backend: Backend) -> PrivacyTier:
        props = backend.privacy_properties() or {}
        remote = bool(backend.is_remote or props.get("remote"))
        retained = bool(props.get("data_retained"))
        if remote and retained:
            return PrivacyTier.PUBLIC
        if remote or retained:
            return PrivacyTier.INTERNAL
        return PrivacyTier.RESTRICTED

    @staticmethod
    def verdict(backend: Backend, tier: PrivacyTier) -> Optional[str]:
        """None when the backend may see this tier, else the reason."""
        clearance = BackendClearance.clearance(backend)
        if tier <= clearance:
            return None
        return (f"data tier {tier} exceeds {backend.name} clearance "
                f"{clearance}")


class PrivacyAwarePlanner(RungPlanner):
    """Wrap a planner; prune rungs the data tier forbids."""

    def __init__(self, inner: RungPlanner, registry,
                 classifier: Optional[DataClassifier] = None):
        self.inner = inner
        self.registry = registry
        self.classifier = classifier or DataClassifier()

    def plan(self, ctx: RouterContext) -> RoutingPlan:
        plan = self.inner.plan(ctx)
        tier = self.classifier.classify(ctx)
        kept: List[RungNode] = []
        pruned: List[str] = []
        for node in plan.nodes:
            backend = self.registry.get(node.backend_name)
            reason = (BackendClearance.verdict(backend, tier)
                      if backend is not None else None)
            node.params["privacy_tier"] = str(tier)
            node.params["backend_clearance"] = (
                str(BackendClearance.clearance(backend))
                if backend is not None else "unknown")
            if reason is None:
                kept.append(node)
            else:
                pruned.append(f"{node.backend_name}: {reason}")
        plan.nodes = kept
        plan.created_by = f"{plan.created_by}+privacy"
        plan.rationale.append(
            f"privacy: data tier {tier}, pruned {len(pruned)}"
            + (": " + "; ".join(pruned) if pruned else ""))
        return plan
