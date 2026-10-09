#!/usr/bin/env python3
"""Precision-audit handoff completeness checker (slice 499).

Verifies the handoff package (docs/gauntlet/499-audit-handoff.json)
is *complete and actionable* — without re-running the world
(running is the auditor's job):

- the manifest is valid JSON with the required schema;
- every claim has an id, a claim statement, reproduce commands,
  and evidence paths;
- every evidence path exists under the repo root;
- every reproduce command references an existing script or test
  file (``python tools/...`` / ``pytest tests/...``).

Exit 0 when the handoff is complete, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import shlex
from dataclasses import dataclass, field
from pathlib import Path

REQUIRED_TOP = ("package", "handoff_version", "date", "claims")
REQUIRED_CLAIM = ("id", "claim", "reproduce", "evidence")


@dataclass
class HandoffReport:
    problems: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.problems


def _check_command(cmd: str, repo: Path, problems: list[str],
                   claim_id: str) -> None:
    try:
        parts = shlex.split(cmd)
    except ValueError as exc:
        problems.append(f"{claim_id}: unparseable command {cmd!r}: {exc}")
        return
    if not parts:
        problems.append(f"{claim_id}: empty reproduce command")
        return
    # Verify referenced files exist: the token after the runner.
    _runner, *rest = parts
    target = None
    for token in rest:
        if token.startswith("-"):
            continue
        if token.startswith("<") and token.endswith(">"):
            continue  # placeholder, e.g. <python-with-build>
        target = token
        break
    if target is not None and not (repo / target).exists():
        problems.append(
            f"{claim_id}: reproduce target missing: {target}")


def check_handoff(manifest_path: Path, repo: Path) -> HandoffReport:
    report = HandoffReport()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return HandoffReport([f"manifest unreadable: {exc}"])
    for key in REQUIRED_TOP:
        if key not in manifest:
            report.problems.append(f"manifest missing key: {key}")
    claims = manifest.get("claims", [])
    if not isinstance(claims, list) or not claims:
        report.problems.append("manifest has no claims")
        return report
    seen_ids: set[str] = set()
    for claim in claims:
        if not isinstance(claim, dict):
            report.problems.append("claim is not an object")
            continue
        for key in REQUIRED_CLAIM:
            if key not in claim:
                report.problems.append(
                    f"claim missing key {key}: {claim.get('id', '?')}")
        claim_id = str(claim.get("id", "?"))
        if claim_id in seen_ids:
            report.problems.append(f"duplicate claim id: {claim_id}")
        seen_ids.add(claim_id)
        for evidence in claim.get("evidence", []):
            if not (repo / evidence).exists():
                report.problems.append(
                    f"{claim_id}: evidence missing: {evidence}")
        for cmd in claim.get("reproduce", []):
            _check_command(str(cmd), repo, report.problems, claim_id)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check the precision-audit handoff package.")
    parser.add_argument("--manifest",
                        default="docs/gauntlet/499-audit-handoff.json")
    args = parser.parse_args(argv)
    repo = Path.cwd()
    report = check_handoff(Path(args.manifest), repo)
    if report.complete:
        print(f"handoff complete: {args.manifest}")
        return 0
    print("handoff INCOMPLETE:")
    for problem in report.problems:
        print(f"  - {problem}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
