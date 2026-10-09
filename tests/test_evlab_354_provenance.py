"""Slice 354 — Dataset provenance.

Covers: provenance validation (acquisition rules, parent shape, step
names), auto-linked step chaining, chain-hash stability, chain
continuity verification (broken link / tip mismatch / missing output),
manifest integration (validate_decl, verify, round-trip), and the
summary embed.
"""

from __future__ import annotations

import pytest

from hugrgate.errors import DatasetError
from hugrgate.evlab import (
    ColumnSpec,
    DatasetManifest,
    DatasetProvenance,
    TransformStep,
    fingerprint_items,
)


def _items():
    return [{"state": {"x": 1}}, {"state": {"x": 2}}]


def _manifest():
    cols = [ColumnSpec(name="state", type="mapping", required=True)]
    return DatasetManifest(name="prov", version="1.0.0", columns=cols)


def _provenance(fp):
    return DatasetProvenance(
        source_uri="https://example.org/data.csv",
        acquisition="download",
        creator="lab",
        license="CC0-1.0",
    )


# --- validation ---------------------------------------------------------------

def test_valid_provenance_passes():
    _provenance("x").validate()


def test_bad_acquisition_rejected():
    with pytest.raises(DatasetError):
        DatasetProvenance(acquisition="telepathy").validate()


def test_download_needs_source_uri():
    with pytest.raises(DatasetError):
        DatasetProvenance(acquisition="download").validate()


def test_derived_needs_parents():
    with pytest.raises(DatasetError):
        DatasetProvenance(acquisition="derived").validate()


def test_parent_shape_enforced():
    with pytest.raises(DatasetError):
        DatasetProvenance(
            acquisition="derived",
            parents=[{"name": "p"}]).validate()


def test_unnamed_step_rejected():
    prov = _provenance("x")
    prov.steps.append(TransformStep(name=""))
    with pytest.raises(DatasetError):
        prov.validate()


# --- chaining -------------------------------------------------------------------

def test_add_step_auto_links_input():
    prov = _provenance("x")
    prov.add_step(TransformStep(name="clean", output_fingerprint="fp1"))
    second = prov.add_step(TransformStep(name="encode",
                                         output_fingerprint="fp2"))
    assert second.input_fingerprint == "fp1"
    assert prov.tip_fingerprint == "fp2"


def test_add_step_keeps_explicit_input():
    prov = _provenance("x")
    prov.add_step(TransformStep(name="a", output_fingerprint="fp1"))
    step = prov.add_step(TransformStep(name="b",
                                       input_fingerprint="pinned",
                                       output_fingerprint="fp2"))
    assert step.input_fingerprint == "pinned"


def test_chain_hash_stable():
    def build():
        prov = _provenance("x")
        prov.add_step(TransformStep(name="clean", tool="scrub",
                                    output_fingerprint="fp1"))
        return prov
    assert build().chain_hash == build().chain_hash
    other = _provenance("x")
    other.add_step(TransformStep(name="clean", tool="scrub",
                                 output_fingerprint="DIFFERENT"))
    assert other.chain_hash != build().chain_hash


def test_empty_chain_tip_none():
    assert _provenance("x").tip_fingerprint is None


# --- verification -----------------------------------------------------------------

def _chained(fp_items):
    prov = DatasetProvenance(
        acquisition="derived",
        parents=[{"name": "raw", "version": "1.0.0",
                  "fingerprint": "parent-fp"}],
        creator="lab",
    )
    prov.add_step(TransformStep(name="filter",
                                input_fingerprint="parent-fp",
                                output_fingerprint="mid-fp"))
    prov.add_step(TransformStep(name="encode", output_fingerprint=fp_items))
    return prov


def test_verify_clean_chain():
    fp = fingerprint_items(_items())
    _chained(fp).verify(fp)


def test_verify_broken_link():
    fp = fingerprint_items(_items())
    prov = _chained(fp)
    prov.steps[1].input_fingerprint = "tampered"
    with pytest.raises(DatasetError):
        prov.verify(fp)


def test_verify_tip_mismatch():
    prov = _chained("some-other-tip")
    with pytest.raises(DatasetError):
        prov.verify(fingerprint_items(_items()))


def test_verify_missing_output():
    prov = _provenance("x")
    prov.add_step(TransformStep(name="vague"))
    with pytest.raises(DatasetError):
        prov.verify("whatever")


def test_verify_first_step_parent_mismatch():
    fp = fingerprint_items(_items())
    prov = _chained(fp)
    prov.steps[0].input_fingerprint = "not-the-parent"
    with pytest.raises(DatasetError):
        prov.verify(fp)


# --- manifest integration -----------------------------------------------------------

def test_manifest_verify_checks_provenance_tip():
    items = _items()
    fp = fingerprint_items(items)
    prov = _chained(fp)
    manifest = _manifest()
    manifest.provenance = prov
    sealed = manifest.seal(items)
    sealed.verify(items)  # chain tip == sealed fingerprint


def test_manifest_verify_rejects_stale_provenance():
    items = _items()
    prov = _chained("stale-tip")
    manifest = _manifest()
    manifest.provenance = prov
    sealed = manifest.seal(items)
    with pytest.raises(DatasetError):
        sealed.verify(items)


def test_manifest_provenance_roundtrip():
    items = _items()
    fp = fingerprint_items(items)
    manifest = _manifest()
    manifest.provenance = _chained(fp)
    sealed = manifest.seal(items)
    clone = DatasetManifest.from_dict(sealed.to_dict())
    assert clone.provenance is not None
    assert clone.provenance.to_dict() == sealed.provenance.to_dict()
    assert clone.provenance.chain_hash == sealed.provenance.chain_hash
    clone.verify(items)


def test_manifest_without_provenance_still_verifies():
    sealed = _manifest().seal(_items())
    sealed.verify(_items())


def test_bad_provenance_type_rejected():
    manifest = _manifest()
    manifest.provenance = "not-provenance"  # type: ignore[assignment]
    with pytest.raises(DatasetError):
        manifest.validate_decl()


def test_summary_embed():
    fp = fingerprint_items(_items())
    summary = _chained(fp).summary()
    assert summary["acquisition"] == "derived"
    assert summary["n_parents"] == 1
    assert summary["n_steps"] == 2
    assert summary["tip_fingerprint"] == fp
    assert len(summary["chain_hash"]) == 64


def test_step_roundtrip():
    step = TransformStep(name="s", tool="t", tool_version="1",
                         params={"k": 1}, input_fingerprint="a",
                         output_fingerprint="b")
    assert TransformStep.from_dict(step.to_dict()).to_dict() == \
        step.to_dict()


def test_provenance_roundtrip():
    prov = _chained(fingerprint_items(_items()))
    clone = DatasetProvenance.from_dict(prov.to_dict())
    assert clone.to_dict() == prov.to_dict()
