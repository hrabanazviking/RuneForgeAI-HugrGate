"""Feature-freeze enforcement for the HugrGate 1.0 release (slice 476).

The freeze is real machinery, not a sign on the door:

- :class:`FreezeManifest` loads ``release/freeze.toml`` — the frozen
  version, the freeze date, the allowed change kinds, and the recorded
  waivers.
- :class:`ChangeRequest` describes a proposed change; :func:`evaluate`
  returns a :class:`FreezeVerdict` of ``allow``, ``deny``, or
  ``waiver-required`` with human-readable reasons.
- :func:`check_public_api_growth` diffs a baseline public-name set
  against the live one so the freeze gate can catch undeclared API
  additions (the full audit lives in slice 486).

Change kinds follow conventional-commit vocabulary. Only kinds that
cannot grow the public surface or the dependency closure may land
without a waiver: ``bugfix``, ``security``, ``docs``, ``tests``,
``refactor``, ``perf``. ``feature``, ``api-add``, and
``dependency-add`` are denied unless a waiver recorded in the
manifest names the exact change.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import tomllib

__all__ = [
    "DEFAULT_MANIFEST_PATH",
    "ChangeRequest",
    "FreezeManifest",
    "FreezeVerdict",
    "Waiver",
    "check_public_api_growth",
    "evaluate",
    "load_manifest",
]

DEFAULT_MANIFEST_PATH = (
    Path(__file__).resolve().parent.parent.parent / "release" / "freeze.toml"
)

VerdictKind = Literal["allow", "deny", "waiver-required"]


@dataclass(frozen=True)
class Waiver:
    """A recorded exception to the freeze."""

    id: str
    change: str
    reason: str
    approved_by: str


@dataclass(frozen=True)
class ChangeRequest:
    """A proposed change awaiting freeze evaluation."""

    kind: str  # conventional-commit kind, e.g. "bugfix", "feature"
    description: str
    touches_public_api: bool = False
    adds_dependency: bool = False
    waiver_id: str | None = None


@dataclass(frozen=True)
class FreezeVerdict:
    """The freeze gate's answer for one :class:`ChangeRequest`."""

    verdict: VerdictKind
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class FreezeManifest:
    """The parsed ``release/freeze.toml``."""

    version: str
    frozen_at: str
    allowed_kinds: frozenset[str]
    waivers: tuple[Waiver, ...] = ()

    def waiver_ids(self) -> frozenset[str]:
        return frozenset(w.id for w in self.waivers)


def load_manifest(path: str | Path = DEFAULT_MANIFEST_PATH) -> FreezeManifest:
    """Parse the freeze manifest; raises on missing/corrupt files."""
    path = Path(path)
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    freeze = raw.get("freeze")
    if not isinstance(freeze, dict):
        raise ValueError(f"{path}: missing [freeze] table")
    version = freeze.get("version")
    frozen_at = freeze.get("frozen_at")
    allowed = freeze.get("allowed_kinds")
    if not isinstance(version, str) or not version:
        raise ValueError(f"{path}: [freeze].version must be a non-empty string")
    if not isinstance(frozen_at, str) or not frozen_at:
        raise ValueError(f"{path}: [freeze].frozen_at must be a non-empty string")
    if not isinstance(allowed, list) or not allowed or not all(
        isinstance(k, str) for k in allowed
    ):
        raise ValueError(f"{path}: [freeze].allowed_kinds must be a non-empty list")
    waivers: list[Waiver] = []
    for entry in raw.get("waivers", []):
        if not isinstance(entry, dict):
            raise ValueError(f"{path}: waiver entries must be tables")
        try:
            waivers.append(
                Waiver(
                    id=str(entry["id"]),
                    change=str(entry["change"]),
                    reason=str(entry["reason"]),
                    approved_by=str(entry["approved_by"]),
                )
            )
        except KeyError as exc:
            raise ValueError(
                f"{path}: waiver missing required field {exc}"
            ) from exc
    return FreezeManifest(
        version=version,
        frozen_at=frozen_at,
        allowed_kinds=frozenset(allowed),
        waivers=tuple(waivers),
    )


def evaluate(change: ChangeRequest, manifest: FreezeManifest) -> FreezeVerdict:
    """Decide whether ``change`` may land under the freeze.

    Rules, in order:

    1. An unknown/empty kind is denied outright — the gate cannot
       classify what it cannot name.
    2. A change touching the public API or adding a dependency needs a
       waiver naming it, even if its kind is otherwise allowed.
    3. An allowed kind with no surface growth is allowed.
    4. A forbidden kind (``feature``, ``api-add``, ``dependency-add``,
       ...) is denied unless a recorded waiver names its ``waiver_id``.
    """
    reasons: list[str] = []
    kind = change.kind.strip().lower()
    if not kind:
        return FreezeVerdict("deny", ("change kind is empty",))

    surface_growth = change.touches_public_api or change.adds_dependency
    waiver_known = (
        change.waiver_id is not None and change.waiver_id in manifest.waiver_ids()
    )
    if change.waiver_id is not None and not waiver_known:
        return FreezeVerdict(
            "deny",
            (f"waiver {change.waiver_id!r} is not recorded in the freeze manifest",),
        )

    if kind not in manifest.allowed_kinds:
        if waiver_known:
            reasons.append(
                f"kind {kind!r} is frozen but waiver {change.waiver_id} covers it"
            )
            return FreezeVerdict("allow", tuple(reasons))
        reasons.append(
            f"kind {kind!r} is not in the freeze allow-list "
            f"({sorted(manifest.allowed_kinds)})"
        )
        return FreezeVerdict("waiver-required", tuple(reasons))

    if surface_growth and not waiver_known:
        if change.touches_public_api:
            reasons.append("change touches the public API")
        if change.adds_dependency:
            reasons.append("change adds a dependency")
        reasons.append("surface growth needs a recorded waiver during the freeze")
        return FreezeVerdict("waiver-required", tuple(reasons))

    reasons.append(f"kind {kind!r} is allowed under the freeze")
    if waiver_known:
        reasons.append(f"waiver {change.waiver_id} recorded")
    return FreezeVerdict("allow", tuple(reasons))


def check_public_api_growth(
    baseline: set[str] | frozenset[str], current: set[str] | frozenset[str]
) -> dict[str, Any]:
    """Diff a baseline public-name set against the live set.

    Returns ``{"added": [...], "removed": [...], "growth": bool}`` with
    sorted name lists. Additions during a freeze must be waived;
    removals are breaking changes regardless of freeze (slice 486
    audits both against the full API baseline).
    """
    added = sorted(set(current) - set(baseline))
    removed = sorted(set(baseline) - set(current))
    return {"added": added, "removed": removed, "growth": bool(added),
            "breakage": bool(removed)}
