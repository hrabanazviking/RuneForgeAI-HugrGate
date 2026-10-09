#!/usr/bin/env python3
"""Dependency-latest audit (Gjallarbrú slice 484).

Records the *actually installed* versions of every runtime
dependency (the validated-latest set for the 1.0 release notes),
verifies each still meets its declared floor, and scans the tree
for deprecated/removed dependency APIs.

Writes docs/gauntlet/484-dependency-latest-manifest.json.
Exit 0 when clean, 1 with a report otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from hugrgate.gauntlet.deps import (
    latest_audit,
    scan_deprecated_api,
)

MANIFEST = Path(__file__).resolve().parent.parent.parent / "docs" / "gauntlet" / \
    "484-dependency-latest-manifest.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit latest dependency versions.")
    parser.add_argument("--root", default=".", help="repository root")
    args = parser.parse_args()
    root = Path(args.root)

    audit = latest_audit()
    findings = scan_deprecated_api(root / "hugrgate") + \
        scan_deprecated_api(root / "tools")

    manifest = {
        "generated_by": "tools/matrix/dep_latest_audit.py (slice 484)",
        "dependencies": audit,
        "deprecated_api_findings": [
            {"path": p, "lineno": n, "reason": r}
            for p, n, r in findings
        ],
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n",
                        encoding="utf-8")
    print(f"wrote {MANIFEST}")
    failed = False
    for name, info in audit.items():
        status = "OK " if info["meets_floor"] else "BELOW FLOOR"
        if not info["meets_floor"]:
            failed = True
        print(f"  [{status}] {name}: installed={info['installed']} "
              f"floor={info['minimum']}")
    for path, lineno, reason in findings:
        failed = True
        print(f"  [DEPRECATED] {path}:{lineno}: {reason}")
    print("LATEST-AUDIT " + ("OK" if not failed else "FAILED"))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
