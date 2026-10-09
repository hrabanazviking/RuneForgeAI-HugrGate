"""GPU scheduling boundary — discovery, parsing, device assignment.

Slice 297.

.. warning::
   **Real-hardware validation needed (Law 13).** No GPU is present on
   this machine (``nvidia-smi`` absent), so live discovery and device
   assignment are implemented against the documented ``nvidia-smi``
   CLI contract and exercised only through (a) parsing of captured
   sample outputs and (b) a scheduler driven by synthetic
   inventories.  Nothing here has run against real GPUs.  Do not
   trust placement decisions until that validation exists.

What this module does:

- :func:`discover_gpus`: run ``nvidia-smi --query-gpu=... --format=csv``
  and parse one :class:`GpuInfo` per device.  Returns ``[]`` when
  ``nvidia-smi`` is missing or reports no GPUs — that is a normal
  CPU-only machine, not an error.
- :func:`parse_smi_csv`: the pure parser, unit-tested against sample
  outputs (the samples are fixtures, not measurements).
- :class:`GpuScheduler`: assigns devices to workers.  Policies:
  ``"least-memory-used"`` (default — pack onto the emptiest device),
  ``"round-robin"``.  Assignments are tracked and released; over-full
  devices raise :class:`GpuschedError` only when
  ``max_workers_per_gpu`` is set and exceeded, otherwise workers
  share.

Placement is a hint: every caller must run correctly with
``device=None`` (CPU fallback).
"""

from __future__ import annotations

import shutil
import subprocess
import threading
from dataclasses import dataclass
from typing import Any

from hugrgate.errors import GpuschedError
from hugrgate.log import get_logger

logger = get_logger(__name__)

__all__ = [
    "GpuInfo",
    "GpuScheduler",
    "discover_gpus",
    "parse_smi_csv",
]

_SMI_QUERY = ("index,name,memory.total,memory.used,memory.free,"
              "utilization.gpu")
_SMI_TIMEOUT_S = 10.0


@dataclass(frozen=True)
class GpuInfo:
    """One GPU as reported by nvidia-smi."""
    index: int
    name: str
    memory_total_mb: int
    memory_used_mb: int
    memory_free_mb: int
    utilization_pct: int

    @property
    def memory_used_frac(self) -> float:
        if self.memory_total_mb <= 0:
            return 0.0
        return self.memory_used_mb / self.memory_total_mb

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "name": self.name,
            "memory_total_mb": self.memory_total_mb,
            "memory_used_mb": self.memory_used_mb,
            "memory_free_mb": self.memory_free_mb,
            "utilization_pct": self.utilization_pct,
        }


def parse_smi_csv(text: str) -> list[GpuInfo]:
    """Parse ``nvidia-smi --format=csv,noheader,nounits`` output.

    Expected columns (``_SMI_QUERY``): index, name, memory.total,
    memory.used, memory.free, utilization.gpu.  Blank lines are
    skipped; malformed rows raise :class:`GpuschedError`.
    """
    gpus: list[GpuInfo] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 6:
            raise GpuschedError(
                f"nvidia-smi csv line {lineno}: expected 6 columns, got "
                f"{len(parts)}: {line!r}")
        try:
            index = int(parts[0])
            total, used, free = (int(parts[2]), int(parts[3]),
                                 int(parts[4]))
            util = int(parts[5].rstrip("%").strip())
        except ValueError as e:
            raise GpuschedError(
                f"nvidia-smi csv line {lineno}: non-numeric field: "
                f"{line!r} ({e})") from e
        if index < 0 or total < 0 or used < 0 or free < 0:
            raise GpuschedError(
                f"nvidia-smi csv line {lineno}: negative value: {line!r}")
        gpus.append(GpuInfo(
            index=index, name=parts[1], memory_total_mb=total,
            memory_used_mb=used, memory_free_mb=free,
            utilization_pct=util))
    # Deterministic order regardless of smi row order.
    gpus.sort(key=lambda g: g.index)
    return gpus


def discover_gpus(smi_binary: str = "nvidia-smi") -> list[GpuInfo]:
    """Discover GPUs via nvidia-smi. ``[]`` when none are present."""
    exe = shutil.which(smi_binary)
    if exe is None:
        logger.info("gpusched: %s not found; CPU-only", smi_binary)
        return []
    try:
        proc = subprocess.run(
            [exe, f"--query-gpu={_SMI_QUERY}",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=_SMI_TIMEOUT_S,
            check=False)
    except (OSError, subprocess.SubprocessError) as e:
        raise GpuschedError(
            f"failed to run {smi_binary}: {e}") from e
    if proc.returncode != 0:
        # nvidia-smi errors when no NVIDIA driver/GPU exists; that is
        # a normal CPU-only machine, not a scheduling failure.
        logger.info("gpusched: %s exited %d: %s", smi_binary,
                    proc.returncode, proc.stderr.strip()[:200])
        return []
    try:
        gpus = parse_smi_csv(proc.stdout)
    except GpuschedError as e:
        raise GpuschedError(f"cannot parse {smi_binary} output: {e}") from e
    logger.info("gpusched: discovered %d GPU(s)", len(gpus))
    return gpus


@dataclass
class _Assignment:
    gpu_index: int
    owner: str


class GpuScheduler:
    """Assign GPU devices to named workers (slice 297).

    Parameters
    ----------
    gpus: inventory (from :func:`discover_gpus` or synthetic).
    policy: ``"least-memory-used"`` or ``"round-robin"``.
    max_workers_per_gpu: cap sharing per device (None = unbounded).
    """

    def __init__(self, gpus: list[GpuInfo] | None = None, *,
                 policy: str = "least-memory-used",
                 max_workers_per_gpu: int | None = None) -> None:
        if policy not in ("least-memory-used", "round-robin"):
            raise GpuschedError(
                f"unknown policy {policy!r}; want 'least-memory-used' "
                f"or 'round-robin'")
        if max_workers_per_gpu is not None and max_workers_per_gpu < 1:
            raise GpuschedError(
                f"max_workers_per_gpu must be >= 1, got "
                f"{max_workers_per_gpu!r}")
        self._gpus = list(gpus) if gpus else discover_gpus()
        self._policy = policy
        self._max_per_gpu = max_workers_per_gpu
        self._lock = threading.Lock()
        self._assignments: dict[str, _Assignment] = {}
        self._rr_cursor = 0

    @property
    def gpus(self) -> list[GpuInfo]:
        return list(self._gpus)

    def assign(self, worker: str) -> int | None:
        """Assign a GPU index to ``worker``. None when no GPUs exist.

        Re-assigning a worker returns its current device.
        """
        if not worker:
            raise GpuschedError("worker name must be non-empty")
        with self._lock:
            if worker in self._assignments:
                return self._assignments[worker].gpu_index
            if not self._gpus:
                return None
            index = self._pick()
            self._assignments[worker] = _Assignment(gpu_index=index,
                                                    owner=worker)
            logger.debug("gpusched: worker %s -> gpu %d", worker, index)
            return index

    def release(self, worker: str) -> bool:
        """Release ``worker``'s device. False when it held none."""
        with self._lock:
            return self._assignments.pop(worker, None) is not None

    def device_of(self, worker: str) -> int | None:
        """Current device of ``worker`` (None if unassigned)."""
        with self._lock:
            a = self._assignments.get(worker)
            return a.gpu_index if a else None

    def _pick(self) -> int:
        load = self._load_by_gpu()
        candidates = [g for g in self._gpus
                      if self._max_per_gpu is None
                      or load[g.index] < self._max_per_gpu]
        if not candidates:
            raise GpuschedError(
                f"all {len(self._gpus)} GPU(s) at max_workers_per_gpu="
                f"{self._max_per_gpu}")
        if self._policy == "round-robin":
            choice = candidates[self._rr_cursor % len(candidates)]
            self._rr_cursor += 1
            return choice.index
        # least-memory-used, tie-broken by fewest assignees then index.
        return min(candidates,
                   key=lambda g: (g.memory_used_frac, load[g.index],
                                  g.index)).index

    def _load_by_gpu(self) -> dict[int, int]:
        load = {g.index: 0 for g in self._gpus}
        for a in self._assignments.values():
            load[a.gpu_index] = load.get(a.gpu_index, 0) + 1
        return load

    def stats(self) -> dict[str, Any]:
        """Scheduler statistics snapshot."""
        with self._lock:
            return {
                "policy": self._policy,
                "gpus": [g.to_dict() for g in self._gpus],
                "assignments": {w: a.gpu_index
                                for w, a in self._assignments.items()},
                "load_by_gpu": self._load_by_gpu(),
            }


#: Sample ``nvidia-smi`` csv outputs used as parser fixtures in tests.
#: These are format samples, not measurements from any machine.
SAMPLE_SMI_TWO_GPU = """\
0, NVIDIA A100-SXM4-40GB, 40960, 1234, 39726, 5
1, NVIDIA A100-SXM4-40GB, 40960, 38912, 2048, 92
"""

SAMPLE_SMI_EMPTY = ""

SAMPLE_SMI_MALFORMED = """\
0, NVIDIA A100-SXM4-40GB, 40960, 1234
"""
