"""Slice 176 — ARM64 compatibility audit tests."""

from __future__ import annotations

import pytest

from hugrgate.edge.platform import (
    Arm64AuditReport,
    Arm64Finding,
    PlatformInfo,
    PlatformProbe,
    audit_arm64,
)


def _pi_info(**over: object) -> PlatformInfo:
    base: dict[str, object] = {
        "arch": "aarch64",
        "system": "Linux",
        "release": "6.6.0",
        "python_version": (3, 11, 2),
        "python_implementation": "CPython",
        "cpu_count": 4,
        "cpu_features": ("aes", "asimd", "crc32", "fp", "neon", "sha2"),
        "page_size": 4096,
        "byteorder": "little",
        "is_64bit": True,
        "live": False,
    }
    base.update(over)
    return PlatformInfo(**base)  # type: ignore[arg-type]


# --- success ---------------------------------------------------------------

def test_healthy_arm64_host_passes():
    report = audit_arm64(_pi_info())
    assert isinstance(report, Arm64AuditReport)
    assert report.passed
    assert report.errors == []
    assert "PASS" in report.summary()


def test_cpuinfo_feature_parsing():
    text = ("processor\t: 0\nFeatures\t: fp asimd evtstrm aes pmull sha1 sha2 crc32\n"
            "processor\t: 1\nFeatures\t: fp asimd neon\n")
    probe = PlatformProbe(cpuinfo_text=text)
    info = probe.probe()
    assert info.live is False
    assert "asimd" in info.cpu_features
    assert "neon" in info.cpu_features
    # union across processors, sorted
    assert info.cpu_features == tuple(sorted(set(info.cpu_features)))


def test_report_serializes_to_jsonable_dict():
    import json
    report = audit_arm64(_pi_info())
    json.dumps(report.to_dict())  # must not raise


# --- failure -----------------------------------------------------------------

def test_big_endian_host_is_an_error():
    report = audit_arm64(_pi_info(byteorder="big"))
    assert not report.passed
    assert any(f.id == "arm64/big-endian" for f in report.errors)


def test_32bit_python_is_an_error():
    report = audit_arm64(_pi_info(is_64bit=False))
    assert not report.passed
    assert any(f.id == "arm64/not-64bit" for f in report.errors)


def test_old_python_is_an_error():
    report = audit_arm64(_pi_info(python_version=(3, 9, 0)))
    assert not report.passed
    assert any(f.id == "arm64/python-old" for f in report.errors)


def test_non_arm64_host_warns_but_may_pass():
    report = audit_arm64(_pi_info(arch="x86_64", cpu_features=()))
    assert any(f.id == "arm64/not-arm64" for f in report.warnings)


def test_missing_simd_warns():
    report = audit_arm64(_pi_info(cpu_features=("fp",)))
    assert any(f.id == "arm64/simd-missing" for f in report.warnings)


def test_single_core_warns():
    report = audit_arm64(_pi_info(cpu_count=1))
    assert any(f.id == "arm64/single-core" for f in report.warnings)


# --- boundary -----------------------------------------------------------------

def test_unknown_severity_rejected():
    with pytest.raises(ValueError):
        Arm64Finding(id="x", severity="critical", area="arch",
                     message="m", remediation="r", source="s")


def test_probe_handles_missing_cpuinfo(monkeypatch):
    def boom(*a: object, **k: object) -> object:
        raise OSError("no /proc here")
    monkeypatch.setattr("builtins.open", boom)
    info = PlatformProbe().probe()
    assert info.cpu_features == ()
    assert info.live is True


def test_live_probe_runs_on_this_host():
    info = PlatformProbe().probe()
    assert info.arch  # non-empty on any host
    assert info.python_version >= (3, 10)


# --- slice 177: Pi detection & baselines -----------------------------------

from hugrgate.edge.platform import (
    PI_BASELINES,
    EdgeBaseline,
    PiBoard,
    detect_pi_board,
    pi_baseline,
)

_PI4_CPUINFO = (
    "processor\t: 0\n"
    "model name\t: ARMv7 Processor rev 3 (v7l)\n"
    "Model\t\t: Raspberry Pi 4 Model B Rev 1.4\n"
    "Revision\t: c03114\n"
    "Serial\t\t: 10000000abcdef12\n"
)

_PI5_MODEL = "Raspberry Pi 5 Model B Rev 1.0\x00"


def test_detect_pi4_from_cpuinfo():
    board = detect_pi_board(cpuinfo_text=_PI4_CPUINFO, model_text="")
    assert board is not None
    assert board.model == "Raspberry Pi 4 Model B"
    assert board.ram_mb == 4096
    assert board.revision == "c03114"
    assert board.detected_live is False


def test_detect_pi5_from_devicetree_model():
    board = detect_pi_board(cpuinfo_text="processor: 0\n",
                            model_text=_PI5_MODEL)
    assert board is not None
    assert "Raspberry Pi 5" in board.model


def test_non_pi_host_returns_none():
    cpuinfo = "processor\t: 0\nmodel name\t: Intel(R) Core(TM)\n"
    assert detect_pi_board(cpuinfo_text=cpuinfo, model_text="") is None


def test_unknown_revision_falls_back_to_family_ram():
    cpuinfo = ("Model\t\t: Raspberry Pi 4 Model B Rev 9.9\n"
               "Revision\t: deadbeef\n")
    board = detect_pi_board(cpuinfo_text=cpuinfo, model_text="")
    assert board is not None
    assert board.ram_mb == 4096  # conservative: smallest Pi 4 family figure


def test_pi_baseline_by_board_and_label():
    board = PiBoard(model="Raspberry Pi 5", revision="d04170",
                    ram_mb=8192, detected_live=False)
    base = pi_baseline(board)
    assert isinstance(base, EdgeBaseline)
    assert base.cpu_count == 4 and base.ram_mb == 8192
    assert pi_baseline("raspberry pi zero 2 w").ram_mb == 512
    assert pi_baseline("Raspberry Pi 3 Model B+").recommended_cache_entries \
        == 250


def test_pi_baseline_unknown_label_raises_with_known_list():
    with pytest.raises(ValueError, match="known models"):
        pi_baseline("Raspberry Pi 400")


def test_pi_baselines_are_conservative_and_jsonable():
    import json
    for base in PI_BASELINES.values():
        assert base.recommended_cache_entries > 0
        assert base.recommended_max_resident_models >= 1
        json.dumps(base.to_dict())
