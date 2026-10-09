"""Agent Nervous System (Campaign XVI) — intent routing.

Slice 378.  Raw user input arrives as text; the nervous system must
decide *which agent owns it*.  :class:`IntentRouter` maps intents to
agents with keyword scoring:

- each registration binds ``(intent, agent_id)`` to a set of
  keywords and a static priority;
- scoring is case-insensitive on word boundaries (``"cat"`` never
  matches ``"concatenate"``) — substring false positives are a
  routing-bug classic;
- the winner is the highest ``keyword_hits + priority``; ties break
  deterministically by ``(agent_id, intent)`` so routing is stable
  across runs;
- when nothing matches, the registered fallback agent takes the
  ticket with confidence 0; with no fallback registered the router
  raises :class:`AgentNotFound` rather than guessing.

When contracts are supplied, registration verifies the agent
actually declares the intent (slice 376) — a router that sends
traffic to agents that never claimed the intent is a misconfiguration
the contract layer exists to catch.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from hugrgate.agents.contract import AgentContract
from hugrgate.errors import AgentContractViolation, AgentNotFound

__all__ = [
    "IntentRoute",
    "IntentRouter",
    "tokenize",
]


def tokenize(text: str) -> frozenset[str]:
    """Lower-cased word tokens of ``text`` (word boundaries)."""
    return frozenset(re.findall(r"[a-z0-9]+", text.lower()))


@dataclass(frozen=True)
class IntentRoute:
    """Where one input was routed and why."""

    intent: str
    agent_id: str
    confidence: float
    reason: str
    fallback: bool = False


@dataclass
class _Registration:
    intent: str
    agent_id: str
    keywords: frozenset[str]
    priority: int


@dataclass
class IntentRouter:
    """Keyword-scored intent → agent routing with fallback."""

    contracts: dict[str, AgentContract] = field(default_factory=dict)
    _regs: list[_Registration] = field(default_factory=list)
    _fallback: str = ""

    def register(
        self,
        intent: str,
        agent_id: str,
        *,
        keywords: tuple[str, ...] = (),
        priority: int = 0,
    ) -> None:
        """Bind ``intent`` to ``agent_id`` with match ``keywords``."""
        if not intent or not intent.strip():
            raise ValueError("intent must be non-empty")
        if not agent_id or not agent_id.strip():
            raise ValueError("agent_id must be non-empty")
        contract = self.contracts.get(agent_id)
        if contract is not None and not contract.handles_intent(intent):
            raise AgentContractViolation(
                f"agent {agent_id!r} does not declare intent {intent!r}",
                agent_id=agent_id,
                intent=intent,
            )
        kws = frozenset(kw.lower() for kw in keywords if kw.strip())
        self._regs = [
            r for r in self._regs
            if not (r.intent == intent and r.agent_id == agent_id)
        ]
        self._regs.append(
            _Registration(intent=intent, agent_id=agent_id,
                          keywords=kws, priority=priority)
        )

    def unregister(self, intent: str, agent_id: str) -> bool:
        """Remove one registration; True when it existed."""
        before = len(self._regs)
        self._regs = [
            r for r in self._regs
            if not (r.intent == intent and r.agent_id == agent_id)
        ]
        return len(self._regs) < before

    def set_fallback(self, agent_id: str) -> None:
        """Agent receiving traffic no registration claims."""
        self._fallback = agent_id

    def route(self, text: str, *, intent_hint: str = "") -> IntentRoute:
        """Route ``text`` to the best agent.

        ``intent_hint`` (e.g. from a classifier upstream) restricts
        candidates to that intent when non-empty.
        """
        tokens = tokenize(text)
        candidates = [
            r for r in self._regs
            if not intent_hint or r.intent == intent_hint
        ]
        scored: list[tuple[float, str, str, _Registration, int]] = []
        for reg in candidates:
            hits = len(reg.keywords & tokens)
            if hits or intent_hint == reg.intent:
                score = float(hits) + reg.priority
                scored.append((score, reg.agent_id, reg.intent, reg, hits))
        if scored:
            scored.sort(key=lambda s: (-s[0], s[1], s[2]))
            score, agent_id, intent, reg, hits = scored[0]
            total_kw = max(len(reg.keywords), 1)
            confidence = min(1.0, (hits / total_kw) * 0.9 + 0.1)
            return IntentRoute(
                intent=intent,
                agent_id=agent_id,
                confidence=round(confidence, 3),
                reason=(f"{hits}/{len(reg.keywords)} keywords matched "
                        f"(priority {reg.priority})"),
            )
        if self._fallback:
            return IntentRoute(
                intent=intent_hint or "unknown",
                agent_id=self._fallback,
                confidence=0.0,
                reason="no registration matched; fallback agent",
                fallback=True,
            )
        raise AgentNotFound(
            f"no agent registered for {text!r}",
            text=text[:120],
            intent_hint=intent_hint,
        )

    def intents(self) -> tuple[str, ...]:
        """All registered intents, sorted."""
        return tuple(sorted({r.intent for r in self._regs}))
