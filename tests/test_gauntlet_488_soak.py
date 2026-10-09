"""Slice 488 — long-duration soak.

``hugrgate/chaos/soak.py`` could soak for hours without noticing a
slow memory leak — no invariant watched memory. This slice adds
``hugrgate/gauntlet/soak.py``: an RSS-growth invariant for
``SoakRunner`` plus ``run_gate_soak()`` driving the real gate, and
``tools/soak_run.py`` as the runnable form.
"""

from __future__ import annotations

import pytest

import hugrgate.gauntlet.soak as soak_mod
from hugrgate.gauntlet.soak import (
    MemoryGrowthInvariant,
    rss_mb,
    run_gate_soak,
)

HAVE_RESOURCE = rss_mb() is not None


@pytest.mark.skipif(not HAVE_RESOURCE, reason="RSS unobservable here")
def test_rss_mb_is_sane():
    rss = rss_mb()
    assert rss is not None
    assert rss > 0


def test_invariant_rejects_bad_args():
    with pytest.raises(ValueError):
        MemoryGrowthInvariant(budget_mb=0)
    with pytest.raises(ValueError):
        MemoryGrowthInvariant(window_ops=0)


def test_invariant_passes_on_stable_memory(monkeypatch):
    monkeypatch.setattr(soak_mod, "rss_mb", lambda: 100.0)
    inv = MemoryGrowthInvariant(budget_mb=10.0, window_ops=100)
    for _ in range(10):
        inv()  # must not raise
    assert inv.max_growth_mb == 0.0


def test_invariant_fires_on_growth(monkeypatch):
    readings = iter([100.0, 100.0, 200.0])
    monkeypatch.setattr(soak_mod, "rss_mb", lambda: next(readings))
    inv = MemoryGrowthInvariant(budget_mb=50.0, window_ops=100)
    inv()  # snapshot
    inv()  # stable
    with pytest.raises(AssertionError) as exc_info:
        inv()  # +100 MiB over budget
    assert "grew 100.0 MiB" in str(exc_info.value)
    assert inv.max_growth_mb == 100.0


def test_invariant_snapshot_refreshes(monkeypatch):
    # Growth that settles must not trip the invariant forever:
    # after window_ops checks the snapshot refreshes.
    readings = iter([100.0, 140.0, 140.0, 140.0, 140.0])
    monkeypatch.setattr(soak_mod, "rss_mb", lambda: next(readings))
    inv = MemoryGrowthInvariant(budget_mb=50.0, window_ops=2)
    for _ in range(5):
        inv()  # must not raise: +40 MiB, then refresh
    assert inv.max_growth_mb == 40.0


def test_invariant_tolerates_unobservable(monkeypatch):
    monkeypatch.setattr(soak_mod, "rss_mb", lambda: None)
    inv = MemoryGrowthInvariant()
    inv()  # must not raise


@pytest.mark.skipif(not HAVE_RESOURCE, reason="RSS unobservable here")
def test_gate_soak_passes():
    summary = run_gate_soak(iterations=200, rss_budget_mb=50.0,
                            duration_s=30.0)
    assert summary.ops == 200
    assert summary.violations == ()
    assert summary.errors == {}
    assert summary.ok
    assert summary.max_rss_growth_mb >= 0.0
