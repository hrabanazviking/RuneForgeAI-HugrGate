"""Slice 297 — GPU scheduling boundary.

Covers: csv parsing (two-GPU sample, empty, malformed rows,
non-numeric fields, negative values, deterministic ordering),
live discovery returning [] on this GPU-less machine, scheduler
policies (least-memory-used, round-robin), re-assignment idempotence,
release, capacity caps, empty-inventory CPU fallback, and config
validation. Law 13: no real GPU hardware here — the parser is tested
on samples, the scheduler on synthetic inventories.
"""

from __future__ import annotations

import pytest

from hugrgate.errors import GpuschedError
from hugrgate.gpusched import (
    SAMPLE_SMI_MALFORMED,
    SAMPLE_SMI_TWO_GPU,
    GpuScheduler,
    discover_gpus,
    parse_smi_csv,
)


def _inventory():
    return parse_smi_csv(SAMPLE_SMI_TWO_GPU)


# --- parsing ---------------------------------------------------------------------------


def test_parse_two_gpus():
    gpus = _inventory()
    assert len(gpus) == 2
    g0, g1 = gpus
    assert (g0.index, g0.name) == (0, "NVIDIA A100-SXM4-40GB")
    assert (g0.memory_total_mb, g0.memory_used_mb,
            g0.memory_free_mb) == (40960, 1234, 39726)
    assert g0.utilization_pct == 5
    assert g1.memory_used_mb == 38912
    assert g1.utilization_pct == 92
    assert g0.memory_used_frac == pytest.approx(1234 / 40960)


def test_parse_empty():
    assert parse_smi_csv("") == []
    assert parse_smi_csv("\n  \n") == []


def test_parse_malformed_column_count():
    with pytest.raises(GpuschedError, match="expected 6 columns"):
        parse_smi_csv(SAMPLE_SMI_MALFORMED)


def test_parse_non_numeric():
    with pytest.raises(GpuschedError, match="non-numeric"):
        parse_smi_csv("0, GPU, lots, 1, 2, 3")


def test_parse_negative_rejected():
    with pytest.raises(GpuschedError, match="negative"):
        parse_smi_csv("0, GPU, 100, -1, 101, 0")


def test_parse_sorts_by_index():
    text = ("1, B, 100, 10, 90, 5\n"
            "0, A, 100, 20, 80, 6\n")
    gpus = parse_smi_csv(text)
    assert [g.index for g in gpus] == [0, 1]


def test_parse_percent_sign_tolerated():
    gpus = parse_smi_csv("0, GPU, 100, 10, 90, 42 %")
    assert gpus[0].utilization_pct == 42


def test_gpu_info_dict_shape():
    d = _inventory()[0].to_dict()
    assert d["index"] == 0
    assert d["memory_total_mb"] == 40960


# --- live discovery ----------------------------------------------------------------------

def test_discover_no_gpu_here():
    # Law 13: this machine has no nvidia-smi; discovery must report
    # the CPU-only truth instead of raising.
    assert discover_gpus() == []


def test_discover_missing_binary():
    assert discover_gpus(smi_binary="definitely-not-a-binary-xyz") == []


# --- scheduler -----------------------------------------------------------------------------

def test_least_memory_used_policy():
    sched = GpuScheduler(_inventory(), policy="least-memory-used")
    # gpu0 is nearly empty (3%), gpu1 nearly full (95%).
    assert sched.assign("w1") == 0
    assert sched.assign("w2") == 0  # still emptiest by memory
    assert sched.device_of("w1") == 0


def test_round_robin_policy():
    sched = GpuScheduler(_inventory(), policy="round-robin")
    assert [sched.assign(f"w{i}") for i in range(4)] == [0, 1, 0, 1]


def test_reassign_idempotent():
    sched = GpuScheduler(_inventory())
    assert sched.assign("w") == sched.assign("w") == 0
    assert len(sched.stats()["assignments"]) == 1


def test_release():
    sched = GpuScheduler(_inventory())
    sched.assign("w")
    assert sched.release("w") is True
    assert sched.device_of("w") is None
    assert sched.release("w") is False  # idempotent


def test_max_workers_per_gpu():
    sched = GpuScheduler(_inventory(), policy="round-robin",
                         max_workers_per_gpu=1)
    sched.assign("a")  # gpu0
    sched.assign("b")  # gpu1
    with pytest.raises(GpuschedError, match="max_workers_per_gpu"):
        sched.assign("c")
    sched.release("a")
    assert sched.assign("c") == 0  # slot freed


def test_empty_inventory_cpu_fallback():
    sched = GpuScheduler([], policy="least-memory-used")
    assert sched.assign("w") is None  # run on CPU
    assert sched.device_of("w") is None


def test_bad_policy_rejected():
    with pytest.raises(GpuschedError, match="unknown policy"):
        GpuScheduler(_inventory(), policy="magic")


def test_bad_cap_rejected():
    with pytest.raises(GpuschedError, match="max_workers_per_gpu"):
        GpuScheduler(_inventory(), max_workers_per_gpu=0)


def test_empty_worker_rejected():
    with pytest.raises(GpuschedError, match="non-empty"):
        GpuScheduler(_inventory()).assign("")


def test_stats_shape():
    sched = GpuScheduler(_inventory())
    sched.assign("w1")
    stats = sched.stats()
    assert stats["policy"] == "least-memory-used"
    assert len(stats["gpus"]) == 2
    assert stats["assignments"] == {"w1": 0}
    assert stats["load_by_gpu"] == {0: 1, 1: 0}
