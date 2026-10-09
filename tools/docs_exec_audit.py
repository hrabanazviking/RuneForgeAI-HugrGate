#!/usr/bin/env python3
"""Documentation executable audit (slice 496).

Extract every ```python block from the given Markdown files and
execute it in a subprocess (repo root prepended to PYTHONPATH,
timeout per block). Blocks whose first line is ``# noexec``
(optionally with ``: reason``) are reported as skipped — for
illustrative fragments that cannot run standalone.

Exit status: 0 when every executed block passes, 1 otherwise.
Prints a per-block report: PASS / FAIL / SKIP / TIMEOUT /
SYNTAX-ERROR.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

BLOCK_RE = re.compile(r"```python[^\n]*\n(.*?)```", re.DOTALL)
NOEXEC_RE = re.compile(r"^#\s*noexec\b\s*:?\s*(.*)$", re.IGNORECASE)


@dataclass
class BlockResult:
    path: str
    index: int
    status: str  # PASS | FAIL | SKIP | TIMEOUT | SYNTAX-ERROR
    detail: str = ""


@dataclass
class AuditReport:
    results: list[BlockResult] = field(default_factory=list)

    @property
    def failed(self) -> list[BlockResult]:
        return [r for r in self.results
                if r.status in ("FAIL", "TIMEOUT", "SYNTAX-ERROR")]

    @property
    def passed(self) -> bool:
        return not self.failed

    def summary(self) -> str:
        lines = []
        for r in self.results:
            lines.append(f"[{r.status:>12}] {r.path}#{r.index}"
                         + (f" — {r.detail}" if r.detail else ""))
        return "\n".join(lines)


def extract_blocks(path: Path) -> list[str]:
    """Return the ```python block bodies in a Markdown file."""
    return BLOCK_RE.findall(path.read_text(encoding="utf-8"))


def noexec_reason(code: str) -> str | None:
    """Reason when the block opts out via a leading ``# noexec``."""
    first = code.strip().splitlines()
    if not first:
        return "empty block"
    match = NOEXEC_RE.match(first[0].strip())
    return match.group(1).strip() or "opted out" if match else None


def run_block(code: str, timeout_s: float,
              workdir: Path) -> tuple[str, str]:
    """Compile then execute a block; return (status, detail)."""
    try:
        compile(code, "<docblock>", "exec")
    except SyntaxError as exc:
        return "SYNTAX-ERROR", f"{exc.msg} (line {exc.lineno})"
    with tempfile.NamedTemporaryFile("w", suffix=".py",
                                     delete=False) as tmp:
        tmp.write(code)
        tmp_path = tmp.name
    try:
        env = dict(os.environ)
        env["PYTHONPATH"] = (str(workdir) + os.pathsep
                             + env.get("PYTHONPATH", ""))
        proc = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True, text=True,
            timeout=timeout_s, cwd=workdir, env=env)
    except subprocess.TimeoutExpired:
        return "TIMEOUT", f"exceeded {timeout_s}s"
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    if proc.returncode == 0:
        return "PASS", ""
    tail = (proc.stderr.strip() or proc.stdout.strip()).splitlines()
    return "FAIL", tail[-1] if tail else f"exit {proc.returncode}"


def audit_files(paths: list[Path], timeout_s: float,
                workdir: Path) -> AuditReport:
    report = AuditReport()
    for path in paths:
        for index, code in enumerate(extract_blocks(path)):
            reason = noexec_reason(code)
            if reason is not None:
                report.results.append(BlockResult(
                    str(path), index, "SKIP", reason))
                continue
            status, detail = run_block(code, timeout_s, workdir)
            report.results.append(BlockResult(str(path), index,
                                              status, detail))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Execute ```python blocks in Markdown docs.")
    parser.add_argument("files", nargs="+", help="Markdown files to audit")
    parser.add_argument("--timeout", type=float, default=60.0,
                        help="seconds per block (default 60)")
    args = parser.parse_args(argv)
    workdir = Path.cwd()
    report = audit_files([Path(f) for f in args.files],
                         args.timeout, workdir)
    print(report.summary())
    n_fail = len(report.failed)
    print(f"\n{len(report.results)} blocks: "
          f"{n_fail} failed, "
          f"{sum(1 for r in report.results if r.status == 'SKIP')} skipped")
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
