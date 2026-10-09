"""Router rollback. Slice 145.

Learning systems change their minds; operators need yesterday's mind
back. :class:`RouterRollback` is a bounded checkpoint stack for
adaptive-policy state (bandit weights, competence profiles, exploration
counters — anything JSON-serializable):

- :meth:`checkpoint` snapshots a state dict with a note and returns its
  id (``ckpt-<n>``);
- :meth:`rollback` restores the state from ``steps`` checkpoints back,
  returning a deep copy;
- the audit log records every checkpoint *and* every rollback — and the
  audit log itself is append-only: rolling back never erases the fact
  that a rollback happened.

Guardrails: ``steps < 1`` is rejected; rolling back past the oldest
checkpoint is rejected (there is no "before the beginning"); the
returned state is deep-copied so the caller cannot mutate the archive.
States must be JSON-serializable — checked at checkpoint time, loudly,
because a checkpoint that cannot round-trip is a lie.
"""

from __future__ import annotations

import copy
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping

from hugrgate.errors import SpecError

__all__ = [
    "Checkpoint",
    "RouterRollback",
]


@dataclass(frozen=True)
class Checkpoint:
    """One archived policy state."""

    checkpoint_id: str
    created_at: float
    note: str
    state: Dict[str, Any] = field(compare=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "created_at": self.created_at,
            "note": self.note,
            "state": copy.deepcopy(self.state),
        }


class RouterRollback:
    """Bounded, audited checkpoint stack for adaptive-policy state."""

    def __init__(self, max_checkpoints: int = 20) -> None:
        if max_checkpoints < 1:
            raise SpecError(
                f"max_checkpoints must be >= 1, got {max_checkpoints}")
        self.max_checkpoints = max_checkpoints
        self._checkpoints: List[Checkpoint] = []
        self._audit: List[Dict[str, Any]] = []
        self._counter = 0

    def __len__(self) -> int:
        return len(self._checkpoints)

    @staticmethod
    def _validate_state(state: Mapping[str, Any]) -> Dict[str, Any]:
        if not isinstance(state, Mapping):
            raise SpecError(
                f"checkpoint state must be a mapping, got "
                f"{type(state).__name__}")
        # Strict check first: default=str would happily stringify a
        # lambda into a lie. A checkpoint that cannot round-trip
        # exactly is rejected here, loudly.
        try:
            strict = json.dumps(dict(state), sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise SpecError(
                f"checkpoint state is not JSON-serializable: {exc}") from exc
        return json.loads(strict)

    def checkpoint(self, state: Mapping[str, Any],
                   note: str = "") -> str:
        """Archive ``state``; returns the checkpoint id."""
        canonical = self._validate_state(state)
        self._counter += 1
        ckpt_id = f"ckpt-{self._counter}"
        self._checkpoints.append(Checkpoint(
            checkpoint_id=ckpt_id,
            created_at=time.time(),
            note=note,
            state=canonical,
        ))
        while len(self._checkpoints) > self.max_checkpoints:
            self._checkpoints.pop(0)
        self._audit.append({
            "action": "checkpoint",
            "checkpoint_id": ckpt_id,
            "note": note,
            "at": time.time(),
        })
        return ckpt_id

    def rollback(self, steps: int = 1) -> Dict[str, Any]:
        """Restore the state from ``steps`` checkpoints back.

        The checkpoint stack is *not* truncated: after a rollback the
        operator can still roll forward by... no — forward history is
        the stack itself; the restored state should be re-checkpointed
        explicitly, which keeps the audit trail honest.
        """
        if not isinstance(steps, int) or steps < 1:
            raise SpecError(
                f"rollback steps must be a positive int, got {steps!r}")
        if steps > len(self._checkpoints):
            raise SpecError(
                f"cannot roll back {steps} steps: only "
                f"{len(self._checkpoints)} checkpoints archived")
        target = self._checkpoints[-steps]
        self._audit.append({
            "action": "rollback",
            "steps": steps,
            "restored_checkpoint_id": target.checkpoint_id,
            "at": time.time(),
        })
        return copy.deepcopy(target.state)

    def history(self) -> List[Dict[str, Any]]:
        """Checkpoint ids in archive order (oldest first)."""
        return [c.to_dict() for c in self._checkpoints]

    def audit_log(self) -> List[Dict[str, Any]]:
        """Append-only record of checkpoints and rollbacks."""
        return [dict(entry) for entry in self._audit]

    def latest_id(self) -> str | None:
        if not self._checkpoints:
            return None
        return self._checkpoints[-1].checkpoint_id
