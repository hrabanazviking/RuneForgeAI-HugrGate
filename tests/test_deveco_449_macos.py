"""Slice 449 — macOS launchd packaging stays valid.

The plist is parsed with plistlib (real validation) and its
keys asserted; the guide must cover the launchctl lifecycle.
"""

from __future__ import annotations

import plistlib
from pathlib import Path

MACOS = Path(__file__).resolve().parent.parent / "deploy" / "macos"
DOCS = Path(__file__).resolve().parent.parent / "docs"


def _plist() -> dict:
    return plistlib.loads(
        (MACOS / "com.hugrgate.daemon.plist").read_bytes())


def test_plist_parses_with_plistlib():
    d = _plist()
    assert d["Label"] == "com.hugrgate.daemon"


def test_plist_runs_hugrgate_serve_with_config():
    args = _plist()["ProgramArguments"]
    assert args[0].endswith("/hugrgate")
    assert args[1] == "serve"
    assert "--config" in args


def test_plist_keeps_alive_and_throttles():
    d = _plist()
    assert d["RunAtLoad"] is True
    assert d["KeepAlive"]["SuccessfulExit"] is False
    assert d["ThrottleInterval"] >= 10


def test_plist_captures_logs():
    d = _plist()
    assert d["StandardOutPath"].endswith("service.log")
    assert d["StandardErrorPath"].endswith("service-error.log")


def test_macos_config_validates():
    from hugrgate.configgen import load_daemon_config
    cfg = load_daemon_config(str(MACOS / "hugrgate.yaml"))
    assert cfg.host == "127.0.0.1"  # loopback default per the guide
    assert cfg.port == 8377


def test_guide_covers_lifecycle():
    text = (DOCS / "macos-launchd.md").read_text(encoding="utf-8")
    for needle in ("launchctl load", "launchctl unload",
                   "kickstart", "/health", "KeepAlive"):
        assert needle in text, needle
