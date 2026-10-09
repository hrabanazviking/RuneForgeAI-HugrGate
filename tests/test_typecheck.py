"""Slice 006 — type-system hardening.

Runs mypy over the package (``--check-untyped-defs``) and requires zero
errors. Skips gracefully when mypy is not installed; install it with
``venv/bin/pip install 'mypy>=1.0'`` to run the gate locally.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

MYPY_ARGS = [
    sys.executable, "-m", "mypy",
    "hugrgate",
    "--ignore-missing-imports",
    "--check-untyped-defs",
    "--no-incremental",  # hermetic: never trust a warm cache in the gate
]


def test_mypy_reports_no_errors():
    if shutil.which("mypy") is None and not _has_mypy_module():
        pytest.skip("mypy not installed")
    proc = subprocess.run(
        MYPY_ARGS, capture_output=True, text=True, cwd=ROOT, timeout=300,
    )
    assert proc.returncode == 0, (
        "mypy gate failed:\n" + proc.stdout + proc.stderr
    )


def _has_mypy_module() -> bool:
    try:
        import mypy  # noqa: F401
        return True
    except ImportError:
        return False


def test_mypy_config_is_declared():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "[tool.mypy]" in text
