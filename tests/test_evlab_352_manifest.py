"""Slice 352 — Dataset manifest standard.

Covers: manifest declaration validation, item schema checking
(success/failure/boundary), fingerprint stability and tamper
detection, seal/verify lifecycle, serialization round-trip, adoption
of v1 bench datasets, and the manifest -> EvaluationLab bridge.
"""

from __future__ import annotations

import pytest

from hugrgate import DecisionPolicy, DecisionSpec
from hugrgate.errors import DatasetError, EvalError
from hugrgate.evlab import (
    ColumnSpec,
    DatasetManifest,
    EvaluationLab,
    Experiment,
    fingerprint_items,
)


def _items():
    return [
        {"state": {"x": 1}, "expected": "a", "group": "g1"},
        {"state": {"x": 2}, "expected": "b", "group": "g1"},
        {"state": {"x": 3}, "expected": "a", "group": "g2"},
    ]


def _manifest(**kw):
    cols = [
        ColumnSpec(name="state", type="mapping", required=True),
        ColumnSpec(name="expected", type="categorical", required=True,
                   options=["a", "b"]),
        ColumnSpec(name="group", type="string", required=False),
    ]
    return DatasetManifest(name="manifest-smoke", version="1.0.0",
                           columns=cols, license="CC0-1.0", **kw)


# --- declaration validation ------------------------------------------------

def test_valid_manifest_decl_passes():
    _manifest().validate_decl()


def test_empty_name_rejected():
    with pytest.raises(DatasetError):
        DatasetManifest(name="", version="1.0.0").validate_decl()


def test_bad_sensitivity_rejected():
    with pytest.raises(DatasetError):
        DatasetManifest(name="d", version="1",
                        sensitivity="topsecret").validate_decl()


def test_duplicate_column_rejected():
    cols = [ColumnSpec(name="x"), ColumnSpec(name="x")]
    with pytest.raises(DatasetError):
        DatasetManifest(name="d", version="1", columns=cols).validate_decl()


def test_unknown_column_type_rejected():
    with pytest.raises(DatasetError):
        DatasetManifest(name="d", version="1",
                        columns=[ColumnSpec(name="x", type="uuid")]).validate_decl()


def test_categorical_needs_options():
    with pytest.raises(DatasetError):
        DatasetManifest(name="d", version="1",
                        columns=[ColumnSpec(name="x", type="categorical")]).validate_decl()


def test_bad_fingerprint_rejected():
    with pytest.raises(DatasetError):
        DatasetManifest(name="d", version="1",
                        fingerprint="not-hex").validate_decl()


# --- item checking ----------------------------------------------------------

def test_check_clean_items():
    assert _manifest().check(_items()) == []


def test_check_missing_required():
    items = [{"expected": "a"}]
    issues = _manifest().check(items)
    assert any(i["column"] == "state" and "missing" in i["issue"]
               for i in issues)


def test_check_optional_missing_ok():
    items = [{"state": {"x": 1}, "expected": "a"}]
    assert _manifest().check(items) == []


def test_check_wrong_type():
    items = [{"state": "nope", "expected": "a"}]
    issues = _manifest().check(items)
    assert any(i["column"] == "state" for i in issues)


def test_check_bad_categorical_option():
    items = [{"state": {"x": 1}, "expected": "zzz"}]
    issues = _manifest().check(items)
    assert any(i["column"] == "expected" for i in issues)


def test_check_bool_is_not_number():
    m = DatasetManifest(name="d", version="1",
                        columns=[ColumnSpec(name="n", type="number")])
    assert m.check([{"n": True}]) != []
    assert m.check([{"n": 3}]) == []
    assert m.check([{"n": 2.5}]) == []


def test_check_non_mapping_item():
    assert _manifest().check(["nope"]) == [
        {"item": 0, "issue": "not a mapping"}]


def test_validate_raises_with_issue_details():
    with pytest.raises(DatasetError) as ei:
        _manifest().validate([{"state": {"x": 1}}])  # missing expected
    assert ei.value.details["n_issues"] >= 1
    assert ei.value.details["issues"]


# --- seal / verify / fingerprint --------------------------------------------

def test_seal_stamps_fingerprint():
    sealed = _manifest().seal(_items())
    assert len(sealed.fingerprint) == 64
    assert sealed.fingerprint == fingerprint_items(_items())


def test_fingerprint_stable_and_sensitive():
    f1 = fingerprint_items(_items())
    assert f1 == fingerprint_items(_items())
    tampered = [dict(i) for i in _items()]
    tampered[0] = dict(tampered[0], expected="b")
    assert fingerprint_items(tampered) != f1


def test_verify_detects_tampering():
    sealed = _manifest().seal(_items())
    tampered = [dict(i) for i in _items()]
    tampered[1] = dict(tampered[1], expected="a")
    with pytest.raises(DatasetError):
        sealed.verify(tampered)


def test_verify_unsealed_rejected():
    with pytest.raises(DatasetError):
        _manifest().verify(_items())


def test_seal_rejects_bad_items():
    with pytest.raises(DatasetError):
        _manifest().seal([{"state": {"x": 1}}])


# --- serialization -----------------------------------------------------------

def test_manifest_roundtrip():
    sealed = _manifest().seal(_items())
    clone = DatasetManifest.from_dict(sealed.to_dict())
    assert clone.to_dict() == sealed.to_dict()
    clone.verify(_items())  # sealed clone still verifies


def test_column_roundtrip():
    col = ColumnSpec(name="c", type="categorical", required=False,
                     options=["x", "y"])
    assert ColumnSpec.from_dict(col.to_dict()).to_dict() == col.to_dict()


# --- bench bridge ------------------------------------------------------------

def _spec_dict():
    return DecisionSpec(type="categorical",
                        options=["a", "b"]).to_dict()


def test_from_bench_dataset_adopts_and_seals():
    items = [{"state": {"x": 1}, "expected": "a"}]
    ds = {"name": "adopted", "version": "2.0.0", "spec": _spec_dict(),
          "items": items}
    manifest = DatasetManifest.from_bench_dataset(ds)
    assert manifest.name == "adopted"
    assert manifest.version == "2.0.0"
    assert manifest.fingerprint == fingerprint_items(items)
    manifest.verify(items)


def test_from_bench_dataset_rejects_bad_items():
    ds = {"name": "bad", "version": "1", "spec": _spec_dict(),
          "items": [{"expected": "a"}]}  # missing state
    with pytest.raises(DatasetError):
        DatasetManifest.from_bench_dataset(ds)


def test_to_bench_dataset_feeds_lab(gate_with_stub):
    items = [{"state": {"x": i}, "expected": "a"} for i in range(4)]
    manifest = DatasetManifest.from_bench_dataset(
        {"name": "labfed", "version": "1.0.0", "spec": _spec_dict(),
         "items": items})
    # from_bench_dataset inferred the permissive schema; tighten it here
    # with an explicit categorical declaration for the bridge test.
    manifest.columns = [
        ColumnSpec(name="state", type="mapping", required=True),
        ColumnSpec(name="expected", type="categorical", required=True,
                   options=["a", "b"]),
    ]
    sealed = manifest.seal(items)
    bench_ds = sealed.to_bench_dataset(items)
    assert bench_ds["name"] == "labfed"

    lab = EvaluationLab(gate=gate_with_stub)
    lab.register_experiment(Experiment(name="manifest-run",
                                       dataset=bench_ds,
                                       backends=["stub"]))
    record = lab.run("manifest-run")
    assert record.backends["stub"]["accuracy"] == pytest.approx(1.0)
    # The v1 bench fingerprint is the 16-char prefix of the manifest's
    # full sha256 anchor: both derive from the same canonical items.
    assert record.dataset_fingerprint == sealed.fingerprint[:16]


def test_to_bench_dataset_propagates_restricted(gate_with_stub):
    items = [{"state": {"x": 1}, "expected": "a"}]
    manifest = DatasetManifest(name="priv", version="1.0.0",
                               sensitivity="restricted",
                               spec=_spec_dict()).seal(items)
    bench_ds = manifest.to_bench_dataset(items)
    assert bench_ds["sensitivity"] == "restricted"
    lab = EvaluationLab(gate=gate_with_stub)
    # Standard policy must refuse the restricted dataset at the lab gate.
    with pytest.raises(EvalError):
        lab.register_experiment(Experiment(name="priv-run",
                                           dataset=bench_ds,
                                           backends=["stub"]))
    # Strict policy passes.
    lab.register_experiment(Experiment(
        name="priv-run-ok", dataset=bench_ds, backends=["stub"],
        policy=DecisionPolicy(privacy_class="strict")))
    assert lab.run("priv-run-ok").privacy_class == "strict"
