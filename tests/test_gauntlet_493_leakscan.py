"""Slice 493 — privacy leak gauntlet.

Redaction exists; this gauntlet plants obviously-fake canary
secrets in decision state and proves none escape through the
observable surfaces: log records, exception messages, and
provenance records under restrictive privacy classes.
"""

from __future__ import annotations

import logging
from typing import Any

from hugrgate import DecisionPolicy, DecisionResult, DecisionSpec, HugrGate
from hugrgate.backend import Backend
from hugrgate.gauntlet.leakscan import (
    CANARIES,
    LeakScanner,
    run_leak_gauntlet,
    scan_text,
)


class _Stub(Backend):
    name = "stub"

    def capabilities(self) -> dict[str, Any]:
        return {"spec_types": ["categorical"]}

    def supports(self, spec: DecisionSpec) -> bool:
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None) -> DecisionResult:
        return DecisionResult(value="a", probability=0.9,
                              distribution={"a": 0.9, "b": 0.1})


SPEC = DecisionSpec(type="categorical", options=["a", "b"])


def _gate() -> HugrGate:
    gate = HugrGate()
    gate.register(_Stub())
    return gate


def test_scan_text_finds_canaries():
    assert scan_text("nothing here") == []
    assert scan_text(f"leaked {CANARIES[0]}!") == [CANARIES[0]]
    assert scan_text(" ".join(CANARIES)) == list(CANARIES)


def test_leak_scanner_captures_records():
    logger = logging.getLogger("hugrgate")
    with LeakScanner() as scanner:
        logger.warning("test message %s", CANARIES[1])
    assert scanner.findings() == [CANARIES[1]]
    # Handler is detached afterwards.
    assert scanner._handler not in logger.handlers


def test_no_leak_through_logs():
    gate = _gate()
    try:
        with LeakScanner() as scanner:
            gate.decide({"api_key": CANARIES[0], "x": 1}, SPEC,
                        DecisionPolicy())
        assert scanner.findings() == [], scanner.log_text()[:500]
    finally:
        gate.close()


def test_no_leak_through_exceptions():
    gate = _gate()
    try:
        try:
            gate.decide({"api_key": CANARIES[0]}, {"type": "nope"},
                        DecisionPolicy())
        except Exception as exc:  # noqa: BLE001 - message under test
            assert scan_text(str(exc)) == []
        else:
            raise AssertionError("expected the invalid spec to fail")
    finally:
        gate.close()


def test_no_leak_through_provenance():
    import json

    gate = _gate()
    try:
        for privacy_class in ("strict", "forbidden"):
            gate.decide({"api_key": CANARIES[0], "x": 1}, SPEC,
                        DecisionPolicy(privacy_class=privacy_class))
        blob = json.dumps(
            [r.to_dict() for r in gate.provenance.scan(lambda r: True)],
            default=str)
        assert scan_text(blob) == []
    finally:
        gate.close()


def test_full_gauntlet_is_clean():
    gate = _gate()
    try:
        report = run_leak_gauntlet(gate, SPEC)
        assert report.clean, report.findings
    finally:
        gate.close()


def test_gauntlet_catches_a_planted_leak():
    # Prove the gauntlet is not theater: a backend whose error
    # message echoes state must be caught.
    class _Leaky(Backend):
        name = "leaky"

        def capabilities(self):
            return {"spec_types": ["categorical"]}

        def supports(self, spec):
            return True

        def evaluate(self, state, spec, context=None):
            raise RuntimeError(f"backend saw {state['api_key']}")

    gate = HugrGate()
    gate.register(_Leaky())
    try:
        report = run_leak_gauntlet(gate, SPEC)
        assert not report.clean
        surfaces = [f["surface"] for f in report.findings]
        assert "exception" in surfaces
        assert CANARIES[0] in report.findings[0]["canaries"]
    finally:
        gate.close()
