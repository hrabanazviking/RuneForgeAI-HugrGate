"""Network fault simulation. Slices 263-264.

The network is a shared fate: when it fails, every remote backend
fails together. :class:`NetworkSimulator` scripts reachability per
host — up/down/partitioned (slice 263) plus time-based flapping
with an injectable clock (slice 264). :class:`NetworkGuard` wraps a
remote backend and fails *fast* with :class:`BackendUnavailable`
when its host is unreachable — no hanging on dead sockets, no
half-open waits.

The policy invariant under test: network failure must never
silently weaken policy. ``DecisionPolicy.remote_inference`` and
``minimum_probability`` are not mutated by network events; when no
backend can serve, the system abstains instead of lowering the bar.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
from typing import Any

from hugrgate.backend import Backend
from hugrgate.errors import BackendUnavailable, SpecError
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "DOWN",
    "UP",
    "NetworkGuard",
    "NetworkSimulator",
]

#: Host reachability states.
UP = "up"
DOWN = "down"


class NetworkSimulator:
    """Scripted per-host network reachability.

    Unknown hosts are reachable by default; :meth:`partition` sets
    per-host states for partial-failure scenarios; :meth:`flap`
    makes a host oscillate up/down on a period (slice 264).
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._down: set[str] = set()
        # host -> (period_s, up_fraction, clock)
        self._flaps: dict[str, tuple[float, float,
                                     Callable[[], float]]] = {}

    def set_down(self, host: str) -> NetworkSimulator:
        with self._lock:
            self._flaps.pop(host, None)
            self._down.add(host)
        return self

    def set_up(self, host: str) -> NetworkSimulator:
        with self._lock:
            self._flaps.pop(host, None)
            self._down.discard(host)
        return self

    def set_all_up(self) -> NetworkSimulator:
        """Heal the whole network, stopping all flaps."""
        with self._lock:
            self._down.clear()
            self._flaps.clear()
        return self

    def flap(self, host: str, period_s: float, up_fraction: float,
             clock: Callable[[], float] = time.monotonic
             ) -> NetworkSimulator:
        """Oscillate ``host`` up/down with period ``period_s``.

        The host is reachable for ``up_fraction`` of each period
        (``0.0`` = always down, ``1.0`` = always up). ``clock`` is
        injectable so tests can drive time deterministically.
        """
        if period_s <= 0:
            raise SpecError(
                f"flap period_s must be > 0, got {period_s}")
        if not 0.0 <= up_fraction <= 1.0:
            raise SpecError(
                f"flap up_fraction must be in [0, 1], got {up_fraction}")
        with self._lock:
            self._down.discard(host)
            self._flaps[host] = (float(period_s), float(up_fraction),
                                 clock)
        return self

    def stop_flap(self, host: str) -> NetworkSimulator:
        """End flapping; the host returns to statically up."""
        with self._lock:
            self._flaps.pop(host, None)
            self._down.discard(host)
        return self

    def flapping_hosts(self) -> list[str]:
        with self._lock:
            return sorted(self._flaps)

    def partition(self, states: Mapping[str, str]) -> NetworkSimulator:
        """Set several hosts at once: ``{"host-a": DOWN, ...}``.

        Explicit static states stop any flap on those hosts.
        """
        with self._lock:
            for host, state in states.items():
                if state == DOWN:
                    self._flaps.pop(host, None)
                    self._down.add(host)
                elif state == UP:
                    self._flaps.pop(host, None)
                    self._down.discard(host)
                else:
                    raise SpecError(
                        f"unknown network state {state!r} for host "
                        f"{host!r}; expected {UP!r} or {DOWN!r}")
        return self

    def is_reachable(self, host: str) -> bool:
        with self._lock:
            flap = self._flaps.get(host)
            if flap is not None:
                period_s, up_fraction, clock = flap
                phase = clock() % period_s
                return phase < period_s * up_fraction
            return host not in self._down

    def down_hosts(self) -> list[str]:
        with self._lock:
            return sorted(self._down)


class NetworkGuard(Backend):
    """Fail-fast wrapper for remote backends under network faults.

    Local backends (``is_remote=False``) never touch the network and
    always delegate. Remote backends delegate only while their host
    is reachable; otherwise they raise :class:`BackendUnavailable`
    immediately — the chaos equivalent of a connection refusal,
    without the socket timeout wait.
    """

    def __init__(self, backend: Backend, network: NetworkSimulator,
                 host: str | None = None):
        if not isinstance(backend, Backend):
            raise SpecError(
                "NetworkGuard wraps a Backend, got "
                f"{type(backend).__name__}")
        if not isinstance(network, NetworkSimulator):
            raise SpecError(
                "NetworkGuard needs a NetworkSimulator, got "
                f"{type(network).__name__}")
        self._backend = backend
        self._network = network
        self._host = host or backend.name
        if not self._host.strip():
            raise SpecError("network host must be non-empty")
        self.name = backend.name
        self.is_remote = backend.is_remote
        self._lock = threading.RLock()
        self._allowed = 0
        self._blocked = 0

    @property
    def host(self) -> str:
        return self._host

    def capabilities(self) -> dict[str, Any]:
        caps = dict(self._backend.capabilities())
        caps["network_guarded"] = True
        return caps

    def supports(self, spec: DecisionSpec) -> bool:
        return self._backend.supports(spec)

    def health(self) -> dict[str, Any]:
        health = dict(self._backend.health())
        health["network_reachable"] = (
            not self.is_remote
            or self._network.is_reachable(self._host))
        return health

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {"allowed": self._allowed, "blocked": self._blocked}

    def evaluate(self, state: Mapping[str, Any], spec: DecisionSpec,
                 context: Mapping[str, Any] | None = None
                 ) -> DecisionResult:
        if self.is_remote and not self._network.is_reachable(self._host):
            with self._lock:
                self._blocked += 1
            raise BackendUnavailable(
                f"network unreachable: remote backend {self.name!r} "
                f"on host {self._host!r}")
        with self._lock:
            self._allowed += 1
        return self._backend.evaluate(state, spec, context)
