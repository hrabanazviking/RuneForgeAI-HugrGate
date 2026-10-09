"""Agent Nervous System (Campaign XVI) — tool routing.

Slice 379.  Agents act through tools; an agent invoking a tool it
was never granted is a privilege-escalation bug.  :class:`ToolRouter`
is the choke point every tool call passes through:

- per-agent :class:`ToolPolicy`: allowed tools, denied tools
  (**deny always wins** over allow), per-ticket call budgets, and
  per-tool argument schemas;
- :meth:`ToolRouter.authorize` checks, in order: a policy exists
  for the agent → the tool is allowed and not denied → the agent's
  contract (when known) permits the tool → arguments match the
  schema → the ticket still has call budget;
- every grant mints a ``call_id``; :meth:`ToolRouter.record_result`
  closes it with success/latency so per-tool reliability stats
  accumulate for the health router (slice 388).

Failures raise the taxonomy, never return ``None``: missing policy
or denied tool → :class:`AgentContractViolation`, exhausted call
budget → :class:`AgentBudgetExhausted`, bad arguments →
:class:`AgentContractViolation` with the schema violations in
details.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hugrgate.agents.contract import AgentContract, check_payload
from hugrgate.errors import (
    AgentBudgetExhausted,
    AgentContractViolation,
)

__all__ = [
    "ToolGrant",
    "ToolPolicy",
    "ToolRouter",
]


@dataclass(frozen=True)
class ToolPolicy:
    """What one agent may do with tools."""

    agent_id: str
    allowed_tools: frozenset[str] = frozenset()
    denied_tools: frozenset[str] = frozenset()
    max_calls_per_ticket: int = 16
    arg_schemas: dict[str, dict[str, str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.agent_id or not self.agent_id.strip():
            raise ValueError("agent_id must be non-empty")
        if self.max_calls_per_ticket < 1:
            raise ValueError("max_calls_per_ticket must be >= 1")

    def allows(self, tool: str) -> bool:
        """True when ``tool`` is allowed and not denied (deny wins)."""
        return tool in self.allowed_tools and tool not in self.denied_tools


@dataclass(frozen=True)
class ToolGrant:
    """An authorized tool call."""

    call_id: str
    agent_id: str
    tool: str
    ticket_id: str


class ToolRouter:
    """Choke point for agent tool invocation."""

    def __init__(
        self, contracts: dict[str, AgentContract] | None = None
    ) -> None:
        self._contracts = contracts or {}
        self._policies: dict[str, ToolPolicy] = {}
        self._calls: dict[tuple[str, str, str], int] = {}  # (agent,ticket,tool)
        self._grants: dict[str, ToolGrant] = {}
        self._next_call = 1
        self._tool_stats: dict[str, dict[str, float]] = {}

    def register_policy(self, policy: ToolPolicy) -> None:
        """Install (or replace) the tool policy for an agent."""
        self._policies[policy.agent_id] = policy

    def policy_for(self, agent_id: str) -> ToolPolicy | None:
        """The installed policy for ``agent_id``, if any."""
        return self._policies.get(agent_id)

    def _calls_used(self, agent_id: str, ticket_id: str) -> int:
        return sum(
            n for (a, t, _), n in self._calls.items()
            if a == agent_id and t == ticket_id
        )

    def authorize(
        self,
        agent_id: str,
        tool: str,
        args: dict[str, object],
        ticket_id: str,
    ) -> ToolGrant:
        """Authorize one tool call; raises on any policy breach."""
        policy = self._policies.get(agent_id)
        if policy is None:
            raise AgentContractViolation(
                f"agent {agent_id!r} has no tool policy registered",
                agent_id=agent_id,
                tool=tool,
            )
        if not policy.allows(tool):
            raise AgentContractViolation(
                f"agent {agent_id!r} may not use tool {tool!r}",
                agent_id=agent_id,
                tool=tool,
                denied=tool in policy.denied_tools,
            )
        contract = self._contracts.get(agent_id)
        if contract is not None and not contract.may_use_tool(tool):
            raise AgentContractViolation(
                f"tool {tool!r} not in agent {agent_id!r} contract",
                agent_id=agent_id,
                tool=tool,
            )
        schema = policy.arg_schemas.get(tool)
        if schema:
            violations = check_payload(schema, args, what=f"tool {tool!r}")
            if violations:
                raise AgentContractViolation(
                    f"bad arguments for tool {tool!r}: " + "; ".join(violations),
                    agent_id=agent_id,
                    tool=tool,
                    violations=list(violations),
                )
        used = self._calls_used(agent_id, ticket_id)
        if used >= policy.max_calls_per_ticket:
            raise AgentBudgetExhausted(
                f"agent {agent_id!r} exceeded {policy.max_calls_per_ticket} "
                f"tool calls on ticket {ticket_id!r}",
                agent_id=agent_id,
                ticket_id=ticket_id,
                limit=policy.max_calls_per_ticket,
            )
        call_id = f"call-{self._next_call:06d}"
        self._next_call += 1
        grant = ToolGrant(
            call_id=call_id, agent_id=agent_id, tool=tool,
            ticket_id=ticket_id,
        )
        self._grants[call_id] = grant
        key = (agent_id, ticket_id, tool)
        self._calls[key] = self._calls.get(key, 0) + 1
        return grant

    def record_result(
        self, call_id: str, ok: bool, latency_ms: float = 0.0
    ) -> None:
        """Close a grant with its outcome (feeds reliability stats)."""
        grant = self._grants.pop(call_id, None)
        if grant is None:
            raise ValueError(f"unknown call_id {call_id!r}")
        stats = self._tool_stats.setdefault(
            grant.tool, {"calls": 0, "failures": 0, "latency_ms": 0.0}
        )
        stats["calls"] += 1
        stats["latency_ms"] += max(0.0, latency_ms)
        if not ok:
            stats["failures"] += 1

    def tool_stats(self, tool: str) -> dict[str, float]:
        """Reliability stats for ``tool`` (copy; zeros when unknown)."""
        stats = self._tool_stats.get(tool)
        if stats is None:
            return {"calls": 0, "failures": 0, "latency_ms": 0.0}
        out = dict(stats)
        out["failure_rate"] = (
            out["failures"] / out["calls"] if out["calls"] else 0.0
        )
        out["mean_latency_ms"] = (
            out["latency_ms"] / out["calls"] if out["calls"] else 0.0
        )
        return out

    def calls_used(self, agent_id: str, ticket_id: str) -> int:
        """Tool calls consumed by ``agent_id`` on ``ticket_id``."""
        return self._calls_used(agent_id, ticket_id)
