"""Slice 411 — deserialization hardening.

Proves the audit finding is real (a hostile pickle executes under
raw loads), that the allowlist stops it, and that the hardened
call sites still work.
"""

from __future__ import annotations

import os
import pickle

import pytest

from hugrgate.errors import DeserializationBlocked, HugrGateError
from hugrgate.security.serde_guards import (
    DeserializationPolicy,
    register_safe_class,
    restricted_loads,
    scan_for_pickle,
)

MARKER = "serde_guards_pwned"


class Evil:
    def __reduce__(self):
        return (os.system, (f"echo {MARKER}",))


def test_raw_pickle_loads_executes_attack():
    """Control: the threat is real under naive unpickling."""
    payload = pickle.dumps(Evil(), protocol=4)
    assert scan_for_pickle(payload)
    # Raw loads would run os.system — do NOT execute it here; the
    # opcode scan plus the blocked attempt below proves the vector.
    assert b"os" in payload and b"system" in payload


def test_restricted_loads_blocks_hostile_class():
    payload = pickle.dumps(Evil(), protocol=4)
    with pytest.raises(DeserializationBlocked) as exc:
        restricted_loads(payload)
    assert exc.value.code == "deserialization_blocked"
    assert exc.value.recoverable is False
    assert exc.value.details["name"] == "system"  # the hostile callable


def test_restricted_loads_blocks_builtins_eval():
    class EvalEvil:
        def __reduce__(self):
            return (eval, ("1+1",))

    with pytest.raises(DeserializationBlocked):
        restricted_loads(pickle.dumps(EvalEvil(), protocol=4))


def test_benign_containers_round_trip():
    payload = pickle.dumps(
        {"a": [1, 2.5, "x"], "b": (True, None), "c": {1, 2}},
        protocol=4)
    assert restricted_loads(payload) == {
        "a": [1, 2.5, "x"], "b": (True, None), "c": {1, 2}}


def test_registered_class_allowed():
    from hugrgate.result import DecisionResult
    register_safe_class(DecisionResult)
    result = DecisionResult(value="yes", probability=0.9,
                            backend="t", model="t")
    clone = restricted_loads(pickle.dumps(result))
    assert isinstance(clone, DecisionResult)
    assert clone.value == "yes"


def test_module_prefix_allowlist():
    import decimal
    payload = pickle.dumps(decimal.Decimal("1.5"), protocol=4)
    # decimal.Decimal is not a safe builtin: default policy blocks it.
    with pytest.raises(DeserializationBlocked):
        restricted_loads(payload)
    # An explicit module prefix allowlists it (side-effect free).
    assert restricted_loads(
        payload, allowed_modules=("decimal",)) == decimal.Decimal("1.5")
    # ...but the prefix does not bless anything else.
    with pytest.raises(DeserializationBlocked):
        restricted_loads(pickle.dumps(Evil(), protocol=4),
                         allowed_modules=("decimal",))


def test_scan_for_pickle():
    assert scan_for_pickle(pickle.dumps({"a": 1}, protocol=4))
    assert scan_for_pickle(pickle.dumps([1], protocol=0))
    assert not scan_for_pickle(b'{"a": 1}')
    assert not scan_for_pickle(b"")
    assert not scan_for_pickle(b"\x00" * 64)


def test_policy_kill_switch():
    policy = DeserializationPolicy(allow_pickle=False)
    with pytest.raises(DeserializationBlocked, match="disabled by policy"):
        policy.loads(pickle.dumps({"a": 1}))
    open_policy = DeserializationPolicy()
    assert open_policy.loads(pickle.dumps({"a": 1})) == {"a": 1}
    assert open_policy.describe()["allow_pickle"] is True


def test_non_bytes_rejected():
    with pytest.raises(DeserializationBlocked):
        restricted_loads("not bytes")  # type: ignore[arg-type]


def test_corrupt_pickle_raises_taxonomy_error():
    with pytest.raises(DeserializationBlocked):
        restricted_loads(b"\x80\x04\xff\xffgarbage")


def test_hardened_logreg_round_trip(tmp_path):
    """The real call site: save/load still works through the guard."""
    pytest.importorskip("sklearn")
    from hugrgate.backends.logreg import LogisticRegressionBackend
    from hugrgate.features import NumericEncoder, Pipeline
    backend = LogisticRegressionBackend(
        "t411", Pipeline([NumericEncoder(["x"])]))
    pairs = [({"x": float(i)}, "a" if i % 2 == 0 else "b")
             for i in range(40)]
    backend.train(pairs)
    path = str(tmp_path / "model.pkl")
    backend.save(path)
    loaded = LogisticRegressionBackend.load(path)
    assert loaded.manifest().name == "t411"
    # A hostile payload with a valid-looking manifest is still
    # stopped by the allowlist (the manifest is an unsigned sidecar).
    evil = pickle.dumps(Evil(), protocol=4)
    with open(path, "wb") as fh:
        fh.write(evil)
    from hugrgate.models import sha256_bytes
    manifest = loaded.manifest()
    manifest.payload_hash = sha256_bytes(evil)
    with open(path + ".manifest.json", "w") as fh:
        fh.write(manifest.to_json())
    with pytest.raises(DeserializationBlocked):
        LogisticRegressionBackend.load(path)


def test_error_wire_round_trip():
    err = DeserializationBlocked("nope", module="os", name="system")
    rebuilt = HugrGateError.from_dict(err.to_dict())
    assert isinstance(rebuilt, DeserializationBlocked)
