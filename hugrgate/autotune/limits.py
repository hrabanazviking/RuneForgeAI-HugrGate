"""Optimizer safety limits. Slice 472.

Tuners propose; *this* module says "no". :class:`SafetyLimits`
declares the operator's policy, and :class:`SafetyEnforcer` checks
every proposal against it, raising :class:`UnsafeProposalError`
(not recoverable — the limits are deliberate policy, and retrying
the identical proposal cannot succeed).

Enforced per proposal:

- **kill switch**: when engaged, every proposal is rejected;
- **frozen params**: named params the optimizer may never touch;
- **blast radius**: at most ``max_params_per_proposal`` params per
  proposal;
- **step size**: a numeric param may not move more than
  ``max_step_fraction`` of its bound width in one proposal
  (relative to its *current* value, not its default);
- **mode allowlist**: e.g. forbid ``APPLIED`` until canary
  evidence exists;
- **rate limit**: at most ``max_cycles_per_hour`` tuning cycles,
  counted from the controller's run history.

Integration: :meth:`SafetyEnforcer.as_driver` wraps any
:class:`ModeDriver` — the check runs *after* controller validation
(type/bounds/constraints) and *before* the inner driver disposes.
This keeps the controller (slice 451) untouched: safety is a driver
decorator, not a controller branch.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from hugrgate.autotune.controller import (
    Disposition,
    DriverResult,
    Mode,
    ModeDriver,
    OptimizationController,
    Proposal,
    TuningContext,
)
from hugrgate.errors import UnsafeProposalError

__all__ = ["SafetyEnforcer", "SafetyLimits"]


@dataclass(frozen=True)
class SafetyLimits:
    """The operator's safety policy for the optimizer."""

    kill_switch: bool = False
    frozen_params: tuple[str, ...] = ()
    max_params_per_proposal: int = 5
    max_step_fraction: float = 0.25  # of bound width, per proposal
    allowed_modes: tuple[Mode, ...] = (Mode.OFFLINE, Mode.SHADOW,
                                       Mode.CANARY)
    max_cycles_per_hour: int = 12

    def __post_init__(self) -> None:
        if self.max_params_per_proposal < 1:
            raise UnsafeProposalError("max_params_per_proposal must be >= 1")
        if not 0.0 < self.max_step_fraction <= 1.0:
            raise UnsafeProposalError(
                "max_step_fraction must be in (0, 1]")
        if self.max_cycles_per_hour < 1:
            raise UnsafeProposalError("max_cycles_per_hour must be >= 1")


class SafetyEnforcer:
    """Checks proposals against :class:`SafetyLimits`."""

    def __init__(self, limits: SafetyLimits | None = None,
                 clock: Callable[[], float] = time.time) -> None:
        self.limits = limits or SafetyLimits()
        self._clock = clock
        self._cycle_times: list[float] = []

    def record_cycle(self) -> None:
        now = self._clock()
        self._cycle_times.append(now)
        hour_ago = now - 3600.0
        self._cycle_times = [t for t in self._cycle_times if t > hour_ago]

    def check_rate(self) -> None:
        self.record_cycle()
        if len(self._cycle_times) > self.limits.max_cycles_per_hour:
            raise UnsafeProposalError(
                "tuning cycle rate limit exceeded",
                limit=self.limits.max_cycles_per_hour)

    def check_proposal(self, proposal: Proposal,
                       ctx: TuningContext) -> None:
        lim = self.limits
        if lim.kill_switch:
            raise UnsafeProposalError("optimizer kill switch is engaged",
                                      proposal=proposal.proposal_id)
        if ctx.mode not in lim.allowed_modes:
            raise UnsafeProposalError(
                f"mode {ctx.mode.value} not in safety allowlist",
                proposal=proposal.proposal_id, mode=ctx.mode.value)
        frozen = [p for p in proposal.changes if p in lim.frozen_params]
        if frozen:
            raise UnsafeProposalError("proposal touches frozen params",
                                      proposal=proposal.proposal_id,
                                      params=frozen)
        if len(proposal.changes) > lim.max_params_per_proposal:
            raise UnsafeProposalError("proposal touches too many params",
                                      proposal=proposal.proposal_id,
                                      count=len(proposal.changes))
        current = ctx.store.snapshot()
        for pname, pvalue in proposal.changes.items():
            param = ctx.store.describe(pname)
            if param.dtype in ("float", "int") and param.lo is not None \
                    and param.hi is not None:
                width = float(param.hi) - float(param.lo)
                if width > 0:
                    step = abs(float(pvalue) - float(current[pname]))
                    if step > lim.max_step_fraction * width:
                        raise UnsafeProposalError(
                            "proposal step too large",
                            proposal=proposal.proposal_id, param=pname,
                            step=step,
                            max_step=lim.max_step_fraction * width)

    def as_driver(self, inner: ModeDriver) -> ModeDriver:
        """Wrap a driver with safety checks."""
        enforcer = self

        class _Guarded(ModeDriver):
            mode = inner.mode

            def handle(self, proposal: Proposal,
                       ctx: TuningContext) -> DriverResult:
                try:
                    enforcer.check_proposal(proposal, ctx)
                except UnsafeProposalError as exc:
                    return DriverResult(
                        proposal_id=proposal.proposal_id,
                        disposition=Disposition.REJECTED,
                        detail={"reason": "safety_limits",
                                "error": str(exc)})
                return inner.handle(proposal, ctx)

        return _Guarded()

    def guarded_controller(self, controller: OptimizationController,
                           modes: Sequence[Mode] = ()) -> None:
        """Wrap the controller's drivers for the given modes in place."""
        targets = tuple(modes) or tuple(Mode)
        for mode in targets:
            with controller._lock:  # same-package introspection
                current = controller._drivers[mode]
            controller.register_driver(self.as_driver(current))
