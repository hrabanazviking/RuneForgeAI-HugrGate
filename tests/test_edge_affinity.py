"""Slice 179 — CPU affinity controls tests."""

from __future__ import annotations

import pytest

from hugrgate.edge.affinity import (
    AffinityController,
    EdgeAffinityError,
    _OsFuncs,
    parse_cpu_list,
    pin_callable,
)


class FakeOs(_OsFuncs):
    """4-CPU host; records set_affinity calls without touching the OS."""

    def __init__(self) -> None:
        self.current = frozenset({0, 1, 2, 3})
        self.calls: list[frozenset[int]] = []

    def cpu_count(self) -> int:
        return 4

    def sched_affinity(self, pid: int) -> frozenset[int]:
        return frozenset(self.current)

    def set_affinity(self, pid: int, cpus: frozenset[int]) -> None:
        self.calls.append(frozenset(cpus))
        self.current = frozenset(cpus)


# --- parse_cpu_list: success ------------------------------------------------

def test_parse_simple_list_and_ranges():
    assert parse_cpu_list("0-3,5") == frozenset({0, 1, 2, 3, 5})
    assert parse_cpu_list("2") == frozenset({2})
    assert parse_cpu_list("1,1,2-2") == frozenset({1, 2})


# --- parse_cpu_list: failure --------------------------------------------------

@pytest.mark.parametrize("spec", [
    "", "  ", "0,,1", "a", "0-b", "1-2-3", "-1", "0--1", "3-1",
])
def test_parse_rejects_bad_specs(spec: str):
    with pytest.raises(EdgeAffinityError):
        parse_cpu_list(spec)


# --- controller: success --------------------------------------------------------

def test_set_and_current_roundtrip():
    fake = FakeOs()
    ctl = AffinityController(os_funcs=fake)
    assert ctl.available_cpus() == frozenset({0, 1, 2, 3})
    assert ctl.set_affinity({1, 2}) == frozenset({1, 2})
    assert ctl.current() == frozenset({1, 2})
    assert fake.calls == [frozenset({1, 2})]


def test_set_affinity_accepts_string_spec():
    ctl = AffinityController(os_funcs=FakeOs())
    assert ctl.set_affinity("0-1") == frozenset({0, 1})


def test_dry_run_records_without_syscall():
    fake = FakeOs()
    ctl = AffinityController(os_funcs=fake, dry_run=True)
    assert ctl.set_affinity({3}) == frozenset({3})
    assert fake.calls == []  # OS untouched


def test_profiles_resolve_against_host():
    ctl = AffinityController(os_funcs=FakeOs())
    assert ctl.profile_cpus("full") == frozenset({0, 1, 2, 3})
    assert ctl.profile_cpus("inference") == frozenset({1, 2, 3})
    assert ctl.profile_cpus("isolated") == frozenset({3})


def test_pinned_restores_previous_set():
    ctl = AffinityController(os_funcs=FakeOs())
    ctl.set_affinity({0, 1, 2})
    with ctl.pinned({2}) as applied:
        assert applied == frozenset({2})
        assert ctl.current() == frozenset({2})
    assert ctl.current() == frozenset({0, 1, 2})


def test_pinned_restores_even_on_exception():
    ctl = AffinityController(os_funcs=FakeOs())
    ctl.set_affinity({0, 1})
    with pytest.raises(RuntimeError):
        with ctl.pinned({1}):
            raise RuntimeError("boom")
    assert ctl.current() == frozenset({0, 1})


def test_pin_callable_runs_and_restores():
    ctl = AffinityController(os_funcs=FakeOs())
    assert pin_callable(lambda: 42, "1-2", ctl) == 42
    assert ctl.current() == frozenset({0, 1, 2, 3})


def test_pinned_outside_ceiling_rejected():
    # Validation is against the cpuset ceiling captured before the
    # first pin, not the transient narrowed mask — pinning {3} after
    # {0} is legal, pinning {9} never is.
    ctl = AffinityController(os_funcs=FakeOs())
    ctl.set_affinity({0})
    with ctl.pinned({3}):
        assert ctl.current() == frozenset({3})
    assert ctl.current() == frozenset({0})
    with pytest.raises(EdgeAffinityError, match="not in available set"):
        ctl.set_affinity({9})


def test_to_dict_is_jsonable():
    import json
    ctl = AffinityController(os_funcs=FakeOs())
    ctl.set_affinity({1})
    json.dumps(ctl.to_dict())


# --- controller: failure ----------------------------------------------------------

def test_set_affinity_rejects_unknown_cpus():
    ctl = AffinityController(os_funcs=FakeOs())
    with pytest.raises(EdgeAffinityError, match="not in available set"):
        ctl.set_affinity({0, 9})


def test_set_affinity_rejects_empty():
    ctl = AffinityController(os_funcs=FakeOs())
    with pytest.raises(EdgeAffinityError, match="must not be empty"):
        ctl.set_affinity(set())


def test_unknown_profile_rejected():
    ctl = AffinityController(os_funcs=FakeOs())
    with pytest.raises(EdgeAffinityError, match="unknown affinity profile"):
        ctl.profile_cpus("turbo")


def test_os_refusal_wrapped():
    class Refusing(FakeOs):
        def set_affinity(self, pid: int, cpus: frozenset[int]) -> None:
            raise OSError("EPERM")
    ctl = AffinityController(os_funcs=Refusing())
    with pytest.raises(EdgeAffinityError, match="OS refused"):
        ctl.set_affinity({1})


def test_missing_syscall_falls_back_to_cpu_count():
    class NoSched(_OsFuncs):
        def cpu_count(self) -> int:
            return 2
        def sched_affinity(self, pid: int) -> frozenset[int]:
            raise EdgeAffinityError("no sched_getaffinity")
    ctl = AffinityController(os_funcs=NoSched(), dry_run=True)
    assert ctl.available_cpus() == frozenset({0, 1})
