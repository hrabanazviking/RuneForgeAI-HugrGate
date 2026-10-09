"""Agent Nervous System (Campaign XVI) — agent capability registry.

Slice 387.  Every router in the nervous system asks the same
questions: *who exists, what can they do, are they healthy?*
:class:`AgentRegistry` is the single directory:

- :meth:`register` stores an agent's validated contract
  (:func:`assert_contract` runs first — the registry never holds
  an invalid contract) plus an opaque ``endpoint`` describing how
  to reach it;
- lookups: :meth:`get` (raises :class:`AgentNotFound`),
  :meth:`find_by_capability`, :meth:`find_by_intent`,
  :meth:`find_by_tool` — all with ``healthy_only=True`` default
  so routers never select a known-sick agent by accident;
- :meth:`set_health` flips the health flag with a note (the
  health router in slice 388 drives this; operators can too).

Duplicate registration is a ``ValueError`` — re-registering with
a new contract version goes through :meth:`unregister` first, so
version changes are explicit, never silent overwrites.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from hugrgate.agents.contract import AgentContract, assert_contract
from hugrgate.errors import AgentNotFound

__all__ = [
    "AgentRegistry",
    "RegisteredAgent",
]


@dataclass(frozen=True)
class RegisteredAgent:
    """One directory entry."""

    contract: AgentContract
    endpoint: str = ""
    healthy: bool = True
    health_note: str = ""
    registered_at: float = 0.0

    @property
    def agent_id(self) -> str:
        """The agent's id (from its contract)."""
        return self.contract.agent_id


class AgentRegistry:
    """The directory of agents known to the nervous system."""

    def __init__(
        self, *, clock: Callable[[], float] | None = None
    ) -> None:
        self._clock = clock or time.monotonic
        self._agents: dict[str, RegisteredAgent] = {}

    def register(
        self, contract: AgentContract, *, endpoint: str = ""
    ) -> RegisteredAgent:
        """Register an agent; its contract is validated first."""
        assert_contract(contract)
        if contract.agent_id in self._agents:
            raise ValueError(
                f"agent {contract.agent_id!r} already registered; "
                "unregister first to replace"
            )
        entry = RegisteredAgent(
            contract=contract, endpoint=endpoint, healthy=True,
            registered_at=self._clock(),
        )
        self._agents[contract.agent_id] = entry
        return entry

    def unregister(self, agent_id: str) -> bool:
        """Remove an agent; True when it existed."""
        return self._agents.pop(agent_id, None) is not None

    def get(self, agent_id: str) -> RegisteredAgent:
        """The entry for ``agent_id``; raises :class:`AgentNotFound`."""
        try:
            return self._agents[agent_id]
        except KeyError:
            raise AgentNotFound(
                f"no agent registered as {agent_id!r}",
                agent_id=agent_id,
            ) from None

    def set_health(
        self, agent_id: str, healthy: bool, note: str = ""
    ) -> RegisteredAgent:
        """Flip an agent's health flag; returns the updated entry."""
        entry = self.get(agent_id)
        updated = RegisteredAgent(
            contract=entry.contract, endpoint=entry.endpoint,
            healthy=healthy, health_note=note,
            registered_at=entry.registered_at,
        )
        self._agents[agent_id] = updated
        return updated

    def find_by_capability(
        self, capability: str, *, healthy_only: bool = True
    ) -> tuple[RegisteredAgent, ...]:
        """Agents declaring ``capability`` (healthy first)."""
        found = [
            e for e in self._agents.values()
            if e.contract.has_capability(capability)
            and (e.healthy or not healthy_only)
        ]
        return tuple(sorted(found, key=lambda e: e.agent_id))

    def find_by_intent(
        self, intent: str, *, healthy_only: bool = True
    ) -> tuple[RegisteredAgent, ...]:
        """Agents handling ``intent`` (healthy first)."""
        found = [
            e for e in self._agents.values()
            if e.contract.handles_intent(intent)
            and (e.healthy or not healthy_only)
        ]
        return tuple(sorted(found, key=lambda e: e.agent_id))

    def find_by_tool(
        self, tool: str, *, healthy_only: bool = True
    ) -> tuple[RegisteredAgent, ...]:
        """Agents allowed ``tool`` by contract (healthy first)."""
        found = [
            e for e in self._agents.values()
            if e.contract.may_use_tool(tool)
            and (e.healthy or not healthy_only)
        ]
        return tuple(sorted(found, key=lambda e: e.agent_id))

    def agent_ids(self) -> tuple[str, ...]:
        """All registered agent ids, sorted."""
        return tuple(sorted(self._agents))

    def __len__(self) -> int:
        return len(self._agents)
