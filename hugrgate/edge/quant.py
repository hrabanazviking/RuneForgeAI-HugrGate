"""Quantized-model profiles and simulated quantization paths. Slices 182-184.

This module models the *planning* side of edge quantization: which
numeric formats exist, what they cost in bytes and latency, and which
one fits a device budget. The *execution* side lives here too —
:func:`quantize_int8` / :func:`dequantize_int8` implement real affine
(per-tensor) INT8 quantization over numpy arrays with deterministic
round-trip error bounds, and :class:`Int4Adapter` implements real
groupwise-symmetric INT4 nibble packing. Slices 183 and 184 harden
those two paths; this slice (182) establishes the profile registry.

All quality/latency factors are labeled *planning estimates*, not
measurements — per-model calibration on target silicon is marked
``NEEDS_HARDWARE_VALIDATION`` in the slice docs.
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Any

from hugrgate.errors import HugrGateError

try:
    import numpy as np
except ImportError:  # optional dependency — pure-python fallback below
    np = None  # type: ignore[assignment]

__all__ = [
    "QUANT_PROFILES",
    "Int4Adapter",
    "QuantError",
    "QuantFormat",
    "QuantProfile",
    "QuantProfileRegistry",
    "QuantizedTensor",
    "dequantize_int8",
    "estimate",
    "int8_matvec",
    "int8_roundtrip_error",
    "quantize_int8",
    "select_profile",
]


class QuantError(HugrGateError):
    """A quantization profile or operation was invalid."""


class QuantFormat(str, Enum):
    """Numeric formats the edge runtime can plan for."""

    FP32 = "fp32"
    FP16 = "fp16"
    INT8 = "int8"
    INT4 = "int4"


@dataclass(frozen=True)
class QuantProfile:
    """One quantization operating point.

    ``size_factor`` / ``latency_factor`` are relative to fp32 and are
    *planning estimates* (see module docstring). ``quality_delta`` is
    the expected top-1 accuracy change in percentage points — negative
    means degradation — and is informational only.
    """

    name: str
    format: QuantFormat
    size_factor: float
    latency_factor: float
    quality_delta_pp: float = 0.0
    min_ram_mb: int = 0
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise QuantError("profile name must be non-empty")
        if not 0 < self.size_factor <= 1.5:
            raise QuantError(
                f"size_factor {self.size_factor} outside (0, 1.5]")
        if not 0 < self.latency_factor <= 2.0:
            raise QuantError(
                f"latency_factor {self.latency_factor} outside (0, 2.0]")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "format": self.format.value,
            "size_factor": self.size_factor,
            "latency_factor": self.latency_factor,
            "quality_delta_pp": self.quality_delta_pp,
            "min_ram_mb": self.min_ram_mb,
            "notes": self.notes,
            "planning_estimate": True,
        }


def _profile(name: str, fmt: QuantFormat, size: float, latency: float,
             quality: float, ram: int, notes: str) -> QuantProfile:
    return QuantProfile(name=name, format=fmt, size_factor=size,
                        latency_factor=latency, quality_delta_pp=quality,
                        min_ram_mb=ram, notes=notes)


#: Canonical profiles. Factors are conservative planning estimates for
#: transformer-ish decoders on ARM64; measure per model on-device.
QUANT_PROFILES: dict[str, QuantProfile] = {
    "fp32": _profile("fp32", QuantFormat.FP32, 1.0, 1.0, 0.0, 2048,
                     "reference precision; rarely viable on small boards"),
    "fp16": _profile("fp16", QuantFormat.FP16, 0.5, 0.7, -0.2, 1024,
                     "NEON fp16 is fast on A76/A72; needs fp16-capable kernels"),
    "int8": _profile("int8", QuantFormat.INT8, 0.25, 0.45, -0.8, 512,
                     "affine per-tensor quantization; see quantize_int8"),
    "int8-mixed": _profile("int8-mixed", QuantFormat.INT8, 0.32, 0.55,
                           -0.4, 768,
                           "int8 weights, fp16 activations; gentler quality hit"),
    "int4": _profile("int4", QuantFormat.INT4, 0.125, 0.35, -2.5, 256,
                     "groupwise symmetric; see Int4Adapter"),
}


class QuantProfileRegistry:
    """Named-profile store; canonical profiles are pre-registered."""

    def __init__(self):
        self._lock = threading.RLock()
        self._profiles: dict[str, QuantProfile] = dict(QUANT_PROFILES)

    def register(self, profile: QuantProfile,
                 *, replace: bool = False) -> None:
        if not isinstance(profile, QuantProfile):
            raise QuantError(
                f"can only register QuantProfile, got "
                f"{type(profile).__name__}")
        with self._lock:
            if profile.name in self._profiles and not replace:
                raise QuantError(
                    f"profile {profile.name!r} already registered; "
                    f"pass replace=True")
            self._profiles[profile.name] = profile

    def get(self, name: str) -> QuantProfile:
        with self._lock:
            try:
                return self._profiles[name]
            except KeyError:
                raise QuantError(
                    f"unknown quantization profile {name!r}; known: "
                    f"{sorted(self._profiles)}") from None

    def list(self) -> list[str]:
        with self._lock:
            return sorted(self._profiles)

    def __len__(self) -> int:
        with self._lock:
            return len(self._profiles)


def estimate(profile: QuantProfile, base_size_mb: float,
             base_latency_ms: float) -> dict[str, float]:
    """Scale a fp32 reference measurement by a profile's factors."""
    if base_size_mb <= 0 or base_latency_ms <= 0:
        raise QuantError("base size and latency must be > 0")
    return {
        "size_mb": base_size_mb * profile.size_factor,
        "latency_ms": base_latency_ms * profile.latency_factor,
    }


def select_profile(registry: QuantProfileRegistry, ram_budget_mb: float,
                   latency_budget_ms: float, base_size_mb: float,
                   base_latency_ms: float,
                   preference: str = "smallest") -> QuantProfile:
    """Pick the most aggressive profile fitting both budgets.

    ``preference="smallest"`` minimizes size; ``"fastest"`` minimizes
    latency. Raises :class:`QuantError` when even fp32 cannot fit —
    the caller must shed load, not silently degrade.
    """
    if preference not in ("smallest", "fastest"):
        raise QuantError(f"unknown preference {preference!r}")
    viable: list[QuantProfile] = []
    for name in registry.list():
        profile = registry.get(name)
        est = estimate(profile, base_size_mb, base_latency_ms)
        if (est["size_mb"] <= ram_budget_mb and profile.min_ram_mb
                <= ram_budget_mb and est["latency_ms"] <= latency_budget_ms):
            viable.append(profile)
    if not viable:
        raise QuantError(
            f"no quantization profile fits ram={ram_budget_mb} MB, "
            f"latency={latency_budget_ms} ms "
            f"(fp32 needs {base_size_mb} MB / {base_latency_ms} ms)")
    if preference == "smallest":
        return min(viable, key=lambda p: estimate(
            p, base_size_mb, base_latency_ms)["size_mb"])
    return min(viable, key=lambda p: estimate(
        p, base_size_mb, base_latency_ms)["latency_ms"])


def _require_numpy() -> None:
    if np is None:  # pragma: no cover - numpy is installed in this env
        raise QuantError(
            "quantized execution paths require numpy; install the "
            "'bench' extra: pip install 'hugrgate[bench]'")


def quantize_int8(weights: np.ndarray, *, symmetric: bool = False,
                  axis: int | None = None
                  ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Affine INT8 quantization — the edge INT8 inference path.

    Per-tensor by default (``axis=None``); ``axis=0`` (or 1) quantizes
    per output-channel, which cuts error when channels live on wildly
    different scales. ``symmetric=True`` pins ``zero_point`` to 0
    (better for weight tensors centered near zero).

    Returns ``(q, scales, zero_points)`` with ``q`` int8 and
    ``weights ≈ scales * (q - zero_points)`` broadcast along ``axis``.
    Deterministic: identical input always yields identical output.
    Rejects NaN/Inf — silently quantizing poisoned weights would corrupt
    every downstream decision.
    """
    _require_numpy()
    w = np.asarray(weights, dtype=np.float64)
    if w.size == 0:
        raise QuantError("cannot quantize an empty tensor")
    if not np.all(np.isfinite(w)):
        raise QuantError("weights contain NaN or Inf; refusing to quantize")

    def _params(block: np.ndarray) -> tuple[float, int]:
        wmin, wmax = float(block.min()), float(block.max())
        if wmax == wmin:
            return 1.0, 0
        if symmetric:
            amax = max(abs(wmin), abs(wmax))
            return amax / 127.0, 0
        scale = (wmax - wmin) / 255.0
        zp = max(-128, min(127, round(-wmin / scale) - 128))
        return scale, zp

    if axis is None:
        scale, zp = _params(w)
        scales = np.array([scale])
        zps = np.array([zp])
        q = np.clip(np.round(w / scale + zp), -128, 127).astype(np.int8)
    else:
        ax = axis % w.ndim
        moved = np.moveaxis(w, ax, 0)
        scales_list: list[float] = []
        zps_list: list[int] = []
        q_blocks = []
        for ch in range(moved.shape[0]):
            scale, zp = _params(moved[ch])
            scales_list.append(scale)
            zps_list.append(zp)
            q_blocks.append(np.clip(np.round(moved[ch] / scale + zp),
                                    -128, 127).astype(np.int8))
        scales = np.array(scales_list)
        zps = np.array(zps_list)
        q = np.moveaxis(np.stack(q_blocks), 0, ax)
    return q, scales, zps


def dequantize_int8(q: np.ndarray, scales: np.ndarray,
                    zero_points: np.ndarray, axis: int | None = None
                    ) -> np.ndarray:
    """Invert :func:`quantize_int8` (per-tensor or per-channel)."""
    _require_numpy()
    qf = np.asarray(q, dtype=np.float64)
    if axis is None:
        return (qf - float(zero_points.ravel()[0])) * float(scales.ravel()[0])
    ax = axis % qf.ndim
    shape = [1] * qf.ndim
    shape[ax] = -1
    s = np.asarray(scales, dtype=np.float64).reshape(shape)
    z = np.asarray(zero_points, dtype=np.float64).reshape(shape)
    return (qf - z) * s


@dataclass(frozen=True)
class QuantizedTensor:
    """A serializable INT8 tensor: codes + parameters + provenance.

    This is what the edge model store (slice 189/191) persists: the
    int8 codes plus everything needed to run or audit the quantized
    op without the original float weights.
    """

    codes: np.ndarray          # int8
    scales: np.ndarray         # float64, one per channel (or one)
    zero_points: np.ndarray    # int64, one per channel (or one)
    shape: tuple[int, ...]
    symmetric: bool
    axis: int | None

    def __post_init__(self) -> None:
        if np is not None and self.codes.dtype != np.int8:
            raise QuantError("codes must be int8")

    @classmethod
    def from_weights(cls, weights: np.ndarray, *,
                     symmetric: bool = False,
                     axis: int | None = None) -> QuantizedTensor:
        q, scales, zps = quantize_int8(weights, symmetric=symmetric,
                                       axis=axis)
        return cls(codes=q, scales=scales,
                   zero_points=zps.astype(np.int64),
                   shape=tuple(np.shape(weights)),
                   symmetric=symmetric, axis=axis)

    def dequantize(self) -> np.ndarray:
        return dequantize_int8(self.codes, self.scales,
                               self.zero_points, axis=self.axis)

    def to_bytes(self) -> bytes:
        """Compact little-endian serialization: header + codes + params."""
        import struct as _struct
        fmt = "<8sB?bq"
        header = _struct.pack(
            fmt, b"HGQT0001", len(self.shape),
            self.symmetric, -1 if self.axis is None else self.axis,
            len(self.scales))
        dims = _struct.pack(f"<{len(self.shape)}q", *self.shape)
        return (header + dims + self.codes.tobytes()
                + self.scales.astype("<f8").tobytes()
                + self.zero_points.astype("<i8").tobytes())

    @classmethod
    def from_bytes(cls, blob: bytes) -> QuantizedTensor:
        import struct as _struct
        fmt = "<8sB?bq"
        hsize = _struct.calcsize(fmt)
        if len(blob) < hsize:
            raise QuantError("quantized tensor blob too short")
        magic, rank, symmetric, axis_raw, nscales = _struct.unpack(
            fmt, blob[:hsize])
        if magic != b"HGQT0001":
            raise QuantError(f"bad magic {magic!r}; not a HugrGate QT blob")
        off = hsize
        dims = _struct.unpack(f"<{rank}q", blob[off:off + 8 * rank])
        off += 8 * rank
        shape = tuple(int(d) for d in dims)
        n = 1
        for d in shape:
            n *= d
        codes = np.frombuffer(blob[off:off + n], dtype=np.int8).copy()
        off += n
        if len(blob) < off + 16 * nscales:
            raise QuantError("quantized tensor blob truncated")
        scales = np.frombuffer(
            blob[off:off + 8 * nscales], dtype="<f8").astype(float)
        off += 8 * nscales
        zps = np.frombuffer(
            blob[off:off + 8 * nscales], dtype="<i8").astype(np.int64)
        if codes.size != n or scales.size != nscales:
            raise QuantError("quantized tensor blob truncated")
        axis = None if axis_raw < 0 else int(axis_raw)
        return cls(codes=codes.reshape(shape), scales=scales,
                   zero_points=zps, shape=shape,
                   symmetric=bool(symmetric), axis=axis)

    def nbytes(self) -> int:
        return len(self.to_bytes())


def int8_matvec(weight_qt: QuantizedTensor, x: np.ndarray,
                bias: np.ndarray | None = None) -> np.ndarray:
    """Simulated quantized inference: ``y = dequant(W) @ x + b``.

    This is the honest edge INT8 path: the multiply happens against
    dequantized int8 codes (what a real kernel computes, up to its own
    accumulation rounding), never against the original float weights.
    """
    _require_numpy()
    w = weight_qt.dequantize()
    xv = np.asarray(x, dtype=np.float64)
    if w.ndim != 2 or xv.ndim != 1 or w.shape[1] != xv.shape[0]:
        raise QuantError(
            f"matvec shape mismatch: W{w.shape} @ x{xv.shape}")
    y = w @ xv
    if bias is not None:
        bv = np.asarray(bias, dtype=np.float64)
        if bv.shape != (w.shape[0],):
            raise QuantError(f"bias shape {bv.shape} != {(w.shape[0],)}")
        y = y + bv
    return y


def int8_roundtrip_error(weights: np.ndarray) -> float:
    """Max absolute error of an int8 round-trip (deterministic bound)."""
    q, scale, zp = quantize_int8(weights)
    rec = dequantize_int8(q, scale, zp)
    _require_numpy()
    return float(np.max(np.abs(np.asarray(weights, dtype=np.float64)
                               - rec)))


class Int4Adapter:
    """Groupwise symmetric INT4 packing (slice 184's execution path).

    Weights are split into groups of ``group_size``; each group gets
    its own float scale, and values are packed two nibbles per byte
    (low nibble first). Deterministic and exactly invertible up to the
    4-bit rounding error.
    """

    def __init__(self, group_size: int = 32):
        if group_size <= 0 or group_size % 2:
            raise QuantError(
                "group_size must be a positive even number")
        self.group_size = group_size

    def pack(self, weights: np.ndarray) -> dict[str, Any]:
        """Pack a 1-D weight vector into nibbles + per-group scales."""
        _require_numpy()
        w = np.asarray(weights, dtype=np.float64).ravel()
        pad = (-len(w)) % self.group_size
        if pad:
            w = np.concatenate([w, np.zeros(pad)])
        groups = w.reshape(-1, self.group_size)
        amax = np.maximum(np.abs(groups).max(axis=1),
                          np.finfo(float).tiny)
        scales = (amax / 7.0).astype(np.float64)
        q = np.clip(np.round(groups / scales[:, None]), -8, 7
                    ).astype(np.int8) + 8  # shift to 0..15
        flat = q.ravel().astype(np.uint8)
        packed = (flat[0::2] | (flat[1::2] << 4)).astype(np.uint8)
        return {"packed": packed, "scales": scales,
                "length": len(weights), "group_size": self.group_size}

    def unpack(self, blob: dict[str, Any]) -> np.ndarray:
        """Unpack a :meth:`pack` blob back to float64 weights."""
        _require_numpy()
        packed = np.asarray(blob["packed"], dtype=np.uint8)
        scales = np.asarray(blob["scales"], dtype=np.float64)
        group_size = int(blob["group_size"])
        if group_size != self.group_size:
            raise QuantError(
                f"blob group_size {group_size} != adapter {self.group_size}")
        flat = np.empty(packed.size * 2, dtype=np.int8)
        flat[0::2] = (packed & 0x0F).astype(np.int8)
        flat[1::2] = ((packed >> 4) & 0x0F).astype(np.int8)
        signed = flat.astype(np.float64) - 8.0  # back to -8..7
        groups = signed.reshape(-1, group_size)
        w = (groups * scales[:, None]).ravel()
        return w[:int(blob["length"])]

    def roundtrip_error(self, weights: np.ndarray) -> float:
        """Max absolute error of a pack/unpack round-trip."""
        rec = self.unpack(self.pack(weights))
        _require_numpy()
        return float(np.max(np.abs(np.asarray(weights, dtype=np.float64)
                                   - rec)))

    def packed_bytes(self, length: int) -> int:
        """Exact packed size in bytes for a vector of ``length``."""
        groups = math.ceil(length / self.group_size)
        return groups * (self.group_size // 2)
