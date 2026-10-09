"""Builder for the calibration benchmark artifact. Slice 099.

Runs :func:`hugrgate.calibration.bench.run_benchmark` at full rounds and
writes ``benchmarks/calibration_500.json``.  Seeded → byte-identical on
every run.

Usage: ``python benchmarks/build_calibration.py [--out benchmarks]``
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hugrgate.calibration.bench import run_benchmark

SEED = 20261009
N = 2000
ARTIFACT = "calibration_500.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="benchmarks")
    args = parser.parse_args()
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    artifact = run_benchmark(seed=SEED, n=N)
    path = outdir / ARTIFACT
    path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    print(f"wrote {path} "
          f"({len(artifact['results'])} dataset×calibrator cells)")


if __name__ == "__main__":
    main()
