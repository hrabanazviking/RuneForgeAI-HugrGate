"""Dynamic ensemble membership — earn your seat. Slice 117.

A fixed member list cannot adapt: a backend that degrades keeps
voting, and a better backend waits outside. :class:`MembershipManager`
holds the member backends and moves them between ``active``,
``standby``, and ``retired`` on evidence:

- an **active** member whose Laplace-smoothed reliability drops below
  ``retire_below`` over at least ``min_observations`` outcomes is
  **retired** (never below ``min_active`` active members);
- a **standby** member whose reliability reaches ``promote_above``
  over ``min_observations`` outcomes is **promoted** to active;
- every transition — automatic or manual — is appended to an event
  log (sequence-numbered, deterministic) for provenance (slice 119).

Standby members keep receiving observations (shadow voting in a real
deployment feeds :meth:`observe`); the manager itself never runs
backends, it only curates the roster.
"""

from __future__ import annotations

from typing import Any

from hugrgate.backend import Backend
from hugrgate.ensemble.reliability import ReliabilityTracker
from hugrgate.errors import PolicyError

__all__ = [
    "STATUS_ACTIVE",
    "STATUS_RETIRED",
    "STATUS_STANDBY",
    "MembershipManager",
]

STATUS_ACTIVE = "active"
STATUS_STANDBY = "standby"
STATUS_RETIRED = "retired"
STATUSES = (STATUS_ACTIVE, STATUS_STANDBY, STATUS_RETIRED)


class MembershipManager:
    """Curates the ensemble roster on observed reliability."""

    def __init__(self, members: list[Backend],
                 initial_standby: list[str] | None = None,
                 retire_below: float = 0.4,
                 promote_above: float = 0.65,
                 min_observations: int = 10,
                 min_active: int = 1,
                 smoothing: float = 1.0):
        if not members:
            raise PolicyError("MembershipManager needs members")
        names = [m.name for m in members]
        if len(set(names)) != len(names):
            raise PolicyError(
                f"member names must be unique, got {names}")
        for label, v in (("retire_below", retire_below),
                         ("promote_above", promote_above)):
            if not 0.0 < v < 1.0:
                raise PolicyError(f"{label} must be in (0, 1), got {v}")
        if retire_below >= promote_above:
            raise PolicyError(
                "retire_below must be < promote_above "
                f"({retire_below} >= {promote_above})")
        if min_observations < 1:
            raise PolicyError(
                f"min_observations must be >= 1, got {min_observations}")
        if min_active < 1:
            raise PolicyError(f"min_active must be >= 1, got {min_active}")
        self._backends: dict[str, Backend] = {m.name: m for m in members}
        self.tracker = ReliabilityTracker(names, smoothing=smoothing)
        self.retire_below = retire_below
        self.promote_above = promote_above
        self.min_observations = min_observations
        self.min_active = min_active
        self._status: dict[str, str] = {n: STATUS_ACTIVE for n in names}
        for name in initial_standby or []:
            self._check(name)
            self._status[name] = STATUS_STANDBY
        self._events: list[dict[str, Any]] = []
        self._seq = 0

    def _check(self, member: str) -> None:
        if member not in self._backends:
            raise PolicyError(
                f"unknown member {member!r}; members are "
                f"{sorted(self._backends)}")

    def _record(self, kind: str, member: str, detail: str = "") -> None:
        self._seq += 1
        self._events.append({
            "seq": self._seq,
            "kind": kind,
            "member": member,
            "status": self._status[member],
            "reliability": round(self.tracker.reliability(member), 4),
            "observations": self.tracker.observation_counts()[member],
            "detail": detail,
        })

    def status(self, member: str) -> str:
        self._check(member)
        return self._status[member]

    def active_members(self) -> list[str]:
        return [n for n, s in self._status.items() if s == STATUS_ACTIVE]

    def standby_members(self) -> list[str]:
        return [n for n, s in self._status.items() if s == STATUS_STANDBY]

    def retired_members(self) -> list[str]:
        return [n for n, s in self._status.items() if s == STATUS_RETIRED]

    def events(self) -> list[dict[str, Any]]:
        return [dict(e) for e in self._events]

    def observe(self, member: str, correct: bool) -> None:
        """Record a labeled outcome; re-evaluate membership."""
        self._check(member)
        self.tracker.observe(member, correct)
        self._reevaluate(member)

    def _reevaluate(self, member: str) -> None:
        obs = self.tracker.observation_counts()[member]
        if obs < self.min_observations:
            return  # not enough evidence to judge
        rel = self.tracker.reliability(member)
        status = self._status[member]
        if status == STATUS_ACTIVE and rel < self.retire_below:
            if len(self.active_members()) <= self.min_active:
                self._record("retire_blocked", member,
                             f"would breach min_active={self.min_active}")
                return
            self._status[member] = STATUS_RETIRED
            self._record("retired", member,
                         f"reliability {rel:.3f} < {self.retire_below}")
        elif status == STATUS_STANDBY and rel >= self.promote_above:
            self._status[member] = STATUS_ACTIVE
            self._record("promoted", member,
                         f"reliability {rel:.3f} >= {self.promote_above}")

    # --- manual controls ---------------------------------------------------

    def retire(self, member: str, reason: str = "manual") -> None:
        self._check(member)
        self._status[member] = STATUS_RETIRED
        self._record("retired", member, reason)

    def to_standby(self, member: str, reason: str = "manual") -> None:
        self._check(member)
        self._status[member] = STATUS_STANDBY
        self._record("standby", member, reason)

    def activate(self, member: str, reason: str = "manual") -> None:
        self._check(member)
        self._status[member] = STATUS_ACTIVE
        self._record("activated", member, reason)

    def build_ensemble(self, strategy: str = "soft", **kwargs: Any):
        """Build an :class:`Ensemble` from the active members.

        Import is local: membership stays below the api module in the
        import graph (no cycle).
        """
        from hugrgate.ensemble.api import Ensemble
        actives = [self._backends[n] for n in self.active_members()]
        if not actives:
            raise PolicyError("no active members to build an ensemble")
        return Ensemble(actives, strategy=strategy, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "statuses": dict(self._status),
            "retire_below": self.retire_below,
            "promote_above": self.promote_above,
            "min_observations": self.min_observations,
            "min_active": self.min_active,
            "reliabilities": {m: self.tracker.reliability(m)
                              for m in self._backends},
            "events": self.events(),
        }
