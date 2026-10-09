"""Router shadow mode. Slice 143.

New policies should earn traffic, not be granted it.
:class:`RouterShadowMode` runs a candidate policy *alongside* the
serving policy: for each decision it records what the candidate *would*
have chosen — with its features, candidates, propensities, and the
served choice — into the telemetry store flagged ``shadow=True``.

Shadow records:

- never affect the served decision (the method returns the served arm;
  the shadow arm is only logged);
- are excluded from offline training (slice 131 skips ``shadow``);
- feed the divergence report: how often would the candidate have
  disagreed, and on which arms?

Promotion rule of thumb (enforced by process, reported here): a
candidate graduates from shadow when its divergence is understood and
its counterfactual value (slice 144) beats the incumbent.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from hugrgate.adaptive.telemetry import RouteEvent, TelemetryStore
from hugrgate.errors import SpecError

__all__ = [
    "RouterShadowMode",
    "ShadowDivergence",
]


@dataclass(frozen=True)
class ShadowDivergence:
    """How much the shadow policy disagrees with the served policy."""

    n_shadow: int
    n_diverged: int
    per_arm_agreement: dict[str, dict[str, int]]  # served -> {shadow: n}

    @property
    def divergence_rate(self) -> float:
        if self.n_shadow == 0:
            return 0.0
        return self.n_diverged / self.n_shadow

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_shadow": self.n_shadow,
            "n_diverged": self.n_diverged,
            "divergence_rate": self.divergence_rate,
            "per_arm_agreement": {
                served: dict(shadowed)
                for served, shadowed in self.per_arm_agreement.items()
            },
        }


class RouterShadowMode:
    """Evaluate a candidate policy without serving its decisions."""

    def __init__(self, store: TelemetryStore, *, enabled: bool = True,
                 policy_version: str = "shadow") -> None:
        if not isinstance(store, TelemetryStore):
            raise SpecError(
                f"RouterShadowMode needs a TelemetryStore, got "
                f"{type(store).__name__}")
        self.store = store
        self.enabled = enabled
        self.policy_version = policy_version

    def record_shadow(self, *, features: Mapping[str, float],
                      candidates: Sequence[str],
                      propensities: Mapping[str, float],
                      shadow_choice: str,
                      served_choice: str,
                      spec: Mapping[str, Any] | None = None,
                      privacy_class: str = "standard",
                      request_id: str | None = None) -> str | None:
        """Log the shadow decision. Returns the request_id, or None when
        shadow mode is disabled (nothing is logged)."""
        if not self.enabled:
            return None
        cand_list = list(candidates)
        if shadow_choice not in cand_list:
            raise SpecError(
                f"shadow choice {shadow_choice!r} not in candidates")
        if served_choice not in cand_list:
            raise SpecError(
                f"served choice {served_choice!r} not in candidates")
        event = RouteEvent(
            request_id=request_id or TelemetryStore.new_request_id(),
            timestamp=time.time(),
            spec=dict(spec) if spec else {},
            features=dict(features),
            candidates=cand_list,
            propensities=dict(propensities),
            chosen=shadow_choice,
            policy_version=self.policy_version,
            privacy_class=privacy_class,
            shadow=True,
            metadata={"served_choice": served_choice,
                      "diverged": shadow_choice != served_choice},
        )
        return self.store.record(event)

    def divergence_report(self) -> ShadowDivergence:
        """Agreement between shadow choices and served choices."""
        n_shadow = 0
        n_diverged = 0
        agreement: dict[str, dict[str, int]] = {}
        for event in self.store.events():
            if not event.shadow:
                continue
            served = event.metadata.get("served_choice")
            if served is None:
                continue
            n_shadow += 1
            if event.chosen != served:
                n_diverged += 1
            agreement.setdefault(str(served), {})
            agreement[str(served)][event.chosen] = \
                agreement[str(served)].get(event.chosen, 0) + 1
        return ShadowDivergence(n_shadow=n_shadow, n_diverged=n_diverged,
                                per_arm_agreement=agreement)

    def shadow_choices_for(self, served_choice: str) -> list[str]:
        """Shadow arms chosen when ``served_choice`` was served."""
        return [e.chosen for e in self.store.events()
                if e.shadow and e.metadata.get("served_choice")
                == served_choice]
