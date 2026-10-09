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


# --- slice 184: INT4 adapter support ------------------------------------------

from hugrgate.edge.quant import Int4Adapter


def test_int4_nd_roundtrip_bounded():
    rng = np.random.default_rng(184)
    w = rng.normal(0, 1, size=(8, 48))  # last axis not a multiple of 32
    adapter = Int4Adapter(group_size=32)
    rec = adapter.unpack(adapter.pack(w))
    assert rec.shape == w.shape
    # symmetric 4-bit: max error <= half a per-group bin (amax/7 / 2)
    groups = w.reshape(-1, 32)
    bound = float(np.abs(groups).max(axis=1).max() / 7.0 / 2.0) + 1e-9
    assert adapter.roundtrip_error(w) <= bound


def test_int4_1d_and_exact_multiple():
    adapter = Int4Adapter(group_size=16)
    w = np.linspace(-3, 3, 64)
    np.testing.assert_allclose(adapter.unpack(adapter.pack(w)), w,
                               atol=0.2)
    assert adapter.packed_bytes(64) == 32
    assert adapter.storage_bytes((4, 64)) == 4 * 32 + 4 * 4 * 8


def test_int4_serialization_roundtrip():
    rng = np.random.default_rng(184)
    adapter = Int4Adapter(group_size=32)
    w = rng.normal(0, 2, size=(5, 40))
    blob = adapter.pack(w)
    data = adapter.to_bytes(blob)
    blob2 = adapter.from_bytes(data)
    np.testing.assert_allclose(adapter.unpack(blob2), adapter.unpack(blob),
                               rtol=0, atol=0)
    # 4 bits/weight + fp64 scales: far below fp32
    assert len(data) < w.nbytes // 2


def test_int4_rejects_bad_inputs():
    adapter = Int4Adapter(group_size=32)
    with pytest.raises(QuantError, match="positive even"):
        Int4Adapter(group_size=7)
    with pytest.raises(QuantError, match="positive even"):
        Int4Adapter(group_size=0)
    with pytest.raises(QuantError, match="empty"):
        adapter.pack(np.array([]))
    with pytest.raises(QuantError, match="NaN or Inf"):
        adapter.pack(np.array([1.0, float("nan")]))


def test_int4_rejects_malformed_blobs():
    adapter = Int4Adapter(group_size=32)
    good = adapter.pack(np.ones((4, 32)))
    with pytest.raises(QuantError, match="must be a dict"):
        adapter.unpack("nope")  # type: ignore[arg-type]
    bad = dict(good)
    del bad["scales"]
    with pytest.raises(QuantError, match="missing key"):
        adapter.unpack(bad)
    bad = dict(good)
    bad["group_size"] = 16
    with pytest.raises(QuantError, match="group_size"):
        adapter.unpack(bad)
    bad = dict(good)
    bad["packed"] = np.zeros(2, dtype=np.uint8)
    with pytest.raises(QuantError, match="truncated"):
        adapter.unpack(bad)
    bad = dict(good)
    bad["shape"] = (4, -32)
    with pytest.raises(QuantError, match="negative dims"):
        adapter.unpack(bad)


def test_int4_rejects_malformed_bytes():
    adapter = Int4Adapter(group_size=32)
    data = adapter.to_bytes(adapter.pack(np.ones((4, 32))))
    with pytest.raises(QuantError, match="bad magic"):
        adapter.from_bytes(b"BADMAGIC" + data[8:])
    with pytest.raises(QuantError, match="too short"):
        adapter.from_bytes(data[:4])
    with pytest.raises(QuantError, match="truncated"):
        adapter.from_bytes(data[:-5])
    other = Int4Adapter(group_size=16)
    with pytest.raises(QuantError, match="group_size"):
        other.from_bytes(data)


def test_int4_deterministic():
    rng = np.random.default_rng(184)
    adapter = Int4Adapter()
    w = rng.normal(0, 1, size=(3, 33))
    b1, b2 = adapter.pack(w), adapter.pack(w)
    np.testing.assert_array_equal(b1["packed"], b2["packed"])
    np.testing.assert_array_equal(b1["scales"], b2["scales"])
