"""Slice 353 — Dataset versioning.

Covers: version parsing (valid/invalid/boundary), bump semantics,
ordering incl. prereleases, compatibility, registry register/get/
latest/resolve/diff/check_compatible, manifest.bumped, and registry
integration with sealed manifests.
"""

from __future__ import annotations

import pytest

from hugrgate.errors import DatasetError
from hugrgate.evlab import (
    ColumnSpec,
    DatasetManifest,
    DatasetRegistry,
    DatasetVersion,
)


def _manifest(name="ds", version="1.0.0", **kw):
    cols = [ColumnSpec(name="state", type="mapping", required=True),
            ColumnSpec(name="expected", type="any", required=False)]
    return DatasetManifest(name=name, version=version,
                           columns=cols, **kw)


# --- parsing ---------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("1.2.3", (1, 2, 3, "", "")),
    ("0.0.1", (0, 0, 1, "", "")),
    ("10.20.30-rc.1+build.5", (10, 20, 30, "rc.1", "build.5")),
    ("2.0.0-alpha", (2, 0, 0, "alpha", "")),
    ("  1.2.3  ", (1, 2, 3, "", "")),  # surrounding whitespace tolerated
])
def test_parse_valid(text, expected):
    v = DatasetVersion.parse(text)
    assert (v.major, v.minor, v.patch, v.prerelease, v.build) == expected
    assert str(v) == text.strip()


@pytest.mark.parametrize("text", [
    "", "1.2", "1.2.3.4", "v1.2.3", "1.02.3", "a.b.c", "1.2.x",
    "1.2.3-", 123, None,
])
def test_parse_invalid(text):
    with pytest.raises(DatasetError):
        DatasetVersion.parse(text)


# --- bumps ------------------------------------------------------------------

def test_bumps():
    v = DatasetVersion.parse("1.2.3")
    assert str(v.bump_major()) == "2.0.0"
    assert str(v.bump_minor()) == "1.3.0"
    assert str(v.bump_patch()) == "1.2.4"
    # Prerelease/build metadata never survives a bump.
    assert str(DatasetVersion.parse("1.2.3-rc.1+b1").bump_patch()) == "1.2.4"


def test_ordering():
    ordered = ["1.0.0-alpha", "1.0.0", "1.0.1", "1.1.0", "2.0.0"]
    parsed = [DatasetVersion.parse(t) for t in ordered]
    assert parsed == sorted(parsed)
    assert DatasetVersion.parse("1.0.0-alpha") < DatasetVersion.parse("1.0.0")


def test_compatibility():
    assert DatasetVersion.parse("1.2.3").is_compatible_with(
        DatasetVersion.parse("1.9.0"))
    assert not DatasetVersion.parse("1.2.3").is_compatible_with(
        DatasetVersion.parse("2.0.0"))


# --- registry -----------------------------------------------------------------

def test_register_and_versions():
    reg = DatasetRegistry()
    reg.register(_manifest(version="1.0.0"))
    reg.register(_manifest(version="1.1.0"))
    reg.register(_manifest(version="2.0.0"))
    assert reg.versions("ds") == ["1.0.0", "1.1.0", "2.0.0"]


def test_register_duplicate_rejected():
    reg = DatasetRegistry()
    reg.register(_manifest(version="1.0.0"))
    with pytest.raises(DatasetError):
        reg.register(_manifest(version="1.0.0"))


def test_register_bad_version_rejected():
    reg = DatasetRegistry()
    with pytest.raises(DatasetError):
        reg.register(_manifest(version="not-a-version"))


def test_get_unknown_rejected():
    reg = DatasetRegistry()
    with pytest.raises(DatasetError):
        reg.get("ds", "1.0.0")
    reg.register(_manifest(version="1.0.0"))
    with pytest.raises(DatasetError):
        reg.get("ds", "9.9.9")
    assert reg.get("ds", "1.0.0").version == "1.0.0"


def test_latest_prefers_releases():
    reg = DatasetRegistry()
    reg.register(_manifest(version="1.0.0"))
    reg.register(_manifest(version="2.0.0-rc.1"))
    assert reg.latest("ds").version == "1.0.0"
    assert reg.latest("ds", include_prerelease=True).version == "2.0.0-rc.1"


def test_latest_unknown_rejected():
    with pytest.raises(DatasetError):
        DatasetRegistry().latest("ghost")


def test_resolve_exact_latest_caret():
    reg = DatasetRegistry()
    for v in ("1.0.0", "1.2.0", "1.5.0", "2.0.0"):
        reg.register(_manifest(version=v))
    assert reg.resolve("ds", "latest").version == "2.0.0"
    assert reg.resolve("ds", "1.2.0").version == "1.2.0"
    assert reg.resolve("ds", "^1.2").version == "1.5.0"
    assert reg.resolve("ds", "^1.0").version == "1.5.0"
    with pytest.raises(DatasetError):
        reg.resolve("ds", "^3.0")


# --- diff / compatibility ------------------------------------------------------

def test_diff_detects_schema_drift():
    old = _manifest(version="1.0.0").seal([{"state": {}}])
    new_cols = [ColumnSpec(name="state", type="mapping", required=True),
                ColumnSpec(name="expected", type="string", required=False),
                ColumnSpec(name="group", type="string", required=False)]
    new = DatasetManifest(name="ds", version="1.1.0",
                          columns=new_cols).seal([{"state": {}}])
    drift = DatasetRegistry.diff(old, new)
    assert drift["added_columns"] == ["group"]
    assert drift["removed_columns"] == []
    assert drift["changed_columns"] == ["expected"]
    assert drift["breaking"] is True
    assert drift["from_version"] == "1.0.0"


def test_diff_rejects_different_datasets():
    with pytest.raises(DatasetError):
        DatasetRegistry.diff(_manifest(name="a"), _manifest(name="b"))


def test_check_compatible():
    old = _manifest(version="1.0.0").seal([{"state": {}}])
    minor = _manifest(version="1.1.0").seal([{"state": {}}])
    assert DatasetRegistry.check_compatible(old, minor) is True
    major = _manifest(version="2.0.0").seal([{"state": {}}])
    assert DatasetRegistry.check_compatible(old, major) is False
    narrowed_cols = [ColumnSpec(name="state", type="string", required=True),
                     ColumnSpec(name="expected", type="any", required=False)]
    narrowed = DatasetManifest(name="ds", version="1.2.0",
                               columns=narrowed_cols).seal([{"state": "x"}])
    assert DatasetRegistry.check_compatible(old, narrowed) is False


# --- manifest.bumped -------------------------------------------------------------

def test_bumped_clears_fingerprint_and_reseals():
    sealed = _manifest(version="1.2.3").seal([{"state": {}}])
    nxt = sealed.bumped("minor")
    assert nxt.version == "1.3.0"
    assert nxt.fingerprint == ""
    assert nxt.name == sealed.name
    with pytest.raises(DatasetError):
        nxt.verify([{"state": {}}])  # unsealed
    resealed = nxt.seal([{"state": {}}])
    resealed.verify([{"state": {}}])


def test_bumped_bad_kind_rejected():
    with pytest.raises(DatasetError):
        _manifest().bumped("epoch")


def test_registry_end_to_end_with_bumps():
    reg = DatasetRegistry()
    items = [{"state": {"x": i}} for i in range(3)]
    v1 = _manifest(version="1.0.0").seal(items)
    reg.register(v1)
    v2 = v1.bumped("minor").seal(items)
    reg.register(v2)
    assert reg.resolve("ds", "latest").version == "1.1.0"
    assert DatasetRegistry.check_compatible(
        reg.get("ds", "1.0.0"), reg.get("ds", "1.1.0")) is True
