"""Edge platform detection, ARM64 audit, and Raspberry Pi baselines.

Slices 176-177.

:class:`PlatformProbe` inspects the host (architecture, CPU features,
OS, page size, Python build) without importing anything heavyweight.
:func:`audit_arm64` turns those facts into an :class:`Arm64AuditReport`
--- a list of typed, severity-graded findings plus remediation advice ---
so a deployment script can decide whether this host is a sane HugrGate
edge target.

:class:`PiBoard` identifies Raspberry Pi hardware from
``/proc/cpuinfo`` (``Revision``/``Model`` lines) and the device-tree
model file; :func:`pi_baseline` maps a detected (or named) board to an
:class:`EdgeBaseline` of conservative, published hardware specs that the
rest of the edge runtime (memory modes, cache tuning, benchmarks)
calibrates against.

The audit never *claims* hardware compatibility it cannot prove: every
finding records how it was derived (``source``) and whether the check
ran against live host data or injected fixtures. Board specs are
published manufacturer figures, not measurements; per-device validation
is marked ``NEEDS_HARDWARE_VALIDATION``.
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
    "EdgeBaseline",
    "PiBoard",
    "PlatformInfo",
    "PlatformProbe",
    "audit_arm64",
    "detect_pi_board",
    "pi_baseline",
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


# --- Raspberry Pi baselines (slice 177) ------------------------------------

#: New-style revision codes (bits 23+ flag) mapped to (model label, RAM MB).
#: Source: Raspberry Pi documentation, "Raspberry Pi Revision Codes".
_PI_REVISIONS: dict[str, tuple[str, int]] = {
    "a020d3": ("Raspberry Pi 3 Model B+", 1024),
    "a03111": ("Raspberry Pi 4 Model B", 1024),
    "b03111": ("Raspberry Pi 4 Model B", 2048),
    "b03112": ("Raspberry Pi 4 Model B", 2048),
    "b03114": ("Raspberry Pi 4 Model B", 2048),
    "c03111": ("Raspberry Pi 4 Model B", 4096),
    "c03112": ("Raspberry Pi 4 Model B", 4096),
    "c03114": ("Raspberry Pi 4 Model B", 4096),
    "d03114": ("Raspberry Pi 4 Model B", 8192),
    "902120": ("Raspberry Pi Zero 2 W", 512),
    "c04170": ("Raspberry Pi 5", 4096),
    "d04170": ("Raspberry Pi 5", 8192),
    "e04170": ("Raspberry Pi 5", 16384),
}


@dataclass(frozen=True)
class PiBoard:
    """An identified Raspberry Pi board."""

    model: str
    revision: str
    ram_mb: int
    detected_live: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"model": self.model, "revision": self.revision,
                "ram_mb": self.ram_mb, "detected_live": self.detected_live}


@dataclass(frozen=True)
class EdgeBaseline:
    """Conservative published-spec baseline for an edge board.

    These are *manufacturer figures*, not measurements — every other
    edge subsystem treats them as calibration anchors and marks its own
    numbers ``NEEDS_HARDWARE_VALIDATION`` until measured on the device.
    """

    board: str
    cpu_count: int
    cpu_desc: str
    ram_mb: int
    recommended_cache_entries: int
    recommended_max_resident_models: int
    recommended_power_budget_mw: int | None
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "board": self.board,
            "cpu_count": self.cpu_count,
            "cpu_desc": self.cpu_desc,
            "ram_mb": self.ram_mb,
            "recommended_cache_entries": self.recommended_cache_entries,
            "recommended_max_resident_models":
                self.recommended_max_resident_models,
            "recommended_power_budget_mw": self.recommended_power_budget_mw,
            "notes": list(self.notes),
        }


def _baseline(board: str, cpu_count: int, cpu_desc: str, ram_mb: int,
              cache_entries: int, resident_models: int,
              power_mw: int | None, *notes: str) -> EdgeBaseline:
    return EdgeBaseline(board=board, cpu_count=cpu_count, cpu_desc=cpu_desc,
                        ram_mb=ram_mb,
                        recommended_cache_entries=cache_entries,
                        recommended_max_resident_models=resident_models,
                        recommended_power_budget_mw=power_mw,
                        notes=notes)


#: Baselines keyed by canonical model label. Cache/model recommendations
#: are deliberately conservative: a Pi 3B+ keeps 1/8th of its 1 GiB for
#: the decision cache; a Pi 5 keeps a full 8 GiB headroom.
PI_BASELINES: dict[str, EdgeBaseline] = {
    "Raspberry Pi 5": _baseline(
        "Raspberry Pi 5", 4, "BCM2712 quad Cortex-A76 @ 2.4 GHz", 8192,
        2000, 4, 15000,
        "16 k page-size kernel images exist; audit flags unusual page sizes",
        "PCIe HATs (Hailo-8, NVMe) raise the power envelope"),
    "Raspberry Pi 4 Model B": _baseline(
        "Raspberry Pi 4 Model B", 4, "BCM2711 quad Cortex-A72 @ 1.8 GHz",
        4096, 1000, 2, 7500,
        "USB-C PD supply required for stable 4-core inference",
        "thermal throttling common without a heatsink/fan"),
    "Raspberry Pi 3 Model B+": _baseline(
        "Raspberry Pi 3 Model B+", 4, "BCM2837B0 quad Cortex-A53 @ 1.4 GHz",
        1024, 250, 1, 5000,
        "32-bit userland historically common; require 64-bit OS for HugrGate",
        "no USB boot quirks tolerated: keep model store on ext4"),
    "Raspberry Pi Zero 2 W": _baseline(
        "Raspberry Pi Zero 2 W", 4, "RP3A0 quad Cortex-A53 @ 1.0 GHz",
        512, 100, 1, 2500,
        "low-RAM operating mode is mandatory, not optional",
        "single USB-OTG port: no high-draw peripherals during inference"),
}


def _parse_cpuinfo_kv(text: str, key: str) -> str | None:
    # Exact key match: /proc/cpuinfo carries both per-CPU "model name"
    # lines and the board summary "Model" line; startswith() would grab
    # the wrong one.
    for line in text.splitlines():
        head, sep, rest = line.partition(":")
        if sep and head.strip().lower() == key.lower():
            value = rest.strip()
            if value:
                return value
    return None


def detect_pi_board(cpuinfo_text: str | None = None,
                   model_text: str | None = None) -> PiBoard | None:
    """Identify a Raspberry Pi board, or return None when not a Pi.

    ``cpuinfo_text`` stands in for ``/proc/cpuinfo`` and ``model_text``
    for ``/sys/firmware/devicetree/base/model``; both default to the
    live host. Returns ``None`` for non-Pi hosts (never raises).
    """
    if cpuinfo_text is None:
        try:
            with open("/proc/cpuinfo", encoding="utf-8") as fh:
                cpuinfo_text = fh.read()
        except OSError:
            return None
    live = model_text is None
    if model_text is None:
        try:
            with open("/sys/firmware/devicetree/base/model",
                      encoding="utf-8") as fh:
                model_text = fh.read().strip("\x00").strip()
        except OSError:
            model_text = ""

    model_line = _parse_cpuinfo_kv(cpuinfo_text, "model")
    revision = (_parse_cpuinfo_kv(cpuinfo_text, "revision") or "").lower()
    model_name = model_text or model_line or ""
    if "raspberry pi" not in model_name.lower():
        return None

    if revision in _PI_REVISIONS:
        model, ram_mb = _PI_REVISIONS[revision]
    else:
        # Unknown revision: trust the model string, take the smallest
        # known baseline for that family as the conservative RAM figure.
        model = model_name.strip()
        ram_mb = 512
        for known, base in PI_BASELINES.items():
            if known.lower() in model.lower():
                ram_mb = base.ram_mb
                break
    return PiBoard(model=model, revision=revision, ram_mb=ram_mb,
                   detected_live=live)


def pi_baseline(board: PiBoard | str) -> EdgeBaseline:
    """Return the :class:`EdgeBaseline` for a board or model label.

    Raises ``ValueError`` naming the known models when the label is
    unknown — guessing a baseline for unlisted hardware would silently
    miscalibrate memory modes, cache tuning, and benchmarks.
    """
    label = board.model if isinstance(board, PiBoard) else board
    for known, baseline in PI_BASELINES.items():
        if known.lower() in label.lower():
            return baseline
    known_names = sorted(PI_BASELINES)
    raise ValueError(
        f"unknown Pi model {label!r}; known models: {known_names}")
