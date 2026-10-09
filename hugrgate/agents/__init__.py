"""HugrGate agent nervous system (Campaign XVI) — connective tissue
for agentic loops: event bus, reactive triggers, state propagation,
and inter-component signaling.

This package ties together the three systems that already exist —
decision memory (:mod:`hugrgate.memory`), observability tracing
(:mod:`hugrgate.observability`), and chaos experiments
(:mod:`hugrgate.chaos`) — into one bounded-decision nervous system
for larger agents.  It does not duplicate them: gates consult
memory access policy, signals feed observability, and the
simulator reuses chaos fault shapes.

Submodules are imported individually
(``from hugrgate.agents import contract``); this ``__init__`` stays
empty so importing the package never pulls the whole layer in —
the same convention as :mod:`hugrgate.observability`.
"""

from __future__ import annotations

__all__: list[str] = []
