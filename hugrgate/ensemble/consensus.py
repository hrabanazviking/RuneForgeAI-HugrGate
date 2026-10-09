"""Consensus thresholds — supermajority gates. Slice 113.

Disagreement *detection* (111) classifies a split; consensus
*thresholds* set the bar a winner must clear to be accepted at all.
The winner's share (``metadata["ensemble"]["winner_share"]``, falling
back to the result probability) must reach ``min_agreement`` —
otherwise the decision becomes an abstention naming the shortfall.

Presets: :meth:`ConsensusConfig.majority` (0.5),
:meth:`ConsensusConfig.supermajority` (2/3),
:meth:`ConsensusConfig.unanimity` (1.0).

Wire it into an ensemble via the ``consensus`` strategy option::

    Ensemble(members, strategy="hard",
             strategy_options={"consensus": 0.67})
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Union

from hugrgate.abstain import abstain
from hugrgate.errors import PolicyError
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "ConsensusConfig",
    "winner_share",
    "apply_consensus",
    "maybe_apply_consensus",
]


class ConsensusConfig:
    """The bar a winner must clear."""

    def __init__(self, min_agreement: float = 0.5):
        if not 0.0 < min_agreement <= 1.0:
            raise PolicyError(
                f"min_agreement must be in (0, 1], got {min_agreement}")
        self.min_agreement = float(min_agreement)

    @classmethod
    def majority(cls) -> "ConsensusConfig":
        return cls(0.5)

    @classmethod
    def supermajority(cls) -> "ConsensusConfig":
        return cls(2.0 / 3.0)

    @classmethod
    def unanimity(cls) -> "ConsensusConfig":
        return cls(1.0)

    def to_dict(self) -> Dict[str, float]:
        return {"min_agreement": self.min_agreement}

    def __repr__(self) -> str:
        return f"ConsensusConfig(min_agreement={self.min_agreement!r})"


def winner_share(result: DecisionResult) -> float:
    """The winner's share of the decision.

    Prefers the ensemble's recorded ``winner_share`` (vote share for
    ballot strategies); falls back to the result probability.
    """
    meta = result.metadata.get("ensemble", {})
    share = meta.get("winner_share")
    if isinstance(share, (int, float)):
        return float(share)
    return result.probability


def apply_consensus(result: DecisionResult, spec: DecisionSpec,
                    config: Optional[ConsensusConfig] = None
                    ) -> DecisionResult:
    """Accept the result iff the winner's share clears the bar.

    Never raises: a shortfall becomes an abstention whose reason names
    the share and the required bar.
    """
    config = config or ConsensusConfig()
    share = winner_share(result)
    if share >= config.min_agreement:
        result.metadata.setdefault("ensemble", {})[
            "consensus"] = {"min_agreement": config.min_agreement,
                            "winner_share": share,
                            "passed": True}
        return result
    out = abstain(
        spec,
        reason=(f"consensus {share:.3f} below required agreement "
                f"{config.min_agreement:.3f}"),
        backend=result.backend,
        metadata={"consensus": {"min_agreement": config.min_agreement,
                                "winner_share": share,
                                "passed": False}})
    out.metadata.setdefault("ensemble", {})["consensus"] = {
        "min_agreement": config.min_agreement,
        "winner_share": share, "passed": False}
    return out


def maybe_apply_consensus(result: DecisionResult, spec: DecisionSpec,
                          setting: Union[None, float, ConsensusConfig,
                                         Dict[str, Any]] = None
                          ) -> DecisionResult:
    """Apply the consensus gate when configured, else pass through.

    ``setting`` may be a float (min_agreement), a ConsensusConfig, or
    a dict like ``{"min_agreement": 0.67}``.
    """
    if setting is None:
        return result
    if isinstance(setting, ConsensusConfig):
        config = setting
    elif isinstance(setting, dict):
        try:
            bar = float(setting.get("min_agreement", 0.5))
        except (TypeError, ValueError) as e:
            raise PolicyError(
                f"consensus min_agreement must be a number, got "
                f"{setting.get('min_agreement')!r}: {e}")
        config = ConsensusConfig(min_agreement=bar)
    else:
        try:
            bar = float(setting)
        except (TypeError, ValueError) as e:
            raise PolicyError(
                f"consensus setting must be a number, a dict, or a "
                f"ConsensusConfig, got {setting!r}: {e}")
        config = ConsensusConfig(min_agreement=bar)
    return apply_consensus(result, spec, config)
