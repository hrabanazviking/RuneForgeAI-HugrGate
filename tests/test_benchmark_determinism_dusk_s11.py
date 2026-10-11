"""Slice 11 (dusk, Wave C) — benchmark output determinism contract.

The routing benchmark scripts (056/058/074) measure real wall-clock time,
so their *measured* values legitimately jitter between live runs and can
never be byte-identical run to run. What slice 11 locks is the formatting
contract that makes reruns differ ONLY via measured floats, never via
key order, float-repr noise, timestamps, or structure:

1. Canonical emission: file bytes are exactly
   ``json.dumps(parsed, indent=2, sort_keys=True)`` — sorted keys, stable
   layout, no nondeterministic fields.
2. Every emitted float has at most 6 decimal places (no float-repr noise
   like 15.000000000000002).
3. Two consecutive runs have identical key structure and identical
   non-float leaves; only float leaves may differ (the measured values).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

SCRIPTS = {
    "routing_latency_056.py": ["--rounds", "3"],
    "routing_energy_058.py": ["--rounds", "2"],
    "routing_stress_074.py": ["--decisions", "10"],
}


def _run_script(root, name, extra_args, out):
    script = os.path.join(root, "benchmarks", name)
    proc = subprocess.run(
        [sys.executable, script, *extra_args, "--out", out],
        capture_output=True, text=True, cwd=root, timeout=600)
    assert proc.returncode == 0, proc.stderr
    with open(out, "rb") as f:
        raw = f.read()
    return raw


def _all_floats(obj):
    if isinstance(obj, float):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _all_floats(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _all_floats(v)


def _leaf_paths(obj, path=()):
    """Yield (path, kind, value) for every leaf; kind is 'float' or 'other'."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _leaf_paths(v, (*path, k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _leaf_paths(v, (*path, i))
    else:
        yield path, ("float" if isinstance(obj, float) else "other"), obj


def _check_canonical(raw):
    parsed = json.loads(raw)
    assert json.dumps(parsed, indent=2, sort_keys=True) == raw.decode("utf-8")


def _check_float_precision(parsed):
    for f in _all_floats(parsed):
        assert f == round(f, 6), f"float with >6dp emitted: {f!r}"


def test_benchmark_output_canonical_sorted_keys(tmp_path):
    """Every script emits canonical JSON: sorted keys, stable layout."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name, args in SCRIPTS.items():
        out = str(tmp_path / (name[:-3] + ".json"))
        raw = _run_script(root, name, args, out)
        _check_canonical(raw)


def test_benchmark_floats_rounded_to_6dp(tmp_path):
    """No float-repr noise: every emitted float has at most 6 decimals."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name, args in SCRIPTS.items():
        out = str(tmp_path / (name[:-3] + ".json"))
        raw = _run_script(root, name, args, out)
        _check_float_precision(json.loads(raw))


def test_benchmark_runs_differ_only_in_measured_floats(tmp_path):
    """Two consecutive runs: identical structure, identical non-float
    leaves; only float leaves (the live measurements) may differ."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name, args in SCRIPTS.items():
        raw1 = _run_script(root, name, args,
                           str(tmp_path / (name[:-3] + "_a.json")))
        raw2 = _run_script(root, name, args,
                           str(tmp_path / (name[:-3] + "_b.json")))
        leaves1 = {p: (k, v) for p, k, v in _leaf_paths(json.loads(raw1))}
        leaves2 = {p: (k, v) for p, k, v in _leaf_paths(json.loads(raw2))}
        assert set(leaves1) == set(leaves2), (
            f"{name}: key structure differs between runs: "
            f"{set(leaves1) ^ set(leaves2)}")
        for p in leaves1:
            k1, v1 = leaves1[p]
            k2, v2 = leaves2[p]
            assert k1 == k2, f"{name}: leaf type changed at {p}"
            if k1 == "other":
                assert v1 == v2, (
                    f"{name}: non-float leaf differs between runs at {p}: "
                    f"{v1!r} vs {v2!r}")
