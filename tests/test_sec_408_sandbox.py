"""Slice 408 — backend sandbox boundary.

``sys.addaudithook``-based enforcement: subprocess, network, and
filesystem-write operations attempted inside a sandbox raise
SandboxViolation *before* they execute.
"""

from __future__ import annotations

import os
import socket
import subprocess
from collections.abc import Mapping
from typing import Any

import pytest

from hugrgate.backend import Backend
from hugrgate.errors import HugrGateError, SandboxViolation
from hugrgate.result import DecisionResult
from hugrgate.security.sandbox import (
    SandboxedBackend,
    SandboxPolicy,
    run_sandboxed,
    sandboxed,
)
from hugrgate.spec import DecisionSpec


def _spec() -> DecisionSpec:
    return DecisionSpec(type="categorical", options=["yes", "no"])


class EvilBackend(Backend):
    """Tries every forbidden operation during evaluate()."""

    name = "evil"

    def capabilities(self) -> dict[str, Any]:
        return {}

    def supports(self, spec: DecisionSpec) -> bool:
        return True

    def evaluate(self, state: Mapping[str, Any], spec: DecisionSpec,
                 context: Mapping[str, Any] | None = None
                 ) -> DecisionResult:
        os.system("echo pwned")
        return DecisionResult(value="yes", probability=1.0,
                              backend=self.name, model="evil")


class GoodBackend(Backend):
    name = "good"

    def capabilities(self) -> dict[str, Any]:
        return {"pure": True}

    def supports(self, spec: DecisionSpec) -> bool:
        return True

    def evaluate(self, state: Mapping[str, Any], spec: DecisionSpec,
                 context: Mapping[str, Any] | None = None
                 ) -> DecisionResult:
        total = sum(v for v in state.values()
                    if isinstance(v, (int, float)))
        return DecisionResult(value="yes" if total > 0 else "no",
                              probability=0.9, backend=self.name,
                              model="good")


def test_subprocess_blocked():
    with run_sandboxed(SandboxPolicy()):
        with pytest.raises(SandboxViolation) as exc:
            os.system("echo no")
    assert exc.value.code == "sandbox_violation"
    assert exc.value.recoverable is False
    assert exc.value.details["category"] == "subprocess"


def test_subprocess_popen_blocked():
    with run_sandboxed(SandboxPolicy()):
        with pytest.raises(SandboxViolation):
            subprocess.run(["echo", "no"], check=False)


def test_network_blocked():
    with run_sandboxed(SandboxPolicy()):
        with pytest.raises(SandboxViolation) as exc:
            socket.getaddrinfo("example.com", 80)
    assert exc.value.details["category"] == "network"


def test_filesystem_write_blocked(tmp_path):
    target = tmp_path / "evil.txt"
    with run_sandboxed(SandboxPolicy()):
        with pytest.raises(SandboxViolation) as exc:
            open(target, "w").close()
    assert exc.value.details["category"] == "filesystem_write"
    assert not target.exists()  # denied *before* the write happened


def test_reads_still_allowed(tmp_path):
    target = tmp_path / "ok.txt"
    target.write_text("hello")
    with run_sandboxed(SandboxPolicy()):
        assert open(target).read() == "hello"


def test_pure_compute_allowed():
    with run_sandboxed(SandboxPolicy()):
        assert sum(range(1000)) == 499500


def test_permissive_policy_allows_listed_operations():
    policy = SandboxPolicy(allow_network=True, allow_filesystem_write=True)
    with run_sandboxed(policy):
        # getaddrinfo may fail without network; the point is no
        # SandboxViolation is raised for the attempt itself.
        try:
            socket.getaddrinfo("localhost", 80)
        except socket.gaierror:
            pass


def test_nested_sandbox_innermost_wins():
    outer = SandboxPolicy(allow_subprocess=True)
    inner = SandboxPolicy()
    with run_sandboxed(outer):
        os.system("echo outer-ok")  # allowed by outer
        with run_sandboxed(inner):
            with pytest.raises(SandboxViolation):
                os.system("echo inner-no")
        os.system("echo outer-ok-again")  # outer restored


def test_no_sandbox_no_interference():
    os.system("echo unrestricted-ok")


def test_decorator_form():
    @sandboxed(SandboxPolicy())
    def sneaky() -> None:
        os.system("echo no")

    with pytest.raises(SandboxViolation):
        sneaky()


def test_sandboxed_backend_contains_evil():
    backend = SandboxedBackend(EvilBackend())
    with pytest.raises(SandboxViolation):
        backend.evaluate({"x": 1}, _spec())
    assert backend.name == "sandboxed(evil)"
    assert backend.policy == SandboxPolicy()
    assert backend.capabilities()["sandbox"]["subprocess"] is False


def test_sandboxed_backend_passes_good_through():
    backend = SandboxedBackend(GoodBackend())
    result = backend.evaluate({"x": 2}, _spec())
    assert result.value == "yes"
    assert backend.supports(_spec())
    assert backend.health()["sandbox"]["network"] is False


def test_violation_wire_round_trip():
    err = SandboxViolation("denied", event="os.system")
    rebuilt = HugrGateError.from_dict(err.to_dict())
    assert isinstance(rebuilt, SandboxViolation)
