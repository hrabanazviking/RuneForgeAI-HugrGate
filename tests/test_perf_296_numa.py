"""Slice 296 — NUMA awareness boundary.

Covers: topology detection (sysfs shape on this machine), fallback
synthesis, cpulist parsing, node_of_cpu/distance accessors, pinning
round-trip with restore, pinned_to context manager, current_node,
suggest_node round-robin, and NumaError paths. Real multi-node
validation is impossible on this single-node VM (asserted, not
assumed).
"""

from __future__ import annotations

import os

import pytest

from hugrgate.errors import NumaError
from hugrgate.numa import (
    NumaTopology,
    _parse_cpulist,
    current_node,
    detect_topology,
    is_numa,
    pin_thread,
    pin_to_node,
    pinned_to,
    suggest_node,
)


def test_parse_cpulist():
    assert _parse_cpulist("0-3,8,10-11") == [0, 1, 2, 3, 8, 10, 11]
    assert _parse_cpulist("0-1\n") == [0, 1]
    assert _parse_cpulist("5") == [5]
    assert _parse_cpulist("") == []


def test_detect_topology_shape():
    topo = detect_topology()
    assert topo.node_ids
    assert topo.cpu_count >= 1
    assert topo.source in ("sysfs", "fallback")
    if topo.source == "sysfs":
        # Every CPU appears on exactly one node.
        seen = [c for cpus in topo.nodes.values() for c in cpus]
        assert len(seen) == len(set(seen)) == topo.cpu_count


def test_is_numa_matches_topology():
    topo = detect_topology()
    assert is_numa(topo) == (len(topo.nodes) > 1)


def test_node_of_cpu_and_distance():
    topo = NumaTopology(nodes={0: [0, 1], 1: [2, 3]},
                        distances={0: {0: 10, 1: 20},
                                   1: {0: 20, 1: 10}})
    assert topo.node_of_cpu(2) == 1
    assert topo.node_of_cpu(99) is None
    assert topo.distance(0, 1) == 20
    assert topo.distance(0, 99) is None
    assert topo.to_dict()["source"] == "sysfs"


def test_pin_thread_round_trip():
    previous = os.sched_getaffinity(0)
    try:
        pin_thread({0})
        assert os.sched_getaffinity(0) == {0}
    finally:
        os.sched_setaffinity(0, previous)
    assert os.sched_getaffinity(0) == previous


def test_pin_thread_rejects_unknown_cpu():
    with pytest.raises(NumaError, match="not in detected topology"):
        pin_thread({10**6})


def test_pin_thread_rejects_empty():
    with pytest.raises(NumaError, match="empty CPU set"):
        pin_thread(set())


def test_pin_to_node_round_trip():
    topo = detect_topology()
    previous = os.sched_getaffinity(0)
    try:
        pin_to_node(topo.node_ids[0], topo)
        assert os.sched_getaffinity(0) == set(topo.nodes[topo.node_ids[0]])
    finally:
        os.sched_setaffinity(0, previous)


def test_pin_to_unknown_node():
    with pytest.raises(NumaError, match="unknown NUMA node"):
        pin_to_node(10**6)


def test_pinned_to_restores():
    topo = detect_topology()
    previous = os.sched_getaffinity(0)
    with pinned_to(topo.node_ids[0], topo):
        assert os.sched_getaffinity(0) == set(topo.nodes[topo.node_ids[0]])
    assert os.sched_getaffinity(0) == previous


def test_current_node():
    topo = detect_topology()
    node = current_node(topo)
    assert node in topo.node_ids


def test_suggest_node_round_robin():
    topo = NumaTopology(nodes={0: [0], 1: [1], 2: [2]})
    assert [suggest_node(i, topo) for i in range(5)] == [0, 1, 2, 0, 1]
    with pytest.raises(NumaError, match="worker_index"):
        suggest_node(-1, topo)


def test_single_node_hardware_noted():
    # Law 13: this VM has one node; multi-node behavior is
    # unvalidated by construction. The test pins the fact.
    topo = detect_topology()
    assert topo.source == "sysfs"  # real sysfs, single node
    assert not is_numa(topo)
