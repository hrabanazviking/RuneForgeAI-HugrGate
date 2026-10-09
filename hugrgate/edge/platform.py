"""Edge platform detection and ARM64 compatibility audit. Slice 176.

:class:`PlatformProbe` inspects the host (architecture, CPU features,
OS, page size, Python build) without importing anything heavyweight.
:func:`audit_arm64` turns those facts into an :class:`Arm64AuditReport`
--- a list of typed, severity-graded findings plus remediation advice ---
so a deployment script can decide whether this host is a sane HugrGate
edge target.

The audit never *claims* hardware compatibility it cannot prove: every
finding records how it was derived (``source``) and whether the check
ran against live host data or injected fixtures.
"""

from __future__ import annotations

import os
import platform
import struct
import sys
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "Arm64AuditReport",
    "Arm64Finding",
    "PlatformInfo",
    "PlatformProbe",
    "audit_arm64",
]

#: Severities, ordered. ``error`` means "do not deploy here";
#: ``warning`` means "degraded but usable"; ``info`` is observational.
SEVERITIES = ("info", "warning", "error")

#: cpuinfo feature flags that matter for vectorized ARM64 inference.
_WANTED_FEATURES = ("asimd", "neon", "fp", "aes", "sha2")


@dataclass(frozen=True)
class PlatformInfo:
    """Immutable snapshot of the host relevant to edge deployment."""

    arch: str                # platform.machine(), e.g. "aarch64"
    system: str              # "Linux", "Darwin", ...
    release: str             # kernel / OS release
    python_version: tuple[int, int, int]
    python_implementation: str
    cpu_count: int | None
    cpu_features: tuple[str, ...]   # parsed from /proc/cpuinfo when present
    page_size: int | None           # os.sysconf("SC_PAGE_SIZE")
    byteorder: str                  # sys.byteorder
    is_64bit: bool
    live: bool = True               # False when built from fixtures

    @property
    def is_arm64(self) -> bool:
        return self.arch.lower() in ("aarch64", "arm64")

    def to_dict(self) -> dict[str, Any]:
        return {
            "arch": self.arch,
            "system": self.system,
            "release": self.release,
            "python_version": list(self.python_version),
            "python_implementation": self.python_implementation,
            "cpu_count": self.cpu_count,
            "cpu_features": list(self.cpu_features),
            "page_size": self.page_size,
            "byteorder": self.byteorder,
            "is_64bit": self.is_64bit,
            "is_arm64": self.is_arm64,
            "live": self.live,
        }


@dataclass(frozen=True)
class Arm64Finding:
    """One audit finding: what was checked, how bad it is, what to do."""

    id: str                  # stable id, e.g. "arm64/neon-missing"
    severity: str            # "info" | "warning" | "error"
    area: str                # "arch" | "cpu" | "os" | "python" | "memory" | "deps"
    message: str
    remediation: str
    source: str              # how the fact was derived, e.g. "platform.machine()"

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise ValueError(f"unknown severity {self.severity!r}")


@dataclass
class Arm64AuditReport:
    """The complete audit: platform facts + findings + verdict."""

    platform: PlatformInfo
    findings: list[Arm64Finding] = field(default_factory=list)

    @property
    def errors(self) -> list[Arm64Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[Arm64Finding]:
        return [f for f in self.findings if f.severity == "warning"]

    @property
    def passed(self) -> bool:
        """No ``error`` findings. Warnings are survivable."""
        return not self.errors

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return (f"arm64 audit {status}: {len(self.errors)} error(s), "
                f"{len(self.warnings)} warning(s), "
                f"{len(self.findings)} finding(s) on {self.platform.arch}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "platform": self.platform.to_dict(),
            "findings": [
                {"id": f.id, "severity": f.severity, "area": f.area,
                 "message": f.message, "remediation": f.remediation,
                 "source": f.source}
                for f in self.findings
            ],
        }


def _cpu_features_from_cpuinfo(text: str) -> tuple[str, ...]:
    """Parse the union of ``Features`` lines from /proc/cpuinfo text."""
    features: set[str] = set()
    for line in text.splitlines():
        if line.lower().startswith("features"):
            _, _, rest = line.partition(":")
            features.update(tok.strip().lower() for tok in rest.split())
    return tuple(sorted(features))


class PlatformProbe:
    """Probe the host. All filesystem reads are injectable for tests."""

    def __init__(self, cpuinfo_text: str | None = None):
        # None -> read the live host; a string -> fixture (live=False).
        self._cpuinfo_text = cpuinfo_text

    def _read_cpuinfo(self) -> tuple[str, bool]:
        if self._cpuinfo_text is not None:
            return self._cpuinfo_text, False
        try:
            with open("/proc/cpuinfo", encoding="utf-8") as fh:
                return fh.read(), True
        except OSError:
            return "", True

    def probe(self) -> PlatformInfo:
        text, live = self._read_cpuinfo()
        try:
            page_size: int | None = os.sysconf("SC_PAGE_SIZE")
        except (OSError, ValueError, AttributeError):
            page_size = None
        vi = sys.version_info
        return PlatformInfo(
            arch=platform.machine(),
            system=platform.system(),
            release=platform.release(),
            python_version=(vi.major, vi.minor, vi.micro),
            python_implementation=platform.python_implementation(),
            cpu_count=os.cpu_count(),
            cpu_features=_cpu_features_from_cpuinfo(text),
            page_size=page_size,
            byteorder=sys.byteorder,
            is_64bit=struct.calcsize("P") == 8,
            live=live,
        )


def audit_arm64(platform_info: PlatformInfo | None = None,
                probe: PlatformProbe | None = None) -> Arm64AuditReport:
    """Audit a host for ARM64 HugrGate edge deployment.

    Findings are conservative: they flag *risks*, never promise
    performance. Anything depending on real edge silicon is marked
    with a ``NEEDS_HARDWARE_VALIDATION`` remediation note.
    """
    info = platform_info or (probe or PlatformProbe()).probe()
    findings: list[Arm64Finding] = []

    # --- architecture ---------------------------------------------------
    if info.is_arm64:
        findings.append(Arm64Finding(
            id="arm64/arch-ok", severity="info", area="arch",
            message=f"host arch {info.arch!r} is 64-bit ARM",
            remediation="none required",
            source="platform.machine()"))
    else:
        findings.append(Arm64Finding(
            id="arm64/not-arm64", severity="warning", area="arch",
            message=(f"host arch {info.arch!r} is not ARM64; edge "
                     "profiles are calibrated for aarch64"),
            remediation=("NEEDS_HARDWARE_VALIDATION: re-run this audit "
                         "on the target ARM64 board before deployment"),
            source="platform.machine()"))
    if info.byteorder != "little":
        findings.append(Arm64Finding(
            id="arm64/big-endian", severity="error", area="arch",
            message=f"byte order {info.byteorder!r} is not little-endian",
            remediation="HugrGate's serialization contracts assume "
                        "little-endian; do not deploy",
            source="sys.byteorder"))
    if not info.is_64bit:
        findings.append(Arm64Finding(
            id="arm64/not-64bit", severity="error", area="arch",
            message="32-bit Python cannot address edge model memory maps",
            remediation="use a 64-bit Python build",
            source="struct.calcsize('P')"))

    # --- CPU features ----------------------------------------------------
    if info.is_arm64 and info.cpu_features:
        missing = [f for f in ("asimd", "neon")
                   if f not in info.cpu_features]
        if missing:
            findings.append(Arm64Finding(
                id="arm64/simd-missing", severity="warning", area="cpu",
                message=(f"SIMD features missing from cpuinfo: "
                         f"{', '.join(missing)}"),
                remediation=("quantized inference paths will fall back to "
                             "scalar code; verify on target silicon"),
                source="/proc/cpuinfo Features"))
        else:
            findings.append(Arm64Finding(
                id="arm64/simd-ok", severity="info", area="cpu",
                message="ASIMD/NEON present — vectorized int8 kernels viable",
                remediation="none required",
                source="/proc/cpuinfo Features"))

    # --- OS / memory -----------------------------------------------------
    if info.page_size not in (4096, 16384, 65536, None):
        findings.append(Arm64Finding(
            id="arm64/page-size-odd", severity="warning", area="os",
            message=f"unusual page size {info.page_size}",
            remediation="verify mmap-based model loading on this kernel",
            source="os.sysconf('SC_PAGE_SIZE')"))
    if info.cpu_count is not None and info.cpu_count < 2:
        findings.append(Arm64Finding(
            id="arm64/single-core", severity="warning", area="cpu",
            message="single-core host; watchdog and inference will contend",
            remediation="pin inference to the core and run the watchdog "
                        "at the lowest priority, or use a bigger board",
            source="os.cpu_count()"))

    # --- Python -----------------------------------------------------------
    if info.python_version < (3, 10):
        findings.append(Arm64Finding(
            id="arm64/python-old", severity="error", area="python",
            message=(f"Python {'.'.join(map(str, info.python_version))} "
                     "is below the supported 3.10 floor"),
            remediation="install Python >= 3.10",
            source="sys.version_info"))

    # --- dependencies -----------------------------------------------------
    try:
        import numpy  # noqa: F401
        findings.append(Arm64Finding(
            id="arm64/numpy-ok", severity="info", area="deps",
            message="numpy importable — vectorized edge kernels available",
            remediation="none required",
            source="import numpy"))
    except ImportError:
        findings.append(Arm64Finding(
            id="arm64/numpy-missing", severity="warning", area="deps",
            message="numpy not installed; quantized paths fall back "
                    "to pure-Python (slow)",
            remediation="pip install 'hugrgate[bench]'",
            source="import numpy"))

    return Arm64AuditReport(platform=info, findings=findings)
