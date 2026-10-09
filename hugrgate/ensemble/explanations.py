"""Ensemble explanations — the council's reasoning in plain words. Slice 120.

``metadata["ensemble"]`` is machine-readable; operators and auditors
need sentences. :func:`explain_ensemble` renders a human-readable
account of an ensemble decision from the recorded metadata:

- **concise**: one paragraph — the verdict, the vote split, the
  dissent, and any escalation, consensus, or calibration notes;
- **verbose**: a multi-line breakdown — per-member ballots with
  weights, the minority report, disagreement, consensus, and
  calibration sections.

Every claim in the text is read straight out of the metadata, so the
explanation can never drift from the recorded decision.
"""

from __future__ import annotations

from typing import Any, Dict, List

from hugrgate.errors import PolicyError
from hugrgate.result import DecisionResult

__all__ = [
    "explain_ensemble",
]

_STYLES = ("concise", "verbose")


def _pct(x: float) -> str:
    return f"{x:.0%}"


def _ballot_lines(ens: Dict[str, Any]) -> List[str]:
    lines = []
    weights = ens.get("weights", {})
    for ballot in ens.get("member_votes", []):
        name = ballot.get("backend", "?")
        w = weights.get(name)
        w_txt = f", weight {w:.2f}" if isinstance(w, (int, float)) else ""
        skipped = ballot.get("skipped")
        if skipped:
            lines.append(
                f"  - {name}: skipped "
                f"({ballot.get('skip_reason', 'no reason')})")
        else:
            lines.append(
                f"  - {name}: voted {ballot.get('value')!r} "
                f"(confidence {ballot.get('probability', 0.0):.2f}"
                f"{w_txt})")
    return lines


def _dissent_sentence(ens: Dict[str, Any]) -> str:
    dissenters = ens.get("minority_report") or []
    if not dissenters:
        return ""
    parts = [f"{d.get('backend')} voted {d.get('value')!r}"
             for d in dissenters]
    return " Dissent: " + "; ".join(parts) + "."


def _outcome_sentence(result: DecisionResult,
                      ens: Dict[str, Any]) -> str:
    """What happened after the vote (escalation / consensus)."""
    bits = []
    disagreement = ens.get("disagreement") or {}
    if disagreement.get("level") not in (None, "none"):
        bits.append(
            f"disagreement was {disagreement.get('level')} "
            f"({disagreement.get('disagreement_rate', 0.0):.0%} of "
            f"ballot pairs differed)")
    if result.metadata.get("policy_verdict") == "review":
        reason = result.metadata.get("review_reason", "")
        bits.append(f"flagged for human review ({reason})")
    if result.metadata.get("disagreement_fallback"):
        bits.append(
            f"fell back: {result.metadata['disagreement_fallback']}")
    consensus = ens.get("consensus") or {}
    if consensus:
        if consensus.get("passed"):
            bits.append(
                f"cleared the consensus bar "
                f"({_pct(consensus.get('winner_share', 0.0))} ≥ "
                f"{_pct(consensus.get('min_agreement', 0.0))})")
        else:
            bits.append(
                f"failed the consensus bar "
                f"({_pct(consensus.get('winner_share', 0.0))} < "
                f"{_pct(consensus.get('min_agreement', 0.0))})")
    calibration = ens.get("calibration") or {}
    if calibration.get("temperature") is not None:
        bits.append(
            f"probabilities temperature-calibrated "
            f"(T={calibration['temperature']:.2f})")
    skipped = ens.get("skipped_votes", 0)
    if skipped:
        bits.append(f"{skipped} member ballot(s) skipped")
    if result.fallback_used and "fell back" not in " ".join(bits):
        bits.append("a fallback backend decided")
    return (" " + " ".join(b + "." for b in bits)) if bits else ""


def _concise(result: DecisionResult, ens: Dict[str, Any]) -> str:
    if result.value is None:
        text = "The council declined to decide."
        return text + _outcome_sentence(result, ens)
    members = ens.get("members", [])
    share = ens.get("winner_share", 0.0)
    usable = ens.get("usable_votes", len(members))
    strategy = ens.get("strategy", "unknown")
    text = (
        f"The council chose {result.value!r} by {strategy} voting "
        f"with {result.probability:.0%} confidence: "
        f"{usable} of {len(members)} member ballots counted, "
        f"{_pct(share)} of the weighted vote for the winner.")
    text += _dissent_sentence(ens)
    text += _outcome_sentence(result, ens)
    return text


def _verbose(result: DecisionResult, ens: Dict[str, Any]) -> str:
    lines = []
    if result.value is None:
        lines.append("Verdict: the council declined to decide.")
    else:
        lines.append(
            f"Verdict: {result.value!r} by {ens.get('strategy')} "
            f"voting (confidence {result.probability:.0%}, "
            f"winner share {_pct(ens.get('winner_share', 0.0))}).")
    lines.append("Ballots:")
    lines.extend(_ballot_lines(ens) or ["  (no ballots recorded)"])
    dissenters = ens.get("minority_report") or []
    if dissenters:
        lines.append("Minority report:")
        for d in dissenters:
            lines.append(
                f"  - {d.get('backend')} dissented with "
                f"{d.get('value')!r} (confidence "
                f"{d.get('probability', 0.0):.2f})")
    else:
        lines.append("Minority report: unanimous — no dissenters.")
    outcome = _outcome_sentence(result, ens).strip()
    if outcome:
        lines.append("Notes: " + outcome)
    return "\n".join(lines)


def explain_ensemble(result: DecisionResult,
                     style: str = "concise") -> str:
    """Render an ensemble decision as human-readable text.

    Raises :class:`PolicyError` for non-ensemble results or unknown
    styles.
    """
    if style not in _STYLES:
        raise PolicyError(
            f"style must be one of {list(_STYLES)}, got {style!r}")
    ens = result.metadata.get("ensemble")
    if not isinstance(ens, dict):
        raise PolicyError("result carries no ensemble metadata")
    if ens.get("recorded") is False:
        raise PolicyError("result is not an ensemble decision")
    if style == "verbose":
        return _verbose(result, ens)
    return _concise(result, ens)
