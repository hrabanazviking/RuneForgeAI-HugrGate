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
