"""Crash-only restart: kill -9 the worker, recover from the journal (slice 272).

Crash-only design means the system never needs a graceful shutdown:
after a SIGKILL at an arbitrary instant, recovery from the journal
alone must yield a consistent state. :class:`CrashOnlyHarness`
proves it — it spawns a worker subprocess writing checkpoints in a
tight loop, kills it with SIGKILL mid-write, then recovers in the
parent and verifies the invariants:

- recovery succeeds (no exception, no manual repair);
- the recovered checkpoint is the newest *completed* write — never
  a torn or phantom one (the journal's tmp+fsync+replace makes a
  killed write invisible);
- torn ``.tmp`` files and corrupt records are ignored.

The worker runs as ``python -m hugrgate.chaos.crash worker <dir>
<count>`` so the kill is a real OS-level SIGKILL, not an
in-process simulation.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import hugrgate
from hugrgate.edge.recovery import CheckpointJournal
from hugrgate.errors import SpecError

__all__ = ["CrashOnlyHarness", "CrashReport", "worker_main"]

_WORKER_STATE_ID = "crash-worker"


def worker_main(directory: str, count: int) -> int:
    """Write ``count`` checkpoints as fast as possible; never exits
    cleanly on its own when ``count`` is huge — the harness kills it.

    Each checkpoint payload is ``{"counter": n}`` written in order,
    so the parent can verify the recovered state is a prefix of the
    write sequence (no torn writes, no gaps).
    """
    journal = CheckpointJournal.open(directory)
    for n in range(1, count + 1):
        journal.checkpoint(_WORKER_STATE_ID, {"counter": n})
    return 0


def _repo_root() -> Path:
    return Path(hugrgate.__file__).resolve().parent.parent


@dataclass
class CrashReport:
    """What the kill taught us."""

    pid: int
    killed: bool
    checkpoints_valid: int
    recovered_counter: int | None
    torn_tmp_files: int
    duration_s: float

    @property
    def recovered_cleanly(self) -> bool:
        return (self.recovered_counter is not None
                and self.recovered_counter >= 1)

    def to_dict(self) -> dict[str, Any]:
        report = {"pid": self.pid,
                  "killed": self.killed,
                  "checkpoints_valid": self.checkpoints_valid,
                  "recovered_counter": self.recovered_counter,
                  "torn_tmp_files": self.torn_tmp_files,
                  "duration_s": self.duration_s,
                  "recovered_cleanly": self.recovered_cleanly}
        json.dumps(report)  # contract: always serializable
        return report


class CrashOnlyHarness:
    """Spawn a checkpoint worker, SIGKILL it, recover, verify."""

    def __init__(self, directory: str | Path,
                 python: str = sys.executable) -> None:
        self._dir = Path(directory)
        self._python = python

    @staticmethod
    def default_kill_signal() -> int:
        """Kill signal for the worker, resolved at call time.

        ``signal.SIGKILL`` does not exist on Windows; evaluating it as
        a default argument would break module import there (slice
        480). Resolve lazily: SIGKILL where available, SIGTERM
        otherwise.
        """
        return getattr(signal, "SIGKILL", signal.SIGTERM)

    def run_worker(self, count: int = 10 ** 9,
                   kill_after_s: float = 1.0,
                   kill_signal: int | None = None,
                   arm_after_first_checkpoint: bool = False) -> CrashReport:
        """Run the worker, kill it after ``kill_after_s``, recover.

        ``kill_signal`` defaults to :meth:`default_kill_signal`.

        ``arm_after_first_checkpoint``: wait (bounded) for the worker
        to write its first checkpoint before starting the kill
        countdown. Slice 500: without this, a slow interpreter
        startup under load lets the kill land before any checkpoint
        exists, and the test measures startup instead of crash
        recovery (flaky ``recovered_counter=None``).
        """
        if kill_after_s <= 0:
            raise SpecError(
                f"kill_after_s must be positive, got {kill_after_s!r}")
        if kill_signal is None:
            kill_signal = self.default_kill_signal()
        self._dir.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        env["PYTHONPATH"] = str(_repo_root()) + os.pathsep + env.get(
            "PYTHONPATH", "")
        started = time.monotonic()
        proc = subprocess.Popen(
            [self._python, "-m", "hugrgate.chaos.crash", "worker",
             str(self._dir), str(count)],
            env=env, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
        if arm_after_first_checkpoint:
            deadline = time.monotonic() + 60.0
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    break  # worker exited on its own; proceed to report
                if any(self._dir.glob("chk_*.json")):
                    break
                time.sleep(0.05)
        try:
            try:
                proc.wait(timeout=kill_after_s)
                killed = False  # worker finished on its own (tiny count)
            except subprocess.TimeoutExpired:
                proc.send_signal(kill_signal)
                proc.wait(timeout=10)
                killed = True
        finally:
            # Never leave a zombie: the wait() above reaps in both
            # branches; this is belt-and-braces for kill failures.
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=10)
        duration_s = time.monotonic() - started

        torn_tmp = [p for p in self._dir.glob("*.tmp")]
        try:
            journal = CheckpointJournal.open(self._dir)
            checkpoints = journal.checkpoints()
            recovered = journal.recover()
        except Exception as e:
            # Any recovery failure here IS the incident this harness
            # tests for: surface it as a SpecError with the cause.
            raise SpecError(
                f"crash-only recovery failed after SIGKILL: {e}") from e

        counter = None
        if recovered is not None:
            counter = recovered.get("counter")
        return CrashReport(
            pid=proc.pid, killed=killed,
            checkpoints_valid=len(checkpoints),
            recovered_counter=counter,
            torn_tmp_files=len(torn_tmp),
            duration_s=duration_s)


def _cli() -> int:
    if len(sys.argv) != 4 or sys.argv[1] != "worker":
        print("usage: python -m hugrgate.chaos.crash worker <dir> <count>",
              file=sys.stderr)
        return 2
    return worker_main(sys.argv[2], int(sys.argv[3]))


if __name__ == "__main__":
    sys.exit(_cli())
