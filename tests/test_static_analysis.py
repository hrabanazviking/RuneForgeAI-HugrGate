"""Slice 022 — static-analysis gate.

Runs ruff over the package, tools, and tests and requires zero
findings. Skips gracefully when ruff is not installed; install it with
``venv/bin/pip install 'ruff>=0.8'`` (the ``lint`` extra) to run the
gate locally.

The gate covers ``ruff check`` (lint rules declared in
``[tool.ruff.lint]``); ``ruff format`` is intentionally *not* gated —
the codebase predates the formatter and a reformat would be pure
churn.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate
ROOT = Path(__file__).resolve().parent.parent

RUFF_ARGS = [
    sys.executable, "-m", "ruff",
    "check",
    "hugrgate", "tools", "tests",
    "--no-cache",  # hermetic: never trust a warm cache in the gate
]


def test_ruff_reports_no_findings():
    if shutil.which("ruff") is None and not _has_ruff_module():
        pytest.skip("ruff not installed")
    proc = subprocess.run(
        RUFF_ARGS, capture_output=True, text=True, cwd=ROOT, timeout=300,
    )
    assert proc.returncode == 0, (
        "ruff gate failed:\n" + proc.stdout + proc.stderr
    )


def _has_ruff_module() -> bool:
    try:
        import ruff  # noqa: F401
        return True
    except ImportError:
        return False


def test_ruff_config_is_declared():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "[tool.ruff.lint]" in text


def test_lint_extra_is_declared():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'lint = ["ruff>=0.8"]' in text
