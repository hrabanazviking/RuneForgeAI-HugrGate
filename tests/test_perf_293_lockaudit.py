"""Slice 293 — lock contention audit.

Covers: InstrumentedLock statistics (counts, wait/hold times,
context-manager use, real contention between threads) and the AST
audit (nested-lock detection, blocking calls, call-in-critical-section
heuristic, cond.wait() exemption, summarize()).
"""

from __future__ import annotations

import textwrap
import threading
import time

import pytest

from hugrgate.lockaudit import (
    Finding,
    InstrumentedLock,
    audit_locks,
    summarize,
)

# --- InstrumentedLock ---------------------------------------------------------------

def test_counts_and_hold_time():
    lock = InstrumentedLock("test")
    with lock:
        time.sleep(0.01)
    with lock:
        pass
    rep = lock.report()
    assert rep["name"] == "test"
    assert rep["acquisitions"] == 2
    assert rep["total_hold_s"] >= 0.01
    assert rep["max_hold_us"] >= 0.01 * 1e6
    assert rep["mean_hold_us"] > 0


def test_measures_real_contention():
    lock = InstrumentedLock("contended")
    entered = threading.Event()
    release = threading.Event()

    def holder():
        with lock:
            entered.set()
            assert release.wait(timeout=5.0)

    t = threading.Thread(target=holder)
    t.start()
    assert entered.wait(timeout=5.0)
    t0 = time.perf_counter()
    with lock:
        waited = time.perf_counter() - t0
    release.set()
    t.join()
    rep = lock.report()
    assert rep["acquisitions"] == 2
    assert rep["max_wait_us"] >= waited * 1e6 * 0.9  # measured, not guessed
    assert rep["total_wait_s"] > 0


def test_uncontended_wait_near_zero():
    lock = InstrumentedLock("fast")
    for _ in range(100):
        with lock:
            pass
    rep = lock.report()
    assert rep["acquisitions"] == 100
    assert rep["mean_wait_us"] < 100.0  # no contention: fast path


def test_bad_kind_rejected():
    with pytest.raises(ValueError, match="kind"):
        InstrumentedLock("x", kind="semaphore")


def test_locked_passthrough():
    lock = InstrumentedLock("p")
    assert not lock.locked()
    with lock:
        assert lock.locked()
    assert not lock.locked()


# --- AST audit ----------------------------------------------------------------------

def _write_pkg(tmp_path, name="fakepkg"):
    pkg = tmp_path / name
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(textwrap.dedent('''\
        import threading
        import time

        class Widget:
            def __init__(self):
                self._lock = threading.RLock()
                self._other_lock = threading.Lock()
                self._cond = threading.Condition()

            def nested(self):
                with self._lock:
                    with self._other_lock:  # nested-lock
                        pass

            def sleeper(self):
                with self._lock:
                    time.sleep(1)  # blocking-call

            def caller(self):
                with self._lock:
                    self._helper()  # call-in-critical-section

            def cond_ok(self):
                with self._cond:
                    self._cond.wait(timeout=1.0)  # correct: not flagged

            def _helper(self):
                pass

            def plain(self):
                with open("x") as fh:  # not a lock: ignored
                    fh.read()
        '''))
    return str(pkg)


def test_audit_finds_patterns(tmp_path):
    pkg = _write_pkg(tmp_path)
    findings = audit_locks(pkg)
    by_kind: dict[str, list[Finding]] = {}
    for f in findings:
        by_kind.setdefault(f.kind, []).append(f)

    nested = [f for f in by_kind.get("nested-lock", [])
              if f.function == "nested"]
    assert len(nested) == 1
    assert "self._other" in nested[0].detail

    blocking = [f for f in by_kind.get("blocking-call", [])
                if f.function == "sleeper"]
    assert any("sleep" in f.detail for f in blocking)

    calls = [f for f in by_kind.get("call-in-critical-section", [])
             if f.function == "caller"]
    assert any("_helper" in f.detail for f in calls)

    # cond.wait() inside `with self._cond:` is correct usage: no finding.
    cond_blocking = [f for f in by_kind.get("blocking-call", [])
                     if f.function == "cond_ok"]
    assert cond_blocking == []
    # `with open(...)` is not a lock block.
    assert all(f.function != "plain" for f in findings)


def test_audit_summarize(tmp_path):
    pkg = _write_pkg(tmp_path)
    s = summarize(audit_locks(pkg))
    assert s["total"] > 0
    assert s["by_kind"]["nested-lock"] >= 1
    assert any("mod.py" in p for p in s["by_file"])


def test_audit_real_package_has_no_nested_locks():
    # The deadlock shape must stay absent from the real codebase.
    findings = audit_locks("hugrgate")
    nested = [f for f in findings if f.kind == "nested-lock"]
    assert nested == []
