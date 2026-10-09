"""Slice 447 — the systemd unit stays valid.

Parsed with configparser for structural assertions and, when
available, verified for real with ``systemd-analyze verify``.
"""

from __future__ import annotations

import configparser
import shutil
import subprocess
from pathlib import Path

import pytest

UNIT = (Path(__file__).resolve().parent.parent
        / "deploy" / "systemd" / "hugrgate.service")


def _unit() -> configparser.ConfigParser:
    parser = configparser.ConfigParser(strict=True)
    parser.read(UNIT, encoding="utf-8")
    return parser


def test_unit_has_required_sections():
    unit = _unit()
    for section in ("Unit", "Service", "Install"):
        assert unit.has_section(section), section


def test_unit_runs_as_nonroot_service():
    svc = _unit()["Service"]
    assert svc["user"] == "hugr"
    assert svc["type"] == "simple"
    assert svc["restart"] == "on-failure"


def test_unit_exec_start_serves_with_config():
    start = _unit()["Service"]["execstart"]
    assert start.startswith("/usr/local/bin/hugrgate serve")
    assert "--config /etc/hugrgate/hugrgate.yaml" in start


def test_unit_is_hardened():
    svc = _unit()["Service"]
    assert svc.getboolean("NoNewPrivileges") is True
    assert svc.getboolean("PrivateTmp") is True
    assert svc["ProtectSystem"] == "full"
    assert svc.getboolean("ProtectHome") is True


def test_unit_wanted_by_multi_user():
    assert (_unit()["Install"]["wantedby"] == "multi-user.target")


@pytest.mark.skipif(shutil.which("systemd-analyze") is None,
                    reason="systemd-analyze not installed")
def test_systemd_analyze_verify():
    # This container's own units are broken (motd-news.timer etc.),
    # so verify exits non-zero on system noise. What matters: no
    # diagnostic names OUR unit except the missing-binary artifact
    # of this environment (the package is not installed
    # system-wide here).
    proc = subprocess.run(
        ["systemd-analyze", "verify", str(UNIT)],
        capture_output=True, text=True, timeout=60)
    for line in proc.stderr.splitlines():
        if "hugrgate.service:" in line:
            assert "not executable" in line, line
