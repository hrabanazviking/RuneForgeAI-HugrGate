"""Distributed chaos tests. Slice 223.

The cluster must degrade gracefully, not mysteriously. :class:`FaultInjector`
describes a fault profile — drop / delay / duplicate / corrupt rates —
with a seeded RNG so chaos is reproducible. :class:`ChaosProxy` is an
``httpx`` transport wrapper that applies the profile between the RPC
client and the (loopback) wire:

- **drop** — the request never arrives (``httpx.ConnectError``);
- **delay** — the request sleeps before it is forwarded;
- **duplicate** — the request is delivered twice, the first reply wins;
- **corrupt** — the first wire byte is flipped, so the receiver's
  ``decode_message`` rejects the envelope.

One fault per request, in priority order drop > corrupt > duplicate >
delay. The proxy counts every fault (``stats()``) for assertions.

These are test-only tools: they live in the shipped package (like the
loopback transports in the test suite) so operators can rehearse
their own topologies, but nothing in production code paths enables
them — there is no flag that turns chaos on by accident.
"""

from __future__ import annotations

import random
import threading
import time

import httpx

from hugrgate.errors import SpecError

__all__ = [
    "ChaosProxy",
    "FaultInjector",
]

#: Fault names, in priority order.
FAULT_DROP = "drop"
FAULT_CORRUPT = "corrupt"
FAULT_DUPLICATE = "duplicate"
FAULT_DELAY = "delay"


class FaultInjector:
    """A seeded, reproducible fault profile.

    Rates are per-request probabilities in [0, 1]. ``seed`` makes the
    fault sequence deterministic; ``seed=None`` uses system entropy.
    """

    def __init__(self, drop_rate: float = 0.0, delay_s: float = 0.0,
                 delay_rate: float = 0.0, duplicate_rate: float = 0.0,
                 corrupt_rate: float = 0.0,
                 seed: int | None = None) -> None:
        for name, rate in (("drop_rate", drop_rate),
                           ("delay_rate", delay_rate),
                           ("duplicate_rate", duplicate_rate),
                           ("corrupt_rate", corrupt_rate)):
            if (not isinstance(rate, (int, float))
                    or not 0.0 <= rate <= 1.0):
                raise SpecError(f"{name} must be in [0, 1], got {rate!r}")
        if not isinstance(delay_s, (int, float)) or delay_s < 0:
            raise SpecError(f"delay_s must be >= 0, got {delay_s!r}")
        self.drop_rate = float(drop_rate)
        self.delay_s = float(delay_s)
        self.delay_rate = float(delay_rate)
        self.duplicate_rate = float(duplicate_rate)
        self.corrupt_rate = float(corrupt_rate)
        self._rng = random.Random(seed)
        self._lock = threading.RLock()

    def next_fault(self) -> str | None:
        """Roll one fault for the next request (priority ordered)."""
        with self._lock:
            if self._rng.random() < self.drop_rate:
                return FAULT_DROP
            if self._rng.random() < self.corrupt_rate:
                return FAULT_CORRUPT
            if self._rng.random() < self.duplicate_rate:
                return FAULT_DUPLICATE
            if self._rng.random() < self.delay_rate:
                return FAULT_DELAY
            return None


class ChaosProxy(httpx.BaseTransport):
    """Apply a :class:`FaultInjector` profile around a transport."""

    def __init__(self, transport: httpx.BaseTransport,
                 injector: FaultInjector | None = None) -> None:
        self._transport = transport
        self._injector = injector or FaultInjector()
        self._counts = {FAULT_DROP: 0, FAULT_CORRUPT: 0,
                        FAULT_DUPLICATE: 0, FAULT_DELAY: 0,
                        "clean": 0}
        self._lock = threading.RLock()

    @property
    def injector(self) -> FaultInjector:
        return self._injector

    def stats(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counts)

    def _note(self, fault: str | None) -> None:
        with self._lock:
            self._counts[fault if fault else "clean"] += 1

    @staticmethod
    def _corrupt(request: httpx.Request) -> httpx.Request:
        body = bytearray(request.content)
        if body:
            body[0] ^= 0xFF  # the envelope framing dies first
        return httpx.Request(request.method, request.url,
                             headers=request.headers, content=bytes(body))

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        fault = self._injector.next_fault()
        self._note(fault)
        if fault == FAULT_DROP:
            raise httpx.ConnectError("chaos: packet dropped")
        if fault == FAULT_DELAY:
            time.sleep(self._injector.delay_s)
        if fault == FAULT_CORRUPT:
            request = self._corrupt(request)
        response = self._transport.handle_request(request)
        if fault == FAULT_DUPLICATE:
            # Delivered twice; the first reply wins. The duplicate
            # exercises the receiver's idempotency — its fate must not
            # fail the original request.
            try:
                self._transport.handle_request(request)
            except Exception:  # noqa: BLE001 - duplicate is fire-and-forget
                pass
        return response
