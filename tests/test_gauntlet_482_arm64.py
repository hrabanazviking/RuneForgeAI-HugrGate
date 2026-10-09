"""Slice 482 — ARM64 matrix.

The architecture axis of the platform matrix: ``normalize_arch()``
unifies ``platform.machine()`` aliases (Linux ``aarch64`` ==
macOS ``arm64``), the validated-platform keys use the normalized
form, and ``check_arch_assumptions()`` proves the tree carries no
x86-64-only assumptions (raw ISA tokens, SIMD intrinsics, exact
``machine()`` string comparisons).
"""

from __future__ import annotations

from pathlib import Path

from hugrgate.gauntlet import platforms
from hugrgate.gauntlet.platforms import (
    PlatformInfo,
    check_arch_assumptions,
    current_platform,
    is_validated,
    normalize_arch,
    record_validated,
)

ROOT = Path(__file__).resolve().parent.parent


def test_normalize_arch_aliases():
    assert normalize_arch("aarch64") == "arm64"
    assert normalize_arch("arm64") == "arm64"
    assert normalize_arch("AMD64") == "x86_64"
    assert normalize_arch("x86_64") == "x86_64"
    assert normalize_arch("  AARCH64  ") == "arm64"
    # Unknown arches pass through lowercased, never crash the matrix.
    assert normalize_arch("riscv64") == "riscv64"


def test_platform_key_uses_normalized_arch():
    linux_arm = PlatformInfo("posix", "linux", "aarch64", 64)
    mac_arm = PlatformInfo("posix", "darwin", "arm64", 64)
    assert linux_arm.arch_key == mac_arm.arch_key == "arm64"
    assert linux_arm.platform_key == ("linux", "arm64")


def test_aarch64_and_arm64_validate_as_one():
    saved = platforms.VALIDATED_PLATFORMS
    try:
        platforms.VALIDATED_PLATFORMS = ()
        record_validated(PlatformInfo("posix", "linux", "aarch64", 64))
        assert is_validated(PlatformInfo("posix", "linux", "arm64", 64))
        assert len(platforms.VALIDATED_PLATFORMS) == 1
    finally:
        platforms.VALIDATED_PLATFORMS = saved


def test_no_arch_assumptions_in_tree():
    findings = check_arch_assumptions(ROOT / "hugrgate")
    assert findings == (), [str(f) for f in findings]


def test_synthetic_isa_token_flagged(tmp_path):
    (tmp_path / "x.py").write_text('FLAGS = "__x86_64__"\n', encoding="utf-8")
    findings = check_arch_assumptions(tmp_path)
    assert len(findings) == 1
    assert "__x86_64__" in findings[0].what


def test_synthetic_exact_machine_comparison_flagged(tmp_path):
    (tmp_path / "x.py").write_text(
        "import platform\n"
        "if platform.machine() == 'x86_64':\n"
        "    fast_path()\n",
        encoding="utf-8",
    )
    findings = check_arch_assumptions(tmp_path)
    assert len(findings) == 1
    assert "normalize_arch" in findings[0].what


def test_normalized_comparison_passes(tmp_path):
    (tmp_path / "x.py").write_text(
        "import platform\n"
        "from hugrgate.gauntlet.platforms import normalize_arch\n"
        "if normalize_arch(platform.machine()) == 'arm64':\n"
        "    fast_path()\n",
        encoding="utf-8",
    )
    assert check_arch_assumptions(tmp_path) == ()


def test_current_host_arch_key_sane():
    info = current_platform()
    assert info.arch_key == normalize_arch(info.machine)
    assert info.bits in (32, 64)
