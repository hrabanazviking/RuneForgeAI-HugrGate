"""Decision memory — episodic recall for the HugrGate runtime.

Campaign XIII (Decision Memory) gives the runtime useful historical
context without turning it into an opaque agent. The memory layer is
built on top of :mod:`hugrgate.provenance`, not beside it:

- :class:`~hugrgate.provenance.ProvenanceStore` remains the
  tamper-evident, hash-chained legal record of *what was decided*;
- :class:`~hugrgate.memory.history.DecisionHistory` keeps *episodes* —
  snapshots of decision records annotated with observed outcomes,
  ground truth, privacy classes, and tags — so the runtime can recall,
  compare, and learn from similar past decisions.

Episodes are deep-copied on the way in and on the way out; the memory
never hands out a mutable reference to its own state. All public
behavior is typed, thread-safe, and bounded (see
:mod:`hugrgate.memory.retention`).
"""

from __future__ import annotations

from hugrgate.memory.history import DecisionHistory, Episode
from hugrgate.memory.outcomes import OUTCOME_KINDS, Outcome
from hugrgate.memory.query import MemoryQuery, find_in_provenance

__all__ = [
    "OUTCOME_KINDS",
    "DecisionHistory",
    "Episode",
    "MemoryQuery",
    "Outcome",
    "find_in_provenance",
]
