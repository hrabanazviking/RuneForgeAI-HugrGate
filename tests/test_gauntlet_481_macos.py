"""Slice 481 — macOS matrix.

macOS has no ``/proc``, no ``select.epoll``, and defaults
``multiprocessing`` to ``spawn``. This slice hardens the one real
gap found — ``HostProfile._detect_memory_mb()`` silently fell back
to 1024 MB on macOS — with a ``sysctl hw.memsize`` probe, and adds
``check_macos_assumptions()`` proving the tree carries no other
macOS-hostile assumptions.
"""

from __future__ import annotations

import builtins
import inspect
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from hugrgate.gauntlet.platforms import check_macos_assumptions
from hugrgate.multiproc import ProcessPool
from hugrgate.routing.hardware import HostProfile

ROOT = Path(__file__).resolve().parent.parent
REAL_OPEN = builtins.open


def _no_proc_open(path, *args, **kwargs):
    if str(path).startswith("/proc/"):
        raise OSError("simulated macOS: no /proc")
    return REAL_OPEN(path, *args, **kwargs)


def _fake_sysctl_ok(*args, **kwargs):
    assert args[0][:3] == ["sysctl", "-n", "hw.memsize"]
    return SimpleNamespace(returncode=0, stdout="17179869184\n")


def _fake_sysctl_fail(*args, **kwargs):
    raise OSError("simulated missing sysctl")


def test_no_macos_hostile_assumptions_in_tree():
    findings = check_macos_assumptions(ROOT / "hugrgate")
    assert findings == (), [str(f) for f in findings]


def test_synthetic_unguarded_proc_read_flagged(tmp_path):
    (tmp_path / "x.py").write_text('open("/proc/cpuinfo")\n', encoding="utf-8")
    findings = check_macos_assumptions(tmp_path)
    assert len(findings) == 1
    assert "/proc/cpuinfo" in findings[0].what


def test_synthetic_guarded_proc_read_passes(tmp_path):
    (tmp_path / "x.py").write_text(
        'try:\n    open("/proc/cpuinfo")\nexcept OSError:\n    pass\n',
        encoding="utf-8",
    )
    assert check_macos_assumptions(tmp_path) == ()


def test_synthetic_epoll_flagged(tmp_path):
    (tmp_path / "x.py").write_text(
        "import select\nselect.epoll()\n", encoding="utf-8"
    )
    findings = check_macos_assumptions(tmp_path)
    assert len(findings) == 1
    assert "epoll" in findings[0].what


def test_synthetic_forced_fork_flagged(tmp_path):
    (tmp_path / "x.py").write_text(
        'import multiprocessing\nmultiprocessing.set_start_method("fork")\n',
        encoding="utf-8",
    )
    findings = check_macos_assumptions(tmp_path)
    assert len(findings) == 1
    assert "fork" in findings[0].what


def test_process_pool_defaults_to_spawn():
    sig = inspect.signature(ProcessPool.__init__)
    assert sig.parameters["start_method"].default == "spawn"


def test_memory_detect_uses_sysctl_on_darwin(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(builtins, "open", _no_proc_open)
    monkeypatch.setattr(subprocess, "run", _fake_sysctl_ok)
    # 17179869184 bytes == 16384.0 MiB
    assert HostProfile._detect_memory_mb() == 16384.0


def test_memory_detect_falls_back_when_sysctl_missing(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(builtins, "open", _no_proc_open)
    monkeypatch.setattr(subprocess, "run", _fake_sysctl_fail)
    assert HostProfile._detect_memory_mb() == 1024.0


def test_memory_detect_prefers_proc_meminfo(monkeypatch):
    # On Linux the /proc path still wins; sysctl must not even run.
    def _boom(*args, **kwargs):
        raise AssertionError("sysctl must not run on Linux")

    monkeypatch.setattr(subprocess, "run", _boom)
    assert HostProfile._detect_memory_mb() > 0
