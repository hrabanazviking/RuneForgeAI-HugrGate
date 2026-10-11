"""Slice 10 (fallback-explain): FallbackChain.explain() human-readable report."""

from __future__ import annotations

from hugrgate.circuit import CircuitRegistry
from hugrgate.fallback import FallbackChain
from tests.ensemble_fakes import BIN_SPEC, ConstantBackend, FailingBackend


def _ok(name: str) -> ConstantBackend:
    return ConstantBackend(name, "yes", {"yes": 0.8, "no": 0.2},
                           spec_types=("binary",))


def test_explain_names_every_backend_and_order():
    chain = FallbackChain([_ok("b1"), _ok("b2"), _ok("b3")])
    text = chain.explain()
    assert isinstance(text, str) and text.strip()
    assert "b1 -> b2 -> b3" in text
    for name in ("b1", "b2", "b3"):
        assert name in text, f"backend {name} missing from explain()"


def test_explain_without_registry_reports_circuit_na():
    chain = FallbackChain([_ok("b1"), _ok("b2")])
    for line in chain.explain().splitlines()[1:]:
        assert "circuit=n/a" in line
        assert "last=never-attempted" in line


def test_explain_reports_last_outcome_after_evaluate():
    chain = FallbackChain([FailingBackend("flaky"), _ok("steady")])
    chain.evaluate({}, BIN_SPEC())
    text = chain.explain()
    assert "flaky: circuit=n/a last=failed" in text
    assert "steady: circuit=n/a last=ok" in text


def test_explain_reports_circuit_state_from_registry():
    registry = CircuitRegistry(failure_threshold=1)
    chain = FallbackChain(
        [FailingBackend("bad"), _ok("good")], circuits=registry)
    chain.evaluate({}, BIN_SPEC())  # failure opens the breaker (threshold 1)
    text = chain.explain()
    assert "bad: circuit=open last=failed" in text
    assert "good: circuit=closed last=ok" in text


def test_explain_skipped_backend_shows_circuit_open():
    registry = CircuitRegistry(failure_threshold=1)
    chain = FallbackChain(
        [FailingBackend("bad"), FailingBackend("also_bad")],
        circuits=registry)
    registry.get("also_bad").record_failure()  # pre-open the second breaker
    try:
        chain.evaluate({}, BIN_SPEC())
    except Exception:  # noqa: BLE001 - deliberately swallow any backend failure
        pass
    text = chain.explain()
    assert "also_bad: circuit=open last=skipped" in text


def test_explain_is_read_only():
    chain = FallbackChain([FailingBackend("x"), _ok("y")])
    before = dict(chain._last_outcome)
    chain.explain()
    chain.explain()
    assert dict(chain._last_outcome) == before
    assert [b.name for b in chain.backends] == ["x", "y"]
