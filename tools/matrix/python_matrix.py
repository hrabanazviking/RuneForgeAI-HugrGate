#!/usr/bin/env python3
"""Python-version matrix check (Gjallarbrú slice 478).

Validates the ``requires-python`` claim: the declared lower bound is
sane, the supported matrix covers it, and every ``hugrgate`` source
file parses under the oldest supported grammar.

Usage: python tools/matrix/python_matrix.py [--root PATH]
Exit code 0 when the matrix is valid, 1 with a report otherwise.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from hugrgate.gauntlet.pymatrix import (
    SUPPORTED_MINORS,
    validate_matrix,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the Python version matrix.")
    parser.add_argument("--root", default=".", help="repository root")
    args = parser.parse_args()

    report = validate_matrix(args.root)
    print(f"requires-python : {report.requires_python}")
    print(f"matrix          : {', '.join(f'{a}.{b}' for a, b in report.matrix)}")
    print(f"files checked   : {report.files_checked}")
    if report.syntax_failures:
        print("SYNTAX FAILURES (newer-than-floor syntax):")
        for failure in report.syntax_failures:
            print(f"  {failure}")
    if report.min_minor not in SUPPORTED_MINORS:
        print(f"lower bound {report.min_minor} is not in the supported matrix")
    ok = report.ok
    print("MATRIX " + ("OK" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
