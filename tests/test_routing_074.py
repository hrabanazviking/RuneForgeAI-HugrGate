"""Slice 074 — routing stress benchmark."""

from __future__ import annotations

import json
import os
import subprocess
import sys


def test_stress_benchmark_artifact():
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    script = os.path.join(root, "benchmarks", "routing_stress_074.py")
    out = os.path.join(root, "benchmarks", "routing_stress_074.json")
    proc = subprocess.run(
        [sys.executable, script, "--decisions", "30", "--out", out],
        capture_output=True, text=True, cwd=root, timeout=600)
    assert proc.returncode == 0, proc.stderr
    with open(out) as f:
        artifact = json.load(f)

    assert artifact["slice"] == "074"
    assert artifact["decisions_per_config"] == 30
    labels = [r["label"] for r in artifact["results"]]
    # every executor x rung-count configuration ran
    for n in (4, 16):
        for variant in ("v1-baseline", "v2-serial", "v2-plan-only",
                        "v2-parallel", "v2-hedged", "v2-early-exit"):
            assert f"{variant}/{n}-rungs" in labels
    for row in artifact["results"]:
        assert row["decisions"] == 30
        assert row["decisions_per_sec"] > 0
        assert row["mean_ms"] > 0
        assert row["p50_ms"] <= row["p99_ms"]
        assert row["p50_ms"] > 0
    # baseline comparisons present and sane
    assert len(artifact["comparisons"]) == 8
    for comp in artifact["comparisons"]:
        assert comp["vs_v1_baseline"] > 0
    # planning alone is cheaper than planning + executing
    by_label = {r["label"]: r for r in artifact["results"]}
    assert (by_label["v2-plan-only/4-rungs"]["decisions_per_sec"]
            > by_label["v2-serial/4-rungs"]["decisions_per_sec"])
