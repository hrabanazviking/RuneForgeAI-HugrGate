"""Slice 182 — quantized-model profiles tests."""

from __future__ import annotations

import pytest

from hugrgate.edge.quant import (
    QUANT_PROFILES,
    QuantError,
    QuantFormat,
    QuantProfile,
    QuantProfileRegistry,
    estimate,
    select_profile,
)

# --- registry: success ------------------------------------------------------------

def test_canonical_profiles_pre_registered():
    reg = QuantProfileRegistry()
    assert set(reg.list()) == set(QUANT_PROFILES)
    assert len(reg) == 5
    int8 = reg.get("int8")
    assert int8.format is QuantFormat.INT8
    assert int8.to_dict()["planning_estimate"] is True


def test_register_custom_profile():
    reg = QuantProfileRegistry()
    reg.register(QuantProfile(name="int8-awq", format=QuantFormat.INT8,
                              size_factor=0.28, latency_factor=0.5))
    assert "int8-awq" in reg.list()


def test_register_replace():
    reg = QuantProfileRegistry()
    with pytest.raises(QuantError, match="already registered"):
        reg.register(QuantProfile(name="int8", format=QuantFormat.INT8,
                                  size_factor=0.2, latency_factor=0.4))
    reg.register(QuantProfile(name="int8", format=QuantFormat.INT8,
                              size_factor=0.2, latency_factor=0.4),
                 replace=True)
    assert reg.get("int8").size_factor == 0.2


# --- registry: failure --------------------------------------------------------------

def test_unknown_profile_raises_with_known_list():
    reg = QuantProfileRegistry()
    with pytest.raises(QuantError, match="known:"):
        reg.get("int2")


def test_register_non_profile_rejected():
    reg = QuantProfileRegistry()
    with pytest.raises(QuantError, match="can only register"):
        reg.register("int8")  # type: ignore[arg-type]


@pytest.mark.parametrize("kwargs", [
    {"name": "", "format": QuantFormat.INT8,
     "size_factor": 0.25, "latency_factor": 0.5},
    {"name": "x", "format": QuantFormat.INT8,
     "size_factor": 0.0, "latency_factor": 0.5},
    {"name": "x", "format": QuantFormat.INT8,
     "size_factor": 0.25, "latency_factor": 0.0},
    {"name": "x", "format": QuantFormat.INT8,
     "size_factor": 2.0, "latency_factor": 0.5},
])
def test_invalid_profile_rejected(kwargs):
    with pytest.raises(QuantError):
        QuantProfile(**kwargs)


# --- estimate / select --------------------------------------------------------------

def test_estimate_scales_reference():
    est = estimate(QUANT_PROFILES["int8"], 4000.0, 200.0)
    assert est == {"size_mb": 1000.0, "latency_ms": 90.0}


def test_estimate_rejects_non_positive_base():
    with pytest.raises(QuantError):
        estimate(QUANT_PROFILES["int8"], 0.0, 200.0)


def test_select_profile_picks_smallest_fitting():
    reg = QuantProfileRegistry()
    # 4000 MB fp32 model, 200 ms fp32 latency; budget fits int8/int4
    chosen = select_profile(reg, ram_budget_mb=600.0,
                            latency_budget_ms=100.0,
                            base_size_mb=4000.0, base_latency_ms=200.0)
    assert chosen.name == "int4"  # smallest fitting


def test_select_profile_fastest_preference():
    reg = QuantProfileRegistry()
    chosen = select_profile(reg, ram_budget_mb=600.0,
                            latency_budget_ms=100.0,
                            base_size_mb=4000.0, base_latency_ms=200.0,
                            preference="fastest")
    assert chosen.name == "int4"  # also the fastest here


def test_select_profile_nothing_fits_raises():
    reg = QuantProfileRegistry()
    with pytest.raises(QuantError, match="no quantization profile fits"):
        select_profile(reg, ram_budget_mb=10.0, latency_budget_ms=1.0,
                       base_size_mb=4000.0, base_latency_ms=200.0)


def test_select_profile_unknown_preference():
    reg = QuantProfileRegistry()
    with pytest.raises(QuantError, match="unknown preference"):
        select_profile(reg, 600.0, 100.0, 4000.0, 200.0,
                       preference="prettiest")


def test_select_profile_respects_min_ram():
    reg = QuantProfileRegistry()
    # A profile whose byte size fits but whose min_ram_mb does not must
    # be skipped: min_ram models runtime overhead beyond the weights.
    reg.register(QuantProfile(name="int4-tiny", format=QuantFormat.INT4,
                              size_factor=0.01, latency_factor=0.3,
                              min_ram_mb=4096))
    with pytest.raises(QuantError, match="no quantization profile fits"):
        select_profile(reg, ram_budget_mb=300.0,
                       latency_budget_ms=1000.0,
                       base_size_mb=4000.0, base_latency_ms=200.0)
    # ...while a generous budget selects it, proving the profile is
    # otherwise viable and min_ram_mb was the gate.
    chosen = select_profile(reg, ram_budget_mb=5000.0,
                            latency_budget_ms=1000.0,
                            base_size_mb=4000.0, base_latency_ms=200.0)
    assert chosen.name == "int4-tiny"


# --- slice 183: INT8 inference path -------------------------------------------

import numpy as np

from hugrgate.edge.quant import (
    QuantizedTensor,
    dequantize_int8,
    int8_matvec,
    int8_roundtrip_error,
    quantize_int8,
)


def _rng():
    return np.random.default_rng(183)


def test_per_tensor_roundtrip_bounded():
    w = _rng().normal(0, 1, size=(64, 32))
    err = int8_roundtrip_error(w)
    # affine 8-bit: worst case half a bin; bin <= range/255
    assert err <= (w.max() - w.min()) / 255.0 + 1e-12


def test_per_channel_beats_per_tensor_on_skewed_channels():
    rng = _rng()
    w = np.vstack([rng.normal(0, 0.01, size=(1, 32)),
                   rng.normal(0, 100.0, size=(1, 32))])
    q_t, s_t, z_t = quantize_int8(w)
    q_c, s_c, z_c = quantize_int8(w, axis=0)
    small_t = float(np.max(np.abs(
        w[0] - dequantize_int8(q_t, s_t, z_t)[0])))
    small_c = float(np.max(np.abs(
        w[0] - dequantize_int8(q_c, s_c, z_c, axis=0)[0])))
    # the tiny channel is no longer drowned by the huge channel's scale
    assert small_c < small_t / 100
    # and per-channel never makes the worst case worse
    err_t = float(np.max(np.abs(w - dequantize_int8(q_t, s_t, z_t))))
    err_c = float(np.max(np.abs(
        w - dequantize_int8(q_c, s_c, z_c, axis=0))))
    assert err_c <= err_t


def test_symmetric_mode_zero_point_zero():
    w = _rng().normal(0, 1, size=256)
    q, scales, zps = quantize_int8(w, symmetric=True)
    assert zps.tolist() == [0]
    rec = dequantize_int8(q, scales, zps)
    assert float(np.max(np.abs(w - rec))) <= w.max() / 127.0 + 1e-9


def test_quantize_rejects_nan_inf_and_empty():
    with pytest.raises(QuantError, match="NaN or Inf"):
        quantize_int8(np.array([1.0, float("nan")]))
    with pytest.raises(QuantError, match="NaN or Inf"):
        quantize_int8(np.array([1.0, float("inf")]))
    with pytest.raises(QuantError, match="empty"):
        quantize_int8(np.array([]))


def test_quantize_deterministic():
    w = _rng().normal(0, 1, size=(16, 16))
    a = quantize_int8(w, axis=0)
    b = quantize_int8(w, axis=0)
    for x, y in zip(a, b, strict=True):
        np.testing.assert_array_equal(np.asarray(x), np.asarray(y))


def test_constant_tensor_degenerate_scale():
    q, scales, zps = quantize_int8(np.full((4, 4), 0.0))
    assert scales.tolist() == [1.0]
    assert zps.tolist() == [0]
    np.testing.assert_array_equal(np.asarray(q),
                                  np.zeros((4, 4), dtype=np.int8))
    # a constant tensor quantizes losslessly to its rounded value
    q2, _, _ = quantize_int8(np.full((4, 4), 2.5))
    np.testing.assert_array_equal(
        np.asarray(dequantize_int8(q2, np.array([1.0]), np.array([0]))),
        np.full((4, 4), 2.0))  # round-half-even of 2.5


def test_quantized_tensor_serialization_roundtrip():
    w = _rng().normal(0, 1, size=(32, 16))
    for axis in (None, 0, 1):
        qt = QuantizedTensor.from_weights(w, axis=axis)
        blob = qt.to_bytes()
        qt2 = QuantizedTensor.from_bytes(blob)
        assert qt2.shape == qt.shape
        assert qt2.symmetric == qt.symmetric
        assert qt2.axis == qt.axis
        np.testing.assert_array_equal(np.asarray(qt2.codes),
                                      np.asarray(qt.codes))
        np.testing.assert_allclose(np.asarray(qt2.scales),
                                   np.asarray(qt.scales))
        assert qt2.nbytes() == len(blob)
        # 4x smaller than fp32 (plus a small header)
        assert len(blob) < w.nbytes


def test_quantized_tensor_rejects_bad_blobs():
    qt = QuantizedTensor.from_weights(np.ones((8, 8)))
    blob = qt.to_bytes()
    with pytest.raises(QuantError, match="bad magic"):
        QuantizedTensor.from_bytes(b"BADMAGIC" + blob[8:])
    with pytest.raises(QuantError, match="too short"):
        QuantizedTensor.from_bytes(blob[:5])
    with pytest.raises(QuantError, match="truncated"):
        QuantizedTensor.from_bytes(blob[:-3])
    with pytest.raises(QuantError, match="codes must be int8"):
        QuantizedTensor(codes=np.zeros((2, 2), dtype=np.int32),
                        scales=np.ones(1), zero_points=np.zeros(1, dtype=np.int64),
                        shape=(2, 2), symmetric=False, axis=None)


def test_int8_matvec_matches_float_reference():
    rng = _rng()
    W = rng.normal(0, 0.5, size=(16, 32))
    x = rng.normal(0, 1, size=32)
    b = rng.normal(0, 0.1, size=16)
    qt = QuantizedTensor.from_weights(W, axis=0)
    y_q = int8_matvec(qt, x, b)
    y_ref = W @ x + b
    # quantized op tracks the float reference within a few bins
    assert float(np.max(np.abs(y_q - y_ref))) < 0.5


def test_int8_matvec_rejects_shape_mismatch():
    qt = QuantizedTensor.from_weights(np.ones((4, 8)), axis=0)
    with pytest.raises(QuantError, match="shape mismatch"):
        int8_matvec(qt, np.ones(7))
    with pytest.raises(QuantError, match="bias shape"):
        int8_matvec(qt, np.ones(8), np.ones(3))
