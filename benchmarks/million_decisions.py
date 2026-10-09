"""Run the million-decision benchmark once; write the artifact.

Slice 299.  This is the *real* 1M run (takes a few minutes) — not a
test.  Tests use small ``n`` via :func:`hugrgate.millionbench.run_million`.

    python benchmarks/million_decisions.py [--n N] [--seed S] \\
        [--out benchmarks/million_decisions.json]
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hugrgate.millionbench import run_million


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1_000_000)
    ap.add_argument("--seed", type=int, default=299)
    ap.add_argument("--out", default="benchmarks/million_decisions.json")
    args = ap.parse_args()

    result = run_million(n=args.n, seed=args.seed)
    artifact = {
        "slice": 299,
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "host": {
            "python": platform.python_version(),
            "machine": platform.machine(),
        },
        "result": result.to_dict(),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, indent=2) + "\n")
    r = result
    print(f"n={r.n:,} elapsed={r.elapsed_s:.1f}s "
          f"{r.decisions_per_s:,.0f} decisions/s")
    print(f"latency us: p50={r.latency_p50_us:.1f} "
          f"p95={r.latency_p95_us:.1f} p99={r.latency_p99_us:.1f} "
          f"max={r.latency_max_us:.1f}")
    print(f"errors={r.errors} rss: {r.rss_before_mb:.0f} -> "
          f"{r.rss_after_mb:.0f} MB")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
