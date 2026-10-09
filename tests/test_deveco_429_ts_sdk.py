"""Slice 429 — TypeScript SDK gate.

Runs the TypeScript SDK's own test suite (``tsc`` strict compile +
``node --test`` against a stub HTTP server) from pytest so the
repo-wide suite covers the TS SDK. Skips when the TS toolchain is
not installed.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

SDK_DIR = Path(__file__).resolve().parent.parent / "sdks" / "typescript"


def _tsc_available() -> bool:
    return (SDK_DIR / "node_modules" / ".bin" / "tsc").exists() and \
        shutil.which("node") is not None


@pytest.mark.skipif(not _tsc_available(),
                    reason="TypeScript toolchain not installed")
def test_typescript_sdk_suite_passes():
    proc = subprocess.run(
        ["npm", "test", "--silent"],
        cwd=SDK_DIR,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, (
        f"npm test failed:\n{proc.stdout}\n{proc.stderr}")


def test_typescript_sdk_sources_present():
    assert (SDK_DIR / "src" / "index.ts").exists()
    assert (SDK_DIR / "src" / "index.test.ts").exists()
    assert (SDK_DIR / "package.json").exists()
    assert (SDK_DIR / "tsconfig.json").exists()
    assert (SDK_DIR / "README.md").exists()
