"""Slice 448 — Windows service packaging content checks.

No PowerShell runs in this environment, so the tests assert the
script and guide say what they must: NSSM lifecycle, config
wiring, health endpoints, and a valid daemon config.
"""

from __future__ import annotations

from pathlib import Path

WIN = Path(__file__).resolve().parent.parent / "deploy" / "windows"
DOCS = Path(__file__).resolve().parent.parent / "docs"


def _script() -> str:
    return (WIN / "hugrgate-service.ps1").read_text(encoding="utf-8")


def test_script_has_nssm_lifecycle():
    text = _script()
    for cmd in ("nssm install", "nssm remove", "nssm start", "nssm stop"):
        assert cmd in text, cmd


def test_script_serves_with_config():
    text = _script()
    assert "serve --config" in text
    assert "ConfigPath" in text


def test_script_requires_elevation_and_nssm():
    text = _script()
    assert "Administrator" in text
    assert "nssm.cc" in text


def test_script_configures_restart_and_logs():
    text = _script()
    assert "SERVICE_AUTO_START" in text
    assert "AppExit Default Restart" in text
    assert "AppRotateBytes" in text


def test_windows_config_validates():
    from hugrgate.configgen import load_daemon_config
    cfg = load_daemon_config(str(WIN / "hugrgate.yaml"))
    assert cfg.host == "127.0.0.1"  # loopback default per the guide
    assert cfg.port == 8377


def test_guide_covers_operations():
    text = (DOCS / "windows-service.md").read_text(encoding="utf-8")
    for needle in ("nssm", "/health", "/protocol", "-Uninstall",
                   "Restart-Service"):
        assert needle in text, needle
