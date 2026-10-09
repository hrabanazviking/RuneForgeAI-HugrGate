"""Tests for slice 099 — calibration benchmark suite.

Reduced rounds (n=200) against a tmp artifact path, per the Campaign III
worker tip: the full artifact is regenerated after the final test run,
before committing.
"""

from __future__ import annotations

import json

import pytest

from hugrgate.calibration.bench import (
    BENCH_CALIBRATORS,
    DATASETS,
    generate_dataset,
    run_benchmark,
)
from hugrgate.errors import CalibrationError


def test_generate_dataset_shapes():
    for kind in DATASETS:
        s, y = generate_dataset(kind, 200, seed=5)
        assert len(s) == len(y) == 200
        assert all(0.0 <= v <= 1.0 for v in s)
        assert set(y) <= {0, 1}
    # Deterministic for a fixed seed.
    assert (generate_dataset("overconfident", 200, seed=5)
            == generate_dataset("overconfident", 200, seed=5))
    with pytest.raises(CalibrationError):
        generate_dataset("nope", 200, seed=5)
    with pytest.raises(CalibrationError):
        generate_dataset("overconfident", 5, seed=5)


def test_benchmark_reduced_rounds(tmp_path):
    artifact = run_benchmark(seed=123, n=200)
    assert artifact["name"] == "calibration_500"
    assert artifact["seed"] == 123
    assert artifact["n_per_dataset"] == 200
    assert len(artifact["results"]) == len(DATASETS) * len(BENCH_CALIBRATORS)
    for cell in artifact["results"]:
        assert set(cell) == {"dataset", "calibrator", "n", "before",
                             "after", "delta_brier", "delta_ece"}
        for m in ("brier", "log_loss", "ece"):
            assert cell["before"][m] >= 0.0
            assert cell["after"][m] >= 0.0
    # The raw baseline never "improves": delta is exactly 0.
    raw = [c for c in artifact["results"] if c["calibrator"] == "raw"]
    assert all(c["delta_brier"] == 0.0 and c["delta_ece"] == 0.0
               for c in raw)
    # On the overconfident set, real calibrators beat raw on Brier.
    over = {c["calibrator"]: c for c in artifact["results"]
            if c["dataset"] == "overconfident"}
    for name in ("platt", "isotonic", "temperature", "ensemble"):
        assert over[name]["after"]["brier"] < over["raw"]["after"]["brier"]
    # Artifact writes cleanly to a tmp path (never the real artifact here).
    tmp = tmp_path / "calibration_500.json"
    tmp.write_text(json.dumps(artifact, indent=2, sort_keys=True))
    assert json.loads(tmp.read_text())["name"] == "calibration_500"
