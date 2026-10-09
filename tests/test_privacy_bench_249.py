"""Tests for slice 249 — privacy benchmark suite.

Reduced rounds against a tmp artifact path, per repo convention:
the full artifact is regenerated after the final test run,
before committing.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "benchmarks"))

import pytest
from privacy_bench_249 import run_benchmark


@pytest.fixture(scope="module")
def artifact():
    return run_benchmark(seed=7, rounds=20)


def test_artifact_shape(artifact):
    assert artifact["name"] == "privacy_bench_249"
    assert artifact["seed"] == 7
    assert artifact["rounds"] == 20
    assert artifact["unit"] == "milliseconds"
    ops = {c["op"] for c in artifact["results"]}
    assert ops == {"secret_scan", "pii_scrub", "redaction", "local_only",
                   "payload_compile", "seal", "unseal", "tokenize",
                   "audit_record", "dry_run"}


def test_measurements_are_real(artifact):
    for cell in artifact["results"]:
        assert set(cell) == {"op", "n", "mean_ms", "min_ms", "max_ms",
                             "p50_ms", "p95_ms"}
        assert cell["n"] == 20
        assert cell["mean_ms"] >= 0.0
        assert cell["min_ms"] >= 0.0
        assert cell["min_ms"] <= cell["p50_ms"] <= cell["p95_ms"]
        assert cell["p95_ms"] <= cell["max_ms"]
        # Real work took real time: not all zeros.
    assert any(c["mean_ms"] > 0.0 for c in artifact["results"])


def test_payload_compile_dominates_stages(artifact):
    by_op = {c["op"]: c for c in artifact["results"]}
    # The full pipeline costs at least as much as its secret-scan
    # stage alone (it runs the scan plus six more stages).
    assert (by_op["payload_compile"]["mean_ms"]
            >= by_op["secret_scan"]["mean_ms"])


def test_artifact_writes_to_tmp(artifact, tmp_path):
    tmp = tmp_path / "privacy_bench_249.json"
    tmp.write_text(json.dumps(artifact, indent=2, sort_keys=True))
    reloaded = json.loads(tmp.read_text())
    assert reloaded["name"] == "privacy_bench_249"
    assert len(reloaded["results"]) == 10


def test_deterministic_workload_shape():
    first = run_benchmark(seed=11, rounds=10)
    second = run_benchmark(seed=11, rounds=10)
    assert [c["op"] for c in first["results"]] == \
        [c["op"] for c in second["results"]]
    assert first["rounds"] == second["rounds"] == 10
