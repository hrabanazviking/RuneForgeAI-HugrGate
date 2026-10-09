"""Slice 479 — Linux matrix.

The platform matrix is built from actually validated platforms only.
``hugrgate/gauntlet/platforms.py`` provides platform detection, a
POSIX-only API scan with guard analysis, Linux live probes, and the
validated-platforms record. The scan's headline finding — an
*unguarded* ``signal.SIGKILL`` default argument in
``hugrgate/chaos/crash.py`` that breaks Windows import — is fixed in
slice 480; this slice proves the detector.
"""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

import pytest

from hugrgate.gauntlet import platforms
from hugrgate.gauntlet.platforms import (
    PlatformInfo,
    current_platform,
    is_validated,
    linux_live_checks,
    record_validated,
    scan_posix_only,
)

ROOT = Path(__file__).resolve().parent.parent


def test_current_platform_matches_reality():
    info = current_platform()
    assert info.os_name == os.name
    assert info.sys_platform == sys.platform
    assert info.machine == platform.machine()
    assert info.bits == (64 if sys.maxsize > 2**32 else 32)


def test_os_key_mapping():
    assert PlatformInfo("posix", "linux", "x86_64", 64).os_key == "linux"
    assert PlatformInfo("posix", "darwin", "arm64", 64).os_key == "macos"
    assert PlatformInfo("nt", "win32", "AMD64", 64).os_key == "windows"


@pytest.mark.skipif(sys.platform != "linux", reason="Linux-only live probes")
def test_linux_live_checks_all_pass():
    checks = linux_live_checks()
    assert checks["is_linux"] is True
    assert checks["epoll_available"] is True
    assert checks["proc_self_readable"] is True
    assert checks["uname_works"] is True


def test_scan_finds_guarded_resource_imports():
    findings = {str(f): f for f in scan_posix_only(ROOT / "hugrgate")}
    guarded = [f for f in findings.values()
               if f.api == "import resource" and f.guarded]
    # Slice 488 added the fourth: hugrgate/gauntlet/soak.py's guarded
    # import for its RSS-growth invariant.
    assert len(guarded) == 4, [str(f) for f in findings.values()]


def test_scan_flags_unguarded_sigkill(tmp_path):
    # Slice 479 proved the detector on the real tree (it found the
    # unguarded signal.SIGKILL default in hugrgate/chaos/crash.py:98);
    # slice 480 fixed it, so this now proves the detector on a
    # synthetic file carrying the same hazard.
    (tmp_path / "x.py").write_text(
        "import signal\n"
        "def run(kill_signal: int = signal.SIGKILL):\n"
        "    pass\n",
        encoding="utf-8",
    )
    findings = scan_posix_only(tmp_path)
    bad = [f for f in findings
           if f.api == "signal.SIGKILL" and not f.guarded]
    assert len(bad) == 1


def test_scan_flags_synthetic_unguarded_fork(tmp_path):
    (tmp_path / "x.py").write_text("import os\nos.fork()\n", encoding="utf-8")
    findings = scan_posix_only(tmp_path)
    assert len(findings) == 1
    assert findings[0].api == "os.fork"
    assert findings[0].guarded is False


def test_scan_accepts_guarded_import(tmp_path):
    (tmp_path / "x.py").write_text(
        "try:\n    import fcntl\n    fcntl.flock\n"
        "except ImportError:\n    fcntl = None\n",
        encoding="utf-8",
    )
    findings = scan_posix_only(tmp_path)
    assert len(findings) == 1
    assert findings[0].guarded is True


def test_scan_accepts_platform_conditional(tmp_path):
    (tmp_path / "x.py").write_text(
        "import sys\nimport os\n"
        "if sys.platform != 'win32':\n    os.fork()\n",
        encoding="utf-8",
    )
    findings = scan_posix_only(tmp_path)
    assert len(findings) == 1
    assert findings[0].guarded is True


def test_record_validated_roundtrip():
    saved = platforms.VALIDATED_PLATFORMS
    try:
        platforms.VALIDATED_PLATFORMS = ()
        info = current_platform()
        assert is_validated(info) is False
        record_validated(info)
        assert is_validated(info) is True
        before = platforms.VALIDATED_PLATFORMS
        record_validated(info)  # idempotent
        assert platforms.VALIDATED_PLATFORMS == before
        assert len(before) == 1
    finally:
        platforms.VALIDATED_PLATFORMS = saved
