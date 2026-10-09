"""Slice 185 — NPU capability abstraction tests."""

from __future__ import annotations

import pytest

from hugrgate.edge.npu import (
    MockNPUAdapter,
    NPUAdapter,
    NPUCapability,
    NPUError,
    NPURegistry,
)


def _cap(**over) -> NPUCapability:
    base = {"vendor": "mock", "device": "MockNPU-1", "tops_int8": 4.0,
            "precisions": ("int8", "fp16")}
    base.update(over)
    return NPUCapability(**base)  # type: ignore[arg-type]


# --- capability: success ------------------------------------------------------------

def test_capability_supports_and_serializes():
    import json
    cap = _cap()
    assert cap.supports("int8") and not cap.supports("int4")
    json.dumps(cap.to_dict())


# --- capability: failure --------------------------------------------------------------

@pytest.mark.parametrize("over", [
    {"tops_int8": 0.0},
    {"tops_int8": -1.0},
    {"precisions": ("int8", "bf17")},
    {"power_mw": 0.0},
    {"power_mw": -50.0},
])
def test_capability_rejects_bad_values(over):
    with pytest.raises(NPUError):
        _cap(**over)


# --- mock adapter: success --------------------------------------------------------------

def test_mock_detect_load_infer_roundtrip():
    adapter = MockNPUAdapter()
    assert adapter.is_available()
    handle = adapter.load_model("models/tiny.hef", precision="int8")
    out = adapter.infer(handle, {"x": [1, 2]})
    assert out["echo"] == {"x": [1, 2]} and out["mock"] is True
    assert adapter.infer_calls == 1
    caps = adapter.capabilities()
    assert caps["available"] is True
    assert caps["capability"]["device"] == "MockNPU-1"


def test_mock_absent_reports_none():
    adapter = MockNPUAdapter(present=False)
    assert adapter.detect() is None
    assert not adapter.is_available()
    assert adapter.capabilities()["available"] is False


# --- mock adapter: failure ----------------------------------------------------------------

def test_mock_requires_available_for_load():
    adapter = MockNPUAdapter(present=False)
    with pytest.raises(NPUError, match="no device/driver"):
        adapter.load_model("m.hef")


def test_mock_rejects_unsupported_precision():
    adapter = MockNPUAdapter()
    with pytest.raises(NPUError, match="lacks precision"):
        adapter.load_model("m.hef", precision="int4")


def test_mock_rejects_unknown_handle():
    adapter = MockNPUAdapter()
    with pytest.raises(NPUError, match="unknown model handle"):
        adapter.infer("mock://nope", {})


def test_abstract_adapter_cannot_instantiate():
    with pytest.raises(TypeError):
        NPUAdapter()  # type: ignore[abstract]


# --- registry: success ----------------------------------------------------------------------

def test_registry_detect_all_and_best_for():
    reg = NPURegistry()
    slow = MockNPUAdapter(_cap(device="Slow", tops_int8=2.0))
    slow.name = "slow-npu"
    fast = MockNPUAdapter(_cap(device="Fast", tops_int8=26.0))
    fast.name = "fast-npu"
    gone = MockNPUAdapter(present=False)
    gone.name = "gone-npu"
    for a in (slow, fast, gone):
        reg.register(a)
    assert len(reg) == 3
    found = reg.detect_all()
    assert set(found) == {"slow-npu", "fast-npu"}
    assert reg.best_for("int8").name == "fast-npu"  # type: ignore[union-attr]
    assert reg.best_for("int8", min_tops=100.0) is None
    assert reg.best_for("int4") is None  # nobody supports int4


# --- registry: failure ------------------------------------------------------------------------

def test_registry_rejects_duplicates_and_non_adapters():
    reg = NPURegistry()
    reg.register(MockNPUAdapter())
    with pytest.raises(NPUError, match="already registered"):
        reg.register(MockNPUAdapter())
    with pytest.raises(NPUError, match="can only register"):
        reg.register("not-an-adapter")  # type: ignore[arg-type]
    with pytest.raises(NPUError, match="unknown NPU adapter"):
        reg.get("missing")


# --- slice 186: Hailo adapter ----------------------------------------------------

from hugrgate.edge.npu import HailoAdapter


class _FakeHailoSdk:
    __version__ = "4.19.0"

    @staticmethod
    def scan_devices():
        return []


class _FakeHailo8Sdk(_FakeHailoSdk):
    @staticmethod
    def scan_devices():
        class Dev:
            device_name = "Hailo-8"
        return [Dev()]


def test_hailo_detect_with_sdk_and_pci():
    adapter = HailoAdapter(sdk=_FakeHailoSdk(),
                           pci_vendor_ids=["0x1e60"])
    cap = adapter.detect()
    assert cap is not None
    assert cap.vendor == "hailo"
    assert cap.device == "Hailo-8L"  # conservative: no 8-class device seen
    assert cap.tops_int8 == 13.0
    assert cap.supports("int8") and not cap.supports("fp16")
    assert adapter.is_available()


def test_hailo_detect_distinguishes_hailo8():
    adapter = HailoAdapter(sdk=_FakeHailo8Sdk(),
                           pci_vendor_ids=["0x1E60"])  # case-insensitive
    cap = adapter.detect()
    assert cap is not None
    assert (cap.device, cap.tops_int8) == ("Hailo-8", 26.0)


def test_hailo_absent_without_sdk():
    assert HailoAdapter(sdk=None,
                        pci_vendor_ids=["0x1e60"]).detect() is None


def test_hailo_absent_without_pci_device():
    adapter = HailoAdapter(sdk=_FakeHailoSdk(), pci_vendor_ids=["0x8086"])
    assert adapter.detect() is None
    assert not adapter.is_available()


def test_hailo_load_model_requires_hef():
    adapter = HailoAdapter(sdk=_FakeHailoSdk(),
                           pci_vendor_ids=["0x1e60"])
    handle = adapter.load_model("models/tiny.hef")
    assert handle == "hailo://models/tiny.hef"
    with pytest.raises(NPUError, match=r"\.hef"):
        adapter.load_model("models/tiny.onnx")


def test_hailo_load_without_device_raises():
    adapter = HailoAdapter(sdk=None, pci_vendor_ids=[])
    with pytest.raises(NPUError, match="NEEDS_HARDWARE_VALIDATION"):
        adapter.load_model("models/tiny.hef")


def test_hailo_infer_marks_hardware_validation():
    adapter = HailoAdapter(sdk=_FakeHailoSdk(),
                           pci_vendor_ids=["0x1e60"])
    handle = adapter.load_model("models/tiny.hef")
    with pytest.raises(NPUError, match="NEEDS_HARDWARE_VALIDATION"):
        adapter.infer(handle, {})
    with pytest.raises(NPUError, match="unknown Hailo model handle"):
        adapter.infer("hailo://nope.hef", {})


def test_hailo_registry_integration():
    reg = NPURegistry()
    reg.register(HailoAdapter(sdk=_FakeHailoSdk(),
                              pci_vendor_ids=["0x1e60"]))
    found = reg.detect_all()
    assert found["hailo"].device == "Hailo-8L"
