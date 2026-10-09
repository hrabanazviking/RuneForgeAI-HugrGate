"""Slice 483 — dependency-minimum matrix.

``pyproject.toml`` declares ``pyyaml>=6.0``; this slice proves the
floor is real: the spec parses, a ``requirements-min.txt`` pins the
floor, and the running environment is checked against it. Version
comparison is numeric (``1.10`` > ``1.9``), dependency-free.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hugrgate.gauntlet.deps import (
    DepRequirement,
    check_minimums,
    parse_requirement,
    read_runtime_dependencies,
    render_min_requirements,
    version_key,
)

ROOT = Path(__file__).resolve().parent.parent
MIN_REQS = ROOT / "tools" / "matrix" / "requirements-min.txt"


def test_runtime_deps_parse():
    deps = read_runtime_dependencies(ROOT / "pyproject.toml")
    by_name = {d.name: d for d in deps}
    assert by_name["pyyaml"].minimum == "6.0"


def test_parse_requirement_forms():
    assert parse_requirement("pyyaml>=6.0") == DepRequirement("pyyaml", "6.0")
    assert parse_requirement("foo") == DepRequirement("foo", None)
    assert parse_requirement("bar>=1.2,<2").minimum == "1.2"
    with pytest.raises(ValueError):
        parse_requirement(">=6.0")
    with pytest.raises(ValueError):
        parse_requirement("")


def test_version_key_is_numeric_not_lexicographic():
    assert version_key("1.10") > version_key("1.9")
    assert version_key("6.0.3") >= version_key("6.0")
    assert version_key("10.0") > version_key("9.99")
    with pytest.raises(ValueError):
        version_key("not-a-version")


def test_minimums_met_in_this_env():
    report = check_minimums()
    assert report.ok, [s for s in report.violations()]
    assert report.violations() == ()


def test_missing_dependency_reported():
    report = check_minimums((DepRequirement("nosuchpkg-xyz", "1.0"),))
    assert not report.ok
    (status,) = report.violations()
    assert status.installed is None
    assert "not installed" in status.reason


def test_too_old_dependency_reported():
    report = check_minimums((DepRequirement("pyyaml", "99.0"),))
    assert not report.ok
    (status,) = report.violations()
    assert status.installed is not None
    assert "floor" in status.reason


def test_min_requirements_file_exists_and_pins_floors():
    assert MIN_REQS.is_file()
    text = MIN_REQS.read_text(encoding="utf-8")
    assert "pyyaml==6.0" in text
    # The checked-in file must match what the generator renders.
    assert text == render_min_requirements()
