"""Agent Nervous System (Campaign XVI) — agent replay.

Slice 397.  "It worked in prod" is not a debugging strategy.
:class:`AgentReplay` records a ticket's step inputs/outputs and
re-runs them against an agent function to answer two questions:

1. **fidelity** — does the agent still produce the recorded
   outputs for the recorded inputs? (regression after a
   contract version bump, slice 387);
2. **determinism** — do two runs with the same seed produce
   identical outputs? (required before any claim of
   reproducibility, and an input to the release gate, 400).

Recording is explicit: :meth:`record_step` appends
``(kind, input, output)`` triples per ticket.  :meth:`replay`
feeds each recorded input back through ``agent_fn`` and diffs
outputs with ``==`` (plus a ``repr`` fallback note on
mismatch).  :meth:`check_determinism` runs the whole ticket
twice.  Event payloads must be JSON-safe — replay is a
debugging tool, not a second memory store.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "AgentReplay",
    "RecordedStep",
    "ReplayReport",
]

#: agent_fn signature: (step_input, seed) -> step_output.
AgentFn = Callable[[Any, int | None], Any]


@dataclass(frozen=True)
class RecordedStep:
    """One recorded step."""

    index: int
    kind: str
    step_input: Any
    step_output: Any


@dataclass(frozen=True)
class ReplayReport:
    """Outcome of replaying a ticket."""

    ticket_id: str
    steps: int
    matched: int
    mismatches: tuple[int, ...]
    deterministic: bool
    seed: int | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def fidelity(self) -> float:
        """Fraction of steps reproducing the recorded output."""
        return self.matched / self.steps if self.steps else 1.0


def _json_safe(value: Any, what: str) -> None:
    try:
        json.dumps(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{what} must be JSON-safe: {exc}") from None


class AgentReplay:
    """Records ticket steps and replays them against agent functions."""

    def __init__(self) -> None:
        self._steps: dict[str, list[RecordedStep]] = {}

    def record_step(
        self,
        ticket_id: str,
        kind: str,
        step_input: Any,
        step_output: Any,
    ) -> RecordedStep:
        """Append one recorded step for ``ticket_id``."""
        if not ticket_id:
            raise ValueError("ticket_id must be non-empty")
        if not kind:
            raise ValueError("kind must be non-empty")
        _json_safe(step_input, "step_input")
        _json_safe(step_output, "step_output")
        steps = self._steps.setdefault(ticket_id, [])
        step = RecordedStep(index=len(steps), kind=kind,
                            step_input=step_input, step_output=step_output)
        steps.append(step)
        return step

    def record(self, ticket_id: str,
               events: list[Mapping[str, Any]]) -> int:
        """Bulk-record ``events`` (each: kind/input/output)."""
        count = 0
        for e in events:
            self.record_step(ticket_id, str(e.get("kind", "step")),
                             e.get("input"), e.get("output"))
            count += 1
        return count

    def steps(self, ticket_id: str) -> tuple[RecordedStep, ...]:
        """Recorded steps for ``ticket_id`` (empty when unknown)."""
        return tuple(self._steps.get(ticket_id, ()))

    def replay(
        self,
        ticket_id: str,
        agent_fn: AgentFn,
        *,
        seed: int | None = None,
    ) -> ReplayReport:
        """Re-run recorded inputs through ``agent_fn`` and diff."""
        steps = self._steps.get(ticket_id)
        if not steps:
            raise ValueError(f"no recorded steps for {ticket_id!r}")
        mismatches: list[int] = []
        notes: list[str] = []
        for step in steps:
            try:
                output = agent_fn(step.step_input, seed)
            except Exception as exc:  # noqa: BLE001 - recorded as mismatch
                mismatches.append(step.index)
                notes.append(f"step {step.index} raised: {exc}")
                continue
            if output != step.step_output:
                mismatches.append(step.index)
                notes.append(
                    f"step {step.index} diff: recorded "
                    f"{step.step_output!r} vs replay {output!r}"
                )
        deterministic = self.check_determinism(ticket_id, agent_fn,
                                               seed=seed)
        return ReplayReport(
            ticket_id=ticket_id,
            steps=len(steps),
            matched=len(steps) - len(mismatches),
            mismatches=tuple(mismatches),
            deterministic=deterministic,
            seed=seed,
            notes=tuple(notes),
        )

    def check_determinism(
        self,
        ticket_id: str,
        agent_fn: AgentFn,
        *,
        seed: int | None = None,
    ) -> bool:
        """True when two runs over the recorded inputs agree."""
        steps = self._steps.get(ticket_id)
        if not steps:
            raise ValueError(f"no recorded steps for {ticket_id!r}")

        def run() -> list[str]:
            out = []
            for step in steps:
                try:
                    out.append(repr(agent_fn(step.step_input, seed)))
                except Exception as exc:  # noqa: BLE001 - nondeterminism
                    out.append(f"<raised {exc}>")
            return out

        return run() == run()

    def forget(self, ticket_id: str) -> bool:
        """Drop a ticket's recording; True when it existed."""
        return self._steps.pop(ticket_id, None) is not None
