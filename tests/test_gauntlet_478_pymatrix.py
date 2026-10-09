"""Slice 478 — Python-version matrix.

``pyproject.toml`` says ``requires-python = ">=3.10"``; this slice
turns the claim into checked machinery
(``hugrgate/gauntlet/pymatrix.py`` + ``tools/matrix/python_matrix.py``):
the declared lower bound is parsed, the supported matrix (3.10-3.13)
must cover it, and every source file must parse under the oldest
grammar via ``ast.parse(feature_version=...)``.
"""

from __future__ import annotations

import sys
from pathlib import Path

from hugrgate.gauntlet.pymatrix import (
    SUPPORTED_MINORS,
    check_syntax_compat,
    read_requires_python,
    validate_matrix,
)

ROOT = Path(__file__).resolve().parent.parent


def test_requires_python_declares_sane_floor():
    spec = read_requires_python(ROOT / "pyproject.toml")
    assert spec.startswith(">=")
    assert "3.10" in spec


def test_matrix_covers_declared_floor():
    report = validate_matrix(ROOT)
    assert report.min_minor == (3, 10)
    assert report.min_minor in report.matrix
    assert report.matrix == SUPPORTED_MINORS


def test_matrix_includes_running_interpreter():
    running = (sys.version_info.major, sys.version_info.minor)
    assert running in SUPPORTED_MINORS, (
        f"running on {running}, outside the supported matrix"
    )


def test_whole_package_parses_under_oldest_grammar():
    checked, failures = check_syntax_compat(ROOT / "hugrgate", (3, 10))
    assert checked > 100, "expected the full package to be scanned"
    assert failures == (), f"files using newer-than-3.10 syntax: {failures[:5]}"


def test_newer_syntax_is_caught(tmp_path):
    # `except*` is 3.11+; the floor is 3.10, so this must be flagged.
    bad = tmp_path / "bad.py"
    bad.write_text("try:\n    pass\nexcept* ValueError:\n    pass\n", encoding="utf-8")
    checked, failures = check_syntax_compat(tmp_path, (3, 10))
    assert checked == 1
    assert len(failures) == 1
    assert "bad.py" in failures[0]


def test_floor_syntax_passes(tmp_path):
    # `match` is 3.10 syntax: legal at the floor.
    ok = tmp_path / "ok.py"
    ok.write_text("match 1:\n    case 1:\n        x = 2\n", encoding="utf-8")
    checked, failures = check_syntax_compat(tmp_path, (3, 10))
    assert checked == 1
    assert failures == ()


def test_empty_tree_passes(tmp_path):
    checked, failures = check_syntax_compat(tmp_path, (3, 10))
    assert (checked, failures) == (0, ())


def test_full_report_is_ok():
    assert validate_matrix(ROOT).ok
