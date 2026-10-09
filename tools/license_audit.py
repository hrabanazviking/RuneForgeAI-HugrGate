#!/usr/bin/env python3
"""License audit CLI (slice 497).

Inventories installed distribution licenses, writes a manifest
JSON, and exits 1 when any package needs legal review.

Usage:
    python tools/license_audit.py [--out docs/gauntlet/497-license-manifest.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hugrgate.gauntlet.license_audit import audit_installed, audit_runtime


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit dependency licenses.")
    parser.add_argument("--out", default="docs/gauntlet/497-license-manifest.json")
    parser.add_argument("--all", action="store_true",
                        help="audit the whole venv instead of the "
                             "runtime closure")
    args = parser.parse_args(argv)
    report = audit_installed() if args.all else audit_runtime()
    data = report.to_dict()
    data["scope"] = "full-venv" if args.all else "runtime-closure"
    Path(args.out).write_text(json.dumps(data, indent=2) + "\n")
    summary = data["summary"]
    print(f"{len(data['packages'])} packages [{data['scope']}]: " +
          ", ".join(f"{k}={v}" for k, v in sorted(summary.items())))
    for pkg in report.needs_review:
        decl = (pkg.declaration or "no license declared")
        print(f"  REVIEW: {pkg.name} {pkg.version} ({decl[:80]})")
    return 0 if report.clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
