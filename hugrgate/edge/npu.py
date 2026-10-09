"""NPU capability abstraction and vendor adapter boundaries.

Slices 185-188.

:class:`NPUCapability` is a plain, comparable record of what an
accelerator can do (TOPS, precisions, power). :class:`NPUAdapter` is
the boundary every vendor backend implements: ``detect()`` returns a
capability or ``None`` when the hardware/driver is absent —
*adapters never raise for missing hardware*, they report absence.
Vendor SDKs are imported lazily inside ``detect()``/``load_model()``
so ``import hugrgate.edge.npu`` never requires HailoRT, TensorRT, or
OpenVINO to be installed.

No NPU hardware exists in this environment: every adapter ships with
an explicit mock twin (``Mock*Adapter``) used by tests, and real
detection paths are marked ``NEEDS_HARDWARE_VALIDATION``.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from hugrgate.errors import HugrGateError

__all__ = [
    "PRECISIONS",
    "HailoAdapter",
    "JetsonAdapter",
    "MockNPUAdapter",
    "NPUAdapter",
    "NPUCapability",
    "NPUError",
    "NPURegistry",
]

#: Precisions an adapter may advertise, ordered by bit-width.
PRECISIONS = ("int4", "int8", "fp16", "fp32")


class NPUError(HugrGateError):
    """An NPU operation failed (load/infer on a present device)."""


@dataclass(frozen=True)
class NPUCapability:
    """What an accelerator offers. All figures are vendor-declared."""

    vendor: str            # "hailo" | "nvidia" | "openvino" | ...
    device: str            # "Hailo-8" | "Orin Nano" | ...
    tops_int8: float       # vendor-declared INT8 TOPS
    precisions: tuple[str, ...]
    power_mw: float | None = None
    driver: str | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        if self.tops_int8 <= 0:
            raise NPUError("tops_int8 must be > 0")
        unknown = [p for p in self.precisions if p not in PRECISIONS]
        if unknown:
            raise NPUError(f"unknown precisions {unknown}")
        if self.power_mw is not None and self.power_mw <= 0:
            raise NPUError("power_mw must be > 0 when given")

    def supports(self, precision: str) -> bool:
        return precision in self.precisions

    def to_dict(self) -> dict[str, Any]:
        return {"vendor": self.vendor, "device": self.device,
                "tops_int8": self.tops_int8,
                "precisions": list(self.precisions),
                "power_mw": self.power_mw, "driver": self.driver,
                "notes": self.notes}


class NPUAdapter(ABC):
    """Boundary every NPU vendor adapter implements.

    Contract:
    - :meth:`detect` never raises for missing hardware/driver: it
      returns ``None``. Only genuine detection bugs raise.
    - :meth:`load_model` / :meth:`infer` raise :class:`NPUError` when
      called while unavailable.
    - SDK imports happen lazily inside methods, never at module top.
    """

    name: str = "npu"
    vendor: str = "generic"

    @abstractmethod
    def detect(self) -> NPUCapability | None:
        """Return the capability, or None when hardware/driver absent."""

    def is_available(self) -> bool:
        return self.detect() is not None

    @abstractmethod
    def load_model(self, model_path: str, **kwargs: Any) -> Any:
        """Load a compiled model; returns an opaque handle."""

    @abstractmethod
    def infer(self, handle: Any, inputs: Any) -> Any:
        """Run inference; returns raw outputs."""

    def capabilities(self) -> dict[str, Any]:
        cap = self.detect()
        return {"name": self.name, "vendor": self.vendor,
                "available": cap is not None,
                "capability": cap.to_dict() if cap else None}

    def require_available(self) -> NPUCapability:
        cap = self.detect()
        if cap is None:
            raise NPUError(
                f"NPU adapter {self.name!r} has no device/driver; "
                f"NEEDS_HARDWARE_VALIDATION on target hardware")
        return cap


@dataclass
class _ModelSlot:
    handle: Any
    precision: str


class MockNPUAdapter(NPUAdapter):
    """Deterministic in-memory twin of an NPU adapter for tests.

    ``present=True`` simulates installed hardware; ``infer`` echoes a
    canned transform of the inputs so routing/selection logic is
    exercisable without silicon.
    """

    name = "mock-npu"
    vendor = "mock"

    def __init__(self, capability: NPUCapability | None = None,
                 present: bool = True):
        self._capability = capability or NPUCapability(
            vendor="mock", device="MockNPU-1", tops_int8=4.0,
            precisions=("int8", "fp16"))
        self._present = present
        self._lock = threading.RLock()
        self._models: dict[str, _ModelSlot] = {}
        self.infer_calls = 0

    def detect(self) -> NPUCapability | None:
        return self._capability if self._present else None

    def load_model(self, model_path: str, **kwargs: Any) -> str:
        cap = self.require_available()
        precision = str(kwargs.get("precision", "int8"))
        if not cap.supports(precision):
            raise NPUError(
                f"mock device lacks precision {precision!r}")
        handle = f"mock://{model_path}#{precision}"
        with self._lock:
            self._models[handle] = _ModelSlot(handle, precision)
        return handle

    def infer(self, handle: str, inputs: Any) -> dict[str, Any]:
        with self._lock:
            if handle not in self._models:
                raise NPUError(f"unknown model handle {handle!r}")
            self.infer_calls += 1
            slot = self._models[handle]
        return {"handle": handle, "precision": slot.precision,
                "echo": inputs, "mock": True}


class NPURegistry:
    """Named adapters with detection and best-fit selection."""

    def __init__(self):
        self._lock = threading.RLock()
        self._adapters: dict[str, NPUAdapter] = {}

    def register(self, adapter: NPUAdapter, *, replace: bool = False) -> None:
        if not isinstance(adapter, NPUAdapter):
            raise NPUError(
                f"can only register NPUAdapter, got "
                f"{type(adapter).__name__}")
        with self._lock:
            if adapter.name in self._adapters and not replace:
                raise NPUError(
                    f"NPU adapter {adapter.name!r} already registered")
            self._adapters[adapter.name] = adapter

    def get(self, name: str) -> NPUAdapter:
        with self._lock:
            try:
                return self._adapters[name]
            except KeyError:
                raise NPUError(
                    f"unknown NPU adapter {name!r}; known: "
                    f"{sorted(self._adapters)}") from None

    def detect_all(self) -> dict[str, NPUCapability]:
        """Detect every registered adapter; absent devices are skipped."""
        found: dict[str, NPUCapability] = {}
        with self._lock:
            adapters = list(self._adapters.values())
        for adapter in adapters:
            cap = adapter.detect()
            if cap is not None:
                found[adapter.name] = cap
        return found

    def best_for(self, precision: str = "int8",
                 min_tops: float = 0.0) -> NPUAdapter | None:
        """Highest-TOPS available adapter supporting ``precision``."""
        best: NPUAdapter | None = None
        best_tops = min_tops
        for name, cap in self.detect_all().items():
            if cap.supports(precision) and cap.tops_int8 > best_tops:
                best, best_tops = self.get(name), cap.tops_int8
        return best

    def __len__(self) -> int:
        with self._lock:
            return len(self._adapters)


# --- vendor adapters (slices 186-188) -------------------------------------------

#: Hailo PCI vendor ID (Hailo-8 / Hailo-8L on PCIe / M.2 HATs).
_HAILO_PCI_VENDOR_ID = "0x1e60"


class HailoAdapter(NPUAdapter):
    """Hailo-8/8L adapter boundary (slice 186).

    Detection is two-stage: the HailoRT SDK must import *and* a Hailo
    PCI device must be enumerable. Either missing → ``None`` (absent,
    not broken). ``sdk`` / ``pci_vendor_ids`` are injectable so tests
    exercise every branch without hardware or the SDK installed.
    """

    name = "hailo"
    vendor = "hailo"

    def __init__(self, sdk: Any | None = None,
                 pci_vendor_ids: list[str] | None = None):
        # sdk=None -> lazy real import on detect(); a passed object is
        # used verbatim (tests inject a fake module).
        self._sdk = sdk
        self._pci_vendor_ids = pci_vendor_ids
        self._lock = threading.RLock()
        self._models: dict[str, str] = {}

    def _load_sdk(self) -> Any | None:
        if self._sdk is not None:
            return self._sdk
        try:
            import hailo_platform
            return hailo_platform
        except ImportError:
            return None

    def _pci_ids(self) -> list[str]:
        if self._pci_vendor_ids is not None:
            return self._pci_vendor_ids
        ids: list[str] = []
        try:
            import glob as _glob
            for path in _glob.glob("/sys/bus/pci/devices/*/vendor"):
                try:
                    with open(path, encoding="utf-8") as fh:
                        ids.append(fh.read().strip().lower())
                except OSError:
                    continue
        except OSError:
            pass
        return ids

    def detect(self) -> NPUCapability | None:
        sdk = self._load_sdk()
        if sdk is None:
            return None
        pci_ids = [v.lower() for v in self._pci_ids()]
        if _HAILO_PCI_VENDOR_ID not in pci_ids:
            return None
        driver = getattr(sdk, "__version__", None)
        # Hailo-8L (13 TOPS, on Pi 5 AI HAT) vs Hailo-8 (26 TOPS):
        # the SDK device query distinguishes them; without a queryable
        # device we report the conservative 8L figure.
        tops = 13.0
        device = "Hailo-8L"
        scan = getattr(sdk, "scan_devices", None)
        if callable(scan):
            try:
                for dev in scan() or []:
                    name = str(getattr(dev, "device_name", "")).lower()
                    if name == "hailo-8":
                        device, tops = "Hailo-8", 26.0
                        break
                    # "hailo-8l" keeps the conservative default
            except Exception:  # noqa: BLE001 - detection must not raise
                pass
        return NPUCapability(
            vendor="hailo", device=device, tops_int8=tops,
            precisions=("int8",), power_mw=2500.0,
            driver=str(driver) if driver else None,
            notes="NEEDS_HARDWARE_VALIDATION: TOPS/power are vendor "
                  "figures; verify on the HAT")

    def load_model(self, model_path: str, **kwargs: Any) -> str:
        self.require_available()
        if not model_path.endswith(".hef"):
            raise NPUError(
                f"Hailo models must be .hef (Hailo Executable Format), "
                f"got {model_path!r}")
        handle = f"hailo://{model_path}"
        with self._lock:
            self._models[handle] = model_path
        return handle

    def infer(self, handle: str, inputs: Any) -> Any:
        self.require_available()
        with self._lock:
            if handle not in self._models:
                raise NPUError(f"unknown Hailo model handle {handle!r}")
        raise NPUError(
            "Hailo infer() needs the HailoRT runtime on-device; "
            "NEEDS_HARDWARE_VALIDATION")


#: Jetson model substrings -> (device label, INT8 TOPS, power mW).
#: Vendor-declared figures; NEEDS_HARDWARE_VALIDATION on-device.
_JETSON_SPECS: dict[str, tuple[str, float, float]] = {
    "orin nano": ("Jetson Orin Nano", 40.0, 15000.0),
    "orin nx": ("Jetson Orin NX", 100.0, 25000.0),
    "xavier nx": ("Jetson Xavier NX", 21.0, 20000.0),
    "xavier agx": ("Jetson AGX Xavier", 32.0, 30000.0),
    "jetson nano": ("Jetson Nano", 0.5, 10000.0),
    "tx2": ("Jetson TX2", 1.3, 15000.0),
}


class JetsonAdapter(NPUAdapter):
    """NVIDIA Jetson adapter boundary (slice 187).

    Detection is three-stage: the device-tree model must name an
    NVIDIA Jetson board, ``/etc/nv_tegra_release`` should exist, and
    TensorRT should import. Missing board identity → ``None``;
    missing TensorRT degrades the capability (CPU-only Jetson is
    still a Jetson, but not an NPU target) — reported via the
    ``notes`` field rather than silent absence.
    """

    name = "jetson"
    vendor = "nvidia"

    def __init__(self, trt: Any | None = None,
                 model_text: str | None = None,
                 tegra_release_present: bool | None = None):
        self._trt = trt
        self._model_text = model_text
        self._tegra_release_present = tegra_release_present
        self._lock = threading.RLock()
        self._models: dict[str, str] = {}

    def _read_model(self) -> str:
        if self._model_text is not None:
            return self._model_text
        try:
            with open("/sys/firmware/devicetree/base/model",
                      encoding="utf-8") as fh:
                return fh.read().strip("\x00").strip()
        except OSError:
            return ""

    def _has_tegra_release(self) -> bool:
        if self._tegra_release_present is not None:
            return self._tegra_release_present
        import os as _os
        return _os.path.exists("/etc/nv_tegra_release")

    def _load_trt(self) -> Any | None:
        if self._trt is not None:
            return self._trt
        try:
            import tensorrt as trt
            return trt
        except ImportError:
            return None

    def _spec(self, model: str) -> tuple[str, float, float] | None:
        lowered = model.lower()
        for key, spec in _JETSON_SPECS.items():
            if key in lowered:
                return spec
        return None

    def detect(self) -> NPUCapability | None:
        model = self._read_model()
        if "nvidia" not in model.lower() or "jetson" not in model.lower():
            return None
        spec = self._spec(model)
        device = spec[0] if spec else model.strip() or "Jetson (unknown)"
        tops = spec[1] if spec else 1.0
        power = spec[2] if spec else None
        trt = self._load_trt()
        notes = ""
        if trt is None:
            notes = ("TensorRT not importable: NPU path unavailable, "
                     "CPU fallback only; NEEDS_HARDWARE_VALIDATION")
        elif not self._has_tegra_release():
            notes = ("nv_tegra_release missing: unusual for a Jetson; "
                     "NEEDS_HARDWARE_VALIDATION")
        return NPUCapability(
            vendor="nvidia", device=device, tops_int8=tops,
            precisions=("int8", "fp16", "fp32"),
            power_mw=power,
            driver=str(getattr(trt, "__version__", "")) or None,
            notes=notes or "NEEDS_HARDWARE_VALIDATION: vendor figures")

    def load_model(self, model_path: str, **kwargs: Any) -> str:
        self.require_available()  # raises when no Jetson is present
        if not model_path.endswith((".engine", ".plan")):
            raise NPUError(
                f"Jetson TensorRT models must be .engine/.plan, got "
                f"{model_path!r}")
        if self._load_trt() is None:
            raise NPUError(
                "TensorRT not importable; cannot load Jetson engine "
                "NEEDS_HARDWARE_VALIDATION")
        handle = f"jetson://{model_path}"
        with self._lock:
            self._models[handle] = model_path
        return handle

    def infer(self, handle: str, inputs: Any) -> Any:
        self.require_available()
        with self._lock:
            if handle not in self._models:
                raise NPUError(f"unknown Jetson model handle {handle!r}")
        raise NPUError(
            "Jetson infer() needs TensorRT on-device; "
            "NEEDS_HARDWARE_VALIDATION")
