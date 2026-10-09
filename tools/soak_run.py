#!/usr/bin/env python3
"""Long-duration soak runner (Gjallarbrú slice 488).

Drives the real HugrGate decision gate and watches for memory
leaks, invariant violations, and unexpected errors.

Usage: python tools/soak_run.py [--iterations N] [--rss-budget-mb MB]
                                [--duration-s S]
Exit 0 when the soak passes, 1 otherwise.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hugrgate.gauntlet.soak import run_gate_soak


def main() -> int:
    parser = argparse.ArgumentParser(description="Soak the decision gate.")
    parser.add_argument("--iterations", type=int, default=2000)
    parser.add_argument("--rss-budget-mb", type=float, default=50.0)
    parser.add_argument("--duration-s", type=float, default=120.0)
    args = parser.parse_args()

    summary = run_gate_soak(iterations=args.iterations,
                            rss_budget_mb=args.rss_budget_mb,
                            duration_s=args.duration_s)
    print(f"ops={summary.ops} elapsed={summary.elapsed_s:.1f}s "
          f"max_rss_growth={summary.max_rss_growth_mb:.1f}MiB "
          f"violations={len(summary.violations)} errors={summary.errors}")
    for violation in summary.violations:
        print(f"  VIOLATION: {violation}")
    print("SOAK " + ("PASS" if summary.ok else "FAIL"))
    return 0 if summary.ok else 1


if __name__ == "__main__":
    sys.exit(main())
