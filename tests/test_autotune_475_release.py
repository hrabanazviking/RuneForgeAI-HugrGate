"""Slice 475 — autonomous optimization release gate. Unit tests."""

from __future__ import annotations

import pytest

from hugrgate.autotune.release import (
    HOLD,
    RELEASE,
    ReleaseCheck,
    assert_release,
    campaign_checks,
    release_gate,
)
from hugrgate.errors import AutotuneError


def test_gate_passes_on_campaign():
    verdict = release_gate()
    print("\n" + verdict.summary())
    assert verdict.passed
    assert verdict.verdict == RELEASE
    assert len(verdict.results) == 6
    assert all(r["passed"] for r in verdict.results)


def test_gate_holds_on_failing_check():
    checks = [ReleaseCheck("bad", lambda: (False, "nope")),
              ReleaseCheck("good", lambda: (True, "ok"))]
    verdict = release_gate(checks)
    assert not verdict.passed
    assert verdict.verdict == HOLD
    with pytest.raises(AutotuneError):
        assert_release(verdict)


def test_crashing_check_holds_not_crashes():
    def _boom():
        raise RuntimeError("check bug")

    verdict = release_gate([ReleaseCheck("boom", _boom)])
    assert not verdict.passed
    assert "raised" in verdict.results[0]["detail"]


def test_zero_checks_refused():
    with pytest.raises(AutotuneError):
        release_gate([])


def test_assert_release_passes_silently():
    assert_release(release_gate())  # must not raise


def test_verdict_serializable():
    d = release_gate().to_dict()
    assert d["verdict"] == "release"
    assert len(d["results"]) == 6
    assert "generated_at" in d


def test_campaign_checks_named():
    names = [c.name for c in campaign_checks()]
    assert names == ["error-taxonomy", "controller-smoke", "safety-posture",
                     "provenance-integrity", "reproducibility",
                     "tuner-exports"]
