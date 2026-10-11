"""DecisionResult.summarize() — one human-readable line (D4 result-summarize)."""

from hugrgate.result import DecisionResult


def _make(value, probability=0.87, backend="b1", latency_ms=12.3,
          accepted=True, distribution=None):
    return DecisionResult(
        value=value,
        probability=probability,
        distribution=distribution if distribution is not None else {},
        accepted=accepted,
        backend=backend,
        latency_ms=latency_ms,
    )


def test_summarize_accepted_includes_value_backend_latency_probability():
    result = _make(value="x")
    summary = result.summarize()
    assert isinstance(summary, str)
    assert "'x'" in summary, f"value repr missing: {summary}"
    assert "b1" in summary, f"backend missing: {summary}"
    assert "12.3" in summary, f"latency missing: {summary}"
    assert "0.87" in summary, f"probability missing: {summary}"
    assert "accepted" in summary, f"status missing: {summary}"


def test_summarize_with_distribution():
    result = _make(value="x", probability=0.87,
                   distribution={"x": 0.87, "y": 0.13})
    summary = result.summarize()
    assert "'x'" in summary
    assert "accepted" in summary


def test_summarize_rejected_status():
    result = _make(value="x", accepted=False)
    summary = result.summarize()
    assert "rejected" in summary


def test_summarize_abstention_value_none_renders_cleanly():
    result = _make(value=None)
    summary = result.summarize()
    assert isinstance(summary, str)
    assert len(summary) > 0
    assert "b1" in summary
    assert "12.3" in summary
    assert "0.87" in summary
    assert "abstain" in summary.lower(), f"no abstention note: {summary}"


def test_summarize_abstention_non_string_value():
    # Non-string values must also survive repr cleanly.
    result = _make(value=42)
    summary = result.summarize()
    assert "42" in summary


def test_summarize_is_stable_single_line():
    result = _make(value="x")
    summary = result.summarize()
    assert "\n" not in summary
    # Deterministic across calls.
    assert result.summarize() == summary
