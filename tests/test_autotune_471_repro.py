"""Slice 471 — optimization reproducibility. Unit tests."""

from __future__ import annotations

import pytest

from hugrgate.autotune.controller import (
    ConfigStore,
    Mode,
    OptimizationController,
    TunableParameter,
)
from hugrgate.autotune.modes import OfflineDriver
from hugrgate.autotune.repro import (
    RunManifest,
    record_manifest,
    restore_bundle,
    snapshot_bundle,
    verify_replay,
)
from hugrgate.autotune.tuners._base import seeded_rng
from hugrgate.autotune.tuners.thresholds import ThresholdTuner
from hugrgate.errors import ReproducibilityError


def _dataset(seed=11, n=200):
    rng = seeded_rng(seed)
    out = []
    for _ in range(n // 2):
        out.append((rng.uniform(0.0, 0.45), 0))
    for _ in range(n // 2):
        out.append((rng.uniform(0.55, 1.0), 1))
    rng.shuffle(out)
    return out


def _make():
    store = ConfigStore()
    store.register(TunableParameter(name="min_prob", dtype="float",
                                    default=0.9, lo=0.0, hi=1.0))
    c = OptimizationController(store=store)
    c.register_objective("f1", lambda values: 0.0)
    tuner = ThresholdTuner(param="min_prob", objective_id="f1",
                           dataset=_dataset(), seed=1)
    c.register_tuner(tuner)
    driver = OfflineDriver()
    c.register_driver(driver)
    return c, tuner, driver


def test_replay_verdict_true_on_identical_rebuild():
    def _factory():
        c2, _tuner2, driver2 = _make()
        return c2, lambda: driver2.seen

    c, tuner, driver = _make()
    run = c.run_cycle(mode=Mode.OFFLINE, seed=9)
    manifest = record_manifest(c, run, {"threshold_tuner": tuner},
                               proposals=driver.seen,
                               data_fingerprint="ds-v1")
    verdict = verify_replay(manifest, _factory)
    assert verdict["match"] is True
    assert verdict["replay_signature"] == verdict["expected_signature"]
    assert verdict["manifest_run_id"] == run.run_id


def test_replay_mismatch_on_tampered_config():
    c, tuner, driver = _make()
    run = c.run_cycle(mode=Mode.OFFLINE, seed=9)
    manifest = record_manifest(c, run, {"threshold_tuner": tuner},
                               proposals=driver.seen)
    # tamper: replay starts at the optimum -> tuner stays silent ->
    # the replay signature (skipped) mismatches the recorded one
    manifest.config_before = {"min_prob": 0.5}

    def _factory():
        c2, _t, driver2 = _make()
        return c2, lambda: driver2.seen

    verdict = verify_replay(manifest, _factory)
    assert verdict["match"] is False
    assert verdict["replay_signature"] != verdict["expected_signature"]


def test_manifest_round_trip():
    c, tuner, driver = _make()
    run = c.run_cycle(mode=Mode.OFFLINE, seed=9)
    manifest = record_manifest(c, run, {"threshold_tuner": tuner},
                               proposals=driver.seen,
                               data_fingerprint="ds-v1")
    d = manifest.to_dict()
    back = RunManifest.from_dict(d)
    assert back.to_dict() == d
    assert back.tuners["threshold_tuner"]["param"] == "min_prob"


def test_manifest_corrupt_rejected():
    with pytest.raises(ReproducibilityError):
        RunManifest.from_dict({"nope": 1})
    with pytest.raises(ReproducibilityError):
        RunManifest.from_dict({"run_id": "x"})  # missing fields


def test_code_version_mismatch():
    c, tuner, driver = _make()
    run = c.run_cycle(mode=Mode.OFFLINE, seed=9)
    manifest = record_manifest(c, run, {"threshold_tuner": tuner},
                               proposals=driver.seen)
    manifest.code_version = "ancient"
    with pytest.raises(ReproducibilityError):
        verify_replay(manifest, lambda: (_make()[0], lambda: {}))


def test_snapshot_bundle_round_trip():
    values = {"b": 2, "a": 1.5, "c": "x"}
    bundle = snapshot_bundle(values)
    assert snapshot_bundle(values) == bundle  # deterministic
    assert restore_bundle(bundle) == values
    with pytest.raises(ReproducibilityError):
        restore_bundle(b"not json")
    with pytest.raises(ReproducibilityError):
        restore_bundle(b"[1, 2]")
