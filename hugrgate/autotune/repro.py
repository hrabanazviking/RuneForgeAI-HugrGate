"""Optimization reproducibility. Slice 471.

A tuning run that cannot be reproduced cannot be trusted. This
module captures a *run manifest* — everything needed to replay a
controller cycle deterministically — and verifies replays.

A :class:`RunManifest` records: the run id, seed, mode, tuner names
with their dataclass configs, objective ids, constraint ids (by
qualified name or repr), the data fingerprint, the config snapshot
before the run, and the code version. :func:`verify_replay` rebuilds
an equivalent controller through a caller-supplied factory, re-runs
the cycle, and compares the resulting proposals change-for-change.

Honest limits, recorded in the manifest: objectives and constraints
are opaque callables — they are recorded by qualified name when
available, else by repr — so replay requires the same code version
(also recorded). A tuner that reads wall-clock time, unseeded RNG,
or the live network is not replayable; the tuners in
:mod:`hugrgate.autotune.tuners` are seeded and deterministic by
construction.
"""

from __future__ import annotations

import dataclasses
import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from hugrgate.autotune.controller import (
    Mode,
    OptimizationController,
    Proposal,
    TuningRun,
)
from hugrgate.autotune.provenance import hash_mapping
from hugrgate.errors import ReproducibilityError

__all__ = [
    "RunManifest",
    "record_manifest",
    "restore_bundle",
    "snapshot_bundle",
    "verify_replay",
]

CODE_VERSION = "gjallarbu-campaign-xix"


def snapshot_bundle(values: Mapping[str, Any]) -> bytes:
    """Canonical JSON bytes of a config snapshot (deterministic)."""
    return json.dumps(dict(values), sort_keys=True,
                      default=str).encode("utf-8")


def restore_bundle(bundle: bytes) -> dict[str, Any]:
    """Inverse of :func:`snapshot_bundle`."""
    try:
        data = json.loads(bundle.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ReproducibilityError("config bundle is corrupt",
                                   error=repr(exc)) from exc
    if not isinstance(data, dict):
        raise ReproducibilityError("config bundle must decode to a dict")
    return dict(data)


def _callable_ref(fn: Callable[..., Any]) -> str:
    mod = getattr(fn, "__module__", "?")
    qual = getattr(fn, "__qualname__", repr(fn))
    return f"{mod}.{qual}"


def _tuner_config(tuner: Any) -> dict[str, Any]:
    if dataclasses.is_dataclass(tuner) and not isinstance(tuner, type):
        return json.loads(json.dumps(dataclasses.asdict(tuner),
                                     default=str))
    return {"repr": repr(tuner)}


@dataclass
class RunManifest:
    """Everything needed to replay one tuning cycle."""

    run_id: str
    seed: int
    mode: str
    tuners: dict[str, dict[str, Any]]  # name -> dataclass config
    objective_ids: list[str]
    objective_refs: dict[str, str]
    constraint_refs: list[str]
    data_fingerprint: str
    config_before: dict[str, Any]
    config_before_hash: str
    proposal_signatures: list[list[str]] = field(default_factory=list)
    code_version: str = CODE_VERSION
    recorded_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "seed": self.seed,
            "mode": self.mode,
            "tuners": {k: dict(v) for k, v in self.tuners.items()},
            "objective_ids": list(self.objective_ids),
            "objective_refs": dict(self.objective_refs),
            "constraint_refs": list(self.constraint_refs),
            "data_fingerprint": self.data_fingerprint,
            "config_before": dict(self.config_before),
            "config_before_hash": self.config_before_hash,
            "proposal_signatures": [list(s) for s in self.proposal_signatures],
            "code_version": self.code_version,
            "recorded_at": self.recorded_at,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> RunManifest:
        try:
            return cls(
                run_id=str(d["run_id"]), seed=int(d["seed"]),
                mode=str(d["mode"]),
                tuners={k: dict(v) for k, v in d["tuners"].items()},
                objective_ids=list(d["objective_ids"]),
                objective_refs=dict(d["objective_refs"]),
                constraint_refs=list(d["constraint_refs"]),
                data_fingerprint=str(d["data_fingerprint"]),
                config_before=dict(d["config_before"]),
                config_before_hash=str(d["config_before_hash"]),
                proposal_signatures=[list(s) for s in
                                     d.get("proposal_signatures", [])],
                code_version=str(d.get("code_version", "?")),
                recorded_at=float(d.get("recorded_at", 0.0)))
        except (KeyError, TypeError, ValueError) as exc:
            raise ReproducibilityError("run manifest is corrupt",
                                       error=repr(exc)) from exc


def record_manifest(controller: OptimizationController, run: TuningRun,
                    tuners: Mapping[str, Any],
                    proposals: Mapping[str, Proposal] | None = None,
                    data_fingerprint: str = "") -> RunManifest:
    """Capture a manifest for a completed run.

    ``proposals`` maps proposal_id -> Proposal (e.g. from the mode
    driver's journal) so the manifest records what each proposal
    actually changed.
    """
    with controller._lock:  # same-package introspection
        objectives = dict(controller._objectives)
        constraints = list(controller._constraints)
    config_before = controller.store.snapshot()
    signatures = [[t, h, d]
                  for t, h, d in _proposal_signature(run, proposals or {})]
    return RunManifest(
        run_id=run.run_id, seed=run.seed, mode=run.mode.value,
        tuners={name: _tuner_config(t) for name, t in tuners.items()},
        objective_ids=sorted(objectives),
        objective_refs={k: _callable_ref(v)
                        for k, v in objectives.items()},
        constraint_refs=[_callable_ref(c) for c in constraints],
        data_fingerprint=data_fingerprint,
        config_before=config_before,
        config_before_hash=hash_mapping(config_before),
        proposal_signatures=signatures)


def _proposal_signature(run: TuningRun,
                        proposals: Mapping[str, Proposal]) -> list[tuple[str, str, str]]:
    """Comparable per-proposal outcome: (tuner, changes-hash, disposition)."""
    sigs = []
    for r in run.results:
        prop = proposals.get(r.proposal_id)
        if prop is not None:
            sigs.append((prop.tuner, hash_mapping(prop.changes),
                         r.disposition.value))
        else:
            tuner = str(r.detail.get("tuner", ""))
            sigs.append((tuner, hash_mapping({}), r.disposition.value))
    return sorted(sigs)


def verify_replay(manifest: RunManifest,
                  make_controller: Callable[
                      [], tuple[OptimizationController,
                                Callable[[], Mapping[str, Proposal]]]],
                  ) -> dict[str, Any]:
    """Rebuild, re-run, and compare. Returns a verdict dict.

    ``make_controller`` must build an equivalent controller (same
    tuners, objectives, constraints, params) from the manifest's
    tuner configs, and return ``(controller, proposals_fn)`` where
    ``proposals_fn`` — called after the replay cycle — returns the
    replay run's proposal_id -> Proposal mapping (e.g. from the mode
    driver's journal). The replay restores the recorded config-before
    snapshot, runs the cycle with the recorded seed/mode, and
    compares proposal signatures change-for-change.
    """
    if manifest.code_version != CODE_VERSION:
        raise ReproducibilityError(
            "code version mismatch: manifest recorded under "
            f"{manifest.code_version}, replaying under {CODE_VERSION}")
    controller, proposals_fn = make_controller()
    controller.store.restore(manifest.config_before)
    replay = controller.run_cycle(mode=Mode(manifest.mode),
                                  seed=manifest.seed)
    actual = [[t, h, d]
              for t, h, d in _proposal_signature(replay, proposals_fn())]
    match = actual == [list(s) for s in manifest.proposal_signatures]
    return {"match": match,
            "reproduced_run_id": replay.run_id,
            "manifest_run_id": manifest.run_id,
            "replay_signature": actual,
            "expected_signature": [list(s) for s in
                                   manifest.proposal_signatures]}
