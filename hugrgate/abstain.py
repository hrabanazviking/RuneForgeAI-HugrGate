"""Abstention — typed "I don't know" results and review banding. Slice 15.

Two outcomes are weaker than acceptance, and they are distinct:

- **abstain**: no value at all (``value=None``, ``accepted=False``). The
  gate refuses to decide. Carries a machine-readable ``abstain_reason``.
- **review**: a value *was* produced, but its probability fell inside the
  policy's ``review_band`` — a human should look before it is acted on.
  ``accepted=False`` with ``policy_verdict="review"`` in metadata.

:func:`apply_abstention_policy` maps :meth:`DecisionPolicy.evaluate`
verdicts to these result types without raising, so pipelines can stay
exception-free when they prefer values over control flow.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec


def abstain(spec: DecisionSpec, reason: str = "below_threshold",
            backend: str = "unknown",
            metadata: Optional[Dict[str, Any]] = None) -> DecisionResult:
    """Build an abstention result: no value, not accepted.

    The distribution is uniform over the spec's value space (empty for
    numeric specs) — maximum uncertainty, honestly represented.
    """
    space = spec.value_space()
    distribution = ({o: 1.0 / len(space) for o in space}
                    if space else {})
    meta = {"abstain_reason": reason, "policy_verdict": "abstain"}
    if metadata:
        meta.update(metadata)
    return DecisionResult(
        value=None,
        probability=0.0,
        distribution=distribution,
        uncertainty=1.0,
        accepted=False,
        backend=backend,
        model="abstention",
        metadata=meta,
    )


def mark_for_review(result: DecisionResult, reason: str,
                    reviewer: Optional[str] = None) -> DecisionResult:
    """Flag an existing result for human review.

    The value and probability are preserved; ``accepted`` becomes False
    and the verdict is recorded in metadata.
    """
    meta = dict(result.metadata)
    meta["policy_verdict"] = "review"
    meta["review_reason"] = reason
    if reviewer:
        meta["reviewer"] = reviewer
    return DecisionResult(
        value=result.value,
        probability=result.probability,
        distribution=dict(result.distribution),
        uncertainty=result.uncertainty,
        accepted=False,
        backend=result.backend,
        model=result.model,
        latency_ms=result.latency_ms,
        calibration_profile=result.calibration_profile,
        fallback_used=result.fallback_used,
        metadata=meta,
    )


def apply_abstention_policy(result: DecisionResult, spec: DecisionSpec,
                            policy: DecisionPolicy) -> DecisionResult:
    """Apply the policy's accept/review/abstain verdict to a result.

    Never raises: ``"abstain"`` becomes an abstention result,
    ``"review"`` becomes a review-flagged result, ``"accept"`` passes
    the result through with ``accepted=True``.
    """
    verdict = policy.evaluate(result)
    if verdict == "accept":
        result.accepted = True
        result.metadata.setdefault("policy_verdict", "accept")
        return result
    if verdict == "review":
        lo, hi = policy.review_band or (0.0, 0.0)
        return mark_for_review(
            result,
            f"probability {result.probability:.3f} inside review band "
            f"[{lo:.3f}, {hi:.3f})")
    # verdict == "abstain"
    reason = (f"latency {result.latency_ms:.1f}ms exceeded "
              f"{policy.maximum_latency_ms}ms"
              if policy.maximum_latency_ms is not None
              and result.latency_ms > policy.maximum_latency_ms
              else f"probability {result.probability:.3f} below minimum "
                   f"{policy.minimum_probability:.3f}")
    return abstain(spec, reason=reason, backend=result.backend,
                   metadata={"fallback_used": result.fallback_used})
