"""Backend fault injection — crash, hang, latency, error-rate, and
malformed-result faults. Slices 252-256.

:class:`FaultyBackend` wraps any :class:`~hugrgate.backend.Backend`
and injects scripted failures into :meth:`evaluate`. Faults are armed
per mode with a rate in [0, 1] and a seed, so every fault sequence is
reproducible. The wrapper is transparent: capabilities, ``supports``,
``health``, ``name``, and ``is_remote`` delegate to the wrapped
backend, and every call is counted in :meth:`fault_stats`.

Fault modes (each slice wires one):

- ``CRASH`` (252) — ``evaluate`` raises
  :class:`~hugrgate.errors.BackendUnavailable`: the process died.
  Recoverable: failover or retry can succeed.
- ``HANG`` (253) — ``evaluate`` blocks until the caller's deadline;
  the timeout layer must convert it to ``TimeoutError``.
- ``LATENCY`` (254) — sleeps a configured delay before delegating.
- ``ERROR_RATE`` (255) — raises ``BackendError`` at the armed rate.
- ``MALFORMED`` (256) — returns a result outside the spec's value
  space; the validation layer must reject it.

These are test-only tools: nothing in production code paths arms
them — there is no flag that turns chaos on by accident.
"""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from hugrgate.backend import Backend
from hugrgate.errors import BackendError, BackendUnavailable, SpecError
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "CRASH",
    "ERROR_RATE",
    "HANG",
    "LATENCY",
    "MALFORMED",
    "FaultSpec",
    "FaultyBackend",
]

#: Fault mode: the backend process died mid-request.
CRASH = "crash"
#: Fault mode: evaluate never returns (slice 253).
HANG = "hang"#: Fault mode: artificial latency before delegating (slice 254).
LATENCY = "latency"
#: Fault mode: probabilistic BackendError (slice 255).
ERROR_RATE = "error_rate"
#: Fault mode: out-of-spec result (slice 256).
MALFORMED = "malformed"

#: All fault modes, in priority order: when several modes fire on one
#: call, the earliest in this tuple wins.
_ALL_MODES = (CRASH, HANG, ERROR_RATE, MALFORMED, LATENCY)


@dataclass(frozen=True)
class FaultSpec:
    """One armed fault: mode, per-call probability, seed, parameters."""

    mode: str
    rate: float = 1.0
    seed: int | None = None
    params: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.mode not in _ALL_MODES:
            raise SpecError(
                f"unknown fault mode {self.mode!r}; "
                f"expected one of {list(_ALL_MODES)}")
        if (not isinstance(self.rate, (int, float))
                or not 0.0 <= self.rate <= 1.0):
            raise SpecError(
                f"fault rate must be in [0, 1], got {self.rate!r}")


class FaultyBackend(Backend):
    """A backend wrapper that injects scripted faults into ``evaluate``.

    Each armed mode rolls independently per call against its own
    seeded RNG; when several modes fire on the same call, priority
    order is crash > hang > error_rate > malformed > latency.

    Modes are wired slice by slice (252-256); arming a mode that is
    not wired yet raises :class:`~hugrgate.errors.SpecError` rather
    than silently doing nothing.
    """

    #: Fault modes with working injectors in this build.
    _WIRED_MODES: tuple[str, ...] = (CRASH, HANG, LATENCY, ERROR_RATE)

    def __init__(self, backend: Backend):
        if not isinstance(backend, Backend):
            raise SpecError(
                "FaultyBackend wraps a Backend, got "
                f"{type(backend).__name__}")
        self._backend = backend
        self.name = backend.name
        self.is_remote = backend.is_remote
        self._lock = threading.RLock()
        self._armed: dict[str, FaultSpec] = {}
        self._rngs: dict[str, random.Random] = {}
        self._counts: dict[str, int] = {"clean": 0}

    # --- transparent delegation -------------------------------------------
    def capabilities(self) -> dict[str, Any]:
        return self._backend.capabilities()

    def supports(self, spec: DecisionSpec) -> bool:
        return self._backend.supports(spec)

    def health(self) -> dict[str, Any]:
        health = dict(self._backend.health())
        with self._lock:
            health["chaos_armed"] = sorted(self._armed)
        return health

    def warmup(self) -> None:
        self._backend.warmup()

    def close(self) -> None:
        self._backend.close()

    # --- fault arming ------------------------------------------------------
    def arm(self, spec: FaultSpec) -> FaultyBackend:
        """Arm (or re-arm) a fault mode. Returns self for chaining."""
        if spec.mode not in self._WIRED_MODES:
            raise SpecError(
                f"fault mode {spec.mode!r} is not wired in this build; "
                f"wired modes: {list(self._WIRED_MODES)}")
        self._check_params(spec)
        with self._lock:
            self._armed[spec.mode] = spec
            self._rngs[spec.mode] = random.Random(spec.seed)
            self._counts.setdefault(spec.mode, 0)
        return self

    def disarm(self, mode: str) -> FaultyBackend:
        with self._lock:
            self._armed.pop(mode, None)
            self._rngs.pop(mode, None)
        return self

    def disarm_all(self) -> FaultyBackend:
        with self._lock:
            self._armed.clear()
            self._rngs.clear()
        return self

    def armed_modes(self) -> list[str]:
        with self._lock:
            return sorted(self._armed)

    def fault_stats(self) -> dict[str, int]:
        """Per-mode fault counts plus clean calls."""
        with self._lock:
            return dict(self._counts)

    def reset_stats(self) -> FaultyBackend:
        with self._lock:
            modes = list(self._counts)
            self._counts = {"clean": 0}
            for mode in modes:
                if mode != "clean":
                    self._counts[mode] = 0
        return self

    # --- evaluation ---------------------------------------------------------
    def evaluate(self, state: Mapping[str, Any], spec: DecisionSpec,
                 context: Mapping[str, Any] | None = None
                 ) -> DecisionResult:
        mode = self._roll_fault()
        with self._lock:
            self._counts[mode if mode else "clean"] += 1
        if mode == CRASH:
            raise BackendUnavailable(
                f"chaos: injected crash of backend {self.name!r}")
        if mode == HANG:
            return self._inject_hang(state, spec, context)
        if mode == LATENCY:
            return self._inject_latency(state, spec, context)
        if mode == ERROR_RATE:
            self._inject_error_rate()
        # The last mode (malformed) is wired by slice 256, which extends
        # _WIRED_MODES and adds its branch here. _roll_fault can only
        # return a wired mode because arm() rejects the rest.
        return self._backend.evaluate(state, spec, context)

    def _roll_fault(self) -> str | None:
        """Roll each armed mode; priority crash > hang > error_rate >
        malformed > latency. Returns the winning mode or None.

        Only wired modes are rolled: :meth:`arm` rejects anything
        else, so an unwired mode can never win a roll.
        """
        with self._lock:
            armed = [(m, self._armed[m], self._rngs[m])
                     for m in _ALL_MODES
                     if m in self._armed and m in self._WIRED_MODES]
        for mode, spec, rng in armed:
            if rng.random() < spec.rate:
                return mode
        return None

    def _spec_for(self, mode: str) -> FaultSpec:
        with self._lock:
            return self._armed[mode]

    @staticmethod
    def _check_params(spec: FaultSpec) -> None:
        """Validate a fault spec's params at arm time."""
        if spec.mode == HANG:
            hang_s = spec.params.get("hang_s")
            if hang_s is not None and (
                    not isinstance(hang_s, (int, float)) or hang_s < 0):
                raise SpecError(
                    f"hang fault param 'hang_s' must be None or >= 0, "
                    f"got {hang_s!r}")
        if spec.mode == LATENCY:
            delay_s = spec.params.get("delay_s")
            if (not isinstance(delay_s, (int, float)) or delay_s < 0):
                raise SpecError(
                    f"latency fault param 'delay_s' is required and must "
                    f"be >= 0, got {delay_s!r}")
        if spec.mode == ERROR_RATE:
            message = spec.params.get("message", "chaos: injected backend error")
            if not isinstance(message, str) or not message.strip():
                raise SpecError(
                    f"error_rate fault param 'message' must be a non-empty "
                    f"string, got {message!r}")

    def _inject_hang(self, state: Mapping[str, Any], spec: DecisionSpec,
                     context: Mapping[str, Any] | None) -> DecisionResult:
        """Block the calling thread: endlessly, or for ``hang_s``
        seconds before delegating (a transient hang that recovers).

        An endless hang is only survivable behind a deadline enforcer
        such as :class:`~hugrgate.timeout.TimeoutBackend`, which runs
        ``evaluate`` on a daemon worker thread — the hung call can
        never block process exit.
        """
        hang_s = self._spec_for(HANG).params.get("hang_s")
        if hang_s is None:
            threading.Event().wait()  # never set: hangs forever
            raise AssertionError("unreachable")  # pragma: no cover
        threading.Event().wait(float(hang_s))
        return self._backend.evaluate(state, spec, context)

    def _inject_latency(self, state: Mapping[str, Any], spec: DecisionSpec,
                        context: Mapping[str, Any] | None) -> DecisionResult:
        """Sleep ``delay_s`` seconds, then delegate to the wrapped backend.

        The sleep models queueing/network delay *before* the backend
        starts work. Observed latency is measured by the caller with a
        monotonic clock; see the slice-254 measurement artifact.
        """
        delay_s = float(self._spec_for(LATENCY).params["delay_s"])
        if delay_s:
            time.sleep(delay_s)
        return self._backend.evaluate(state, spec, context)

    def _inject_error_rate(self) -> None:
        """Raise :class:`~hugrgate.errors.BackendError`: the backend
        answered, but with a failure. Unlike a crash (the process is
        gone) or a hang (no answer at all), an error is the backend
        *reporting* its own inability — recoverable, routable, and
        counted by the circuit breaker."""
        message = self._spec_for(ERROR_RATE).params.get(
            "message", "chaos: injected backend error")
        raise BackendError(f"{message} (backend {self.name!r})")
