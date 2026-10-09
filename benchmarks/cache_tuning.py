"""Cache performance tuning benchmark — slice 292.

Reproducible workload measuring DecisionCache hot-path costs:

- cache_key latency (isolated)
- get-hit / get-miss latency
- put latency
- mixed workload throughput (70% get-hit, 20% get-miss, 10% put)

All randomness is seeded (seed=292); the workload is rebuilt
identically on every run.  Emits a JSON artifact:

    python benchmarks/cache_tuning.py --out benchmarks/cache_tuning_<tag>.json

Compare baseline vs tuned with two runs and diff the ``summary`` block.
"""

from __future__ import annotations

import argparse
import json
import platform
import random
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hugrgate import DecisionPolicy, DecisionSpec
from hugrgate.cache import DecisionCache, cache_key
from hugrgate.result import DecisionResult

SEED = 292
N_STATES = 1000
N_KEY_ITERS = 4000
N_OP_ITERS = 4000
N_MIXED = 20000


def _build_workload(seed: int = SEED):
    rng = random.Random(seed)
    options = [f"opt{i}" for i in range(8)]
    spec = DecisionSpec(type="categorical", options=options)
    policy = DecisionPolicy(minimum_probability=0.1)
    dist = {f"opt{i}": (0.9 if i == 1 else 0.1 / 7) for i in range(8)}
    result = DecisionResult(value="opt1", probability=0.9,
                            distribution=dist, backend="bench",
                            latency_ms=1.0,
                            metadata={"route": ["a", "b"]})

    states = []
    for _s in range(N_STATES):
        # Shuffled insertion order on purpose: equivalent dicts must
        # still hash equal (order-insensitive keys).
        keys = [f"feat{i}" for i in range(12)]
        rng.shuffle(keys)
        state = {k: (rng.random(), f"v{k}", [rng.randint(0, 9)])
                 for k in keys}
        states.append(state)
    return spec, policy, result, states


def _timed(fn, iters):
    fn()  # warmup
    samples = []
    for _ in range(iters):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1e6)
    return samples


def bench_key(spec, policy, states):
    return _timed(lambda: cache_key(states[0], spec, policy), N_KEY_ITERS)


def bench_get_hit(cache, spec, policy, states):
    return _timed(lambda: cache.get(states[0], spec, policy), N_OP_ITERS)


def bench_get_miss(cache, spec, policy):
    miss = {"nope": "missing"}
    return _timed(lambda: cache.get(miss, spec, policy), N_OP_ITERS)


def bench_put(cache, spec, policy, result, states):
    return _timed(lambda: cache.put(states[1], spec, policy, result),
                  N_OP_ITERS)


def bench_mixed(spec, policy, result, states):
    rng = random.Random(SEED + 1)
    cache = DecisionCache(ttl_seconds=600.0, max_size=N_STATES * 2)
    for st in states:
        cache.put(st, spec, policy, result)
    ops = []
    for _ in range(N_MIXED):
        r = rng.random()
        st = states[rng.randrange(N_STATES)]
        if r < 0.70:
            ops.append(("get", st))
        elif r < 0.90:
            ops.append(("get", {"miss": rng.random()}))
        else:
            ops.append(("put", st))
    t0 = time.perf_counter()
    for kind, st in ops:
        if kind == "get":
            cache.get(st, spec, policy)
        else:
            cache.put(st, spec, policy, result)
    elapsed = time.perf_counter() - t0
    return elapsed, cache.stats()


def _summary(samples):
    return {
        "n": len(samples),
        "mean_us": statistics.fmean(samples),
        "p50_us": statistics.median(samples),
        "p95_us": sorted(samples)[int(len(samples) * 0.95)],
        "min_us": min(samples),
        "max_us": max(samples),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    spec, policy, result, states = _build_workload()

    key_samples = bench_key(spec, policy, states)

    cache = DecisionCache(ttl_seconds=600.0, max_size=N_STATES * 2)
    for st in states:
        cache.put(st, spec, policy, result)
    hit_samples = bench_get_hit(cache, spec, policy, states)
    miss_samples = bench_get_miss(cache, spec, policy)
    put_samples = bench_put(cache, spec, policy, result, states)

    mixed_elapsed, mixed_stats = bench_mixed(spec, policy, result, states)

    artifact = {
        "slice": 292,
        "seed": SEED,
        "host": {
            "python": platform.python_version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
        "workload": {
            "n_states": N_STATES,
            "state_keys": 12,
            "key_iters": N_KEY_ITERS,
            "op_iters": N_OP_ITERS,
            "mixed_ops": N_MIXED,
        },
        "summary": {
            "cache_key_us": _summary(key_samples),
            "get_hit_us": _summary(hit_samples),
            "get_miss_us": _summary(miss_samples),
            "put_us": _summary(put_samples),
            "mixed_ops_per_s": N_MIXED / mixed_elapsed,
            "mixed_hit_rate": mixed_stats["hit_rate"],
        },
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, indent=2) + "\n")
    s = artifact["summary"]
    print(f"cache_key : {s['cache_key_us']['mean_us']:7.2f} us mean "
          f"(p50 {s['cache_key_us']['p50_us']:.2f})")
    print(f"get_hit   : {s['get_hit_us']['mean_us']:7.2f} us mean "
          f"(p50 {s['get_hit_us']['p50_us']:.2f})")
    print(f"get_miss  : {s['get_miss_us']['mean_us']:7.2f} us mean "
          f"(p50 {s['get_miss_us']['p50_us']:.2f})")
    print(f"put       : {s['put_us']['mean_us']:7.2f} us mean "
          f"(p50 {s['put_us']['p50_us']:.2f})")
    print(f"mixed     : {s['mixed_ops_per_s']:9.1f} ops/s "
          f"(hit_rate {s['mixed_hit_rate']:.3f})")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
