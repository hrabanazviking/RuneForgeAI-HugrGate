"""Slice 480 — Windows matrix.

Slice 479's scan found the Windows import-time crash: an unguarded
``signal.SIGKILL`` evaluated as a default argument in
``hugrgate/chaos/crash.py``. This slice fixes it
(``kill_signal=None`` + call-time resolution via
``default_kill_signal()``) and proves the fix by simulating a
Windows ``signal`` module (no ``SIGKILL``) and re-importing.
"""

from __future__ import annotations

import importlib
import signal
from pathlib import Path

import pytest

import hugrgate.chaos.crash as crash_mod
from hugrgate.chaos.crash import CrashOnlyHarness
from hugrgate.gauntlet.platforms import check_windows_import_safety

ROOT = Path(__file__).resolve().parent.parent


def test_no_unguarded_posix_apis_remain():
    """The Windows import gate is green across the whole package."""
    bad = check_windows_import_safety(ROOT / "hugrgate")
    assert bad == (), [str(f) for f in bad]


def test_default_kill_signal_is_sigkill_where_available():
    if not hasattr(signal, "SIGKILL"):  # pragma: no cover - non-POSIX
        pytest.skip("no SIGKILL on this platform")
    assert CrashOnlyHarness.default_kill_signal() == signal.SIGKILL


def test_crash_module_imports_without_sigkill():
    """Simulate Windows: ``signal`` without SIGKILL must not break import."""
    had_sigkill = hasattr(signal, "SIGKILL")
    saved = getattr(signal, "SIGKILL", None)
    if had_sigkill:
        del signal.SIGKILL  # simulate the Windows signal module
    try:
        assert not hasattr(signal, "SIGKILL")
        reloaded = importlib.reload(crash_mod)
        assert reloaded.CrashOnlyHarness.default_kill_signal() == signal.SIGTERM
    finally:
        if had_sigkill:
            signal.SIGKILL = saved
        importlib.reload(crash_mod)
    assert hasattr(signal, "SIGKILL") == had_sigkill


def test_run_worker_accepts_explicit_signal(tmp_path):
    harness = CrashOnlyHarness(tmp_path)
    # Explicit signal still honored; tiny count finishes before the kill.
    report = harness.run_worker(count=10, kill_after_s=30.0,
                                kill_signal=signal.SIGTERM)
    assert report is not None


def test_run_worker_defaults_resolve(tmp_path):
    harness = CrashOnlyHarness(tmp_path)
    report = harness.run_worker(count=10, kill_after_s=30.0)
    assert report is not None


def test_kill_signal_default_is_none():
    """The hazard (def-time signal.SIGKILL) is gone from the signature."""
    import inspect

    sig = inspect.signature(CrashOnlyHarness.run_worker)
    assert sig.parameters["kill_signal"].default is None
