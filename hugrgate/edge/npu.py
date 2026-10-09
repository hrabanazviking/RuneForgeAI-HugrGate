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
