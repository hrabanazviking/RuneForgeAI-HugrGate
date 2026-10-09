"""Slice 490 — hostile backend gauntlet.

The gate's contract is total containment: ``decide`` must only let
taxonomy errors escape. Attacking it found two real gaps, both now
fixed in ``hugrgate/core.py``:

1. ``_translate_backend_error`` (and the async path's inline copy)
   caught ``Exception`` — a hostile backend raising raw
   ``BaseException`` / ``KeyboardInterrupt`` / ``SystemExit``
   propagated uncaught and could kill the host's control flow.
   Now contained as chained ``BackendError``.
2. ``_finalize_result`` touched ``result.latency_ms`` before any
   type check — a backend returning a string/None leaked
   ``AttributeError``. Now fails closed with ``BackendError`` on
   non-``DecisionResult`` returns.

``hugrgate/gauntlet/hostile.py`` holds the hostile doubles; every
one is driven through the live ``decide`` path below.
"""

from __future__ import annotations

import pytest

from hugrgate import DecisionPolicy, DecisionSpec, HugrGate
from hugrgate.errors import Abstention, BackendError, HugrGateError, SpecError
from hugrgate.gauntlet.hostile import (
    BadDistributionBackend,
    BaseExceptionBackend,
    ExplodingBackend,
    KeyboardInterruptBackend,
    NaNBackend,
    NoneBackend,
    OutOfSpaceBackend,
    SystemExitBackend,
    WrongTypeBackend,
)

SPEC = DecisionSpec(type="categorical", options=["a", "b"])


def _decide(backend) -> object:
    gate = HugrGate()
    gate.register(backend)
    try:
        return gate.decide({"x": 1}, SPEC, DecisionPolicy())
    finally:
        gate.close()


def test_exploding_backend_contained():
    with pytest.raises(BackendError):
        _decide(ExplodingBackend())


def test_base_exception_contained():
    """Raw BaseException must not escape the gate (slice 490 fix)."""
    with pytest.raises(BackendError) as exc_info:
        _decide(BaseExceptionBackend())
    assert isinstance(exc_info.value.__cause__, BaseException)


def test_keyboard_interrupt_contained():
    """A hostile KeyboardInterrupt must not kill the host loop."""
    with pytest.raises(BackendError) as exc_info:
        _decide(KeyboardInterruptBackend())
    assert isinstance(exc_info.value.__cause__, KeyboardInterrupt)


def test_system_exit_contained():
    """A hostile SystemExit must not exit the host process."""
    with pytest.raises(BackendError) as exc_info:
        _decide(SystemExitBackend())
    assert isinstance(exc_info.value.__cause__, SystemExit)


def test_nan_probability_contained():
    with pytest.raises(HugrGateError):
        _decide(NaNBackend())


def test_wrong_type_return_contained():
    """A string return must not leak AttributeError (slice 490 fix)."""
    with pytest.raises(BackendError) as exc_info:
        _decide(WrongTypeBackend())
    assert "not a DecisionResult" in str(exc_info.value)


def test_none_return_contained():
    with pytest.raises(BackendError):
        _decide(NoneBackend())


def test_out_of_space_value_rejected():
    with pytest.raises(SpecError):
        _decide(OutOfSpaceBackend())


def test_bad_distribution_rejected():
    with pytest.raises(HugrGateError):
        _decide(BadDistributionBackend())


def test_abstention_still_propagates():
    from hugrgate.backend import Backend

    class _Abstain(Backend):
        name = "abstain"

        def capabilities(self):
            return {"spec_types": ["categorical"]}

        def supports(self, spec):
            return True

        def evaluate(self, state, spec, context=None):
            raise Abstention("nope")

    with pytest.raises(Abstention):
        _decide(_Abstain())


def test_backend_error_subclass_propagates_unchanged():
    from hugrgate.backend import Backend
    from hugrgate.errors import BackendUnavailable

    class _Down(Backend):
        name = "down"

        def capabilities(self):
            return {"spec_types": ["categorical"]}

        def supports(self, spec):
            return True

        def evaluate(self, state, spec, context=None):
            raise BackendUnavailable("gone")

    with pytest.raises(BackendUnavailable):
        _decide(_Down())


def test_cancelled_error_propagates_in_async_path():
    """Slice 500 regression: CancelledError is control flow, not hostility.

    Containing it broke asyncio.wait_for timeouts (the waiter needs
    the cancellation to propagate so it can raise TimeoutError).
    """
    import asyncio

    from hugrgate.backend import Backend

    class _Cancelling(Backend):
        name = "cancelling"

        def capabilities(self):
            return {"spec_types": ["categorical"]}

        def supports(self, spec):
            return True

        async def aevaluate(self, state, spec, context=None):
            raise asyncio.CancelledError("spurious")

        def evaluate(self, state, spec, context=None):
            raise AssertionError("sync path not under test")

    async def main():
        gate = HugrGate()
        gate.register(_Cancelling())
        try:
            with pytest.raises(asyncio.CancelledError):
                await gate.adecide({"x": 1}, SPEC, DecisionPolicy())
        finally:
            gate.close()

    asyncio.run(main())


def test_wait_for_timeout_still_raises_timeout_error():
    """End-to-end: a slow backend under wait_for yields TimeoutError."""
    import asyncio

    from hugrgate.backend import Backend
    from hugrgate.result import DecisionResult

    class _Slow(Backend):
        name = "slow"

        def capabilities(self):
            return {"spec_types": ["categorical"]}

        def supports(self, spec):
            return True

        def evaluate(self, state, spec, context=None):
            raise AssertionError("async-only")

        async def aevaluate(self, state, spec, context=None):
            await asyncio.sleep(30)
            return DecisionResult(value="a", probability=1.0,
                                  distribution={"a": 1.0, "b": 0.0})

    async def main():
        gate = HugrGate()
        gate.register(_Slow())
        try:
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(
                    gate.adecide({"x": 1}, SPEC, DecisionPolicy()),
                    timeout=0.2)
        finally:
            gate.close()

    asyncio.run(main())
