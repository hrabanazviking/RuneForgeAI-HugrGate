"""Agent Nervous System (Campaign XVI) — agent privacy routing.

Slice 390.  Health picks who *deserves* traffic, cost picks who
*we can afford* — privacy picks who *may see it*.  Every signal
carries a privacy class (payload key ``"privacy_class"``,
default ``"public"``); :class:`PrivacyRouter` admits only agents
whose clearance covers it:

``class_rank(signal_class) <= class_rank(agent_clearance)``

Clearance comes from explicit :meth:`set_clearance` or falls back
to the agent's contract ``privacy_clearance`` (376) — one ladder,
one source of truth (:data:`hugrgate.privacy.PRIVACY_CLASS_ORDER`).
Routing is fail-closed: unlisted agents and uncovered classes
are excluded, never warned-and-passed.  When nothing qualifies,
:meth:`route` raises :class:`AgentNotFound` with the required
class in details so the caller can escalate to a cleared agent
instead of leaking.

:meth:`check` is the single-agent predicate for gates that need
a yes/no without candidate lists (memory gates, tool router).
"""

from __future__ import annotations

from hugrgate.agents.contract import AgentContract
from hugrgate.agents.types import AgentSignal
from hugrgate.errors import AgentNotFound
from hugrgate.privacy import PRIVACY_CLASS_ORDER, class_rank

__all__ = [
    "PrivacyRouter",
    "signal_privacy_class",
]


def signal_privacy_class(signal: AgentSignal) -> str:
    """The signal's privacy class (payload key, default ``"public"``)."""
    cls = signal.payload.get("privacy_class", "public")
    if not isinstance(cls, str) or cls not in PRIVACY_CLASS_ORDER:
        raise ValueError(
            f"signal {signal.topic!r} carries invalid privacy_class "
            f"{cls!r}"
        )
    return cls


class PrivacyRouter:
    """Fail-closed privacy-aware candidate filtering."""

    def __init__(
        self, contracts: dict[str, AgentContract] | None = None
    ) -> None:
        self._contracts = contracts or {}
        self._clearance: dict[str, str] = {}
        self._stats = {"routed": 0, "denied_signals": 0}

    def set_clearance(self, agent_id: str, clearance: str) -> None:
        """Set an agent's explicit clearance (overrides contract)."""
        if clearance not in PRIVACY_CLASS_ORDER:
            raise ValueError(f"unknown clearance {clearance!r}")
        self._clearance[agent_id] = clearance

    def clearance_of(self, agent_id: str) -> str | None:
        """Effective clearance: explicit, else contract, else None."""
        if agent_id in self._clearance:
            return self._clearance[agent_id]
        contract = self._contracts.get(agent_id)
        return contract.privacy_clearance if contract else None

    def check(self, agent_id: str, privacy_class: str) -> bool:
        """True when the agent's clearance covers ``privacy_class``."""
        if privacy_class not in PRIVACY_CLASS_ORDER:
            raise ValueError(f"unknown privacy class {privacy_class!r}")
        clearance = self.clearance_of(agent_id)
        if clearance is None:
            return False
        return class_rank(privacy_class) <= class_rank(clearance)

    def route(
        self,
        signal: AgentSignal,
        candidates: tuple[str, ...] | list[str],
    ) -> tuple[str, ...]:
        """Candidates cleared for the signal's privacy class.

        Deterministic order (sorted).  Raises
        :class:`AgentNotFound` when nothing qualifies.
        """
        if not candidates:
            raise ValueError("candidates must not be empty")
        cls = signal_privacy_class(signal)
        allowed = tuple(sorted(c for c in candidates if self.check(c, cls)))
        self._stats["routed"] += 1
        if not allowed:
            self._stats["denied_signals"] += 1
            raise AgentNotFound(
                f"no candidate cleared for privacy class {cls!r}",
                privacy_class=cls,
                candidates=list(candidates),
            )
        return allowed

    def stats(self) -> dict[str, int]:
        """Router counters (copy)."""
        return dict(self._stats)
