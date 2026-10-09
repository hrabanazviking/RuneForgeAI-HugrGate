"""Slice 489 — fuzz all public interfaces.

The generic harness (``hugrgate/gauntlet/fuzz.py``) feeds seeded
hostile garbage (huge strings, deep nesting, NaN/Inf, wrong types)
to public entry points and proves only documented exception kinds
escape: ``HugrGateError`` subclasses and stdlib validation errors.
Anything else — ``IndexError``, ``RecursionError``,
``SystemExit``, ... — is an unexpected escape, i.e. a bug.
"""

from __future__ import annotations

import random

from hugrgate.gauntlet.fuzz import (
    ALLOWED_EXCEPTIONS,
    FuzzReport,
    fuzz_callable,
    fuzz_targets,
    generate_garbage,
)


def test_garbage_generator_covers_hostile_shapes():
    rng = random.Random(489)
    values = [generate_garbage(rng) for _ in range(500)]
    kinds = {type(v).__name__ for v in values}
    assert {"list", "dict", "tuple", "set", "str", "bytes", "float",
            "int", "bool", "NoneType"} <= kinds
    assert any(isinstance(v, float) and v != v for v in values)  # NaN
    assert any(isinstance(v, str) and len(v) >= 10000 for v in values)


def test_garbage_generator_is_bounded():
    rng = random.Random(7)
    for _ in range(200):
        v = generate_garbage(rng)
        assert not (isinstance(v, str) and len(v) > 10000)


def test_fuzz_report_shape():
    report = FuzzReport(target="t", cases=10)
    assert report.clean
    report.raise_if_dirty()  # must not raise


def test_allowed_raises_are_not_findings():
    def _raises(v):
        raise ValueError("bad input")

    report = fuzz_callable(_raises, seed=1, cases=20)
    assert report.clean
    assert report.allowed_raises == 20


def test_unexpected_escape_is_a_finding():
    def _leaks(*args):
        raise IndexError("internal oops")

    report = fuzz_callable(_leaks, seed=1, cases=20)
    assert not report.clean
    assert len(report.unexpected) == 20
    assert all(kind == "IndexError" for kind, _ in report.unexpected)
    try:
        report.raise_if_dirty()
    except AssertionError as exc:
        assert "IndexError" in str(exc)
    else:
        raise AssertionError("raise_if_dirty did not raise")


def test_fuzzing_is_deterministic():
    def _f(v):
        if not isinstance(v, dict):
            raise TypeError("want dict")
        return v.get("a")

    r1 = fuzz_callable(_f, seed=489, cases=100)
    r2 = fuzz_callable(_f, seed=489, cases=100)
    assert (r1.ok_cases, r1.allowed_raises, len(r1.unexpected)) == \
           (r2.ok_cases, r2.allowed_raises, len(r2.unexpected))


def test_curated_targets_are_clean():
    reports = fuzz_targets(seed=489, cases=300)
    assert len(reports) == 6
    for report in reports:
        assert report.clean, (report.target, report.unexpected[:1])
        report.raise_if_dirty()


def test_allowed_exceptions_cover_taxonomy():
    from hugrgate.errors import HugrGateError, SpecError

    assert issubclass(SpecError, HugrGateError)
    assert issubclass(HugrGateError, ALLOWED_EXCEPTIONS)
    assert issubclass(ValueError, ALLOWED_EXCEPTIONS)
