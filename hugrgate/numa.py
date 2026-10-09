"""NUMA awareness boundary — topology detection and thread pinning.

Slice 296.

.. warning::
   **Real-hardware validation needed (Law 13).** Everything here is
   implemented against the Linux sysfs NUMA ABI and exercised on a
   single-node VM (this machine: one node, two CPUs). The multi-node
   behaviors — cross-node pinning, distance-aware placement, and any
   performance claim about locality — have NOT been validated on real
   multi-socket hardware. Do not cite NUMA speedups until that
   validation exists.

What this module does:

- :func:`detect_topology`: read ``/sys/devices/system/node`` into a
  :class:`NumaTopology` (node -> CPUs, distances). Falls back to a
  single synthetic node when sysfs is absent (non-Linux, containers).
- :func:`current_node`: the NUMA node the calling thread is pinned to
  (via affinity intersection).
- :func:`pin_thread` / :func:`pin_to_node`: ``os.sched_setaffinity``
  wrappers. Best-effort: failures raise :class:`NumaError`
  (recoverable — run unpinned).
- :func:`pinned_to`: context manager that pins for a block and
  restores the previous affinity.
- :func:`suggest_node`: round-robin node suggestion for striping
  workers across nodes.

Design note: pinning is a *hint*, never a correctness mechanism. All
callers must run correctly unpinned; NUMA placement only reduces
cross-node traffic where the hardware has nodes to cross.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hugrgate.errors import NumaError
from hugrgate.log import get_logger

logger = get_logger(__name__)

__all__ = [
    "NumaTopology",
    "current_node",
    "detect_topology",
    "is_numa",
    "pin_thread",
    "pin_to_node",
    "pinned_to",
    "suggest_node",
]

_SYS_NODE = Path("/sys/devices/system/node")


def _parse_cpulist(text: str) -> list[int]:
    """Parse a Linux cpulist like ``0-3,8,10-11``."""
    cpus: list[int] = []
    for part in text.strip().split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, hi = part.split("-", 1)
            cpus.extend(range(int(lo), int(hi) + 1))
        else:
            cpus.append(int(part))
    return sorted(set(cpus))


@dataclass
class NumaTopology:
    """Detected NUMA topology."""
    nodes: dict[int, list[int]]          # node id -> cpu ids
    distances: dict[int, dict[int, int]] = field(default_factory=dict)
    source: str = "sysfs"               # "sysfs" | "fallback"

    @property
    def node_ids(self) -> list[int]:
        return sorted(self.nodes)

    @property
    def cpu_count(self) -> int:
        return sum(len(c) for c in self.nodes.values())

    def node_of_cpu(self, cpu: int) -> int | None:
        for node, cpus in self.nodes.items():
            if cpu in cpus:
                return node
        return None

    def distance(self, a: int, b: int) -> int | None:
        return self.distances.get(a, {}).get(b)

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": {str(k): v for k, v in self.nodes.items()},
            "distances": {str(k): {str(k2): v2 for k2, v2 in v.items()}
                          for k, v in self.distances.items()},
            "source": self.source,
        }


def detect_topology() -> NumaTopology:
    """Detect NUMA topology from sysfs, or synthesize one node."""
    if _SYS_NODE.is_dir():
        nodes: dict[int, list[int]] = {}
        for child in sorted(_SYS_NODE.iterdir()):
            m = re.fullmatch(r"node(\d+)", child.name)
            if not m:
                continue
            cpulist = child / "cpulist"
            try:
                cpus = _parse_cpulist(cpulist.read_text(encoding="utf-8"))
            except OSError as e:
                logger.warning("numa: cannot read %s: %s", cpulist, e)
                continue
            nodes[int(m.group(1))] = cpus
        if nodes:
            distances: dict[int, dict[int, int]] = {}
            for node in nodes:
                dist_file = _SYS_NODE / f"node{node}" / "distance"
                try:
                    vals = [int(v) for v in
                            dist_file.read_text(encoding="utf-8").split()]
                    ids = sorted(nodes)
                    if len(vals) == len(ids):
                        distances[node] = dict(zip(ids, vals, strict=True))
                except OSError:
                    pass
            topo = NumaTopology(nodes=nodes, distances=distances,
                                source="sysfs")
            logger.info("numa: detected %d node(s) via sysfs: %s",
                        len(nodes), topo.to_dict()["nodes"])
            return topo
    # Fallback: one synthetic node with every visible CPU.
    count = os.cpu_count() or 1
    topo = NumaTopology(nodes={0: list(range(count))}, source="fallback")
    logger.info("numa: sysfs unavailable; single-node fallback (%d cpus)",
                count)
    return topo


def is_numa(topology: NumaTopology | None = None) -> bool:
    """True when the machine actually has multiple NUMA nodes."""
    topo = topology or detect_topology()
    return len(topo.nodes) > 1


def _affinity() -> set[int]:
    try:
        return set(os.sched_getaffinity(0))
    except (AttributeError, OSError) as e:
        raise NumaError(f"cannot read thread affinity: {e}") from e


def current_node(topology: NumaTopology | None = None) -> int | None:
    """NUMA node of the calling thread (None if undeterminable)."""
    topo = topology or detect_topology()
    pinned = _affinity()
    votes: dict[int, int] = {}
    for cpu in pinned:
        node = topo.node_of_cpu(cpu)
        if node is not None:
            votes[node] = votes.get(node, 0) + 1
    if not votes:
        return None
    # The node holding most of our pinned CPUs wins.
    return max(votes, key=lambda n: votes[n])


def pin_thread(cpus: set[int] | list[int],
               topology: NumaTopology | None = None) -> None:
    """Pin the calling thread to ``cpus``. Raises :class:`NumaError`."""
    want = set(cpus)
    if not want:
        raise NumaError("cannot pin thread to an empty CPU set")
    topo = topology or detect_topology()
    known = set()
    for c in topo.nodes.values():
        known.update(c)
    unknown = want - known
    if unknown:
        raise NumaError(
            f"CPUs {sorted(unknown)} not in detected topology "
            f"({topo.cpu_count} cpus across nodes {topo.node_ids})")
    try:
        os.sched_setaffinity(0, want)
    except (AttributeError, OSError) as e:
        raise NumaError(f"failed to pin thread to CPUs {sorted(want)}: "
                        f"{e}") from e
    logger.debug("numa: thread pinned to CPUs %s", sorted(want))


def pin_to_node(node: int, topology: NumaTopology | None = None) -> None:
    """Pin the calling thread to every CPU of ``node``."""
    topo = topology or detect_topology()
    if node not in topo.nodes:
        raise NumaError(
            f"unknown NUMA node {node}; known nodes: {topo.node_ids}")
    pin_thread(set(topo.nodes[node]), topo)


class pinned_to:
    """Context manager: pin to ``node`` for the block, then restore.

    Usage::

        with pinned_to(1):
            ...  # runs on node 1's CPUs
        # previous affinity restored
    """

    def __init__(self, node: int,
                 topology: NumaTopology | None = None) -> None:
        self._node = node
        self._topology = topology or detect_topology()
        self._previous: set[int] | None = None

    def __enter__(self) -> pinned_to:
        self._previous = _affinity()
        pin_to_node(self._node, self._topology)
        return self

    def __exit__(self, *exc: Any) -> None:
        if self._previous is not None:
            try:
                os.sched_setaffinity(0, self._previous)
            except (AttributeError, OSError) as e:
                raise NumaError(
                    f"failed to restore thread affinity: {e}") from e


def suggest_node(worker_index: int, topology: NumaTopology | None = None
                 ) -> int:
    """Round-robin node suggestion for striping workers across nodes."""
    topo = topology or detect_topology()
    ids = topo.node_ids
    if worker_index < 0:
        raise NumaError(
            f"worker_index must be >= 0, got {worker_index}")
    return ids[worker_index % len(ids)]
